"""The write engine: compose, validate, dedup, write — one path in.

The shared seam the roadmap names (cycle-1): `claudron capture` (CLI) and
`claudron new` (its composer) go through this module, so N writers get one
validate/dedup implementation; E3's future MCP `claudron_write` will join
them. Nothing writes a note into a vault except through here.

Dedup **routes, never hard-rejects**: a near-duplicate becomes a
``suggest_update``/``suggest_supersede`` result returned to the caller —
a silent-drop gate would also drop the contradicting updates curation
exists to catch (roadmap E3 contract).

The write path also *maintains* the index: after a note lands, its entry
is appended and ``index.json`` rewritten last (mtime ≥ the note's), so the
next write loads the index instead of rebuilding it. Without this, every
capture stales the index and fleet writes degrade to Θ(vault) each —
Θ(N²) over a vault's life.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .knowledge import ensure_index, index_entry, write_index
from .locking import atomic_write_text, vault_write_lock
from .schema import (
    DEDUP_EXEMPT,
    MATURITY_VALUES,
    STATUS_VOCAB,
    TYPE_DIRS,
    TYPES,
    Finding,
    claimed_names,
    content_fingerprint,
    parse_note,
    set_frontmatter_field,
    slugify,
    validate_note,
)
from .vault import Vault, is_within_root


class ScopeError(Exception):
    """A write refused before composition: unregistered fleet, or a path/
    scope that escapes the vault root. Not a schema Finding — the CLI maps
    it to a usage error (exit 2), the MCP layer to its error payload."""


@dataclass
class WriteResult:
    """The engine's uniform outcome — one shape for every door.

    ``action`` is E3's approval-frozen wire vocabulary:
    created | updated | suggest_update | suggest_supersede | rejected.
    ``errors`` is non-empty exactly when action == "rejected" (validation
    Findings; nothing was written). ``to_dict()`` is the MCP payload.
    """

    action: str
    path: str  # written/updated note, or the existing note for suggestions
    reason: str
    errors: list[Finding] = field(default_factory=list)

    @property
    def written(self) -> bool:
        """True iff a note actually landed. The load-bearing signal every door
        reports: a ``suggest_*`` dedup route (and ``rejected``) *succeeds* having
        written nothing, so a consumer must branch on this, not on ok/exit
        (docs/CLI_CONTRACT.md). Lives on the shared type so the CLI and a future
        MCP ``claudron_write`` can't drift on the string match."""
        return self.action in ("created", "updated")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["errors"] = [f.to_dict() for f in self.errors]
        data["written"] = self.written
        return data


def _rejected(findings: list[Finding]) -> WriteResult:
    return WriteResult(
        action="rejected",
        path="",
        reason=f"{len(findings)} validation error(s); nothing written",
        errors=findings,
    )


def yaml_scalar(value: str) -> str:
    """Quote a string for hand-assembled frontmatter unless it round-trips
    through the real YAML parser as the identical string (implicit typing:
    bare `true`/`0`/dates become non-strings). json.dumps output is valid
    double-quoted YAML."""
    if value != value.strip():
        return json.dumps(value)
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError:
        return json.dumps(value)
    if isinstance(parsed, str) and parsed == value:
        return value
    return json.dumps(value)


def compose_note(
    *,
    note_type: str,
    title: str,
    owner: str,
    body: str = "",
    tags: list[str] | None = None,
    maturity: str | None = None,
    source_url: str | None = None,
    source_type: str | None = None,
) -> str:
    """Assemble a schema-valid note. Hand-assembled rather than yaml.dump —
    pins key order, flow-style tags, unquoted ISO dates so the note stays
    human-shaped; yaml_scalar covers the escaping that trades away.

    ``source_url``/``source_type`` are SCHEMA.md optional fields and are
    omitted entirely when unset — an empty ``source_url:`` would make every
    unsourced note read as sourced-but-unknown.
    """
    today = date.today().isoformat()
    lines = [
        "---",
        f"title: {yaml_scalar(title)}",
        f"type: {note_type}",
        f"status: {STATUS_VOCAB[note_type]['default']}",
    ]
    if maturity:
        lines.append(f"maturity: {maturity}")
    lines.append(f"owner: {yaml_scalar(owner)}")
    if tags:
        lines.append(f"tags: {json.dumps([t.strip() for t in tags])}")
    if source_url:
        lines.append(f"source_url: {yaml_scalar(source_url)}")
    if source_type:
        lines.append(f"source_type: {yaml_scalar(source_type)}")
    lines += [f"created: {today}", f"updated: {today}", "schema_version: 1", "---"]
    body = body.strip()
    return "\n".join(lines) + f"\n\n# {title}\n" + (f"\n{body}\n" if body else "")


