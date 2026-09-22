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

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    #: How many local commits await reconciliation, when :func:`pull_ff_only`
    #: could not fast-forward. None when the question does not apply or the
    #: count could not be read.
    #:
    #: DELIBERATELY NOT `detail`, and #156's proposed fix asks for something
    #: impossible here: it specifies `detail = "not fast-forwardable: N local
    #: commit(s) await reconciliation"` AND `ok=True`. Those cannot both hold,
    #: because `ok` is DERIVED as `not detail` two lines below. Following it
    #: literally would make every ahead clone report ok=False, and the contract
    #: on `detail` one line up is the reason that is wrong rather than merely
    #: inconvenient: an ahead state does not need the human -- the `--check`
    #: door reports it and a scheduled reconciliation resolves it. Training
    #: every hook to log a degradation on a healthy vault is #149's exact
    #: false-signal class. So the count gets its own field and `detail` stays
    #: empty, which keeps `ok` True and keeps the number.
    local_ahead: int | None = None

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
            "local_ahead": self.local_ahead,
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


REBASE_MARKERS = ("rebase-merge", "rebase-apply")


def _rebase_marker_dir(git_dir: Path | None) -> Path | None:
    """The in-progress rebase's state directory, or None."""
    if git_dir is None:
        return None
    for marker in REBASE_MARKERS:
        d = git_dir / marker
        if d.exists():
            return d
    return None


def _killed_rebase(root: Path, git_dir: Path | None, t: float) -> bool:
    """Was this rebase KILLED mid-replay, rather than stopped on a conflict?

    **This is the discrimination the whole fix turns on, and getting it
    backwards is worse than the bug.** A rebase stopped on a conflict holds
    markers a human is meant to see and work a human has possibly already
    started; aborting that destroys their resolution. A rebase killed by the
    per-op timeout holds neither — nothing stopped it deliberately, there is
    nothing to resolve, and leaving it is how a live tree sat detached for
    twelve days with the wrong files checked out.

    Two independent facts, and BOTH must say "kill", because each can be absent
    for its own reason:

    * **no unmerged paths** — a conflict always has them; a kill never does.
    * **no ``stopped-sha``** — git writes that file when it stops ON a commit,
      which is what a conflict is. A kill leaves the todo list and `done` but
      no stopped commit.

    Requiring both means an ambiguous state — anything that looks even
    partly like a conflict — is treated as a conflict and left alone. The
    asymmetry is deliberate: failing toward "leave it for the human" costs a
    refusal, failing the other way costs their work.

    Measured on the live clone that produced the outage: `done` = 1 pick,
    `git-rebase-todo` = 58 remaining, **no stopped-sha, zero unmerged paths** —
    the signature of a kill.
    """
    marker = _rebase_marker_dir(git_dir)
    if marker is None:
        return False
    if (marker / "stopped-sha").exists():
        return False                      # stopped ON a commit: a conflict
    # `--no-optional-locks` for the same reason `_uncommitted` carries it: a
    # plain `diff` may refresh and rewrite the index, and this predicate is
    # reached from the read-only health door as well as from `sync`.
    unmerged = run_git(root, "--no-optional-locks", "diff", "--name-only",
                       "--diff-filter=U", timeout=t)
    if unmerged.returncode != 0 or unmerged.stdout.strip():
        # Either there are conflicted paths, or the question could not be
        # answered — both mean "do not abort".
        return False
    return True


