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
    warnings: list = field(default_factory=list)  # Finding

    def to_dict(self) -> dict:
        data = asdict(self)
        data["warnings"] = [w.to_dict() for w in self.warnings]
        return data


def check_run_id(run_id: str | None, *, no_commit: bool = False) -> str | None:
    """Refuse a malformed run id (``None`` is no run). A run commits later, so ``no_commit`` with it is a contradiction."""
    if run_id is None:
        return None
    if no_commit:
        raise RunError("--run-id and --no-commit conflict: a run's writes are committed by `run-commit`")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise RunError(f"invalid run id {run_id!r}: 1–64 of letters, digits, '.', '_' or '-', not starting with "
                       "a punctuation mark")
    return run_id


def _journal(vault: Vault, run_id: str) -> Path:
    """The run's journal: local state the vault gitignores, but not disposable (VAULT-STRUCTURE.md)."""
    return vault.root / ".claudron" / "runs" / f"{run_id}.json"


def _read(vault: Vault, run_id: str) -> dict | None:
    try:
        data = json.loads(_journal(vault, run_id).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("paths"), list) else None


def record(vault: Vault, run_id: str, path: Path) -> None:
    """Add a path the run wrote to its journal. The caller holds the vault write lock."""
    journal = _journal(vault, run_id)
    data = _read(vault, run_id) or {"run_id": run_id, "paths": [],
                                    "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    rel = str(Path(path).resolve().relative_to(vault.root.resolve()))
    if rel not in data["paths"]:
        data["paths"].append(rel)
    data["dirty"] = True  # written since the run's last commit
    journal.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(journal, json.dumps(data, indent=2) + "\n")


def _commits(vault: Vault, run_id: str) -> list[str]:
    """Commits whose message carries this run's trailer, newest first."""
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    proc = run_git(vault.root, "log", "--format=%H", "-E", f"--grep=^{TRAILER}: {re.escape(run_id)}$",
                   timeout=DEFAULT_GIT_TIMEOUT)
    return proc.stdout.split() if proc.returncode == 0 else []


def _already_reverted(vault: Vault) -> set[str]:
    """Every sha a later commit reverted (``git revert`` writes 'This reverts commit <sha>.'), in one scan."""
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    proc = run_git(vault.root, "log", "--format=%B", "-F", "--grep=This reverts commit", timeout=DEFAULT_GIT_TIMEOUT)
    return set(re.findall(r"This reverts commit ([0-9a-f]{40})", proc.stdout)) if proc.returncode == 0 else set()


def _head(vault: Vault) -> str:
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    proc = run_git(vault.root, "rev-parse", "--verify", "-q", "HEAD", timeout=DEFAULT_GIT_TIMEOUT)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def commit_run(vault: Vault, run_id: str) -> RunResult:
    """Land every path the run wrote since its last commit as one commit with the run's trailer."""
    from .engine import _commit_subject, commit_guarded
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir

    check_run_id(run_id)
    with vault_write_lock(vault):
        data = _read(vault, run_id)
        if data is None:
            raise RunError(f"no run {run_id!r}: no write named it")
        if _git_dir(vault.root, DEFAULT_GIT_TIMEOUT) is None:
            raise RunError("run-commit needs a git vault: in a plain directory the run's notes are already final")
        if not data.get("dirty"):
            return RunResult(run_id, "unchanged", data["paths"], reason="nothing new to commit")
        paths = [p for p in data["paths"] if (vault.root / p).exists()]
        before = _head(vault)
        warnings = commit_guarded(vault, [vault.root / p for p in paths],
                                  f"{_commit_subject('run', f'{run_id}: {len(paths)} note(s)')}\n\n"
                                  + "\n".join(paths) + f"\n\n{TRAILER}: {run_id}")
        after = _head(vault)
        if after != before:
            data["dirty"] = False
            atomic_write_text(_journal(vault, run_id), json.dumps(data, indent=2) + "\n")
    landed = after != before
    return RunResult(run_id, "committed" if landed else "unchanged", paths, [after] if landed else [],
                     "one commit for the run" if landed else "nothing committed", warnings)


def revert_run(vault: Vault, run_id: str) -> RunResult:
    """Revert the run's commit(s), newest first. A revert that conflicts is aborted and reported."""
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir, _interrupted_state, run_git

    t = DEFAULT_GIT_TIMEOUT
    check_run_id(run_id)
    with vault_write_lock(vault):
        git_dir = _git_dir(vault.root, t)
        if git_dir is None:
            raise RunError("revert-run needs a git vault: a plain directory keeps no runs to revert")
        if interrupted := _interrupted_state(vault.root, git_dir, t):
            raise RunError(f"refusing to revert: {interrupted} — resolve the tree first")
        commits = _commits(vault, run_id)
        data = _read(vault, run_id)
        paths = data["paths"] if data else []
        if not commits:
            if paths:
                raise RunError(f"run {run_id!r} was never committed; its notes are on disk uncommitted: "
                               + ", ".join(paths) + f" (commit it with `claudron run-commit {run_id}`)")
            raise RunError(f"no commit carries '{TRAILER}: {run_id}'")
        reverted = _already_reverted(vault)
        todo = [sha for sha in commits if sha not in reverted]
        if not todo:
            return RunResult(run_id, "unchanged", paths, commits, "already reverted")
        made, touched = [], set()
        for sha in todo:
            files = run_git(vault.root, "show", "--name-only", "--format=", sha, timeout=t).stdout.split()
            proc = run_git(vault.root, "revert", "--no-edit", sha, timeout=t)
            if proc.returncode != 0:
                run_git(vault.root, "revert", "--abort", timeout=t)
                said = (proc.stderr or proc.stdout or "").strip()[:200]
                raise RunError(f"revert of {sha[:12]} conflicts with later edits and was aborted; the tree is as "
                               f"it was ({said})")
            made.append(_head(vault))
            touched.update(files)
        _reindex(vault, touched)
    return RunResult(run_id, "reverted", paths, made, f"reverted {len(made)} commit(s)")


def _reindex(vault: Vault, paths: set[str]) -> None:
    """Refresh just the index entries a revert changed: rebuilt when the note is back, dropped when it is gone."""
    from .knowledge import ensure_index, index_entry, write_index
    from .schema import has_conflict_markers
    from .vault import note_tiers, parse_frontmatter

    index = ensure_index(vault)
    entries = [e for e in index.get("entries", []) if e.get("path") not in paths]
    tiers = sorted(note_tiers(vault), key=lambda bt: len(bt[0].parts), reverse=True)  # deepest base wins
    for rel in sorted(paths):
        md = vault.root / rel
        tier = next((t for base, t in tiers if md.is_relative_to(base)), None)
        if md.suffix != ".md" or tier is None or not md.is_file():
            continue
        text = md.read_text()
        if not has_conflict_markers(text):
            fm, body = parse_frontmatter(text)
            entries.append(index_entry(fm, body, md, tier, vault.root))
    index["entries"] = entries
    write_index(vault, index)
