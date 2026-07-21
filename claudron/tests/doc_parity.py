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
    """Body of a ``## <header>`` section, up to the next ``## ``."""
    return (REPO_ROOT / doc).read_text().split(f"## {header}", 1)[1].split("\n## ", 1)[0]


def fenced_block(doc: str, header: str) -> str:
    """The first fenced code block inside a ``## <header>`` section."""
    return section(doc, header).split("```", 2)[1]


def code_values(cell: str) -> tuple[str, ...]:
    """Backticked value list from a table cell -> tuple of values."""
    return tuple(re.findall(r"`([^`]+)`", cell))
