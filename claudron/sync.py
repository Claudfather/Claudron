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


class SyncError(Exception):
    """Environment problems (not a git repo, no git binary) — the CLI maps
    these to exit 3; conflicts are NOT errors, they are reported results."""


def _git(root: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise SyncError(f"git is unavailable: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError(f"git {' '.join(args)} timed out") from exc


def _changed_md(root: Path, spec: list[str]) -> list[str]:
    """Vault-relative .md paths from a `git diff --name-only` invocation."""
    out = _git(root, "diff", "--name-only", *spec)
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
    conflict or push failure was left for the human."""
    root = vault.root
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise SyncError(f"vault is not a git repository: {root}")

    result = SyncResult()

    # Commit any working-tree changes first — captures don't commit, sync
    # owns the commit so notes actually travel.
    porcelain = _git(root, "status", "--porcelain").stdout.strip()
    if porcelain:
        _git(root, "add", "-A")
        n = len(porcelain.splitlines())
        commit = _git(
            root, "commit",
            "-m", f"claudron sync: {n} change(s) from {socket.gethostname()}",
        )
        result.committed = commit.returncode == 0

    if pull:
        pulled = _git(root, "pull", "--rebase", "origin", "HEAD", timeout=timeout)
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
        pushed = _git(root, "push", "origin", "HEAD", timeout=timeout)
        result.pushed = pushed.returncode == 0
        if not result.pushed:
            result.detail = f"push failed: {pushed.stderr.strip()[:200]}"

    return result
