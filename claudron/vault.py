"""Vault detection, scaffolding, validation, and status.

A vault is a directory containing ``_shared/`` (or ``shared/``) at its
root. Detection walks up from a starting path (like git walks up looking
for ``.git/``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
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

# Opt-in marker FILE (Claudlobby#602 P1). A top-level dir carrying it is a
# *system container*: it holds nested fleets one level down (`<system>/<fleet>/
# fleet.yaml`) plus its own `<system>/shared/` knowledge bucket. A vault with no
# such marker is flat and scans byte-identically to before — the invariant.
SYSTEM_MARKER = ".claudron-system"

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

SCHEMA_VERSION = 2  # bump when index.json entry shape changes (mismatch forces rebuild)

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


def _ensure_gitignore(root: Path) -> None:
    """Guarantee the vault's ignore rules are present at *root*/.gitignore.

    A fresh vault gets the full template. An *adopted* vault that already has
    a .gitignore gets only the missing rules appended — never a silent skip:
    `_write_if_absent` would leave a pre-existing .gitignore untouched, so
    `init --adopt` on a repo that already has one would never gain the `.env`
    / `.claudron/` lines, defeating the secrets guarantee (VAULT-STRUCTURE.md
    §Secrets never commit). Line-exact match errs toward re-appending an
    already-covered rule (harmless) rather than skipping a missing one."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_GITIGNORE_CONTENT)
        return
    existing = gitignore.read_text()
    have = {ln.strip() for ln in existing.splitlines()}
    missing = [
        ln
        for ln in _GITIGNORE_CONTENT.splitlines()
        if ln.strip() and not ln.startswith("#") and ln not in have
    ]
    if missing:
        sep = "" if existing.endswith("\n") else "\n"
        gitignore.write_text(
            f"{existing}{sep}\n# claudron vault — added by `init --adopt`\n"
            + "\n".join(missing)
            + "\n"
        )


# ── data model ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Vault:
    """Immutable snapshot of a detected vault."""

    root: Path
    shared: Path  # root / "_shared"
    projects: dict[str, Path]  # {name: root / "projects" / name}
    fleets: dict[str, Path]  # {name: fleet_dir} — flat AND nested, bare-name key
    systems: dict[str, Path]  # {name: root / name} — .claudron-system containers

    @property
    def recognized_top_level(self) -> set[str]:
        """Top-level dir names that are NOT the ``other:`` hatch — TOP-LEVEL
        (flat) fleets + system containers. The single set the other:/S3
        consumers exclude by, and every one of them does a *top-level* walk.

        Nested fleet names are deliberately excluded: ``_scan_vault`` folds a
        nested fleet into ``fleets`` under its BARE name, but that name is not a
        top-level dir. Including it would shadow an unrelated same-named
        top-level dir out of the other:/S3 hatch — silent data loss
        (Claudlobby#602 review). A flat fleet's dir is ``root/<name>`` (parent
        IS the root); a nested fleet's is ``root/<system>/<name>`` (parent is
        the system dir), so ``path.parent == self.root`` selects flat fleets."""
        flat_fleets = {
            name for name, path in self.fleets.items() if path.parent == self.root
        }
        return flat_fleets | set(self.systems)


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


def _child_dirs(parent: Path) -> Iterator[Path]:
    """Yield *parent*'s eligible child dirs — sorted, skipping SKIP_DIRS and
    dotfiles. The single definition of a "scannable" vault directory."""
    for d in sorted(parent.iterdir()):
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            yield d


def is_within_root(path: Path, root: Path) -> bool:
    """True iff *path* is safely contained by *root*.

    The single containment primitive for every write/repair path (engine's
    ``resolve_target_dir`` + ``append_addendum``, ``capture --update``,
    ``validate --fix``). Two independent guards: (1) the fully symlink-resolved
    *path* stays inside the resolved *root* — catches a component pointing
    *out*; (2) no existing component from *path* up to *root* is itself a
    symlink — rejects a symlinked tier/fleet dir outright, so a write cannot be
    redirected through one even if it happens to resolve back inside. Pass
    *path* **unresolved** — a pre-resolved path has already lost its symlinks
    and defeats guard 2. Works on a not-yet-created target."""
    root = root.resolve()
    if not path.resolve().is_relative_to(root):
        return False
    probe = path
    while probe != root and probe.parent != probe:
        if probe.is_symlink():
            return False
        probe = probe.parent
    return True


