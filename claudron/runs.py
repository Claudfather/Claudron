"""Harvest runs: every write tagged with its run, the whole run undone in one revert (#200 §4).

An automated writer (a harvest run) makes many small writes. A write that
names a ``run_id`` is committed at once, like every door's write (#157: a note
is durable on return), with a ``Claudron-Run: <run_id>`` trailer.
``revert_run`` finds every commit carrying the trailer and reverses them all
as **one** revert commit — or, if any conflicts with later edits, none of
them. Auto-drain is only safe if it can be undone.

Deliberately no deferred "commit the run later" step: uncommitted run writes
would sit in the tree, where ``sync``'s safety net sweeps them up untagged,
and the window #157 closed would reopen.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .locking import vault_write_lock
from .vault import Vault

#: A run id: what a commit trailer can carry safely.
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
TRAILER = "Claudron-Run"


class RunError(ValueError):
    """A run verb that can't proceed (a bad id, an unknown run, a revert that conflicts)."""


@dataclass
class RunResult:
    """What ``revert_run`` did: ``action`` is ``reverted`` or ``unchanged``."""

    run_id: str
    action: str
    commits: list[str] = field(default_factory=list)  # the run's commits it reverted
    revert: str = ""  # the revert commit
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def check_run_id(run_id: str | None, *, no_commit: bool = False) -> str | None:
    """Refuse a malformed run id (``None`` is no run). A run is a set of commits, so ``no_commit`` contradicts it."""
    if run_id is None:
        return None
    if no_commit:
        raise RunError("--run-id and --no-commit conflict: a run is the set of commits carrying its trailer")
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise RunError(f"invalid run id {run_id!r}: 1–64 of letters, digits, '.', '_' or '-', not starting with "
                       "a punctuation mark")
    return run_id


def trailer(run_id: str | None) -> str:
    """The message suffix a run's commits carry ('' outside a run)."""
    return f"\n\n{TRAILER}: {run_id}" if run_id else ""


def _git(vault: Vault, *args: str):
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    return run_git(vault.root, *args, timeout=DEFAULT_GIT_TIMEOUT)


def _commits(vault: Vault, run_id: str) -> list[str]:
    """Commits whose message carries this run's trailer, newest first."""
    proc = _git(vault, "log", "--format=%H", "-E", f"--grep=^{TRAILER}: {re.escape(run_id)}$")
    return proc.stdout.split() if proc.returncode == 0 else []


def _already_reverted(vault: Vault) -> set[str]:
    """Every sha a later commit reverted (its message says 'This reverts commit <sha>.'), in one scan."""
    proc = _git(vault, "log", "--format=%B", "-F", "--grep=This reverts commit")
    return set(re.findall(r"This reverts commit ([0-9a-f]{40})", proc.stdout)) if proc.returncode == 0 else set()


def revert_run(vault: Vault, run_id: str) -> RunResult:
    """Revert every commit of the run not yet reverted, newest first, as one commit — or none."""
    from .engine import _commit_subject
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir, _interrupted_state

    t = DEFAULT_GIT_TIMEOUT
    check_run_id(run_id)
    with vault_write_lock(vault):
        git_dir = _git_dir(vault.root, t)
        if git_dir is None:
            raise RunError("revert-run needs a git vault: a plain directory keeps no runs to revert")
        if interrupted := _interrupted_state(vault.root, git_dir, t):
            raise RunError(f"refusing to revert: {interrupted} — resolve the tree first")
        commits = _commits(vault, run_id)
        if not commits:
            raise RunError(f"no commit carries '{TRAILER}: {run_id}'")
        reverted = _already_reverted(vault)
        todo = [sha for sha in commits if sha not in reverted]
        if not todo:
            return RunResult(run_id, "unchanged", commits, reason="already reverted")
        # Staged, not committed, one after another: if any conflicts, `--abort`
        # takes the tree and index back to before the first, so the run is
        # undone whole or not at all.
        proc = _git(vault, "revert", "--no-commit", *todo)
        if proc.returncode != 0:
            _git(vault, "revert", "--abort")
            said = (proc.stderr or proc.stdout or "").strip()[:200]
            raise RunError(f"reverting run {run_id} conflicts with later edits; nothing was reverted ({said})")
        message = (f"{_commit_subject('revert-run', run_id)}\n\n"
                   + "\n".join(f"This reverts commit {sha}." for sha in todo))
        done = _git(vault, "commit", "-m", message)
        if done.returncode != 0:
            _git(vault, "revert", "--abort")
            raise RunError(f"the revert of run {run_id} could not be committed: {done.stderr.strip()[:200]}")
        head = _git(vault, "rev-parse", "HEAD").stdout.strip()
    from . import ops

    ops.record(vault, "run.reverted", run_id=run_id, commits=len(todo), revert=head)
    # The reverted notes are newer than the index now, so the next read rebuilds it (mtime staleness).
    return RunResult(run_id, "reverted", todo, head, f"reverted {len(todo)} commit(s) in one")
