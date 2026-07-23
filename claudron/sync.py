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
not O(vault) (gauntlet finding).

Single-writer-per-machine is the E2 assumption; cross-machine
serialization happens here at the git layer. Hooks call the halves
(`--pull` at SessionStart with a hard timeout, `--push` at SessionEnd)
and fail open on any nonzero outcome.
"""

from __future__ import annotations

import socket
import subprocess
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
        raise SyncError(f"git {' '.join(args)} timed out") from exc


def _changed_md(root: Path, spec: list[str]) -> list[str]:
    """Vault-relative .md paths from a `git diff --name-only` invocation."""
    out = run_git(root, "diff", "--name-only", *spec)
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p.endswith(".md")]


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
    if run_git(root, "rev-parse", "--git-dir", timeout=t).returncode != 0:
        raise SyncError(f"vault is not a git repository: {root}")

    result = SyncResult()

    # Hold the vault write-lock across the whole git critical section: a
    # `git add -A`/commit or a rebase that rewrites working-tree files must not
    # interleave with a concurrent `capture` writing a note + index on the same
    # machine (the local-writer race the lock exists for; cross-machine
    # serialization still happens at the git layer below).
    with vault_write_lock(vault):
        # Commit any working-tree changes first — captures don't commit, sync
        # owns the commit so notes actually travel. Every call is bounded by t
        # so a wedged git releases the lock instead of holding it forever.
        porcelain = run_git(root, "status", "--porcelain", timeout=t).stdout.strip()
        if porcelain:
            run_git(root, "add", "-A", timeout=t)
            n = len(porcelain.splitlines())
            commit = run_git(
                root, "commit",
                "-m", f"claudron sync: {n} change(s) from {socket.gethostname()}",
                timeout=t,
            )
            result.committed = commit.returncode == 0

        if pull:
            pulled = run_git(root, "pull", "--rebase", "origin", "HEAD", timeout=t)
            if pulled.returncode != 0:
                # Conflict (or no remote). The rebase stays stopped with markers
                # in the working tree — the standard resolve/--continue flow;
                # sync never aborts it (aborting would erase the markers the
                # human is supposed to see). Scan only the unmerged files.
                result.quarantined = scan_quarantine(
                    vault, paths=_changed_md(root, ["--diff-filter=U"])
                )
                result.detail = (
                    "pull hit conflicts — markers left for the human; conflicted "
                    "notes are quarantined from search until resolved"
                    if result.quarantined
                    else f"pull failed: {pulled.stderr.strip()[:200]}"
                )
                return result
            result.pulled = True
            # A clean pull can still land markers committed elsewhere — scan
            # exactly what the pull changed (no-op pull: ORIG_HEAD absent or
            # equal to HEAD → zero files → zero reads).
            result.quarantined = scan_quarantine(
                vault, paths=_changed_md(root, ["ORIG_HEAD..HEAD"])
            )

        if push:
            pushed = run_git(root, "push", "origin", "HEAD", timeout=t)
            result.pushed = pushed.returncode == 0
            if not result.pushed:
                result.detail = f"push failed: {pushed.stderr.strip()[:200]}"

    return result
