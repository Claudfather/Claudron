"""The write engine: compose, validate, dedup, write — one path in.

The shared seam named in the roadmap (cycle-1): `claudron capture` (CLI),
`claudron new` (its composer), and E3's MCP `claudron_write` all go through
this module, so N writers get one validate/dedup implementation. Nothing
writes a note into a vault except through here.

Dedup **routes, never hard-rejects**: a near-duplicate becomes a
``suggest_update``/``suggest_supersede`` result returned to the caller —
a silent-drop gate would also drop the contradicting updates curation
exists to catch (roadmap E3 contract).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

from .knowledge import build_index, load_index
from .schema import (
    STATUS_VOCAB,
    TYPE_DIRS,
    Finding,
    parse_note,
    slugify,
    validate_note,
)
from .vault import Vault

# Dedup ignores notes whose activity is done — a superseded/archived note
# doesn't attract new captures (its topic moved on; the fresh note is the
# successor). A *stale* match suggests supersession instead of update.
_DEDUP_TERMINAL = frozenset({"superseded", "archived", "completed", "ratified"})


class ScopeError(Exception):
    """A write refused before composition: unregistered fleet, or a scope
    that escapes the vault root. Not a schema Finding — the CLI maps it to
    a usage error (exit 2), the MCP layer to its error payload."""


@dataclass
class WriteResult:
    """The engine's uniform outcome — E3's MCP write returns it verbatim."""

    action: str  # created | updated | suggest_update | suggest_supersede
    path: str  # created/updated note, or the existing note for suggestions
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


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
) -> str:
    """Assemble a schema-valid note. Hand-assembled rather than yaml.dump —
    pins key order, flow-style tags, unquoted ISO dates so the note stays
    human-shaped; yaml_scalar covers the escaping that trades away."""
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
    lines += [f"created: {today}", f"updated: {today}", "schema_version: 1", "---"]
    heading_body = body.strip() if body.strip() else ""
    content = f"\n\n# {title}\n" + (f"\n{heading_body}\n" if heading_body else "")
    return "\n".join(lines) + content


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

    base = base.resolve()
    if not base.is_relative_to(vault.root.resolve()):
        raise ScopeError(f"scope {(project or fleet)!r} escapes the vault root")
    return base


def find_duplicate(vault: Vault, title: str) -> tuple[str, str, str] | None:
    """Index-backed dedup: (path, status, matched-name) for a live note whose
    title/alias/slug collides with *title*; None when the field is clear.
    Terminal-status notes never attract dedup."""
    index = load_index(vault) or build_index(vault)
    wanted = title.lower()
    slug = slugify(title)
    for entry in index.get("entries", []):
        if entry.get("status", "") in _DEDUP_TERMINAL:
            continue
        names = [str(entry.get("title", "")).lower()] + [
            str(a).lower() for a in entry.get("aliases", [])
        ]
        if wanted in names or entry.get("filename", "") == slug:
            matched = entry.get("title", entry.get("filename", ""))
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
) -> WriteResult | list[Finding]:
    """The guarded write path. Validate → dedup (routes) → write.

    Returns a WriteResult, or the strict-tier Finding list when the
    composed note fails validation (nothing is written in that case).
    Raises ScopeError for scope refusals (see resolve_target_dir).
    """
    target_dir = resolve_target_dir(vault, note_type, project=project, fleet=fleet)

    text = compose_note(
        note_type=note_type, title=title, owner=owner, body=body,
        tags=tags, maturity="draft",
    )
    fm, note_body, err = parse_note(text)
    findings = validate_note(
        fm, note_body, strict=True, path=f"{slugify(title)}.md",
        raw=text, parse_error=err,
    )
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        return errors

    if not force:
        dup = find_duplicate(vault, title)
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
    target.write_text(text)
    return WriteResult(
        action="created",
        path=str(target),
        reason="strict-validated, no live duplicate" + (" (forced)" if force else ""),
    )


_UPDATED_LINE_RE = re.compile(r"^updated\s*:.*$", re.MULTILINE)


def append_addendum(vault: Vault, note_path: Path, body: str) -> WriteResult:
    """Append a dated addendum section and bump `updated` — line-level
    edits only, the note's own formatting is preserved."""
    text = note_path.read_text()
    today = date.today().isoformat()
    if _UPDATED_LINE_RE.search(text.split("---", 2)[1] if text.startswith("---") else ""):
        head, sep, rest = text.partition("---")
        fm_block, sep2, tail = rest.partition("---")
        fm_block = _UPDATED_LINE_RE.sub(f"updated: {today}", fm_block, count=1)
        text = head + sep + fm_block + sep2 + tail
    addendum = f"\n\n## Addendum — {today}\n\n{body.strip()}\n"
    note_path.write_text(text.rstrip("\n") + addendum)
    return WriteResult(
        action="updated",
        path=str(note_path),
        reason=f"addendum appended, updated bumped to {today}",
    )
