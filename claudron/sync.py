"""Vault sync: the git leg of the SD-card loop (E2).

`sync` is a thin, explicit git wrapper — commit vault changes, pull
--rebase, push. Conflicts are reported and left as markers for the human,
never auto-resolved; marker-bearing notes are quarantined (excluded from
index/lookup/recall — detection is stateless, see
schema.has_conflict_markers) until resolved.

Single-writer-per-machine is the E2 assumption; cross-machine
serialization happens here at the git layer. Hooks call the halves
(`--pull` at SessionStart with a hard timeout, `--push` at SessionEnd)
and fail open on any nonzero outcome.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .schema import has_conflict_markers
from .vault import Vault, iter_markdown_files


@dataclass
class SyncResult:
    ok: bool
    pulled: bool = False
    pushed: bool = False
    committed: bool = False
    quarantined: list[str] = field(default_factory=list)
    detail: str = ""

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
    except FileNotFoundError as exc:
        raise SyncError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError(f"git {' '.join(args)} timed out") from exc


def scan_quarantine(vault: Vault) -> list[str]:
    """Vault-relative paths of notes carrying unresolved conflict markers."""
    hits: list[str] = []
    for md in sorted(vault.root.rglob("*.md")):
        if ".git" in md.parts:
            continue
        try:
            if has_conflict_markers(md.read_text()):
                hits.append(str(md.relative_to(vault.root)))
        except OSError:
            continue
    return hits


def sync(
    vault: Vault,
    *,
    pull: bool = True,
    push: bool = True,
    timeout: float | None = None,
) -> SyncResult:
    """Commit → pull --rebase → push. Raises SyncError for environment
    problems; returns ok=False (with detail + quarantine list) when a
    conflict was left for the human."""
    root = vault.root
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise SyncError(f"vault is not a git repository: {root}")

    result = SyncResult(ok=True)

    # Commit any working-tree changes first — captures don't commit, sync
    # owns the commit so notes actually travel.
    if _git(root, "status", "--porcelain").stdout.strip():
        _git(root, "add", "-A")
        commit = _git(root, "commit", "-m", "claudron sync: vault changes")
        result.committed = commit.returncode == 0

    if pull:
        pulled = _git(root, "pull", "--rebase", "origin", "HEAD", timeout=timeout)
        if pulled.returncode != 0:
            # Conflict (or no remote). The rebase stays stopped with markers
            # in the working tree — the standard resolve/--continue flow;
            # sync never aborts it (aborting would erase the markers the
            # human is supposed to see).
            result.quarantined = scan_quarantine(vault)
            if result.quarantined:
                result.ok = False
                result.detail = (
                    "pull hit conflicts — markers left for the human; "
                    "conflicted notes are quarantined from search until resolved"
                )
                return result
            result.detail = f"pull failed: {pulled.stderr.strip()[:200]}"
            result.ok = False
            return result
        result.pulled = True
        # A clean pull can still land markers committed elsewhere.
        result.quarantined = scan_quarantine(vault)

    if push:
        pushed = _git(root, "push", "origin", "HEAD", timeout=timeout)
        result.pushed = pushed.returncode == 0
        if not result.pushed:
            result.ok = False
            result.detail = f"push failed: {pushed.stderr.strip()[:200]}"

    return result