def _default_branch(root: Path, t: float) -> str | None:
    """The branch this clone is supposed to live on, or None if it cannot be
    determined.

    **NONE IS A REAL ANSWER AND USED TO BE A GUESS.** This returned a hardcoded
    ``"main"`` when neither source could answer, which is a guess wearing the
    grammar of a fact -- and it refused live vaults. Measured on git 2.39.5: a
    bare ``git init`` names its branch ``master``, and the bootstrap every new
    vault takes (``git init`` + ``git remote add`` + ``git push -u``, or a
    clone of a still-empty remote) leaves ``refs/remotes/origin/HEAD`` unset.
    On a host with no ``init.defaultBranch``, all three conditions hold at
    once, so the guess said ``main``, the clone said ``master``, and every
    ``claudron sync`` refused with "HEAD is on 'master', the vault syncs on
    'main'" -- a new vault that could never sync at all.
    
    The ``origin/`` strip is load-bearing and is measured, not assumed:
    ``symbolic-ref --short refs/remotes/origin/HEAD`` answers ``origin/main``
    while ``symbolic-ref --short HEAD`` answers ``main``. Comparing the two
    unstripped makes every healthy clone look like a side branch, so the
    refusal below would fire on every sync on every host.
    """
    ref = run_git(root, "symbolic-ref", "--quiet", "--short",
                  "refs/remotes/origin/HEAD", timeout=t)
    if ref.returncode == 0 and ref.stdout.strip():
        name = ref.stdout.strip()
        remote = "origin/"
        return name[len(remote):] if name.startswith(remote) else name
    cfg = run_git(root, "config", "init.defaultBranch", timeout=t)
    if cfg.returncode == 0 and cfg.stdout.strip():
        return cfg.stdout.strip()
    return None


def _alone_in_its_history(root: Path, t: float) -> bool:
    """Is there NO other branch this clone could be supposed to be on?

    The second of the two facts a bootstrap needs. A brand-new vault has one
    line of history and nothing beside it; a mature vault on a side branch has
    `origin/main` (or a local `main`) sitting right there, which is the thing
    it is stranding work away from.

    **The obvious measure does not work, and it was measured rather than
    reasoned about.** "Does this clone hold commits that reach no remote"
    (`rev-list --count HEAD --not --remotes`) reads **0** on the adversarial
    vault -- because `sync` had already pushed the side branch, so the history
    IS on a remote, just on the wrong branch. That is the outage's own shape
    (59 commits off the default branch, 53 reaching no remote, and therefore 6
    that did), so a predicate satisfied by it is no predicate at all.

    An unreadable ref list returns False: the caller treats "cannot establish"
    as "not a bootstrap", which refuses.
    """
    refs = run_git(root, "for-each-ref", "--format=%(refname:short)",
                   "refs/heads", "refs/remotes", timeout=t)
    if refs.returncode != 0:
        return False
    head = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=t)
    current = head.stdout.strip() if head.returncode == 0 else ""
    up = run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", timeout=t)
    upstream = up.stdout.strip() if up.returncode == 0 else ""
    for name in refs.stdout.splitlines():
        name = name.strip()
        if name and name != current and name != upstream:
            return False
    return True


def _is_bootstrap(default: str | None, alone: bool) -> bool:
    """Both facts must agree before the side-branch guard stands down.

    A bootstrap is NOT merely "origin/HEAD is unset". A mature vault loses that
    ref too -- a pruned remote ref, a reclone, a hand-rolled `remote add` -- and
    treating the absence alone as a bootstrap removes the guard exactly where
    it is needed. Reproduced: a mature vault on a genuine side branch with
    three commits of its own and no origin/HEAD was committed AND pushed with
    no refusal at all.

    So: the default branch could not be determined **and** there is no other
    branch this clone could be supposed to be on. The third state -- "cannot
    say" -- is not a bootstrap, which refuses.

    The mirror of `_killed_rebase` and `_is_expirable`, and the same fail-safe
    direction for the same reason. Refusing a genuine bootstrap costs one
    confused new user an override that the refusal itself prints; passing a
    diverged mature vault is the outage.
    """
    return default is None and alone


