"""Vault detection, scaffolding, validation, and status.

A vault is a directory containing ``_shared/`` (or ``shared/``) at its
root. Detection walks up from a starting path (like git walks up looking
for ``.git/``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from .schema import (
    CONVENTIONS_TEMPLATE,
    NON_NOTE_FILES,
    STALENESS_DONE,
    has_conflict_markers,
    parse_note,
    split_fence,
)


def _write_if_absent(path: Path, content: str) -> None:
    """Idempotent scaffold write — the single home of the pattern (and of
    the reason .gitkeep files exist: git drops empty directories, so a
    young vault's clone would otherwise lose its whole scaffold)."""
    if not path.exists():
        path.write_text(content)


# ── shared constants ─────────────────────────────────────────────────

SKIP_DIRS = frozenset(
    {"_shared", "shared", "projects", "_packs", ".git", ".github", ".claudron",
     "__pycache__"}
)

SHARED_MARKERS = ("_shared", "shared")

# Single source of truth for the shared tier tree: keys are the tiers that
# status/index/search walk; values are on-disk filing subdirs (scaffolded
# nested, walked as one tier — rglob sweeps them in the tier's pass).
# `planning` was added in E1 (SCHEMA.md), deliberately reversing issue #4 —
# vault-level planning docs are content.
SHARED_TIERS: dict[str, tuple[str, ...]] = {
    "knowledge": (),
    "decisions": (),
    "runbooks": (),
    "planning": ("active", "completed"),
}

# Walked by status/index/search — derived, cannot drift from the map.
SHARED_SUBDIRS = tuple(SHARED_TIERS)


def _scaffold_leaves() -> tuple[str, ...]:
    leaves: list[str] = []
    for tier, subs in SHARED_TIERS.items():
        if subs:
            leaves.extend(f"{tier}/{sub}" for sub in subs)
        else:
            leaves.append(tier)
    return tuple(leaves)


# Created by scaffolding (init, fleet add) — derived from the same map.
SCAFFOLD_TREE = _scaffold_leaves()


def scaffold_shared_tree(base: Path, *, exist_ok: bool = False) -> None:
    """Create the shared tier tree under *base* (a `_shared/` or fleet
    `shared/` mount point).

    Each leaf gets a ``.gitkeep``: git doesn't track empty directories, so
    without them a young vault's clone arrives with no ``_shared/`` at all
    — undetectable as a vault, and the whole SD-card promise silently
    fails on machine B (caught by the live loop verification)."""
    for name in SCAFFOLD_TREE:
        leaf = base / name
        leaf.mkdir(parents=True, exist_ok=exist_ok)
        _write_if_absent(leaf / ".gitkeep", "")

# Status semantics live in schema.py (SCHEMA.md is the SSOT): staleness
# uses STALENESS_DONE (imported above); lookup exclusion uses the distinct
# LOOKUP_EXCLUDED — ratified is done-not-hidden, so the sets differ.

SCHEMA_VERSION = 1  # bump when index.json structure changes

# CONVENTIONS.md is the always-loaded layer (injected, not retrieved) —
# never indexed/searched as a note; validate budget-checks it separately
# (which is why it is NOT in schema.NON_NOTE_FILES).
_SKIP_NAMES = NON_NOTE_FILES | {"CONVENTIONS.md"}


def iter_markdown_files(base: Path):
    """Yield .md file paths under *base*, skipping INDEX.md and README.md."""
    if not base.is_dir():
        return
    for md in sorted(base.rglob("*.md")):
        if md.name not in _SKIP_NAMES:
            yield md


# `runtime/` stays fleet-scoped (`*/runtime/`) — it only ever lives at
# `<fleet>/runtime/`; `.env` is any-depth (not `*/.env`) because secrets can
# also sit at the vault root. Do not "fix" the asymmetry to match.
_GITIGNORE_CONTENT = """\
# claudron vault — gitignored runtime & secrets
*/runtime/
.env
.claudron/
"""

# ── data model ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Vault:
    """Immutable snapshot of a detected vault."""

    root: Path
    shared: Path  # root / "_shared"
    projects: dict[str, Path]  # {name: root / "projects" / name}
    fleets: dict[str, Path]  # {name: root / name} where fleet.yaml exists


# ── detection ─────────────────────────────────────────────────────────


def _dir_named(parent: Path, name: str) -> bool:
    """True if ``parent/name`` is a directory with exactly that name.

    ``(parent / "shared").is_dir()`` alone is a footgun on case-insensitive
    filesystems: it matches ``/Users/Shared`` on macOS, which made detect()
    treat ``/Users`` as a vault and walk the whole home directory. Listing
    the parent is the only reliable way to see the on-disk casing
    (``resolve()`` does not case-correct).
    """
    if not (parent / name).is_dir():
        return False
    try:
        return name in os.listdir(parent)
    except OSError:
        return False


def detect(path: Path | None = None) -> Vault | None:
    """Walk up from *path* looking for ``_shared/`` or ``shared/``.

    Returns a :class:`Vault` on success, ``None`` if no vault found.
    """
    start = (path or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if _dir_named(candidate, "_shared"):
            return _scan_vault(candidate)
        # shared/ is also valid, but NOT inside fleet overlays (which
        # have fleet.yaml next to their shared/ dir).
        if _dir_named(candidate, "shared") and not (candidate / "fleet.yaml").is_file():
            return _scan_vault(candidate)
    return None


def _scan_vault(root: Path) -> Vault:
    # Prefer _shared/ over shared/ when both exist
    shared = root / "_shared" if (root / "_shared").is_dir() else root / "shared"

    # Discover projects/
    projects: dict[str, Path] = {}
    projects_dir = root / "projects"
    if projects_dir.is_dir():
        projects = {
            d.name: d
            for d in sorted(projects_dir.iterdir())
            if d.is_dir() and not d.name.startswith(".")
        }

    # Discover fleet overlays (dirs containing fleet.yaml)
    fleets: dict[str, Path] = {}
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            if (d / "fleet.yaml").is_file():
                fleets[d.name] = d

    return Vault(root=root, shared=shared, projects=projects, fleets=fleets)


# ── scaffolding ───────────────────────────────────────────────────────


class VaultError(Exception):
    """Raised when a vault operation fails."""


def init(path: str | Path, *, adopt: bool = False) -> Path:
    """Create a new vault at *path*.

    Raises :class:`VaultError` if the directory is non-empty and
    *adopt* is ``False``, or if ``_shared/`` already exists.

    Returns the vault root.
    """
    root = Path(path).resolve()

    for marker in SHARED_MARKERS:
        if root.is_dir() and (root / marker).is_dir():
            raise VaultError(
                f"vault already exists at {root}\n"
                f"  (has {marker}/ directory — run `claudron status --vault {root}` to inspect)"
            )

    if root.is_dir() and any(root.iterdir()) and not adopt:
        raise VaultError(
            f"directory not empty: {root}\n"
            f"  use --adopt to turn an existing directory into a vault"
        )

    scaffold_shared_tree(root / "_shared", exist_ok=True)
    projects = root / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    _write_if_absent(projects / ".gitkeep", "")
    _write_if_absent(root / "_shared" / "CONVENTIONS.md", CONVENTIONS_TEMPLATE)
    _write_if_absent(root / ".gitignore", _GITIGNORE_CONTENT)

    if adopt:
        backfill_updated(root)

    return root


def backfill_updated(root: Path) -> int:
    """Backfill missing ``updated`` from file mtime across adopted notes.

    The one sanctioned mutation (docs/CLI_CONTRACT.md), at adoption time
    only — it is the remedy for the W101 wall a legacy docs tree would
    otherwise produce. Line-level insert after ``created:`` (or at the
    fence top); never re-serializes YAML, so user formatting is preserved.
    Returns the number of files touched.
    """
    touched = 0
    for md in root.rglob("*.md"):
        if md.name in _SKIP_NAMES:
            continue
        text = md.read_text()
        fm, _, err = parse_note(text)
        if err is not None or not fm or "updated" in fm:
            continue
        stamp = datetime.fromtimestamp(md.stat().st_mtime).date().isoformat()
        lines = text.splitlines(keepends=True)
        insert_at = None
        for i, line in enumerate(lines[1:], start=1):
            if line.rstrip("\r\n") == "---":
                insert_at = i  # fence end — fallback position
                break
            if line.split(":", 1)[0].strip() == "created":
                insert_at = i + 1
                break
        if insert_at is None:
            continue
        lines.insert(insert_at, f"updated: {stamp}\n")
        md.write_text("".join(lines))
        touched += 1
    return touched


# ── status ────────────────────────────────────────────────────────────


def status(vault: Vault, *, stale_days: int = 90) -> dict:
    """Vault health summary.

    Returns a dict with doc counts per tier, stale counts, and warnings.
    """
    today = date.today()
    tiers: dict[str, dict] = {}
    warnings: list[str] = []

    def _count_tier(name: str, base: Path) -> None:
        docs = 0
        stale = 0
        if not base.is_dir():
            tiers[name] = {"docs": 0, "stale": 0, "path": str(base)}
            return
        for md in iter_markdown_files(base):
            docs += 1
            if _is_stale(md, today, stale_days):
                stale += 1
        tiers[name] = {"docs": docs, "stale": stale, "path": str(base)}

    # Shared tiers
    for subdir in SHARED_SUBDIRS:
        _count_tier(f"shared/{subdir}", vault.shared / subdir)

    # Projects
    for name, proj_path in vault.projects.items():
        _count_tier(f"projects/{name}", proj_path)

    # Fleets
    for name, fleet_path in vault.fleets.items():
        fleet_shared = fleet_path / "shared"
        if fleet_shared.is_dir():
            _count_tier(f"{name}/shared", fleet_shared)

    total_docs = sum(t["docs"] for t in tiers.values())
    total_stale = sum(t["stale"] for t in tiers.values())

    if total_docs == 0:
        warnings.append("vault is empty — no knowledge docs found")

    # Conflict quarantine: marker-bearing notes are excluded from search
    # until a human resolves them — surface them here so they can't rot
    # invisibly (detection is stateless; fixing the file clears it).
    # Full-vault second read, accepted: status is an at-will command, not
    # the SessionStart hot path (which scans changed files only).
    quarantined = scan_quarantine(vault)
    for path in quarantined:
        warnings.append(f"quarantined (unresolved conflict markers): {path}")

    # Check index freshness
    index_path = vault.root / ".claudron" / "index.json"
    index_fresh = False
    if index_path.is_file():
        index_fresh = not index_is_stale(vault, index_path)

    return {
        "root": str(vault.root),
        "tiers": tiers,
        "total_docs": total_docs,
        "total_stale": total_stale,
        "projects": list(vault.projects.keys()),
        "fleets": list(vault.fleets.keys()),
        "quarantined": quarantined,
        "index_present": index_path.is_file(),
        "index_fresh": index_fresh,
        "warnings": warnings,
    }


def scan_quarantine(vault: Vault, paths: list[str] | None = None) -> list[str]:
    """Vault-relative paths of notes carrying unresolved conflict markers.

    The single home of the quarantine scan. *paths* restricts the scan
    (sync passes the pull's changed files so a no-op pull reads nothing);
    None scans the whole vault (status). Deliberately covers files the
    tier walker skips — a conflicted CONVENTIONS.md matters most, it is
    the always-injected layer.
    """
    if paths is not None:
        candidates = [vault.root / p for p in paths if p.endswith(".md")]
    else:
        candidates = [
            md for md in sorted(vault.root.rglob("*.md")) if ".git" not in md.parts
        ]
    hits: list[str] = []
    for md in candidates:
        try:
            if md.is_file() and has_conflict_markers(md.read_text()):
                hits.append(str(md.relative_to(vault.root)))
        except OSError:
            continue
    return hits


def _is_stale(path: Path, today: date, default_ttl_days: int) -> bool:
    """Check if a doc is expired based on frontmatter or mtime."""
    try:
        text = path.read_text()
    except OSError:
        return False

    fm = _quick_fm(text)
    if not fm:
        # No frontmatter — use mtime
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
        return (today - mtime).days > default_ttl_days

    # Explicit expires field
    expires = fm.get("expires")
    if expires:
        if isinstance(expires, date):
            return today > expires
        try:
            return today > date.fromisoformat(str(expires))
        except (ValueError, TypeError):
            pass

    # Status-based: terminal statuses aren't "stale", they're done
    if fm.get("status", "") in STALENESS_DONE:
        return False

    # Fall back to updated/created date + TTL
    for field in ("updated", "created"):
        val = fm.get(field)
        if val:
            try:
                d = val if isinstance(val, date) else date.fromisoformat(str(val))
                return (today - d).days > default_ttl_days
            except (ValueError, TypeError):
                pass

    return False


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split markdown into (frontmatter dict, body str).

    Returns ``({}, text)`` if no frontmatter present.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.splitlines(keepends=True)
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            end = i
            break
    if end is None:
        return {}, text
    try:
        fm = yaml.safe_load("".join(lines[1:end])) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    body = "".join(lines[end + 1 :]).lstrip("\n")
    return fm, body


def _quick_fm(text: str) -> dict | None:
    """Fast frontmatter extraction (no body return)."""
    fm, _ = parse_frontmatter(text)
    return fm or None


_stale_cache: dict[tuple[str, float], bool] = {}


def clear_stale_cache() -> None:
    """Clear the stale-check cache (used by tests)."""
    _stale_cache.clear()


def index_is_stale(vault: Vault, index_path: Path) -> bool:
    """True if any .md under vault root is newer than the index.

    Caches the result per (path, index_mtime) so repeated lookups in the
    same process skip the O(n) stat walk.
    """
    index_mtime = index_path.stat().st_mtime
    cache_key = (str(index_path), index_mtime)
    cached = _stale_cache.get(cache_key)
    if cached is not None:
        return cached
    for md in vault.root.rglob("*.md"):
        if md.name.startswith("."):
            continue
        if md.stat().st_mtime > index_mtime:
            _stale_cache[cache_key] = True
            return True
    _stale_cache[cache_key] = False
    return False
