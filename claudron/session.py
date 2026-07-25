"""Session loop: recall — the session-start context brief (E2).

`recall` assembles what a Claude Code session should know before working:
the vault's always-loaded CONVENTIONS layer, the current project's own
notes (context by membership), and shared/fleet notes relevant to the
project or query (context by relevance, behind an abstention threshold —
a weak match injects nothing rather than something).

stdout discipline matters more here than anywhere: the brief is injected
into agent context verbatim by the SessionStart hook.
"""

from __future__ import annotations

from pathlib import Path

from .knowledge import KnowledgeDoc, lookup, walk_knowledge_tier
from .schema import count_tokens, has_conflict_markers, parse_note
from .vault import Vault

# Whole-brief hard cap (count_tokens proxy, same as
# schema.CONVENTIONS_BUDGET — which caps just the conventions component at
# ≤120 soft / ≤160 hard; this caps the whole brief). Conventions first, then project notes,
# then shared matches until the budget is spent — the brief competes with
# real work for context, so it degrades by dropping notes, never growing.
BRIEF_TOKEN_BUDGET = 900

# In-context discovery (boundary spec §10.5.2). Parking MCP gave up
# in-context tool announcement; for any host running the engine's hooks the
# recall brief *is* that channel — it already injects vault context every
# session, so one line closes the loop. Front-end-neutral by design: it
# names the engine's own doors, not any consumer's verbs.
BRIEF_DISCOVERY_HINT = (
    "query more: `claudron lookup <terms>` · capture: `claudron capture --stdin`"
)

# The abstention floor: a shared/fleet match below this injects nothing
# (02-session-loop.md deliverable 1). Session policy, deliberately NOT
# knowledge.TIER_A_THRESHOLD — that is a tier-escalation trigger that
# retires with E4's ranking rework; this is a product relevance floor E4
# must re-calibrate consciously against its new score scale. At today's
# scale it excludes filename-only (30) and body-only (20) matches.
RECALL_ABSTENTION_FLOOR = 50

_SUMMARY_CHARS = 140


def derive_project(cwd: Path | None = None) -> str:
    """Project name for recall scoping: the git-repo directory name when
    inside a repo (walk up for .git), else the cwd's own name."""
    start = (cwd or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate.name
    return start.name


def _summary(body: str) -> str:
    """First substantive body line, truncated — the one-line summary the
    brief shows per note."""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:_SUMMARY_CHARS]
    return ""


def _entry(doc: KnowledgeDoc, vault: Vault, score: int | None = None) -> dict:
    """Recall entry from an already-parsed doc — one read per note, total.

    Stable key set for --json consumers: `maturity` is "" when unrated;
    `score` is None for project-tier notes (membership, not relevance —
    the null is the signal, kept explicit rather than by key absence)."""
    return {
        "title": doc.title,
        "path": str(doc.source_path.relative_to(vault.root)),
        "tier": doc.tier,
        "type": doc.note_type,
        "status": doc.status,
        "maturity": doc.maturity,
        "updated": doc.updated,
        "summary": _summary(doc.body),
        "score": score,
    }


def recall(
    vault: Vault,
    *,
    project: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> dict:
    """Assemble the recall data: conventions + project notes + relevant
    shared notes. Pure data; rendering/budgeting lives in render_brief.

    Contract: with ``project=None`` and ``query=None`` the note sections are
    empty (only conventions can appear). recall() itself never pulls —
    session-boundary callers need hooks.session_start_brief, which owns the
    pull-before-recall ordering the acceptance test depends on.
    """
    conventions = None
    conv_path = vault.shared / "CONVENTIONS.md"
    if conv_path.is_file():
        text = conv_path.read_text()
        # Quarantine applies here too: CONVENTIONS.md bypasses the tier
        # walker (injected, not retrieved), so the parse-time guard never
        # sees it — without this check a conflicted CONVENTIONS.md would
        # inject raw markers into every session brief.
        if has_conflict_markers(text):
            conventions = None
        else:
            fm, body, _ = parse_note(text)
            conventions = (body if fm is not None else text).strip() or None

    notes: list[dict] = []
    seen: set[str] = set()

    # Project tier: membership, not relevance — most recently updated first.
    if project and project in vault.projects:
        docs = walk_knowledge_tier(vault.projects[project], f"project:{project}")
        entries = sorted(
            (_entry(doc, vault) for doc in docs),
            key=lambda e: e["updated"],
            reverse=True,
        )
        for entry in entries[:limit]:
            notes.append(entry)
            seen.add(entry["path"])

    # Shared/fleet tiers: relevance with abstention — weak matches stay out.
    # The implicit default (bare project name) stays index-only: a full-text
    # scan on every SessionStart would be O(vault) work the abstention floor
    # mostly discards. An explicit --query buys the full search.
    terms = query or project
    if terms:
        shared_added = 0
        # Overfetch: the floor and project-dedup drop some candidates.
        for result in lookup(
            terms, vault, limit=limit * 2, tier_b=query is not None
        ):
            if result.score < RECALL_ABSTENTION_FLOOR:
                continue
            entry = _entry(result.doc, vault, score=result.score)
            if entry["path"] in seen:
                continue
            notes.append(entry)
            seen.add(entry["path"])
            shared_added += 1
            if shared_added >= limit:  # --limit is per tier
                break

    return {
        "project": project,
        "query": query,
        "conventions": conventions,
        "notes": notes,
    }


def render_brief(data: dict) -> str:
    """Render recall data as the injectable markdown brief, enforcing the
    whole-brief token budget (drop notes, never truncate mid-thought).

    Presentation transforms live here, not in recall(): --json consumers
    get the authentic data (incl. the conventions body's own H1)."""
    sections: list[str] = []
    spent = 0

    if data["conventions"]:
        body = data["conventions"]
        # Drop a leading H1 — this renderer supplies the section header.
        lines = body.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join(lines[1:]).strip()
        if body:
            block = f"## Vault conventions\n\n{body}"
            sections.append(block)
            spent += count_tokens(block)

    header = "## Recalled context" + (
        f" — {data['project']}" if data["project"] else ""
    )
    spent += count_tokens(header)

    def _fit(reserve_hint: bool) -> list[str]:
        """Notes that fit, optionally holding back room for the hint."""
        budget = spent + (count_tokens(BRIEF_DISCOVERY_HINT) if reserve_hint else 0)
        kept = []
        for note in data["notes"]:
            qualifier = note["type"] or "note"
            if note["maturity"]:
                qualifier += f", {note['maturity']}"
            line = (
                f"- **{note['title']}** ({qualifier}) — "
                f"{note['summary']} `{note['path']}`"
            )
            cost = count_tokens(line)
            if budget + cost > BRIEF_TOKEN_BUDGET:
                break
            kept.append(line)
            budget += cost
        return kept

    # Reserve the hint's cost up front rather than appending it afterwards: a
    # saturated brief is exactly the session where the agent most needs to know
    # it can ask for more, and append-and-drop silences the channel on
    # precisely those. But the reservation must never cost a *whole* section —
    # if holding room for the hint leaves no note at all, the notes win and the
    # hint is dropped. Recalled context is the payload; the hint is the pointer.
    lines = _fit(reserve_hint=True)
    with_hint = bool(lines)
    if not lines:
        lines = _fit(reserve_hint=False)

    if lines:
        parts = [header, "\n".join(lines)]
        if with_hint:
            parts.append(BRIEF_DISCOVERY_HINT)
        sections.append("\n\n".join(parts))

    return "\n\n".join(sections)