def _refuse_off_default(root: Path, t: float, allow: str | None) -> str | None:
    """Refusal text when HEAD is not the default branch, or None.

    A clone left on a side branch is the state where captures look durable in
    ``git log`` and exist on no other machine: on the host that produced this
    issue, 59 commits accrued there and 53 reached no remote at all. Refusing
    costs one message; not refusing cost six weeks of invisible divergence.

    Answering "I cannot tell which branch I am on" is NOT a refusal: a detached
    HEAD is already caught by ``_interrupted_state`` upstream of this, and
    inventing a second refusal for it here would fire on states this check has
    no opinion about.
    """
    head = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=t)
    if head.returncode != 0 or not head.stdout.strip():
        return None
    current = head.stdout.strip()
    if allow is not None and allow == current:
        return None
    default = _default_branch(root, t)
    if default is None:
        # An undetermined default is not on its own a licence to pass -- see
        # `_is_bootstrap`, which is where the two facts are weighed.
        if _is_bootstrap(default, _alone_in_its_history(root, t)):
            return None
        return (
            f"refusing to sync: HEAD is on '{current}' and the vault's default "
            "branch cannot be determined (no origin/HEAD, no "
            "init.defaultBranch), while this clone holds other branches -- so "
            "this may be stranding work. Restore the ref with `git remote "
            "set-head origin --auto`, or pass --branch "
            f"{current} to sync this branch deliberately"
        )
    if current == default:
        return None
    return (
        f"refusing to sync: HEAD is on '{current}', the vault syncs on "
        f"'{default}' — checkout the default branch, or pass --branch "
        f"{current} to sync a side branch deliberately"
    )
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


@dataclass(frozen=True)
class CommitOutcome:
    """Which step ran and how it went — ``step`` is ``"add"`` or ``"commit"``.

    #157 specified ``commit_paths() -> CompletedProcess``, and that is not
    enough: `sync` must tell a failed STAGE (a refusal — name git's own message)
    from a failed COMMIT (`committed=False`, carry on), and recovering that from
    the returned process means reading argv. Two attempts at that were wrong —
    `run_git` injects a `-c user.name=…` prefix for `commit` only, so positions
    shift, and a membership test then depends on a test double populating
    ``args`` faithfully, which is a coupling between production logic and the
    fidelity of a stub. Naming the step removes the inference entirely.
    """

    step: str
    proc: subprocess.CompletedProcess

    @property
    def ok(self) -> bool:
        return self.proc.returncode == 0

    @property
    def error(self) -> str:
        """git's own message, or the exit code when it said nothing."""
        said = (self.proc.stderr or "").strip() or (self.proc.stdout or "").strip()
        return said[:200] if said else f"exit {self.proc.returncode}"


def commit_paths(root: Path, paths: list[Path], message: str, *,
                 timeout: float | None = None) -> CommitOutcome:
    """``git add`` the NAMED paths and commit them. Returns the commit's result.

    Extracted from :func:`sync` so the write door and the safety net share one
    definition of "stage and commit" — the identity fallback, the bounded
    invoker, and the add-failure-is-reported-not-swallowed rule (#157).

    **It stages only what it is given.** `sync` passes nothing and gets `add -A`
    (the net sweeps whatever is lying around); the write door passes the note it
    just wrote, so a capture cannot commit a half-finished file somebody else
    was editing in the same tree. An empty ``paths`` therefore means "everything"
    and is the net's call, never the door's.

    THE CALLER DECIDES WHAT A FAILURE MEANS, which is why this returns the
    process rather than raising or returning a bool: for `sync` a failed commit
    is `committed=False`, for the write door it is a warning on a note that is
    already on disk. Collapsing those would force one of them to lie.
    """
    t = timeout if timeout is not None else DEFAULT_GIT_TIMEOUT
    if paths:
        added = run_git(root, "add", "--", *[str(p) for p in paths], timeout=t)
    else:
        added = run_git(root, "add", "-A", timeout=t)
    if added.returncode != 0:
        # Hand the ADD's failure back, not a commit that was never attempted:
        # naming the cause rather than the symptom is why sync stopped here too.
        return CommitOutcome("add", added)
    return CommitOutcome("commit", run_git(root, "commit", "-m", message, timeout=t))


