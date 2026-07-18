"""Knowledge retrieval engine.

Searches vault tiers by title, tags, filename, and content.
Uses a two-tier strategy:

- **Tier A** — frontmatter index (``.claudron/index.json``). Cheap
  title/tag/alias matching without reading file bodies.
- **Tier B** — full-text scan of markdown bodies (fallback when Tier A
  misses or scores below threshold).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .locking import atomic_write_text, vault_write_lock
from .schema import LOOKUP_EXCLUDED, content_fingerprint, has_conflict_markers
from .vault import (
    SCHEMA_VERSION,
    SHARED_SUBDIRS,
    SKIP_DIRS,
    Vault,
    index_is_stale,
    iter_markdown_files,
    note_tiers,
    parse_frontmatter,
)

# ── data models ───────────────────────────────────────────────────────


@dataclass
class KnowledgeDoc:
    title: str
    tags: list[str]
    body: str
    source_path: Path
    tier: str  # "shared" | "project:<name>" | "fleet:<name>" | "other"
    status: str = "active"
    expires: str = ""
    note_type: str = ""  # SCHEMA.md type enum
    maturity: str = ""  # D11 trust axis — E4 ranks on it; recall labels it
    updated: str = ""  # sortable stamp (updated, else created)


@dataclass
class KnowledgeResult:
    doc: KnowledgeDoc
    score: int
    match_type: str  # "title" | "alias" | "tag" | "heading" | "filename" | "content"


# ── scoring weights ───────────────────────────────────────────────────

W_TITLE_EXACT = 100
W_ALIAS_EXACT = 90
W_TITLE_SUBSTR = 80
W_HEADING = 70
W_TAG_EXACT = 60
W_TITLE_WORD_OVERLAP = 50
W_TAG_PARTIAL = 40
W_FILENAME = 30
W_BODY = 20
W_BODY_EXTRA = 5  # per additional body match, capped
W_BODY_EXTRA_CAP = 25

TIER_A_THRESHOLD = 50  # if best Tier A score < this, fall back to Tier B

W_WORD_BOUNDARY_BONUS = 10  # bonus when substring match aligns to word boundaries

SCORE_CAP = 200


def _is_word_boundary_match(needle: str, haystack: str) -> bool:
    """True if *needle* appears in *haystack* at word boundaries on both sides."""
    return bool(re.search(r"\b" + re.escape(needle) + r"\b", haystack))


def _derive_title(stem: str) -> str:
    s = stem.replace("-", " ").replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else stem


# ── tier walking ─────────────────────────────────────────────────────


def walk_knowledge_tier(base: Path, tier: str) -> list[KnowledgeDoc]:
    """Recursively collect knowledge docs under *base*. Public: the session
    layer walks project tiers through this (membership, not relevance)."""
    docs: list[KnowledgeDoc] = []
    for md_path in iter_markdown_files(base):
        doc = _parse_doc(md_path, tier)
        if doc is not None:
            docs.append(doc)
    return docs


def _stamp(fm: dict) -> str:
    """Canonical sortable recency stamp: `updated`, else `created`.

    The single home of this derivation — the index and E4's future
    notes.updated column must use it too, or recency sorting and ranking
    silently diverge (simplify-panel finding)."""
    return str(fm.get("updated") or fm.get("created") or "")


def _parse_doc(path: Path, tier: str) -> KnowledgeDoc | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    if has_conflict_markers(text):
        return None  # quarantined until a human resolves (stateless)
    fm, body = parse_frontmatter(text)
    title = fm.get("title") or _derive_title(path.stem)
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return KnowledgeDoc(
        title=title,
        tags=[str(t) for t in tags],
        body=body.rstrip(),
        source_path=path,
        tier=tier,
        status=fm.get("status", "active"),
        expires=str(fm.get("expires", "")),
        note_type=str(fm.get("type", "")),
        maturity=str(fm.get("maturity", "")),
        updated=_stamp(fm),
    )


# ── index (Tier A) ───────────────────────────────────────────────────


def index_entry(fm: dict, body: str, md: Path, tier: str, vault_root: Path) -> dict:
    """One index entry from parsed frontmatter + body — the single home of
    the entry shape (build_index and the write engine's incremental update
    both construct entries through this). ``content_hash`` is the
    title-independent body fingerprint dedup keys on alongside the title."""
    return {
        "title": fm.get("title") or _derive_title(md.stem),
        "tags": fm.get("tags") or [],
        "aliases": fm.get("aliases") or [],
        "status": fm.get("status", "active"),
        "updated": _stamp(fm),
        "expires": str(fm.get("expires", "")),
        "content_hash": content_fingerprint(body),
        "filename": md.stem,
        "path": str(md.relative_to(vault_root)),
        "tier": tier,
    }


def write_index(vault: "Vault", index: dict) -> None:
    """Persist the index. Write failures warn, never raise — the index is
    a disposable mirror; the vault stays the source of truth."""
    index_dir = vault.root / ".claudron"
    try:
        index_dir.mkdir(exist_ok=True)
        atomic_write_text(
            index_dir / "index.json", json.dumps(index, indent=2, default=str)
        )
    except OSError as exc:
        import warnings

        warnings.warn(
            f"claudron: could not write index to {index_dir}: {exc}",
            stacklevel=2,
        )


def ensure_index(vault: "Vault") -> dict:
    """A fresh index: loaded when current, rebuilt when stale/missing.
    The one home of the freshness policy (lookup and the write engine
    both go through it)."""
    return load_index(vault) or build_index(vault)


def _iter_indexable(vault: "Vault"):
    """Yield ``(path, tier, text)`` for every note that belongs in the index —
    readable and not quarantined. The single walk :func:`build_index` and
    :func:`index_divergence` share, so "what is indexed" cannot drift between
    the builder and the drift-detector."""
    for base, tier in note_tiers(vault):
        for md in iter_markdown_files(base):
            try:
                text = md.read_text()
            except OSError:
                continue
            if has_conflict_markers(text):
                continue  # quarantined (see _parse_doc)
            yield md, tier, text


def build_index(vault: "Vault") -> dict:
    """Build frontmatter-only index, write to ``.claudron/index.json``.

    Held under the vault write-lock across the disk read AND the write: a full
    rebuild that reads the tree at T0 and writes at T2 would otherwise clobber a
    concurrent capture that landed a note at T1 (read-path lost-update). The lock
    is re-entrant, so calling this from within a mutator that already holds it
    (capture → ensure_index → build_index) is a no-op acquisition, not a deadlock.
    """
    with vault_write_lock(vault):
        entries: list[dict] = []
        for md, tier, text in _iter_indexable(vault):
            fm, body = parse_frontmatter(text)
            entries.append(index_entry(fm, body, md, tier, vault.root))

        index = {"schema_version": SCHEMA_VERSION, "entries": entries}
        write_index(vault, index)
        return index


def _read_index_raw(vault: "Vault") -> dict | None:
    """The index.json decode both :func:`load_index` and :func:`index_divergence`
    share — read, parse, shape-check, schema-version-check. Returns ``None`` on
    missing/corrupt/stale-schema (no pruning; that is load_index's job). One home
    so the two callers can't drift on the decode."""
    index_path = vault.root / ".claudron" / "index.json"
    if not index_path.is_file():
        return None
    try:
        data = json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not (isinstance(data, dict) and "entries" in data):
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None  # stale schema — trigger rebuild
    return data


def load_index(vault: Vault) -> dict | None:
    """Load index if it exists and is fresh. Returns None if stale or missing.

    Prunes ghost entries — index rows whose note has since been deleted from
    disk — before returning, rewriting the index when it does. mtime-forward
    staleness cannot see a deletion (a removed file leaves nothing newer), so
    without this a deleted note would linger in dedup and lookup until the
    next full rebuild."""
    index_path = vault.root / ".claudron" / "index.json"
    if not index_path.is_file():
        return None
    if index_is_stale(vault, index_path):
        return None
    data = _read_index_raw(vault)
    if data is None:
        return None
    entries = data["entries"]
    live = [e for e in entries if (vault.root / e.get("path", "")).exists()]
    if len(live) == len(entries):
        return data
    # Ghosts to drop — but a concurrent capture may have appended between our
    # read and now. Re-read under the write-lock and prune THAT, so we never
    # clobber the appended entry with our stale snapshot.
    with vault_write_lock(vault):
        fresh = _read_index_raw(vault)
        if fresh is None:
            return data
        fresh["entries"] = [
            e for e in fresh["entries"] if (vault.root / e.get("path", "")).exists()
        ]
        write_index(vault, fresh)
        return fresh


def index_divergence(vault: "Vault", *, quarantined: set[str] | None = None) -> dict:
    """Count how far the index has drifted from the notes on disk.

    ``missing`` — notes that should be indexed but aren't (a dropped write, a
    coarse-mtime staleness miss). ``ghost`` — index rows whose note is gone.
    ``corrupt`` — index.json is present but unparseable (itself the silent
    failure this detector exists to surface). All three are the *silent* failure
    class the disposable mirror can introduce: recall and dedup quietly work off
    a stale/garbage index with no error. Surfaced by ``claudron status`` and read
    by the G1 gate; zero on a fresh index.

    Reads ``index.json`` raw (not through :func:`load_index`, which auto-prunes
    ghosts and hides staleness). ``quarantined`` (vault-relative conflicted
    paths) lets a caller that already scanned for markers — ``status`` — pass its
    set so the on-disk walk stays stat-only instead of re-reading every note
    body; omitted, we read bodies via :func:`_iter_indexable` to exclude
    quarantined notes, matching :func:`build_index` exactly.
    """
    index_path = vault.root / ".claudron" / "index.json"
    present = index_path.is_file()
    data = _read_index_raw(vault)
    if data is None:
        # present-but-None == corrupt/stale-schema: the detector's whole point.
        return {"missing": 0, "ghost": 0, "index_present": present, "corrupt": present}

    indexed = {e.get("path") for e in data["entries"]}
    if quarantined is not None:
        skip = set(quarantined)
        on_disk = {
            rel
            for base, _tier in note_tiers(vault)
            for md in iter_markdown_files(base)
            if (rel := str(md.relative_to(vault.root))) not in skip
        }
    else:
        on_disk = {
            str(md.relative_to(vault.root)) for md, _tier, _text in _iter_indexable(vault)
        }
    return {
        "missing": len(on_disk - indexed),
        "ghost": len(indexed - on_disk),
        "index_present": present,
        "corrupt": False,
    }


# ── scoring ──────────────────────────────────────────────────────────


def _score_index_entry(query: str, entry: dict) -> tuple[int, str]:
    """Score a single index entry against *query*. Returns (score, match_type)."""
    q = query.lower()
    total = 0
    best_type = "none"

    title = entry.get("title", "").lower()
    tags = [str(t).lower() for t in entry.get("tags", [])]
    aliases = [str(a).lower() for a in entry.get("aliases", [])]
    filename = entry.get("filename", "").lower()

    # Try single-substring first (exact phrase match scores higher)
    if q == title:
        return min(W_TITLE_EXACT, SCORE_CAP), "title"
    if q in aliases:
        return min(W_ALIAS_EXACT, SCORE_CAP), "alias"

    # Single phrase substring (word-boundary matches score higher)
    if q in title:
        total += W_TITLE_SUBSTR
        if _is_word_boundary_match(q, title):
            total += W_WORD_BOUNDARY_BONUS
        best_type = "title"
    if any(q == t for t in tags):
        total += W_TAG_EXACT
        if best_type == "none":
            best_type = "tag"
    if any(q in t for t in tags) and not any(q == t for t in tags):
        total += W_TAG_PARTIAL
        if best_type == "none":
            best_type = "tag"
    if q in filename:
        total += W_FILENAME
        if best_type == "none":
            best_type = "filename"

    if total > 0:
        return min(total, SCORE_CAP), best_type

    # Multi-word tokenization: score each word independently
    tokens = q.split()
    if len(tokens) > 1:
        token_total = 0
        token_type = "none"
        for token in tokens:
            if token in title:
                token_total += W_TITLE_WORD_OVERLAP
                if token_type == "none":
                    token_type = "title"
            if any(token == t for t in tags):
                token_total += W_TAG_EXACT
                if token_type == "none":
                    token_type = "tag"
            if any(token in t for t in tags) and not any(token == t for t in tags):
                token_total += W_TAG_PARTIAL
                if token_type == "none":
                    token_type = "tag"
            if token in filename:
                token_total += W_FILENAME
                if token_type == "none":
                    token_type = "filename"
        if token_total > 0:
            return min(token_total, SCORE_CAP), token_type

    return 0, "none"


def _score_body(query: str, doc: KnowledgeDoc) -> tuple[int, str]:
    """Tier B: score against body content (headings + body text)."""
    q = query.lower()
    body = doc.body.lower()
    total = 0
    best_type = "none"

    # Check headings
    for line in doc.body.splitlines():
        if re.match(r"^#{1,3}\s", line) and q in line.lower():
            total += W_HEADING
            best_type = "heading"
            break

    # Body substring
    matches = body.count(q)
    if matches > 0:
        total += W_BODY
        if best_type == "none":
            best_type = "content"
        extra = min((matches - 1) * W_BODY_EXTRA, W_BODY_EXTRA_CAP)
        total += extra

    # Multi-word tokenization for body
    if total == 0:
        tokens = q.split()
        if len(tokens) > 1:
            token_hits = sum(1 for t in tokens if t in body)
            if token_hits > 0:
                total += W_BODY * token_hits // len(tokens)
                best_type = "content"

    return min(total, SCORE_CAP), best_type


# ── filtering ────────────────────────────────────────────────────────


def _is_excluded(
    entry: dict, include_archived: bool = False, include_expired: bool = False
) -> bool:
    """True if this entry should be excluded from results."""
    if not include_archived and entry.get("status", "active") in LOOKUP_EXCLUDED:
        return True
    if not include_expired:
        expires = entry.get("expires", "")
        if expires:
            try:
                exp_date = date.fromisoformat(str(expires))
                if date.today() > exp_date:
                    return True
            except (ValueError, TypeError):
                pass
    return False


def _is_doc_excluded(
    doc: KnowledgeDoc, include_archived: bool = False, include_expired: bool = False
) -> bool:
    """Check exclusion for a parsed KnowledgeDoc (Tier B)."""
    return _is_excluded(
        {"status": doc.status, "expires": doc.expires},
        include_archived,
        include_expired,
    )


# ── main lookup ──────────────────────────────────────────────────────


def lookup(
    query: str,
    vault: "Vault",
    *,
    project: str | None = None,
    fleet: str | None = None,
    limit: int = 5,
    include_archived: bool = False,
    include_expired: bool = False,
    tier_b: bool = True,
) -> list[KnowledgeResult]:
    """Search vault knowledge. Returns ranked results.

    ``tier_b=False`` restricts to the frontmatter index — no full-text
    body scan. Hot-path callers (recall at every SessionStart) use it for
    implicit queries where an O(vault) scan would mostly be discarded.
    """
    index = ensure_index(vault)

    # ── Tier A: index-based scoring ──
    results: list[KnowledgeResult] = []
    best_a_score = 0

    for entry in index.get("entries", []):
        if _is_excluded(entry, include_archived, include_expired):
            continue
        score, match_type = _score_index_entry(query, entry)
        if score > 0:
            best_a_score = max(best_a_score, score)
            doc_path = vault.root / entry["path"]
            doc = _parse_doc(doc_path, entry.get("tier", "shared"))
            if doc is not None:
                results.append(
                    KnowledgeResult(doc=doc, score=score, match_type=match_type)
                )

    # ── Tier B: full-text fallback ──
    if tier_b and best_a_score < TIER_A_THRESHOLD:
        result_by_path = {r.doc.source_path: r for r in results}
        for doc in _collect_all_docs(vault, project=project, fleet=fleet):
            if _is_doc_excluded(doc, include_archived, include_expired):
                continue
            score, match_type = _score_body(query, doc)
            if score > 0:
                existing = result_by_path.get(doc.source_path)
                if existing is not None:
                    # Merge: add body score to existing Tier A score
                    existing.score = min(existing.score + score, SCORE_CAP)
                else:
                    result = KnowledgeResult(
                        doc=doc, score=score, match_type=match_type
                    )
                    results.append(result)
                    result_by_path[doc.source_path] = result

    # ── Sort: score desc, then tier priority ──
    tier_priority = {"project": 0, "fleet": 1, "shared": 2, "other": 3}

    def _sort_key(r: KnowledgeResult) -> tuple:
        tier_base = r.doc.tier.split(":")[0] if ":" in r.doc.tier else r.doc.tier
        return (-r.score, tier_priority.get(tier_base, 3))

    results.sort(key=_sort_key)
    return results[:limit]


def _collect_all_docs(
    vault: "Vault",
    *,
    project: str | None = None,
    fleet: str | None = None,
) -> list[KnowledgeDoc]:
    """Collect docs from all tiers in search order."""
    docs: list[KnowledgeDoc] = []

    # Project-local (most specific)
    if project and project in vault.projects:
        docs.extend(walk_knowledge_tier(vault.projects[project], f"project:{project}"))
    else:
        # No project scope — include all projects at lower priority
        for name, proj_path in vault.projects.items():
            docs.extend(walk_knowledge_tier(proj_path, f"project:{name}"))

    # Fleet shared
    if fleet and fleet in vault.fleets:
        fleet_shared = vault.fleets[fleet] / "shared"
        docs.extend(walk_knowledge_tier(fleet_shared, f"fleet:{fleet}"))

    # Vault shared (always)
    for subdir in SHARED_SUBDIRS:
        docs.extend(walk_knowledge_tier(vault.shared / subdir, "shared"))

    # Unrecognized root dirs
    fleet_names = set(vault.fleets.keys())
    for d in sorted(vault.root.iterdir()):
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            if d.name not in fleet_names:
                docs.extend(walk_knowledge_tier(d, f"other:{d.name}"))

    return docs
