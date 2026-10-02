"""Harvest runs: many writes, one commit, one revert (#200 §4).

An automated writer (a harvest run) makes many small writes. Committed one by
one they bury a bad run in history; reversing it means finding every commit.
So a write that names a ``run_id`` is **not** committed at once: the door
records its path in the run's journal (``.claudron/runs/<run_id>.json``, local
state the vault gitignores). ``commit_run`` then lands the whole run as **one
commit** carrying a ``Claudron-Run: <run_id>`` trailer, and ``revert_run``
reverses exactly that commit. Auto-drain is only safe if it can be undone.

Both are idempotent: committing a committed run, or reverting a reverted one,
does nothing and says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .locking import atomic_write_text, vault_write_lock
from .vault import Vault

#: A run id: what a commit trailer and a journal file name can both carry safely.
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
TRAILER = "Claudron-Run"


class RunError(ValueError):
    """A run verb that can't proceed (a bad id, an unknown or uncommitted run)."""


@dataclass
class RunResult:
    """What ``commit_run`` or ``revert_run`` did."""

    run_id: str
    action: str  # committed | reverted | unchanged
    paths: list[str]
    commits: list[str] = field(default_factory=list)
    reason: str = ""
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def check_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise RunError(f"invalid run id {run_id!r}: 1–64 of letters, digits, '.', '_' or '-', not starting with "
                       "a punctuation mark")
    return run_id


def _journal(vault: Vault, run_id: str) -> Path:
    return vault.root / ".claudron" / "runs" / f"{check_run_id(run_id)}.json"


def _read(vault: Vault, run_id: str) -> dict | None:
    try:
        data = json.loads(_journal(vault, run_id).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("paths"), list) else None


def record(vault: Vault, run_id: str, path: Path) -> None:
    """Add a path the run wrote to its journal. The caller holds the vault write lock."""
    journal = _journal(vault, run_id)
    data = _read(vault, run_id) or {"run_id": run_id, "started": _now(), "paths": []}
    rel = str(Path(path).resolve().relative_to(vault.root.resolve()))
    if rel not in data["paths"]:
        data["paths"].append(rel)
    data["dirty"] = True  # written since the run's last commit
    journal.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(journal, json.dumps(data, indent=2) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _commits(vault: Vault, run_id: str) -> list[str]:
    """Commits whose message carries this run's trailer, newest first."""
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    proc = run_git(vault.root, "log", "--format=%H", "-E", f"--grep=^{TRAILER}: {re.escape(run_id)}$",
                   timeout=DEFAULT_GIT_TIMEOUT)
    return proc.stdout.split() if proc.returncode == 0 else []


def _reverted(vault: Vault, sha: str) -> bool:
    """Has a later commit reverted ``sha``? (``git revert`` writes 'This reverts commit <sha>'.)"""
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    proc = run_git(vault.root, "log", "--format=%H", "-F", f"--grep=This reverts commit {sha}",
                   timeout=DEFAULT_GIT_TIMEOUT)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def commit_run(vault: Vault, run_id: str) -> RunResult:
    """Land every path the run wrote since its last commit as one commit with the run's trailer."""
    from .engine import _commit_subject, commit_guarded
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir

    with vault_write_lock(vault):
        data = _read(vault, run_id)
        if data is None:
            raise RunError(f"no run {run_id!r}: no write named it")
        if _git_dir(vault.root, DEFAULT_GIT_TIMEOUT) is None:
            raise RunError("run-commit needs a git vault: in a plain directory the run's notes are already final")
        if not data.get("dirty"):
            return RunResult(run_id, "unchanged", data["paths"], _commits(vault, run_id), "nothing new to commit")
        paths = [p for p in data["paths"] if (vault.root / p).exists()]
        subject = _commit_subject("harvest", f"run {run_id}: {len(paths)} note(s)")
        before = _commits(vault, run_id)
        warnings = commit_guarded(vault, [vault.root / p for p in paths],
                                  f"{subject}\n\n" + "\n".join(paths) + f"\n\n{TRAILER}: {run_id}")
        commits = _commits(vault, run_id)
        landed = len(commits) > len(before)
        if landed:
            data["dirty"] = False
            atomic_write_text(_journal(vault, run_id), json.dumps(data, indent=2) + "\n")
    return RunResult(run_id, "committed" if landed else "unchanged", paths, commits,
                     "one commit for the run" if landed else "nothing committed",
                     [w.to_dict() for w in warnings])


def revert_run(vault: Vault, run_id: str) -> RunResult:
    """Revert the run's commit(s), newest first. A revert that conflicts is aborted and reported."""
    from .knowledge import build_index
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir, _interrupted_state, run_git

    t = DEFAULT_GIT_TIMEOUT
    check_run_id(run_id)
    with vault_write_lock(vault):
        if _git_dir(vault.root, t) is None:
            raise RunError("revert-run needs a git vault: a plain directory keeps no runs to revert")
        interrupted = _interrupted_state(vault.root, _git_dir(vault.root, t), t)
        if interrupted:
            raise RunError(f"refusing to revert: {interrupted} — resolve the tree first")
        commits = _commits(vault, run_id)
        data = _read(vault, run_id)
        if not commits:
            if data and data["paths"]:
                raise RunError(f"run {run_id!r} was never committed; its notes are on disk uncommitted: "
                               + ", ".join(data["paths"]) + f" (commit it with `claudron run-commit {run_id}`)")
            raise RunError(f"no commit carries '{TRAILER}: {run_id}'")
        todo = [sha for sha in commits if not _reverted(vault, sha)]
        if not todo:
            return RunResult(run_id, "unchanged", data["paths"] if data else [], commits, "already reverted")
        made = []
        for sha in todo:
            proc = run_git(vault.root, "revert", "--no-edit", sha, timeout=t)
            if proc.returncode != 0:
                run_git(vault.root, "revert", "--abort", timeout=t)
                said = (proc.stderr or proc.stdout or "").strip()[:200]
                raise RunError(f"revert of {sha[:12]} conflicts with later edits and was aborted; the tree is as "
                               f"it was ({said})")
            made.append(run_git(vault.root, "rev-parse", "HEAD", timeout=t).stdout.strip())
        build_index(vault)  # reverted notes changed or vanished under the index
    return RunResult(run_id, "reverted", data["paths"] if data else [], made, f"reverted {len(made)} commit(s)")
