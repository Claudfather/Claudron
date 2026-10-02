"""Section-targeted writes: the fact-level door harvest files into (#200 §4).

Four operations on an existing note, each through the same lock → validate →
index → commit path as ``capture --update``:

- ``append_fact``: add a fact to section S, with an evidence ref.
- ``add_evidence``: add another ref to a fact already there (recurrence counts).
- ``add_alias``: add a name the note answers to.
- ``supersede_fact``: replace a fact, moving the old one to ``## History``.

A fact is one bullet carrying a stable id, with its evidence nested under it::

    ## Behavior & gotchas

    - The deploy freezes on Fridays. <!-- fact:3f2a91c0d4e1 -->
      - evidence: session:abc:3 · 2026-10-02 · asserted by user

The id is a hash of the fact's normalized text, so the same fact written twice
is the same fact. **Idempotent:** a fact whose id and evidence ref are already
there is a no-op (``unchanged``); the same fact with a new ref adds that ref.
The HTML comment is invisible when the note renders. Nothing here runs a model
or decides placement: the caller names the note and the section.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .engine import ScopeError, _commit_or_record, yaml_scalar
from .knowledge import ensure_index, index_entry, write_index
from .locking import atomic_write_text, vault_write_lock
from .schema import Finding, _as_str_list, parse_note, set_frontmatter_field, validate_note
from .vault import Vault, is_within_root

OPS = ("append_fact", "add_evidence", "add_alias", "supersede_fact")
HISTORY = "History"

_FACT_RE = re.compile(r"^- (?P<text>.*?) <!-- fact:(?P<id>[0-9a-f]{12}) -->$")
_EVIDENCE_RE = re.compile(r"^  - evidence: (?P<ref>[^·]+?)(?: · .*)?$")
_SECTION_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$")


class AmendError(ValueError):
    """A malformed request (unknown op, missing field, a fact or section that isn't there)."""


@dataclass
class AmendResult:
    """One amend's outcome. ``action`` is ``updated``, ``unchanged`` (an idempotent replay;
    nothing written) or ``rejected`` (validation; nothing written); ``outcome`` says which
    change: ``fact_added``, ``evidence_added``, ``alias_added`` or ``fact_superseded``."""

    action: str
    op: str
    path: str
    outcome: str = ""
    fact_id: str = ""
    reason: str = ""
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)

    @property
    def written(self) -> bool:
        return self.action == "updated"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["errors"] = [f.to_dict() for f in self.errors]
        data["warnings"] = [f.to_dict() for f in self.warnings]
        data["written"] = self.written
        return data


@dataclass
class Evidence:
    ref: str
    date: str = ""
    asserted_by: str = ""

    def line(self) -> str:
        bits = [self.ref, self.date or date.today().isoformat()]
        if self.asserted_by:
            bits.append(f"asserted by {self.asserted_by}")
        return "  - evidence: " + " · ".join(bits)


def fact_id(text: str) -> str:
    """The stable id of a fact: its text, case- and whitespace-folded, hashed."""
    return hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()[:12]


def _one_line(value: object, what: str, *, forbid: tuple[str, ...] = ("<!--", "-->")) -> str:
    """``value`` as one line of text; refuses an empty one and any marker the fact format reads."""
    text = " ".join(str(value or "").split())
    if not text:
        raise AmendError(f"{what} is required")
    if bad := [m for m in forbid if m in text]:
        raise AmendError(f"{what} may not contain {' or '.join(repr(m) for m in bad)}")
    return text


def _split(text: str) -> tuple[str, str]:
    """The note's frontmatter (both fences and the newline after) and its body, exactly as on disk."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 3)
        if end != -1:
            return text[:end + 5], text[end + 5:]
    return "", text


def _evidence(raw: object) -> Evidence:
    if not isinstance(raw, dict):
        raise AmendError("evidence must be an object: {ref, date?, asserted_by?}")
    return Evidence(_one_line(raw.get("ref"), "evidence ref", forbid=("<!--", "-->", "·")),
                    _one_line(raw.get("date") or date.today().isoformat(), "evidence date"),
                    " ".join(str(raw.get("asserted_by") or "").split()))


# --- the body as sections of lines ----------------------------------------------------------------

def _spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """``{section: (heading line, end)}`` for each ``##`` section, fences respected; the first of a repeated name."""
    spans, fenced, current = {}, False, None
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        m = None if fenced else _SECTION_RE.match(line)
        if m:
            if current:
                spans.setdefault(current[0], (current[1], i))
            current = (m.group(1), i)
    if current:
        spans.setdefault(current[0], (current[1], len(lines)))
    return spans


