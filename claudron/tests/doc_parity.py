"""Readers for the normative tables and sections in owned documents.

Plain importable helpers — no pytest magic, so `conftest.py` stays what it was:
fixtures, auto-injected by name.

Parity gates live wherever the artifact they pin is tested (`SCHEMA.md`'s in
test_schema.py, `CLI_CONTRACT.md`'s in test_cli.py), but they all read markdown
the same way. One reader for all of them: a second copy of this parser would be
the exact drift the tables it reads exist to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def doc_table(doc: str, marker: str) -> list[list[str]]:
    """Rows of the markdown table following ``<!-- doc-parity: MARKER -->``.

    *doc* is repo-root-relative. Returns data rows only (header dropped,
    separator skipped), each as a list of stripped cells.
    """
    text = (REPO_ROOT / doc).read_text()
    section_text = text.split(f"<!-- doc-parity: {marker} -->")[1]
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not set(cells[0]) <= {"-", " "}:  # skip separator row
                rows.append(cells)
        elif rows:
            break
    return rows[1:]  # drop header


def section(doc: str, header: str) -> str:
    """Body of the ``## <header>`` section, up to the next ``## `` heading.

    Anchored on purpose. A plain ``split("## " + header)`` matches a ``###``
    subsection, a prose mention, or a mere prefix (``"Env"`` inside
    ``"Environment"``) and silently returns the wrong body — a parity gate
    reading the wrong section passes vacuously, which is worse than no gate.
    Raises on zero or multiple matches rather than guessing.
    """
    text = (REPO_ROOT / doc).read_text()
    starts = [m.end() for m in re.finditer(rf"^## {re.escape(header)}\s*$", text, re.M)]
    if len(starts) != 1:
        raise AssertionError(
            f"{doc}: expected exactly one '## {header}' heading, found {len(starts)}"
        )
    body = text[starts[0] :]
    end = re.search(r"^## ", body, re.M)
    return body[: end.start()] if end else body


def fenced_block(doc: str, header: str) -> str:
    """The first fenced code block inside a ``## <header>`` section.

    Bounded at *both* ends. Anchoring only the start lets a section with no
    fence of its own silently return a *later* section's block — the gate then
    asserts against text from somewhere else entirely and passes vacuously,
    which is worse than no gate. Raises if the section has no fence rather
    than reaching past its end for one.

    The end bound tolerates a line-initial ``## `` *inside* the fence, which is
    why this does not simply call :func:`section`.
    """
    text = (REPO_ROOT / doc).read_text()
    starts = [m.end() for m in re.finditer(rf"^## {re.escape(header)}\s*$", text, re.M)]
    if len(starts) != 1:
        raise AssertionError(
            f"{doc}: expected exactly one '## {header}' heading, found {len(starts)}"
        )
    body = text[starts[0] :]
    parts = body.split("```")
    if len(parts) < 3:
        raise AssertionError(f"{doc}: '## {header}' contains no fenced block")
    # The fence must open before the section does — a heading appearing in the
    # prose *before* the first fence means the fence belongs to a later one.
    if re.search(r"^## ", parts[0], re.M):
        raise AssertionError(
            f"{doc}: '## {header}' has no fenced block of its own "
            "(the next fence belongs to a later section)"
        )
    return parts[1]


def code_values(cell: str) -> tuple[str, ...]:
    """Backticked value list from a table cell -> tuple of values."""
    return tuple(re.findall(r"`([^`]+)`", cell))
