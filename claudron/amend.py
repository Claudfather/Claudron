"""Section-targeted writes: the fact-level door harvest files into (#200 §4).

Four operations on an existing note, each a transform over the shared edit
door (``engine.edit_note``: lock → transform → lenient validate → write →
index → commit, the same door ``capture --update`` uses):

- ``append_fact``: add a fact to section S, with an evidence ref.
- ``add_evidence``: add another ref to a fact already there (recurrence counts).
- ``add_alias``: add a name the note answers to.
- ``supersede_fact``: replace a fact, moving the old one to ``## History``.

The fact format is SCHEMA.md §Facts. In short, a fact is one bullet carrying
a stable id (a hash of its folded text), with its evidence nested under it,
so the same fact written twice is the same fact. **Idempotent:** a fact whose
id and evidence ref are already there writes nothing (``unchanged``); the
same fact with a new ref adds only that ref. Nothing here runs a model or
decides placement: the caller names the note and the section.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .engine import WriteResult, edit_note, yaml_scalar
from .knowledge import ensure_index, fenced_lines, section_headings
from .schema import _as_str_list, claimed_names, set_frontmatter_field
from .vault import Vault

OPS = ("append_fact", "add_evidence", "add_alias", "supersede_fact")
HISTORY = "History"

_FACT_RE = re.compile(r"^- (?P<text>.*?) <!-- fact:(?P<id>[0-9a-f]{12}) -->$")
_EVIDENCE_RE = re.compile(r"^  - evidence: (?P<ref>[^·]+?)(?: · .*)?$")


class AmendError(ValueError):
    """A malformed request (unknown op, missing field, a fact that isn't there, a taken alias)."""


@dataclass
class AmendResult(WriteResult):
    """A :class:`WriteResult` (``updated`` | ``unchanged`` | ``rejected``) plus which op ran,
    what it changed (``fact_added``, ``evidence_added``, ``alias_added``, ``fact_superseded``)
    and the fact it concerns."""

    op: str = ""
    outcome: str = ""
    fact_id: str = ""


@dataclass
class Evidence:
    ref: str
    date: str
    asserted_by: str

    def line(self) -> str:
        who = [f"asserted by {self.asserted_by}"] if self.asserted_by else []
        return "  - evidence: " + " · ".join([self.ref, self.date, *who])


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


def _evidence(raw: object) -> Evidence:
    if not isinstance(raw, dict):
        raise AmendError("evidence must be an object: {ref, date?, asserted_by?}")
    return Evidence(_one_line(raw.get("ref"), "evidence ref", forbid=("<!--", "-->", "·")),
                    _one_line(raw.get("date") or date.today().isoformat(), "evidence date"),
                    " ".join(str(raw.get("asserted_by") or "").split()))


# --- the body as sections of lines ----------------------------------------------------------------

def _split(text: str) -> tuple[str, str]:
    """The frontmatter (both fences and the newline after) and the body, exactly as read.

    ``read_text`` has already folded CRLF to ``\\n``, as for every door. A closing
    fence at the very end (a note with no body) leaves an empty body.
    """
    if text.startswith("---\n"):
        if (end := text.find("\n---\n", 3)) != -1:
            return text[:end + 5], text[end + 5:]
        if text.endswith("\n---"):
            return text + "\n", ""
    return "", text


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """``(name, heading line, end)`` for every ``##`` section, in order (a name may repeat)."""
    heads = section_headings(lines)
    return [(name, n, heads[k + 1][0] if k + 1 < len(heads) else len(lines)) for k, (n, name) in enumerate(heads)]


def _spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """``{section: (heading line, end)}``: where a write into a named section goes (its first occurrence)."""
    spans: dict[str, tuple[int, int]] = {}
    for name, n, end in _sections(lines):
        spans.setdefault(name, (n, end))
    return spans


def _facts(lines: list[str], start: int, end: int) -> dict[str, tuple[int, int]]:
    """``{fact id: (bullet line, end of its evidence lines)}`` within ``lines[start:end]``, outside code."""
    fenced = fenced_lines(lines)
    out, i = {}, start
    while i < end:
        m = None if i in fenced else _FACT_RE.match(lines[i])
        j = i + 1
        if m:
            while j < end and _EVIDENCE_RE.match(lines[j]):
                j += 1
            out[m.group("id")] = (i, j)
        i = j
    return out


def _find_fact(lines: list[str], wanted: str) -> tuple[str, tuple[int, int]] | None:
    """``(section, span)`` of a live fact — anywhere but ``## History``, which holds superseded ones."""
    for name, head, end in _sections(lines):
        if name != HISTORY and wanted in (facts := _facts(lines, head + 1, end)):
            return name, facts[wanted]
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


def _append(lines: list[str], span: tuple[int, int], new: list[str]) -> None:
    """Add lines to a section, after its last non-blank line."""
    at = span[1]
    while at > span[0] + 1 and not lines[at - 1].strip():
        at -= 1
    lines[at:at] = new


# --- the operations: each edits ``lines`` and returns (outcome, fact id) --------------------------

def _append_fact(lines: list[str], req: dict) -> tuple[str, str]:
    section = _one_line(req.get("section"), "section", forbid=("<!--", "-->", "#"))
    if section == HISTORY:
        raise AmendError(f"'{HISTORY}' holds superseded facts; append a fact to another section")
    text, ev = _one_line(req.get("fact"), "fact"), _evidence(req.get("evidence"))
    fid = fact_id(text)
    if found := _find_fact(lines, fid):
        if ev.ref in _refs(lines, found[1]):
            return "unchanged", fid
        lines.insert(found[1][1], ev.line())
        return "evidence_added", fid
    _append(lines, _ensure_section(lines, section), [f"- {text} <!-- fact:{fid} -->", ev.line()])
    return "fact_added", fid


def _add_evidence(lines: list[str], req: dict) -> tuple[str, str]:
    fid, ev = _one_line(req.get("fact_id"), "fact_id"), _evidence(req.get("evidence"))
    found = _find_fact(lines, fid)
    if not found:
        raise AmendError(f"no live fact {fid} in this note")
    if ev.ref in _refs(lines, found[1]):
        return "unchanged", fid
    lines.insert(found[1][1], ev.line())
    return "evidence_added", fid


def _supersede_fact(lines: list[str], req: dict) -> tuple[str, str]:
    old = _one_line(req.get("fact_id"), "fact_id")
    text, ev = _one_line(req.get("fact"), "fact"), _evidence(req.get("evidence"))
    found = _find_fact(lines, old)
    if not found:
        raise AmendError(f"no live fact {old} in this note")
    new = fact_id(text)
    if new == old:
        raise AmendError("the new fact is the same fact; use add_evidence")
    section, (start, end) = found
    old_text = _FACT_RE.match(lines[start]).group("text")
    old_evidence = lines[start + 1:end]
    del lines[start:end]
    if existing := _find_fact(lines, new):  # the replacement is already a fact: add this evidence to it
        if ev.ref not in _refs(lines, existing[1]):
            lines.insert(existing[1][1], ev.line())
    else:
        _append(lines, _spans(lines)[section], [f"- {text} <!-- fact:{new} -->", ev.line()])
    # The old fact keeps its provenance in History: the evidence that backed it moves with it.
    _append(lines, _ensure_section(lines, HISTORY),
            [f"- {old_text} — superseded {ev.date} by fact:{new} <!-- superseded:{old} -->", *old_evidence])
    return "fact_superseded", new


_BODY_OPS = {"append_fact": _append_fact, "add_evidence": _add_evidence, "supersede_fact": _supersede_fact}


def _set_list_field(text: str, key: str, values: list[str]) -> str:
    """Rewrite a top-level frontmatter list field as a flow list, dropping a block list's item lines first.

    Only the frontmatter is touched; a block list's items may be indented or not (``- a`` under ``key:``).
    """
    head, body = _split(text)
    lines = head.splitlines(keepends=True)
    out, skipping = [], False
    for line in lines:
        if skipping and (line[:1].isspace() or line.startswith("- ")) and line.rstrip("\n") != "---":
            continue
        skipping = not line[:1].isspace() and line.split(":", 1)[0] == key and line.rstrip().endswith(":")
        out.append(line)
    flow = "[" + ", ".join(yaml_scalar(v) for v in values) + "]"
    return set_frontmatter_field("".join(out), key, flow) + body


# --- the door -------------------------------------------------------------------------------------

def amend(vault: Vault, note_path: Path, request: dict, *, run_id: str | None = None,
          no_commit: bool = False) -> AmendResult:
    """Apply one operation to an existing note through ``engine.edit_note``.

    Raises :class:`AmendError` for a malformed request (and ``ScopeError`` for a
    path outside the vault, ``RunError`` for a bad run id); none writes anything.
    """
    op = request.get("op")
    if op not in OPS:
        raise AmendError(f"unknown op {op!r} (choose from {', '.join(OPS)})")
    if not note_path.is_file():
        raise AmendError(f"no such note: {note_path}")
    done: dict[str, str] = {}

    if op == "add_alias":
        alias = _one_line(request.get("alias"), "alias")
        _refuse_taken(vault, note_path, alias)

        def transform(text: str, fm: dict) -> str | None:
            if alias.lower() in {n.lower() for n in claimed_names(fm)}:
                return None
            done["outcome"] = "alias_added"
            return _set_list_field(text, "aliases", [*_as_str_list(fm.get("aliases")), alias])
    else:
        def transform(text: str, fm: dict) -> str | None:
            head, body = _split(text)
            lines = body.split("\n")
            done["outcome"], done["fact_id"] = _BODY_OPS[op](lines, request)
            return None if done["outcome"] == "unchanged" else head + "\n".join(lines)

    result = edit_note(vault, note_path, transform, verb="amend", run_id=run_id, no_commit=no_commit)
    return AmendResult(action=result.action, path=result.path, reason=result.reason, errors=result.errors,
                       warnings=result.warnings, op=op, outcome=done.get("outcome", "") if result.written else "",
                       fact_id=done.get("fact_id", ""))


def _refuse_taken(vault: Vault, note_path: Path, alias: str) -> None:
    """An alias another note already answers to would make the name ambiguous (W104); refuse it."""
    rel = str(note_path.resolve().relative_to(vault.root.resolve()))
    for entry in ensure_index(vault).get("entries", []):
        if entry.get("path") != rel and alias.lower() in claimed_names(entry):
            raise AmendError(f"alias {alias!r} is already a name of {entry.get('path')}")