def sync(
    vault: Vault,
    *,
    pull: bool = True,
    push: bool = True,
    timeout: float | None = None,
    branch: str | None = None,
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
    def _done(res: SyncResult) -> SyncResult:
        """Record this attempt, then hand the result back.

        Every exit from the locked section goes through here, so the
        journal counts REFUSALS as attempts too -- a clone that has been
        refusing for a week and one nobody has asked to sync look identical
        without that, and telling them apart is the whole point of having a
        denominator (#149). `last_state` is `ok` or `refused` and nothing
        else; it is deliberately NOT the health door's verdict vocabulary,
        which describes a CLONE rather than an attempt.
        """
        _journal_write(root, ok=res.ok, state="ok" if res.ok else "refused")
        return res

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
            return _done(result)

        # A side branch is refused BEFORE the `add -A` below, not after: the
        # whole harm of a clone on the wrong branch is that it keeps
        # accumulating work nothing else can see, so a refusal that committed
        # first would add one more stranded commit each time it fired.
        off_default = _refuse_off_default(root, t, branch)
        if off_default:
            result.detail = off_default
            return _done(result)

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
                    return _done(result)
                expired_note = f"expired stale index.lock (age {age}s, no owner)"
            else:
                owner = {True: "held", False: "no owner", None: "unknown"}[holder]
                result.detail = (
                    f"refusing to sync: .git/index.lock is present (age {age}s, "
                    f"owner {owner}) — another git process may be running; "
                    "nothing was written"
                )
                return _done(result)
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

        # Commit any working-tree changes first. SINCE #157 THE WRITE DOOR
        # COMMITS ITS OWN NOTES, so this is the SAFETY NET rather than the only
        # commit: what it still catches is everything written AROUND the door --
        # a hand-edited plan, a working document, a bot writing with a shell
        # redirect (which this estate does). The older comment here said
        # "captures don't commit, sync owns the commit so notes actually travel",
        # which stopped being true at #157 and would have sent the next reader
        # looking for the durability guarantee in the wrong place.
        porcelain = run_git(root, "status", "--porcelain", timeout=t).stdout.strip()
        if porcelain:
            # THE SAFETY NET, and it stays even though the write door now
            # commits its own notes (#157). What it catches is everything
            # written AROUND the door -- a hand-edited plan, a working document,
            # a bot writing with a shell redirect (which this estate still
            # does). Deleting it because captures commit themselves would
            # strand exactly those files, which is the population it exists for.
            #
            # "straggler(s)" rather than "change(s)" on purpose: the two commit
            # classes stay countable in `git log`, so "how much still arrives
            # around the door" is a number rather than an impression.
            n = len(porcelain.splitlines())
            outcome = commit_paths(
                root, [],   # [] = add -A: the net sweeps, the door does not
                f"vault sync: {n} straggler(s) from {socket.gethostname()}",
                timeout=t,
            )
            if not outcome.ok and outcome.step == "add":
                # The pre-existing rule, preserved: a failed STAGE is a refusal
                # naming git's own message, never a commit that was never
                # attempted and a porcelain re-read blaming the tree.
                result.detail = _detail(f"git add failed: {outcome.error}")
                return _done(result)
            result.committed = outcome.ok

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
                return _done(result)
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
                    # A KILLED replay is cleaned up; a CONFLICT is not. See
                    # `_killed_rebase` for why both of its facts must agree
                    # before anything is aborted -- a conflict's markers are a
                    # human's work in progress, and erasing them is worse than
                    # the wedge this fixes.
                    if _killed_rebase(root, git_dir, t):
                        abort = run_git(root, "rebase", "--abort", timeout=t)
                        left = _interrupted_state(root, git_dir, t)
                        if abort.returncode == 0 and left is None:
                            head = run_git(root, "symbolic-ref", "--quiet",
                                           "--short", "HEAD", timeout=t)
                            sha = run_git(root, "rev-parse", "--short", "HEAD",
                                          timeout=t)
                            where = (f"{head.stdout.strip()}@{sha.stdout.strip()}"
                                     if head.returncode == 0 and sha.returncode == 0
                                     else "its previous branch")
                            result.detail = (
                                f"{exc} — rebase aborted, repository restored "
                                f"to {where}"
                            )
                            return _done(result)
                        # The abort itself failed, or left something behind.
                        # Fall through to the human-facing text rather than
                        # claiming a repair that did not happen.
                    left = _interrupted_state(root, git_dir, t)
                    result.detail = _detail(
                        f"{exc} — {left}; left for the human"
                        if left
                        else f"{exc} — repository left consistent"
                    )
                    return _done(result)
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
                    return _done(result)
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

        # The success path's recording, still inside the lock -- `detail` is
        # final by here, and `ok` is derived from it.
        _done(result)

    return result


# ── the health door (#154) ────────────────────────────────────────────
#
# THE STATE NAMES ARE THE CONTRACT, not the implementation. Two consumers key
# on them -- the supervisor's doctor rung and the scheduled vault-sync job --
# and an implementation can be rewritten where a name that has been keyed on
# cannot. They are chosen once, here, and they are deliberately the vocabulary
# the repair doors already use (`_killed_rebase`, `_interrupted_state`,
# `_refuse_off_default`, `_index_lock_state`): a health door that invented a
# parallel naming would make "what sync refuses" and "what check reports" two
# things a reader has to translate between.

#: Verdicts in PRECEDENCE order -- the first whose condition holds wins, and
#: this tuple is the only place that order is written down.
#:
#: The S-table of the design doc maps onto it as:
#:
#: ===================================  ==================
#: state                                design-doc state
#: ===================================  ==================
#: ``unknown``                          (none -- see below)
#: ``stale-lock``                       S11
#: ``rebase-conflict``                  S8
#: ``rebase-killed``                    S9
#: ``merge``                            S10
#: ``detached``                         S7
#: ``side-branch``                      S5 and S6
#: ``dirty``                            S4
#: ``divergent``                        S13
#: ``behind``                           S3
#: ``ahead``                            S2
#: ``unreachable``                      S12 (only with ``reach=True``)
#: ``clean``                            S1
#: ===================================  ==================
#:
#: S5 and S6 share ``side-branch`` on purpose; the ``upstream`` field (a name
#: or ``None``) is what tells them apart, so thirteen states are thirteen
#: verdicts only because ``unknown`` is not one of the design's states.
#:
#: **``unknown`` is the one value with no S-row, and it is the important one.**
#: The S-table enumerates states of the CLONE. It has nothing to say about a
#: check that could not RUN -- git missing, a git call timing out -- and a
#: reader that cannot reach its source must never answer the same as one that
#: looked and found nothing wrong. Returning ``clean`` there would rebuild the
#: exact silence this door exists to end: for twelve days every probe on the
#: outage host reported the engine healthy.
CHECK_STATES = (
    "unknown",
    "stale-lock",
    "rebase-conflict",
    "rebase-killed",
    "merge",
    "detached",
    "side-branch",
    "dirty",
    "divergent",
    "behind",
    "ahead",
    "unreachable",
    "clean",
)

def pull_ff_only(vault: Vault, *, timeout: float | None = None) -> SyncResult:
    """Fetch the upstream and FAST-FORWARD onto it. Never commits, never rebases.

    THE NON-REWRITING PULL, for callers on a latency budget -- the hooks above
    all else. `sync(pull=True)` commits whatever is on disk and then runs
    `git pull --rebase` in the live tree, and a budget that is right for
    latency is wrong for a history rewrite: the only two outcomes of a 2 s
    rebase on a busy host are "nothing to do" and "killed part-way". A killed
    replay detaches HEAD and leaves commits reachable from no branch. On the
    host that produced #156 that happened at 14:08:39 on 2026-09-09, one pick
    completed and 58 pending, and the tree sat that way until 20:22.

    Every write this does is bounded by construction rather than by the clock:
    `fetch` writes only under `.git/`, so killing it leaves the working tree
    untouched; `merge --ff-only` is a single ref-and-tree update with no replay
    to be interrupted half-way. That is what makes a 2 s budget honest here and
    dishonest for a rebase.

    NOT FAST-FORWARDABLE IS NOT AN ERROR. A clone with local commits is
    `ahead`, which is a legitimate state that the `--check` door reports and a
    scheduled reconciliation resolves. Returning ok=False would train every
    hook caller to log a degradation on a healthy vault, and #149 is about
    exactly that class of false signal. So: `pulled=False`, `ok=True`, and a
    detail that counts the commits awaiting reconciliation.

    THE FETCH NAMES THE UPSTREAM'S OWN REMOTE AND REF, never the default
    branch: on a clone whose HEAD tracks something else, fetching the default
    branch by name would leave `@{upstream}` stale and the following
    `merge --ff-only @{upstream}` would fast-forward onto a ref nobody
    refreshed -- a silent no-op that reads as success.

    Refusals are `sync()`'s, reused rather than restated: mid-surgery via
    :func:`_interrupted_state`, a side branch via :func:`_refuse_off_default`.
    Hooks never pass a branch, so a side-branch clone refuses here exactly as
    it does there -- one decision for that state, applied by every door that
    moves the tree.
    """
    root = vault.root
    t = timeout if timeout is not None else DEFAULT_GIT_TIMEOUT
    git_dir = _git_dir(root, t)
    if git_dir is None:
        raise SyncError(f"vault is not a git repository: {root}")

    result = SyncResult()

    # The same write lock `sync()` takes, for the same reason: a `merge
    # --ff-only` updates working-tree files and must not interleave with a
    # concurrent `capture` writing a note and an index on this machine.
    with vault_write_lock(vault):
        interrupted = _interrupted_state(root, git_dir, t)
        if interrupted:
            result.detail = (
                f"refusing to pull: {interrupted} — nothing was written; "
                "resolve the repository first"
            )
            return result

        # `allow=None`: a hook has no --branch to pass, and a door that only
        # fast-forwards is not a reason to relax the side-branch rule -- a side
        # branch is refused because work accrues where nothing else can see it,
        # which a fast-forward does not fix.
        off_default = _refuse_off_default(root, t, None)
        if off_default:
            result.detail = off_default
            return result

        upstream = run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", timeout=t)
        if upstream.returncode != 0 or not upstream.stdout.strip():
            # No tracking branch is a legitimate local-only vault, not a fault:
            # there is nothing to fast-forward onto and nothing to report.
            result.detail = ""
            return result
        ref = upstream.stdout.strip()
        remote, _, branch = ref.partition("/")
        if not remote or not branch:
            result.detail = (
                f"refusing to pull: cannot read the upstream as <remote>/<branch> "
                f"(got '{ref}')"
            )
            return result

        fetched = run_git(root, "fetch", remote, branch, timeout=t)
        if fetched.returncode != 0:
            result.detail = (
                f"fetch failed: {(fetched.stderr or fetched.stdout).strip()[:200]}"
            )
            return result

        merged = run_git(root, "merge", "--ff-only", ref, timeout=t)
        if merged.returncode == 0:
            result.pulled = True
            return result

        # Not fast-forwardable: count what is waiting rather than echoing git.
        # `ok` stays True -- see the docstring. The count is best-effort: a
        # number that cannot be read must not turn a healthy ahead state into a
        # failure, so it degrades to the state without the count.
        rev = run_git(root, "rev-list", "--count", f"{ref}..HEAD", timeout=t)
        n = rev.stdout.strip() if rev.returncode == 0 else ""
        result.pulled = False
        result.local_ahead = int(n) if n.isdigit() and int(n) > 0 else None
        return result


#: Where `sync()` records its outcome, so `check()` can answer "when did this
#: clone last sync successfully" -- the denominator a consumer needs to tell a
#: vault that is quietly failing from one nobody has asked to sync. Under
#: `.claudron/`, which is gitignored, and written by `sync()` alone.
SYNC_JOURNAL = "sync.json"


@dataclass
class CheckResult:
    """One read-only verdict about a vault clone's git state.

    ``detail`` is human-readable and is the ONLY field a consumer must not key
    on; it carries why a verdict is ``unknown``, which is a sentence rather
    than a category.
    """

    state: str = "unknown"
    branch: str | None = None
    default_branch: str | None = None
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    uncommitted: int | None = None
    uncommitted_oldest_age_s: int | None = None
    lock_age_s: int | None = None
    interrupted: str | None = None
    last_sync_ok_at: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """``clean`` is the only healthy verdict. ``unknown`` is NOT ok -- that
        is the whole point of having it."""
        return self.state == "clean"

    def to_dict(self) -> dict:
        return {
            "check": True,
            "state": self.state,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "upstream": self.upstream,
            "ahead": self.ahead,
            "behind": self.behind,
            "uncommitted": self.uncommitted,
            "uncommitted_oldest_age_s": self.uncommitted_oldest_age_s,
            "lock_age_s": self.lock_age_s,
            "interrupted": self.interrupted,
            "last_sync_ok_at": self.last_sync_ok_at,
            "detail": self.detail,
        }


def _journal_path(root: Path) -> Path:
    return root / ".claudron" / SYNC_JOURNAL


def _journal_read(root: Path) -> dict:
    """The sync journal, or an empty dict. Never raises: a health door that
    died on an unreadable optional file would be less available than the thing
    it reports on."""
    try:
        with open(_journal_path(root), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _journal_write(root: Path, *, ok: bool, state: str) -> None:
    """Record this run's outcome. Called by `sync()` under the write lock it
    already holds, and by nothing else -- `check()` only ever reads.

    Best-effort by construction: a vault whose `.claudron/` cannot be written
    still syncs, and losing the denominator is not worth failing the numerator.
    """
    now = datetime.now(timezone.utc).isoformat()
    data = _journal_read(root)
    data["last_attempt_at"] = now
    data["last_state"] = state
    if ok:
        data["last_ok_at"] = now
    try:
        path = _journal_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return


def _uncommitted(root: Path, t: float) -> tuple[int, int | None]:
    """``(count, oldest_age_s)`` over the paths `status --porcelain` lists.

    `--porcelain` needs no index lock, which is exactly why it kept answering
    for twelve days while every WRITE in the vault failed -- so this is a count
    of files, never evidence that the repository is writable.

    **`--no-optional-locks` is load-bearing, and the read-only pin is what
    found it.** A plain `git status` REFRESHES the index's stat cache and
    writes `.git/index` to do it -- measured: touch a tracked file, run
    `status`, and the index mtime moves, while the same command under
    `--no-optional-locks` leaves it alone. A live vault's files are touched
    constantly, so without the flag this door would write the index on
    essentially every call: the exact defect it was built to remove from
    `status --json`, rebuilt inside its replacement.
    """
    out = run_git(root, "--no-optional-locks", "status", "--porcelain", timeout=t)
    if out.returncode != 0:
        return 0, None
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    oldest: float | None = None
    now = time.time()
    for ln in lines:
        rel = ln[3:].strip()
        if " -> " in rel:                       # a rename: take the destination
            rel = rel.split(" -> ", 1)[1]
        rel = rel.strip('"')
        try:
            mtime = os.path.getmtime(root / rel)
        except OSError:
            continue                            # deleted, or an unreadable path
        age = now - mtime
        oldest = age if oldest is None else max(oldest, age)
    return len(lines), (int(oldest) if oldest is not None else None)


def check(vault: Vault, *, timeout: float | None = None,
          reach: bool = False) -> CheckResult:
    """A read-only, git-only verdict on one vault clone.

    **Read-only is the point, not a courtesy.** The door this replaces --
    `status --json` -- walks every note and WRITES the index on its way to an
    answer, so asking "is this healthy" mutated the thing being asked about and
    could not be run on a wedged or read-only tree. Every git command here is a
    query; nothing touches the index, the working tree or the journal. The
    test suite pins that rather than trusting this paragraph.

    **It answers offline.** No network call happens unless ``reach`` is passed,
    because the watchdog that polls this must not be gated on a remote being up.

    Raises :class:`SyncError` when the vault is not a git repository at all,
    which is what `sync()` already does for the same condition and what the CLI
    already maps to its environment-error exit. That is deliberately NOT a
    verdict: a directory that is not a clone has no clone-health to report, and
    inventing a state for it would put a second meaning into a vocabulary whose
    whole value is that consumers can key on it.
    """
    root = vault.root
    t = timeout if timeout is not None else DEFAULT_GIT_TIMEOUT
    last_ok = _journal_read(root).get("last_ok_at")

    def _unknown(why: str) -> CheckResult:
        return CheckResult(state="unknown", detail=why, last_sync_ok_at=last_ok)

    try:
        git_dir = _git_dir(root, t)
    except SyncError as exc:
        return _unknown(str(exc))
    if git_dir is None:
        raise SyncError(f"vault is not a git repository: {root}")

    r = CheckResult(last_sync_ok_at=last_ok)
    try:
        r.interrupted = _interrupted_state(root, git_dir, t)
        r.default_branch = _default_branch(root, t)

        head = run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", timeout=t)
        r.branch = head.stdout.strip() if head.returncode == 0 else None

        up = run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", timeout=t)
        r.upstream = up.stdout.strip() if up.returncode == 0 and up.stdout.strip() else None

        if r.upstream:
            # MEASURED, not assumed: `--left-right --count @{upstream}...HEAD`
            # prints LEFT then RIGHT, left being the upstream side (behind) and
            # right the HEAD side (ahead). Swapping the two would be a silent
            # contract bug -- every consumer would read a clone that needs a
            # pull as one that needs a push.
            counts = run_git(root, "rev-list", "--left-right", "--count",
                             "@{upstream}...HEAD", timeout=t)
            if counts.returncode == 0:
                parts = counts.stdout.split()
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    r.behind, r.ahead = int(parts[0]), int(parts[1])

        r.uncommitted, r.uncommitted_oldest_age_s = _uncommitted(root, t)

        lock = _index_lock_state(git_dir)
        if lock is not None:
            _, r.lock_age_s, _ = lock

        reachable: bool | None = None
        if reach:
            probe = run_git(root, "ls-remote", "--exit-code", "origin", "HEAD",
                            timeout=t)
            reachable = probe.returncode == 0

        killed = _killed_rebase(root, git_dir, t)
        # Only asked when the default branch could not be determined, and
        # only to tell a brand-new clone from a mature one that lost the
        # ref -- the same weighing `_refuse_off_default` does, through the
        # same predicate, so the health door and the refusal door cannot
        # disagree about one clone.
        alone = (r.default_branch is None) and _alone_in_its_history(root, t)
    except SyncError as exc:
        # A git call that could not complete. Everything gathered so far is
        # discarded rather than reported beside a verdict derived from a
        # partial read: a half-answer wearing a confident label is the failure
        # this vocabulary's `unknown` exists to prevent.
        return _unknown(str(exc))

    r.state = _verdict(r, killed=killed, reach=reach, reachable=reachable,
                      bootstrap=_is_bootstrap(r.default_branch, alone))
    return r


def _verdict(r: CheckResult, *, killed: bool, reach: bool,
             reachable: bool | None, bootstrap: bool = False) -> str:
    """The precedence in :data:`CHECK_STATES`, applied.

    Split out from :func:`check` so the ordering can be tested against a
    constructed result without a repository -- the gathering and the judging
    fail for different reasons and are worth being able to exercise apart.
    """
    # A LOCK IS REPORTED ON AGE ALONE, while `sync()` deletes one only when it
    # is also provably ownerless. The asymmetry is deliberate: the bar for
    # ACTING on a lock is higher than the bar for TELLING someone about it,
    # because deleting a live lock corrupts the index and mentioning one costs
    # nothing. Reporting only the provably-ownerless ones would go silent on a
    # wedged vault whose host has no way to name the holder -- which is how the
    # original lock sat for ten and a half days while every read kept working.
    # Young locks are ordinary concurrent writes and are not a verdict at all,
    # so a watchdog polling this does not flap.
    if r.lock_age_s is not None and r.lock_age_s >= STALE_LOCK_AGE_S:
        return "stale-lock"
    if r.interrupted and "rebase" in r.interrupted:
        return "rebase-killed" if killed else "rebase-conflict"
    if r.interrupted and "merge" in r.interrupted:
        return "merge"
    if r.branch is None:
        return "detached"
    if r.default_branch and r.branch != r.default_branch:
        return "side-branch"
    if r.default_branch is None and not bootstrap:
        # The default could not be determined AND this clone has other branches
        # beside it, so it may well be on the wrong one. `side-branch` rather
        # than a fourteenth state: the consumer's action is identical, and the
        # verdict matches what `sync` does with the same clone. A genuine
        # bootstrap -- one line of history, nothing beside it -- is not this.
        return "side-branch"
    if r.uncommitted:
        return "dirty"
    if r.ahead and r.behind:
        return "divergent"
    if r.behind:
        return "behind"
    if r.ahead:
        return "ahead"
    if reach and reachable is False:
        return "unreachable"
    return "clean"