def resolve_target_dir(
    vault: Vault,
    note_type: str,
    *,
    project: str | None = None,
    fleet: str | None = None,
) -> Path:
    """Target directory for a note, with the containment + fleet guards the
    E1 review mandated. Raises ScopeError on refusal.

    Projects file flat (projects/<name>/ is one tier); TYPE_DIRS applies
    only inside shared trees.
    """
    if project:
        base = vault.root / "projects" / project
    elif fleet:
        if fleet not in vault.fleets:
            raise ScopeError(
                f"fleet not in vault: {fleet}\n  run: claudron fleet add {fleet}"
            )
        base = vault.fleets[fleet] / "shared" / TYPE_DIRS[note_type]
    else:
        base = vault.shared / TYPE_DIRS[note_type]

    if not is_within_root(base, vault.root):
        raise ScopeError(f"scope {(project or fleet)!r} escapes the vault root")
    return base.resolve()


def find_duplicate(
    entries: list[dict], title: str, body: str = ""
) -> tuple[str, str, str] | None:
    """Dedup against index entries: (path, status, matched-name) for a live
    note whose title/alias/slug OR body content collides; None when clear.

    Two signals, either sufficient: the title/alias/slug name set
    (:func:`claimed_names`), and a title-independent body fingerprint
    (:func:`content_fingerprint`) — so byte-identical content re-sent under
    a different or mangled title is caught, never silently twinned. An empty
    fingerprint (stub note, no body) yields no content signal and falls back
    to the name set.

    Detection is deliberately tier-blind (a cross-tier twin is exactly the
    W104 wikilink ambiguity dedup exists to prevent) and skips only
    DEDUP_EXEMPT notes — a *ratified* decision still attracts, it must
    never be silently twinned. Multi-tier matches return first-in-index;
    advisory only (if a later epic acts on the path, adopt the resolver's
    tier priority here).
    """
    wanted = title.lower()
    slug = slugify(title)
    fingerprint = content_fingerprint(body)
    for entry in entries:
        if entry.get("status", "") in DEDUP_EXEMPT:
            continue
        name_hit = wanted in claimed_names(entry) or entry.get("filename", "") == slug
        content_hit = bool(fingerprint) and entry.get("content_hash") == fingerprint
        if name_hit or content_hit:
            matched = entry.get("title") or entry.get("filename", "")
            return entry["path"], str(entry.get("status", "")), str(matched)
    return None


def _free_slug(base: Path, slug: str) -> Path:
    """First free `slug[-N].md` in *base* (SCHEMA.md collision suffixes)."""
    target = base / f"{slug}.md"
    n = 2
    while target.exists():
        target = base / f"{slug}-{n}.md"
        n += 1
    return target


def _tier_label(project: str | None, fleet: str | None) -> str:
    if project:
        return f"project:{project}"
    if fleet:
        return f"fleet:{fleet}"
    return "shared"


