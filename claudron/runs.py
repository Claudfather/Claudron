"""Harvest runs: every write tagged with its run, the whole run undone in one revert (#200 §4).

An automated writer (a harvest run) makes many small writes. A write that
names a ``run_id`` is committed at once, like every door's write (#157: a note
is durable on return), with a ``Claudron-Run: <run_id>`` trailer.
``revert_run`` finds every commit carrying the trailer and reverses them all
as **one** revert commit — or, if any conflicts with later edits, none of
them. Auto-drain is only safe if it can be undone.

Deliberately no deferred "commit the run later" step: uncommitted run writes
would be committed by the next ``sync`` without the run's trailer, and the
window #157 closed would reopen.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import ops
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


def _git(vault: Vault, *args: str, stdout_is_data: bool = True):
    from .sync import DEFAULT_GIT_TIMEOUT, run_git

    return run_git(vault.root, *args, timeout=DEFAULT_GIT_TIMEOUT, stdout_is_data=stdout_is_data)


def _commits(vault: Vault, run_id: str) -> list[str]:
    """Commits whose message carries this run's trailer, newest first."""
    proc = _git(vault, "log", "--format=%H", "-E", f"--grep=^{TRAILER}: {re.escape(run_id)}$")
    return proc.stdout.split() if proc.returncode == 0 else []


#: The subject verb of the commit ``revert_run`` makes. No other writer uses it, and a subject's
#: verb is never note text (``engine._commit_subject``), so only a revert-run commit carries it.
REVERT_VERB = "revert-run"
_REVERTED_LINE = re.compile(r"^This reverts commit ([0-9a-f]{40})\.$", re.MULTILINE)


def _already_reverted(vault: Vault) -> set[str]:
    """Every sha a revert-run commit reverted, in one scan.

    Only revert-run's own commits count: their subject's verb is ``revert-run`` and
    their body has one ``This reverts commit <sha>.`` line per commit. Any other
    commit that carries those words (a captured title is a commit subject) is
    not a revert record, and reading it as one would leave its run in place.
    """
    from .engine import _subject_verb

    proc = _git(vault, "log", "--format=%x1e%s%x1f%b", "-F", "--grep=This reverts commit")
    if proc.returncode != 0:
        return set()
    shas: set[str] = set()
    for record in proc.stdout.split("\x1e"):
        subject, _, body = record.partition("\x1f")
        if _subject_verb(subject) == REVERT_VERB:
            shas.update(_REVERTED_LINE.findall(body))
    return shas


#: A revert or a cherry-pick a person left stopped part-way, by the file or directory git keeps
#: for it in the git directory. revert-run refuses each before its own revert starts: that revert
#: would fail on it, and the cleanup's ``git revert --abort`` would take the state, the index and
#: the person's half-done resolution with it.
_STOPPED_PICKS = (
    ("REVERT_HEAD", "a revert is stopped part-way"),
    ("CHERRY_PICK_HEAD", "a cherry-pick is stopped part-way"),
    ("sequencer", "a revert or a cherry-pick of several commits is stopped part-way"),
)


def _stopped_pick(git_dir: Path) -> str | None:
    """Why a revert or a cherry-pick is stopped part-way in this repository, or None."""
    for mark, what in _STOPPED_PICKS:
        if (git_dir / mark).exists():
            return what
    return None


def revert_run(vault: Vault, run_id: str) -> RunResult:
    """Revert every commit of the run not yet reverted, newest first, as one commit — or none."""
    from .engine import _commit_subject
    from .sync import DEFAULT_GIT_TIMEOUT, _git_dir, _interrupted_state, commit_staged

    t = DEFAULT_GIT_TIMEOUT
    check_run_id(run_id)
    with vault_write_lock(vault):
        git_dir = _git_dir(vault.root, t)
        if git_dir is None:
            raise RunError("revert-run needs a git vault: a plain directory keeps no runs to revert")
        if interrupted := _interrupted_state(vault.root, git_dir, t) or _stopped_pick(git_dir):
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
        # undone whole or not at all. The revert's Auto-merging and CONFLICT
        # lines name a file by its bytes, so its stdout is read as git's
        # messages; the commit is sync's commit of what is staged, which reads
        # its own the same way. Whatever stops the run once the revert has
        # started (a conflict, a commit git refuses, a timeout, an interrupt),
        # the abort runs before the error goes on, so the vault is never left
        # mid-revert.
        try:
            proc = _git(vault, "revert", "--no-commit", *todo, stdout_is_data=False)
            if proc.returncode != 0:
                said = (proc.stderr or proc.stdout or "").strip()[:200]
                raise RunError(f"reverting run {run_id} conflicts with later edits; nothing was reverted ({said})")
            message = (f"{_commit_subject(REVERT_VERB, run_id)}\n\n"
                       + "\n".join(f"This reverts commit {sha}." for sha in todo))
            done = commit_staged(vault.root, message, timeout=t)
            if not done.ok:
                raise RunError(f"the revert of run {run_id} could not be committed: {done.error}")
        except BaseException:
            with contextlib.suppress(Exception):  # the error that stopped the run is the one reported
                _git(vault, "revert", "--abort")
            raise
        head = _git(vault, "rev-parse", "HEAD").stdout.strip()
    ops.record(vault, "run.reverted", run_id=run_id, commits=len(todo), revert=head)
    # The reverted notes are newer than the index now, so the next read rebuilds it (mtime staleness).
    return RunResult(run_id, "reverted", todo, head, f"reverted {len(todo)} commit(s) in one")
