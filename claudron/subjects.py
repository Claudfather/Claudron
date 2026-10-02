"""Subjects and resolve: the read pipes harvest places facts with (#200 §4).

A **subject** is a note other facts can be filed under. There is no stored
registry — a subject exists because its note exists — so ``subjects`` derives
the list from the index, and ``resolve`` ranks the candidates for a name.
Choosing among them is the caller's judgment; this module never picks one,
writes nothing, and runs no model.

Both are keyed on today's note ``type`` and on each note's actual ``##``
sections, so they keep working when SCHEMA.md's memory homes (#200 §2) land:
a home becomes one more filter, not a different shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .knowledge import W_ALIAS_EXACT, W_TITLE_EXACT, _score_index_entry, ensure_index
from .schema import LOOKUP_EXCLUDED, _as_str_list, slugify, trust_class
from .vault import Vault

#: A name whose slug is the note's slug (``api-guide`` ↔ ``API Guide``): under an
#: exact alias, over a title substring. Exact matches — title, alias, slug, in
#: that order — outrank every fuzzy one, whose summed score can reach the same
#: cap: an exact title must never lose to a note that merely shares its words.
W_SLUG = 85


@dataclass
class Subject:
    """One subject, as ``subjects`` lists it and ``resolve`` ranks it."""

    title: str
    path: str
    type: str
    aliases: list[str]
    sections: list[str]
    tags: list[str]
    maturity: str
    trust: str
    updated: str
    source_type: str = ""
    tier: str = ""  #: as the index records it: ``shared``, ``project:<name>``, ``fleet:<name>``, ``system:…``, ``other:…``
    score: int | None = None
    match_type: str | None = None
    #: ``resolve`` only: the note *is* one of the names (exact title, alias or slug), not a fuzzy hit.
    #: ``match_type`` can't say so: a fuzzy title hit is labelled ``title`` too.
    exact: bool | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _subject(entry: dict, score: int | None = None, match_type: str | None = None,
             exact: bool | None = None) -> Subject:
    tags = _as_str_list(entry.get("tags"))
    return Subject(
        title=entry.get("title", ""), path=entry.get("path", ""), type=entry.get("type", ""),
        aliases=_as_str_list(entry.get("aliases")), sections=list(entry.get("sections") or []), tags=tags,
        maturity=entry.get("maturity", ""), trust=trust_class(entry.get("maturity", ""), entry.get("source_type", "")),
        updated=entry.get("updated", ""), source_type=entry.get("source_type", ""),
        tier=entry.get("tier", ""), score=score,
        match_type=match_type, exact=exact,
    )


def _live(entries: list[dict], note_type: str | None, project: str | None = None) -> list[dict]:
    """Index entries a fact could still be filed under: not archived or superseded, of the type
    and (with ``project``) in the project tier asked."""
    return [e for e in entries if e.get("status") not in LOOKUP_EXCLUDED
            and (note_type is None or e.get("type") == note_type)
            and (project is None or e.get("tier") == f"project:{project}")]


def subjects(vault: Vault, *, note_type: str | None = None, project: str | None = None) -> list[Subject]:
    """Every live subject (optionally of one ``type``), by title.

    Drafts are included and labelled by ``trust``: a harvested fact must find
    the draft a previous run wrote, or it would file a twin beside it.
    """
    entries = _live(ensure_index(vault).get("entries", []), note_type, project)
    return sorted((_subject(e) for e in entries), key=lambda s: (s.title.lower(), s.path))


def resolve(vault: Vault, name: str, *, note_type: str | None = None, aliases: list[str] | None = None,
            context: str | None = None, limit: int = 5, project: str | None = None) -> list[Subject]:
    """The top ``limit`` candidate subjects for ``name``, best first.

    Each candidate takes its best match across ``name`` and ``aliases``. An exact
    title, alias or slug match (in that order) outranks any fuzzy one; below
    them, the index's title, tag and filename scoring orders the rest.
    ``context`` (a sentence about the subject) only breaks ties among notes that
    already matched by name; it never brings in a note on its own, so a long
    context can't drag in everything that mentions a common word.
    """
    names = [(n.strip(), n.strip().lower(), slugify(n)) for n in [name, *(aliases or [])] if n and n.strip()]
    found = []
    for entry in _live(ensure_index(vault).get("entries", []), note_type, project):
        title = str(entry.get("title", "")).lower()
        entry_aliases = {a.lower() for a in _as_str_list(entry.get("aliases"))}
        rank, score, kind = max((_match(n, entry, title, entry_aliases) for n in names), default=(0, 0, "none"))
        if score:
            found.append(((-rank, -score, -_context_overlap(context, entry), title),
                          _subject(entry, score, kind, exact=rank > 0)))
    found.sort(key=lambda f: f[0])
    return [subject for _, subject in found[:limit]]


def _match(name: tuple[str, str, str], entry: dict, title: str, aliases: set[str]) -> tuple[int, int, str]:
    """``(exactness rank, score, match_type)`` of one ``(name, lowered, slug)`` against one note."""
    raw, lowered, slug = name
    if lowered == title:
        return 3, W_TITLE_EXACT, "title"
    if lowered in aliases:
        return 2, W_ALIAS_EXACT, "alias"
    if slug == entry.get("slug"):
        return 1, W_SLUG, "slug"
    score, kind = _score_index_entry(raw, entry)
    return 0, score, kind


def _context_overlap(context: str | None, entry: dict) -> int:
    """How many of the context's words appear in the note's title, tags or sections (a tiebreak only)."""
    if not context:
        return 0
    haystack = " ".join([entry.get("title", ""), *_as_str_list(entry.get("tags")),
                         *(entry.get("sections") or [])]).lower()
    return sum(1 for word in set(context.lower().split()) if len(word) > 3 and word in haystack)
