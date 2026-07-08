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

from .knowledge import TIER_A_THRESHOLD, KnowledgeDoc, parse_doc, lookup
from .schema import parse_note
from .vault import Vault, iter_markdown_files

# Whole-brief hard cap (whitespace-token proxy, same convention as
# schema.CONVENTIONS_BUDGET — which caps just the conventions component at
# ≤160; this caps the whole brief). Conventions first, then project notes,
# then shared matches until the budget is spent — the brief competes with
# real work for context, so it degrades by dropping notes, never growing.
BRIEF_TOKEN_BUDGET = 900

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
    """Recall entry from an already-parsed doc — one read per note, total."""
    entry = {
        "title": doc.title,
        "path": str(doc.source_path.relative_to(vault.root)),
        "tier": doc.tier,
        "type": doc.note_type,
        "status": doc.status,
        "updated": doc.updated,
        "summary": _summary(doc.body),
    }
    if doc.maturity:
        entry["maturity"] = doc.maturity
    if score is not None:
        entry["score"] = score
    return entry


def recall(
    vault: Vault,
    *,
    project: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> dict:
    """Assemble the recall data: conventions + project notes + relevant
    shared notes. Pure data; rendering/budgeting lives in render_brief."""
    conventions = None
    conv_path = vault.shared / "CONVENTIONS.md"
    if conv_path.is_file():
        text = conv_path.read_text()
        fm, body, err = parse_note(text)
        raw = body if err is None and fm is not None else text
        # Drop a leading H1 — render_brief adds its own section header.
        lines = raw.strip().splitlines()
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        conventions = "\n".join(lines).strip() or None

    notes: list[dict] = []
    seen: set[str] = set()

    # Project tier: membership, not relevance — most recently updated first.
    if project and project in vault.projects:
        entries = [
            _entry(doc, vault)
            for md in iter_markdown_files(vault.projects[project])
            if (doc := parse_doc(md, f"project:{project}")) is not None
        ]
        entries.sort(key=lambda e: e["updated"], reverse=True)
        for entry in entries[:limit]:
            notes.append(entry)
            seen.add(entry["path"])

    # Shared/fleet tiers: relevance with abstention — weak matches stay out.
    terms = query or project
    if terms:
        shared_added = 0
        # Overfetch: the threshold and project-dedup drop some candidates.
        for result in lookup(terms, vault, limit=limit * 2):
            if result.score < TIER_A_THRESHOLD:
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
    whole-brief token budget (drop notes, never truncate mid-thought)."""
    sections: list[str] = []
    spent = 0

    def tokens(text: str) -> int:
        return len(text.split())

    if data["conventions"]:
        block = f"## Vault conventions\n\n{data['conventions']}"
        sections.append(block)
        spent += tokens(block)

    lines: list[str] = []
    header = "## Recalled context" + (
        f" — {data['project']}" if data["project"] else ""
    )
    spent += tokens(header)
    for note in data["notes"]:
        qualifier = note["type"] or "note"
        if note.get("maturity"):
            qualifier += f", {note['maturity']}"
        line = f"- **{note['title']}** ({qualifier}) — {note['summary']} `{note['path']}`"
        cost = tokens(line)
        if spent + cost > BRIEF_TOKEN_BUDGET:
            break
        lines.append(line)
        spent += cost

    if lines:
        sections.append(header + "\n\n" + "\n".join(lines))

    return "\n\n".join(sections)