def _facts(lines: list[str], start: int, end: int) -> dict[str, tuple[int, int]]:
    """``{fact id: (bullet line, end of its evidence lines)}`` within ``lines[start:end]``."""
    out = {}
    i = start
    while i < end:
        m = _FACT_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < end and _EVIDENCE_RE.match(lines[j]):
            j += 1
        out[m.group("id")] = (i, j)
        i = j
    return out


def _find_fact(lines: list[str], wanted: str) -> tuple[int, int] | None:
    """A fact by id anywhere but ``## History`` (a superseded fact is not a live one)."""
    for name, (head, end) in _spans(lines).items():
        if name != HISTORY and wanted in (facts := _facts(lines, head + 1, end)):
            return facts[wanted]
    return None


def _refs(lines: list[str], span: tuple[int, int]) -> set[str]:
    return {m.group("ref").strip() for line in lines[span[0] + 1:span[1]] if (m := _EVIDENCE_RE.match(line))}


def _ensure_section(lines: list[str], name: str) -> tuple[int, int]:
    """The section's span, creating it at the end (before ``## History``) when the note has none."""
    spans = _spans(lines)
    if name in spans:
        return spans[name]
    at = spans[HISTORY][0] if HISTORY in spans and name != HISTORY else len(lines)
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    lines[at:at] = ["", f"## {name}", ""]
    return _spans(lines)[name]


def _insert_at(lines: list[str], span: tuple[int, int]) -> int:
    """Where a new bullet goes in a section: after its last non-blank line."""
    at = span[1]
    while at > span[0] + 1 and not lines[at - 1].strip():
        at -= 1
    return at


# --- the operations -------------------------------------------------------------------------------

def _append_fact(lines: list[str], req: dict) -> str:
    section = _one_line(req.get("section"), "section")
    if section == HISTORY:
        raise AmendError(f"'{HISTORY}' holds superseded facts; append a fact to another section")
    text, ev = _one_line(req.get("fact"), "fact"), _evidence(req.get("evidence"))
    fid = fact_id(text)
    found = _find_fact(lines, fid)
    if found:
        if ev.ref in _refs(lines, found):
            return "unchanged"
        lines.insert(found[1], ev.line())
        return "evidence_added"
    span = _ensure_section(lines, section)
    at = _insert_at(lines, span)
    lines[at:at] = [f"- {text} <!-- fact:{fid} -->", ev.line()]
    return "fact_added"


def _add_evidence(lines: list[str], req: dict) -> str:
    fid, ev = _one_line(req.get("fact_id"), "fact_id"), _evidence(req.get("evidence"))
    found = _find_fact(lines, fid)
    if not found:
        raise AmendError(f"no live fact {fid} in this note")
    if ev.ref in _refs(lines, found):
        return "unchanged"
    lines.insert(found[1], ev.line())
    return "evidence_added"


def _supersede_fact(lines: list[str], req: dict) -> str:
    old = _one_line(req.get("fact_id"), "fact_id")
    text, ev = _one_line(req.get("fact"), "fact"), _evidence(req.get("evidence"))
    found = _find_fact(lines, old)
    if not found:
        raise AmendError(f"no live fact {old} in this note")
    new = fact_id(text)
    if new == old:
        raise AmendError("the new fact is the same fact; use add_evidence")
    section = next(name for name, (h, e) in _spans(lines).items() if h < found[0] < e)
    old_text = _FACT_RE.match(lines[found[0]]).group("text")
    del lines[found[0]:found[1]]
    if not _find_fact(lines, new):
        span = _spans(lines)[section]
        at = _insert_at(lines, span)
        lines[at:at] = [f"- {text} <!-- fact:{new} -->", ev.line()]
    history = _ensure_section(lines, HISTORY)
    at = _insert_at(lines, history)
    when = ev.date or date.today().isoformat()
    lines.insert(at, f"- {old_text} — superseded {when} by fact:{new} <!-- superseded:{old} -->")
    return "fact_superseded"


