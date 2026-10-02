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

from .knowledge import _score_index_entry, ensure_index
from .schema import LOOKUP_EXCLUDED, _as_str_list, slugify, trust_class
from .vault import Vault

#: Exact matches, strongest first, with the score each reports. They outrank every
#: fuzzy match, whose summed score can reach the same cap (an exact title must
#: never lose to a note that merely shares its words).
EXACT = (("title", 100), ("alias", 90), ("slug", 85))


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
    score: int | None = None
    match_type: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _subject(entry: dict, score: int | None = None, match_type: str | None = None) -> Subject:
    tags = _as_str_list(entry.get("tags"))
    return Subject(
        title=entry.get("title", ""), path=entry.get("path", ""), type=entry.get("type", ""),
        aliases=_as_str_list(entry.get("aliases")), sections=list(entry.get("sections") or []), tags=tags,
        maturity=entry.get("maturity", ""), trust=trust_class(entry.get("maturity", ""),
                                                              entry.get("source_type", ""), tags),
        updated=entry.get("updated", ""), score=score, match_type=match_type,
    )


def _live(entries: list[dict], note_type: str | None) -> list[dict]:
    """Index entries a fact could still be filed under: not archived or superseded, of the type asked."""
    return [e for e in entries if e.get("status") not in LOOKUP_EXCLUDED
            and (note_type is None or e.get("type") == note_type)]


def subjects(vault: Vault, *, note_type: str | None = None) -> list[Subject]:
    """Every live subject (optionally of one ``type``), by title.

    Drafts are included and labelled by ``trust``: a harvested fact must find
    the draft a previous run wrote, or it would file a twin beside it.
    """
    entries = _live(ensure_index(vault).get("entries", []), note_type)
    return sorted((_subject(e) for e in entries), key=lambda s: (s.title.lower(), s.path))


def resolve(vault: Vault, name: str, *, note_type: str | None = None, aliases: list[str] | None = None,
            context: str | None = None, limit: int = 5) -> list[Subject]:
    """The top ``limit`` candidate subjects for ``name``, best first.

    Each candidate takes its best match across ``name`` and ``aliases``. An exact
    title, alias or slug match (in that order) outranks any fuzzy one; below
    them, the index's title, tag and filename scoring orders the rest.
    ``context`` (a sentence about the subject) only breaks ties among notes that
    already matched by name; it never brings in a note on its own, so a long
    context can't drag in everything that mentions a common word.
    """
    names = [n.strip() for n in [name, *(aliases or [])] if n and n.strip()]
    found: list[tuple[tuple[int, int, int], Subject]] = []
    for entry in _live(ensure_index(vault).get("entries", []), note_type):
        best = max((_match(candidate, entry) for candidate in names), default=(0, 0, "none"))
        if best[1]:
            rank, score, kind = best
            found.append(((rank, score, _context_overlap(context, entry)), _subject(entry, score, kind)))
    found.sort(key=lambda f: (-f[0][0], -f[0][1], -f[0][2], f[1].title.lower()))
    return [subject for _, subject in found[:limit]]


def _match(candidate: str, entry: dict) -> tuple[int, int, str]:
    """``(exactness rank, score, match_type)`` of one name against one note."""
    lowered = candidate.lower()
    exact = {"title": lowered == str(entry.get("title", "")).lower(),
             "alias": lowered in {a.lower() for a in _as_str_list(entry.get("aliases"))},
             "slug": slugify(candidate) == entry.get("slug")}
    for rank, (kind, score) in zip(range(len(EXACT), 0, -1), EXACT):
        if exact[kind]:
            return rank, score, kind
    score, kind = _score_index_entry(candidate, entry)
    return 0, score, kind


def _context_overlap(context: str | None, entry: dict) -> int:
    """How many of the context's words appear in the note's title, tags or sections (a tiebreak only)."""
    if not context:
        return 0
    haystack = " ".join([entry.get("title", ""), *_as_str_list(entry.get("tags")),
                         *(entry.get("sections") or [])]).lower()
    return sum(1 for word in set(context.lower().split()) if len(word) > 3 and word in haystack)