def capture(
    vault: Vault,
    *,
    note_type: str,
    title: str,
    body: str,
    owner: str,
    tags: list[str] | None = None,
    project: str | None = None,
    fleet: str | None = None,
    force: bool = False,
    source_url: str | None = None,
    source_type: str | None = None,
) -> WriteResult:
    """The guarded write path. Validate → dedup (routes) → write → index.

    Always returns a WriteResult (action == "rejected" carries the
    validation Findings; nothing written). Raises ScopeError for scope
    refusals (see resolve_target_dir).

    Provenance rides as frontmatter, not as a body line. ``source_url`` is
    carried, not yet *matched on*: making it a third dedup signal alongside
    the name set and the content fingerprint is #55's step, and a half-built
    signal that dedups sometimes is worse than one that never claims to.
    """
    if note_type not in TYPES:
        # Guard before any type-keyed access — validate_note owns the E002
        # message but runs after composition, which would KeyError first.
        return _rejected(
            validate_note(
                {"title": title, "type": note_type, "created": "1970-01-01"},
                body,
                strict=True,
                path=f"{slugify(title)}.md",
            )
        )

    target_dir = resolve_target_dir(vault, note_type, project=project, fleet=fleet)

    text = compose_note(
        note_type=note_type, title=title, owner=owner, body=body,
        tags=tags, maturity=MATURITY_VALUES[0],
        source_url=source_url, source_type=source_type,
    )
    fm, note_body, err = parse_note(text)
    findings = validate_note(
        fm, note_body, strict=True, path=f"{slugify(title)}.md",
        raw=text, parse_error=err,
    )
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        return _rejected(errors)

    # One lock over dedup→write→index: two concurrent writers must not both
    # pass dedup against the same base index and then clobber each other's
    # append (last-writer-wins drops a note from the index — invisible to
    # lookup and dedup). Readers stay lockless; atomic writes protect them.
    with vault_write_lock(vault):
        index = ensure_index(vault)

        if not force:
            dup = find_duplicate(index.get("entries", []), title, note_body)
            if dup is not None:
                dup_path, dup_status, matched = dup
                action = "suggest_supersede" if dup_status == "stale" else "suggest_update"
                hint = (
                    "it is stale — supersede it (superseded_by) with a fresh note"
                    if action == "suggest_supersede"
                    else "append there (capture --update) instead of duplicating"
                )
                return WriteResult(
                    action=action,
                    path=dup_path,
                    reason=f"'{matched}' already covers this ({dup_path}, status: {dup_status}) — {hint}",
                )

        target = _free_slug(target_dir, slugify(title))
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, text)

        # Maintain the index: append the entry, write index.json last so its
        # mtime ≥ the note's — the next write loads instead of rebuilding.
        index["entries"].append(
            index_entry(fm, note_body, target, _tier_label(project, fleet), vault.root)
        )
        write_index(vault, index)

    return WriteResult(
        action="created",
        path=str(target),
        reason="strict-validated, no live duplicate" + (" (forced)" if force else ""),
    )


def append_addendum(vault: Vault, note_path: Path, body: str) -> WriteResult:
    """Append a dated addendum section and bump `updated` — line-level
    edits only, the note's own formatting is preserved.

    Self-guards containment (any door may call this directly) and
    re-validates the result at the *lenient* tier — updates target
    existing, possibly adopted/legacy notes, which strict would wrongly
    block. A corrupting addendum is reported, and reverted, not silently
    "updated"."""
    if not is_within_root(note_path, vault.root):
        raise ScopeError(f"path {str(note_path)!r} escapes the vault root")
    note_path = note_path.resolve()

    rel = str(note_path.relative_to(vault.root))
    today = date.today().isoformat()

    # One lock over read→write→index (same critical section as capture): a
    # concurrent writer must not stale the index between our read and rewrite.
    with vault_write_lock(vault):
        # Fresh index BEFORE the write (writing first would stale it and force
        # a full rebuild — the pattern this module exists to avoid).
        index = ensure_index(vault)

        original = note_path.read_text()
        text = set_frontmatter_field(original, "updated", today)
        text = text.rstrip("\n") + f"\n\n## Addendum — {today}\n\n{body.strip()}\n"

        fm, note_body, err = parse_note(text)
        findings = validate_note(
            fm, note_body, strict=False, path=rel, raw=text, parse_error=err
        )
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            return _rejected(errors)

        atomic_write_text(note_path, text)

        # Refresh the note's entry, write index.json last (mtime ≥ the note's).
        for entry in index.get("entries", []):
            if entry.get("path") == rel:
                entry["updated"] = today
                entry["content_hash"] = content_fingerprint(note_body)
                break
        write_index(vault, index)

    return WriteResult(
        action="updated",
        path=str(note_path),
        reason=f"addendum appended, updated bumped to {today}",
    )
