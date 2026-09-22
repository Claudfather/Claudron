"""Vault sync: the git leg of the SD-card loop (E2).

`sync` is a thin, explicit git wrapper — commit vault changes, pull
--rebase, push. Conflicts are reported and left as markers for the human
(the rebase stays stopped for the standard resolve/--continue flow),
never auto-resolved; marker-bearing notes are quarantined (excluded from
index/lookup/recall — detection is stateless, see
schema.has_conflict_markers) until resolved.

The quarantine scan is bounded to what the pull actually changed
(``ORIG_HEAD..HEAD`` on a clean pull, unmerged files on a conflict) — a
no-op pull reads zero notes, which keeps the SessionStart hook O(changed),
not O(vault).

Single-writer-per-machine is the E2 assumption; cross-machine
serialization happens here at the git layer. Hooks call the halves
(`--pull` at SessionStart with a hard timeout, `--push` at SessionEnd)
and fail open on any nonzero outcome.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .locking import vault_write_lock
from .vault import Vault, scan_quarantine


@dataclass
class SyncResult:
    pulled: bool = False
    pushed: bool = False
    committed: bool = False
    quarantined: list[str] = field(default_factory=list)
    detail: str = ""  # non-empty exactly when something needs the human

    @property
    def ok(self) -> bool:
        return not self.detail

    def to_dict(self) -> dict:
        return {
            "pulled": self.pulled,
            "pushed": self.pushed,
            "committed": self.committed,
            "quarantined": self.quarantined,
            "detail": self.detail,
        }


# Default per-git-op bound when a caller passes no timeout. The hooks pass their
# own tight budgets (SessionStart pull, SessionEnd push); this is the floor for a
# manual `claudron sync` so a hung git can't pin the vault write-lock forever.
DEFAULT_GIT_TIMEOUT = 30.0


class SyncError(Exception):
    """Environment problems (not a git repo, no git binary) — the CLI maps
    these to exit 3; conflicts are NOT errors, they are reported results."""


class SyncTimeout(SyncError):
    """A git op that exceeded its budget.

    A *subclass*, so every existing ``except SyncError`` keeps catching it —
    but callers that care can now tell the two apart, and they must: an
    unavailable git changes nothing on disk, while a timeout can kill git
    part-way through a rebase replay. That is the only failure here that
    leaves the repository inconsistent, and it leaves **no conflict markers**
    to show for it (#147).
    """


# Fallback commit identity for the engine's OWN commits — sync's commit and
# init's seed commit. On a host with no configured git identity (a fresh Pi, a
# container, CI), git refuses to auto-guess one and the commit fails, silently
# dropping vault writes — and those low-config hosts are exactly the ones the
# fleet loop targets (#91). We inject this for `commit` ONLY when no identity is
# configured; a user's own identity is preserved whenever present.
_FALLBACK_IDENTITY = ("-c", "user.name=Claudron", "-c", "user.email=claudron@claudron.invalid")


def _has_git_identity(root: Path) -> bool:
    """True when a commit identity (user.name AND user.email) is configured for
    *root* at any scope. A plain `git config` read — not run_git — so it never
    recurses through the commit-identity injection below."""
    for key in ("user.name", "user.email"):
        try:
            got = subprocess.run(
                ["git", "-C", str(root), "config", key],
                capture_output=True, text=True,
            )
        except (FileNotFoundError, PermissionError):
            return False
        if got.returncode != 0 or not got.stdout.strip():
            return False
    return True


def run_git(root: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    """The package git invoker: guarded subprocess with SyncError-typed
    environment failures (git missing/not executable, timeouts). Every
    *vault-scoped* git call goes through this — the one deliberate
    exception is cli._derive_owner's global `git config` lookup, which
    must not receive `-C root` and carries its own guard.

    A `commit` on a host with no configured git identity gets a fallback
    identity injected (:data:`_FALLBACK_IDENTITY`) so the engine's commits
    never silently fail on a bare host (#91); a configured identity always
    wins."""
    prefix: list[str] = []
    if args and args[0] == "commit" and not _has_git_identity(root):
        prefix = list(_FALLBACK_IDENTITY)
    try:
        return subprocess.run(
            ["git", "-C", str(root), *prefix, *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise SyncError(f"git is unavailable: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncTimeout(f"git {' '.join(args)} timed out") from exc


def _changed_md(root: Path, spec: list[str]) -> list[str]:
    """Vault-relative .md paths from a `git diff --name-only` invocation."""
    out = run_git(root, "diff", "--name-only", *spec)
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p.endswith(".md")]


def _git_dir(root: Path, t: float) -> Path | None:
    """The vault's absolute ``.git`` directory, or None when git cannot answer
    (which is also how "not a git repository" is detected)."""
    out = run_git(root, "rev-parse", "--git-dir", timeout=t)
    if out.returncode != 0:
        return None
    p = Path(out.stdout.strip())
    return p if p.is_absolute() else root / p


def _interrupted_state(root: Path, git_dir: Path | None, t: float) -> str | None:
    """Why this repository is mid-surgery, or None when it is not.

    Two independent facts, because they miss in opposite directions: the rebase
    directories catch a stop, and the detached HEAD catches a repository left
    on a bare SHA with no rebase at all. Checking either alone leaves a real
    state unseen.

    The reason this needs its own predicate rather than a ``--porcelain`` read:
    a stopped rebase has **zero unmerged paths**, so every scoped porcelain
    query reads perfectly clean while HEAD is detached (#147). Nothing already
    in this module could see it.
    """
    if git_dir is not None:
        for marker, what in (
            ("rebase-merge", "a rebase is stopped part-way"),
            ("rebase-apply", "a rebase or `git am` is stopped part-way"),
            ("MERGE_HEAD", "a merge is in progress"),
        ):
            if (git_dir / marker).exists():
                return what
    if run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD",
               timeout=t).returncode != 0:
        return "HEAD is detached"
    return None


#: How long a lock must sit before age alone stops arguing for a live writer.
#: A real git write on this estate's slowest disk finishes in seconds; the lock
#: that caused the outage sat for 914,102 s (ten and a half days). Anything in
#: between is refused rather than guessed at.
STALE_LOCK_AGE_S = 600


def _lock_holder(lock: Path) -> bool | None:
    """Is a live process holding *lock* open?

    ``True`` held · ``False`` provably unheld · ``None`` cannot say.

    **The three states are the whole point, and `None` is not `False`.** The one
    destructive act in this module is deleting someone's lock, and a lock whose
    holder is still running means a real concurrent write: stealing it corrupts
    the index. So an unanswerable probe reads as "someone is working", never as
    "safe to delete".

    **Ownership comes from the kernel, not from the file.** Measured: a live
    ``index.lock`` caught mid-write holds no pid at all — git writes the new
    index into it, not a process id — so there is nothing in the file to read,
    and the pid-reuse hazard that would come with a recorded pid never arises.
    ``lsof`` reports whoever has the fd open *right now*, which is by definition
    a living process.

    Probe order, each with its semantics measured rather than assumed:

    * ``lsof -t`` — exit 0 with pids when held, exit 1 when not. Both directions
      verified on this platform.
    * GNU ``fuser`` — **only** when ``--version`` identifies psmisc. BSD
      ``fuser`` exits 0 for an unheld file, so on that implementation a "no
      owner" reading is indistinguishable from "owner"; it must never be read as
      evidence, and here it is not read at all.
    * otherwise ``None``.
    """
    if shutil.which("lsof"):
        try:
            r = subprocess.run(["lsof", "-t", str(lock)],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode == 0 and r.stdout.strip():
            return True
        if r.returncode == 1:
            return False
        return None                     # any other rc: lsof could not answer
    if shutil.which("fuser"):
        try:
            ver = subprocess.run(["fuser", "--version"],
                                 capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        if "psmisc" not in (ver.stdout + ver.stderr).lower():
            return None                 # BSD fuser: exit 0 proves nothing
        try:
            r = subprocess.run(["fuser", str(lock)],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode == 0:
            return True
        if r.returncode == 1:
            return False
        return None
    return None


def _index_lock_state(git_dir: Path | None, *,
                      max_age_s: int = STALE_LOCK_AGE_S
                      ) -> tuple[Path, int, bool | None] | None:
    """``(path, age_s, holder)`` for a present ``index.lock``, else ``None``."""
    if git_dir is None:
        return None
    lock = git_dir / "index.lock"
    try:
        age = int(time.time() - os.path.getmtime(lock))
    except OSError:
        return None                     # absent, or vanished under us
    return lock, max(age, 0), _lock_holder(lock)


def _is_expirable(age: int, holder: bool | None, max_age_s: int) -> bool:
    """Both facts must agree before anything is deleted.

    Old **and** provably ownerless. Age alone is not enough — a slow write on a
    loaded SD card is old and live — and ownerlessness alone is not enough,
    because a probe run in the instant between git's ``open`` and its first
    write would report no holder for a lock that is about to be used.

    The mirror of ``_killed_rebase``'s shape, and the same fail-safe direction:
    ambiguity resolves to "leave it alone".
    """
    return age >= max_age_s and holder is False


def sync(
    vault: Vault,
    *,
    pull: bool = True,
    push: bool = True,
    timeout: float | None = None,
) -> SyncResult:
    """Commit → pull --rebase → push. Raises SyncError for environment
    problems; returns ok=False (with detail + quarantine list) when a
    conflict or push failure was left for the human.

    Every git op is bounded (``timeout`` or :data:`DEFAULT_GIT_TIMEOUT`): sync
    holds the vault write-lock across the whole critical section, and the lock
    can only be reclaimed when the holder exits — so a git that *hangs* (a gpg
    passphrase prompt on commit, a credential prompt or network stall on
    pull/push) rather than crashes must be forced to fail, or it would pin the
    lock and deadlock every concurrent capture on the machine."""
    root = vault.root
    t = timeout if timeout is not None else DEFAULT_GIT_TIMEOUT
    git_dir = _git_dir(root, t)
    if git_dir is None:
        raise SyncError(f"vault is not a git repository: {root}")

    result = SyncResult()

    # Hold the vault write-lock across the whole git critical section: a
    # `git add -A`/commit or a rebase that rewrites working-tree files must not
    # interleave with a concurrent `capture` writing a note + index on the same
    # machine (the local-writer race the lock exists for; cross-machine
    # serialization still happens at the git layer below).
    with vault_write_lock(vault):
        # Refuse to touch a repository that is mid-surgery, before writing
        # anything to it. A stopped rebase detaches HEAD, and a commit made on
        # a detached HEAD is reachable from no branch at all — which is how
        # four bots' work spent four hours one `--abort` away from vanishing,
        # while every check anyone ran reported the tree clean (#147).
        # Reporting and stopping is the whole remedy: repairing a stopped
        # rebase stays the human's call, exactly as on the conflict path below.
        interrupted = _interrupted_state(root, git_dir, t)
        if interrupted:
            result.detail = (
                f"refusing to sync: {interrupted} — nothing was written; "
                "resolve the repository first"
            )
            return result

        # A stale index.lock blocks every git WRITE while leaving every git
        # READ working, which is why the last one went unnoticed for ten days:
        # `status --porcelain` needs no lock and answers "merely dirty", so
        # sync blamed the dirty tree and never mentioned the lock. Checked
        # before the first write, and never past a live one.
        lock_state = _index_lock_state(git_dir)
        if lock_state is not None:
            lock, age, holder = lock_state
            if _is_expirable(age, holder, STALE_LOCK_AGE_S):
                try:
                    lock.unlink()
                except OSError as exc:
                    result.detail = (
                        f"refusing to sync: .git/index.lock is present "
                        f"(age {age}s, no owner) and could not be removed: "
                        f"{exc}; nothing was written"
                    )
                    return result
                expired_note = f"expired stale index.lock (age {age}s, no owner)"
            else:
                owner = {True: "held", False: "no owner", None: "unknown"}[holder]
                result.detail = (
                    f"refusing to sync: .git/index.lock is present (age {age}s, "
                    f"owner {owner}) — another git process may be running; "
                    "nothing was written"
                )
                return result
        else:
            expired_note = None

        def _detail(text: str) -> str:
            """Compose a detail that never drops a repair we performed.

            An expired lock is something this run DID, and it stays true
            whatever happens afterwards. Without composing, the next
            assignment overwrites it and a sync that silently repaired a
            ten-day wedge reports only its next problem -- which is the same
            class of silence this issue exists to end.
            """
            return f"{expired_note}; {text}" if expired_note else text

        # Commit any working-tree changes first — captures don't commit, sync
        # owns the commit so notes actually travel. Every call is bounded by t
        # so a wedged git releases the lock instead of holding it forever.
        porcelain = run_git(root, "status", "--porcelain", timeout=t).stdout.strip()
        if porcelain:
            added = run_git(root, "add", "-A", timeout=t)
            if added.returncode != 0:
                # Returning HERE is the difference between naming the cause and
                # naming a symptom. Unchecked, a failed `add` fell through to a
                # `commit` that also failed, and the porcelain re-read below
                # then reported "the working tree is not clean after the
                # pre-pull commit" -- true, useless, and pointing at the tree
                # rather than at whatever stopped the write. git's own message
                # says what happened.
                result.detail = _detail(
                    f"git add failed: {added.stderr.strip()[:200]}"
                    if added.stderr.strip()
                    else f"git add failed (exit {added.returncode})"
                )
                return result
            n = len(porcelain.splitlines())
            commit = run_git(
                root, "commit",
                "-m", f"claudron sync: {n} change(s) from {socket.gethostname()}",
                timeout=t,
            )
            result.committed = commit.returncode == 0

        if pull:
            # A rebase must not be *started* unless it is safe to finish. Both
            # checks below are refusals rather than attempts, because the cost
            # is asymmetric: a refused pull is a logged no-op, an attempted one
            # can replay dozens of commits onto the wrong base and be killed
            # half-way through (#147).
            # Re-read only when a commit was actually attempted: with nothing
            # to commit the tree was already clean and nothing here has written
            # to it since. SessionStart runs on a 2s budget and that is the
            # common path, so this saves a git invocation on every clean sync.
            if porcelain and run_git(
                root, "status", "--porcelain", timeout=t
            ).stdout.strip():
                # The commit above did not take, so the tree is still dirty and
                # git would refuse the rebase anyway — but it would refuse
                # *after* deciding to start one. Stop here instead, and say
                # which of the two things went wrong.
                result.detail = _detail(
                    "pull skipped: the working tree is not clean after the "
                    "pre-pull commit, so a rebase cannot be started safely"
                )
                return result
            upstream = run_git(
                root, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                "@{upstream}", timeout=t,
            )
            if upstream.returncode != 0:
                # A branch that has never been pushed has nothing to rebase
                # onto. This is the ordinary first-push case, so the PUSH below
                # still runs — only the pull is skipped. The old `origin HEAD`
                # refspec hid this state entirely by rebasing onto the remote's
                # default branch instead.
                result.detail = _detail(
                    "pull skipped: this branch has no upstream to rebase onto"
                )
            else:
                # Bare `pull --rebase` rebases onto THIS branch's own upstream.
                # Naming `origin HEAD` resolved HEAD *on the remote*, where it
                # is a symbolic ref to the default branch — so on any
                # non-default branch it rebased onto origin/main and queued the
                # entire divergence rather than the handful of unpushed
                # commits it reads as meaning (#147).
                try:
                    pulled = run_git(root, "pull", "--rebase", timeout=t)
                except SyncTimeout as exc:
                    # The third case the returncode branch below cannot cover:
                    # git was killed mid-replay, so there is no returncode and
                    # no conflict markers. Saying so is the entire fix for the
                    # silence that let this run six weeks unnoticed.
                    left = _interrupted_state(root, git_dir, t)
                    result.detail = _detail(
                        f"{exc} — {left}; left for the human"
                        if left
                        else f"{exc} — repository left consistent"
                    )
                    return result
                if pulled.returncode != 0:
                    # Conflict (or no remote). The rebase stays stopped with
                    # markers in the working tree — the standard
                    # resolve/--continue flow; sync never aborts it (aborting
                    # would erase the markers the human is supposed to see).
                    # Scan only the unmerged files.
                    result.quarantined = scan_quarantine(
                        vault, paths=_changed_md(root, ["--diff-filter=U"])
                    )
                    result.detail = _detail(
                        "pull hit conflicts — markers left for the human; "
                        "conflicted notes are quarantined from search until "
                        "resolved"
                        if result.quarantined
                        else f"pull failed: {pulled.stderr.strip()[:200]}"
                    )
                    return result
                result.pulled = True
                # A clean pull can still land markers committed elsewhere —
                # scan exactly what the pull changed (no-op pull: ORIG_HEAD
                # absent or equal to HEAD → zero files → zero reads).
                result.quarantined = scan_quarantine(
                    vault, paths=_changed_md(root, ["ORIG_HEAD..HEAD"])
                )

        if push:
            pushed = run_git(root, "push", "origin", "HEAD", timeout=t)
            result.pushed = pushed.returncode == 0
            if not result.pushed:
                result.detail = _detail(f"push failed: {pushed.stderr.strip()[:200]}")

        # A clean run still has to SAY it repaired something. Without this the
        # one outcome where the fix did its whole job -- expired the lock and
        # then succeeded -- is the one that reports nothing.
        if expired_note and not result.detail:
            result.detail = expired_note

    return result