def _add_alias(text: str, fm: dict, req: dict) -> tuple[str, str]:
    alias = _one_line(req.get("alias"), "alias")
    current = _as_str_list(fm.get("aliases"))
    if alias.lower() in {a.lower() for a in current} or alias.lower() == str(fm.get("title", "")).lower():
        return text, "unchanged"
    return _set_list_field(text, "aliases", [*current, alias]), "alias_added"


def _set_list_field(text: str, field: str, values: list[str]) -> str:
    """Rewrite a top-level list field as a flow list, dropping a block list's item lines first."""
    lines = text.splitlines(keepends=True)
    out, skipping = [], False
    for i, line in enumerate(lines):
        if i and line.rstrip("\r\n") == "---":
            skipping = False
        if skipping and line[:1].isspace():
            continue
        skipping = line.split(":", 1)[0].strip() == field and line.rstrip().endswith(":")
        out.append(line)
    flow = "[" + ", ".join(yaml_scalar(v) for v in values) + "]"
    return set_frontmatter_field("".join(out), field, flow)


# --- the door -------------------------------------------------------------------------------------

def amend(vault: Vault, note_path: Path, request: dict, *, run_id: str | None = None,
          no_commit: bool = False) -> AmendResult:
    """Apply one operation to an existing note, under the vault write lock.

    Raises :class:`AmendError` for a malformed request and ``ScopeError`` for a
    path outside the vault; both write nothing. ``written`` is false for an
    ``unchanged`` replay.
    """
    op = request.get("op")
    if op not in OPS:
        raise AmendError(f"unknown op {op!r} (choose from {', '.join(OPS)})")
    if not is_within_root(note_path, vault.root):
        raise ScopeError(f"path {str(note_path)!r} escapes the vault root")
    if run_id:
        from .runs import check_run_id
        check_run_id(run_id)  # refused before anything is written
    note_path = note_path.resolve()
    if not note_path.is_file():
        raise AmendError(f"no such note: {note_path.relative_to(vault.root.resolve())}")
    rel = str(note_path.relative_to(vault.root.resolve()))

    with vault_write_lock(vault):
        index = ensure_index(vault)
        original = note_path.read_text()
        fm, _, err = parse_note(original)
        if fm is None:
            raise AmendError(f"{rel} has no readable frontmatter ({err})")
        if op == "add_alias":
            text, outcome = _add_alias(original, fm, request)
        else:
            head, body = _split(original)
            lines = body.split("\n")
            outcome = {"append_fact": _append_fact, "add_evidence": _add_evidence,
                       "supersede_fact": _supersede_fact}[op](lines, request)
            text = head + "\n".join(lines)
        fid = fact_id(request["fact"]) if op in ("append_fact", "supersede_fact") else str(request.get("fact_id", ""))
        if outcome == "unchanged":
            return AmendResult("unchanged", op, str(note_path), outcome, fid, "already there; nothing written")
        text = set_frontmatter_field(text, "updated", date.today().isoformat())

        fm, note_body, err = parse_note(text)
        errors = [f for f in validate_note(fm, note_body, strict=False, path=rel, raw=text, parse_error=err)
                  if f.severity == "error"]
        if errors:
            return AmendResult("rejected", op, str(note_path), "", fid, f"{len(errors)} validation error(s); "
                               "nothing written", errors=errors)
        atomic_write_text(note_path, text)

        for n, entry in enumerate(index.get("entries", [])):
            if entry.get("path") == rel:
                index["entries"][n] = index_entry(fm, note_body, note_path, entry.get("tier", "shared"),
                                                  vault.root)
                break
        write_index(vault, index)

        warnings = _commit_or_record(vault, note_path, run_id, no_commit, "amend", fm.get("title") or rel,
                                     str(fm.get("type") or "unknown"), "existing")

    return AmendResult("updated", op, str(note_path), outcome, fid, f"{op}: {outcome}", warnings=warnings)