def detect(path: Path | None = None) -> Vault | None:
    """Walk up from *path* looking for ``_shared/`` or ``shared/``.

    Returns a :class:`Vault` on success, ``None`` if no vault found.
    """
    start = (path or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if _dir_named(candidate, "_shared"):
            return _scan_vault(candidate)
        # shared/ is also valid, but NOT the binding root when it is a fleet
        # overlay's shared/ (fleet.yaml sits beside it) NOR a system container's
        # shared/ (B2: a `.claudron-system` dir has no sibling fleet.yaml, so
        # this branch would otherwise bind the container and lose the global
        # _shared/ above it). In both cases keep walking up to the true root,
        # whose _shared/ (or a plain shared/) always binds via the checks above.
        if (
            _dir_named(candidate, "shared")
            and not (candidate / "fleet.yaml").is_file()
            and not (candidate / SYSTEM_MARKER).is_file()
        ):
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

    # Discover fleet overlays (dirs containing fleet.yaml) and opt-in system
    # containers (dirs carrying a .claudron-system marker; their nested fleets
    # live one level down). A flat vault has no markers, so `systems` stays
    # empty and this is byte-identical to the pre-P1 flat-fleet loop.
    fleets: dict[str, Path] = {}
    systems: dict[str, Path] = {}
    for d in _child_dirs(root):
        if (d / SYSTEM_MARKER).is_file():
            # System container: record it, then fold its nested fleets into the
            # SAME fleets dict under their BARE names (F5 global-unique keys —
            # never namespaced). The container itself is never a flat fleet.
            systems[d.name] = d
            for sub in _child_dirs(d):
                if (sub / "fleet.yaml").is_file():
                    # Bare-name key (F5 global-unique — never namespaced). A
                    # duplicate bare fleet name across depths (a flat fleet + a
                    # nested one, or two systems' nested fleets) silently
                    # last-wins here — an F5 violation Claudlobby's
                    # _find_fleet_dir raises on. Claudron's validate flagging it
                    # via a new S-code is a tracked follow-up (parity with the
                    # recall-union deferral); the clobber is left as-is for now.
                    fleets[sub.name] = sub
            continue
        if (d / "fleet.yaml").is_file():
            fleets[d.name] = d

    return Vault(
        root=root, shared=shared, projects=projects, fleets=fleets, systems=systems
    )


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
    _ensure_gitignore(root)

    if adopt:
        backfill_updated(root)

    return root


def note_tiers(vault: Vault) -> Iterator[tuple[Path, str]]:
    """(base dir, tier tag) for every note tier in *vault* — the single scope
    shared by ``build_index`` and adopt-backfill so they cannot diverge.
    Mirrors the indexer's walk: each shared subdir, every project, each fleet's
    ``shared/``, each ``.claudron-system`` container's ``shared/`` (``system:``),
    and any unrecognized root dir (the ``other:`` hatch). It
    deliberately never descends a fleet's ``library/``/``voices/``/``runtime/``
    — those are Claudlobby overlay content, not notes (a plain ``root.rglob``
    would wrongly sweep them in, which is the bug this enumerator exists to
    prevent)."""
    for subdir in SHARED_SUBDIRS:
        yield vault.shared / subdir, "shared"
    for name, proj_path in vault.projects.items():
        yield proj_path, f"project:{name}"
    for name, fleet_path in vault.fleets.items():
        yield fleet_path / "shared", f"fleet:{name}"
    # Opt-in system containers: the container's shared/ is its own tier, parallel
    # to a fleet's shared/. Its nested fleets already flowed through the fleet
    # loop above (_scan_vault folds them into vault.fleets under bare names).
    for name, sys_path in vault.systems.items():
        yield sys_path / "shared", f"system:{name}"
    # The `other:` hatch — unrecognized root dirs. Fleets AND system containers
    # are recognized tiers, so a system container is never mis-pooled as other:.
    # Hoist the property once: it rebuilds a set on every access (O(n²) in-loop).
    recognized = vault.recognized_top_level
    for d in _child_dirs(vault.root):
        if d.name not in recognized:
            yield d, f"other:{d.name}"


def backfill_updated(root: Path) -> int:
    """Backfill missing ``updated`` from file mtime across adopted notes.

    The one sanctioned mutation (docs/CLI_CONTRACT.md), at adoption time
    only — it is the remedy for the W101 wall a legacy docs tree would
    otherwise produce. Line-level insert after ``created:`` (or at the
    fence top); never re-serializes YAML, so user formatting is preserved.
    Scoped to the note tiers (:func:`note_tiers`), never a bare
    ``root.rglob`` — else it would rewrite a fleet's library/voices/runtime
    overlay content, which are not notes. Returns the number of files touched.
    """
    vault = detect(root)
    if vault is None:  # not a vault yet (init scaffolds _shared before calling)
        return 0
    touched = 0
    for base, _tier in note_tiers(vault):
        for md in iter_markdown_files(base):
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

    # Index-vs-vault divergence: the silent-failure detector (a dropped write,
    # a coarse-mtime miss, a ghost row, or a corrupt index.json). Nonzero means
    # recall/dedup are working off a bad mirror with no error — surface it as a
    # warning so it can't rot invisibly, and carry the numbers for the G1 gate.
    # Pass the quarantine set we already computed so divergence walks paths only
    # instead of re-reading every note body. Lazy import: knowledge imports
    # vault, so a module-level import here would cycle.
    from .knowledge import index_divergence

    divergence = index_divergence(vault, quarantined=set(quarantined))
    if divergence.get("corrupt"):
        warnings.append(
            "index.json is present but unreadable (corrupt) — recall/dedup run "
            "on nothing until rebuilt; run `claudron index --full`"
        )
    elif divergence["missing"] or divergence["ghost"]:
        warnings.append(
            f"index diverged from disk: {divergence['missing']} note(s) missing, "
            f"{divergence['ghost']} ghost entr(y/ies) — run `claudron index --full`"
        )

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
        "divergence": divergence,
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
    """True if any indexed-tier note is newer than the index.

    Walks only :func:`note_tiers` — the same scope ``build_index`` indexes —
    never a bare ``root.rglob``, which would sweep in a fleet's
    ``runtime``/``library``/``voices`` overlay content and hold the index
    perpetually 'stale' against thousands of files it never indexes anyway.

    Caches the result per (path, index_mtime) so repeated lookups in the
    same process skip the stat walk.
    """
    index_mtime = index_path.stat().st_mtime
    cache_key = (str(index_path), index_mtime)
    cached = _stale_cache.get(cache_key)
    if cached is not None:
        return cached
    for base, _tier in note_tiers(vault):
        for md in iter_markdown_files(base):
            if md.stat().st_mtime > index_mtime:
                _stale_cache[cache_key] = True
                return True
    _stale_cache[cache_key] = False
    return False
