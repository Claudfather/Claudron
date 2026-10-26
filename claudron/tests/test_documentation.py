"""The repo's own `documentation/` tree stays valid (#235).

CI ran neither check before. #232 found 19 strict findings here that sat unnoticed
until someone ran the validator by hand, and archived plans still marked live —
which no validator mode flags, because `draft` and `active` are valid plan statuses.
"""

from __future__ import annotations

from claudron.schema import STATUS_VOCAB, parse_note, validate_path
from claudron.vault import iter_markdown_files

from .doc_parity import REPO_ROOT

DOCS = REPO_ROOT / "documentation"


def test_documentation_is_strict_clean():
    findings = validate_path(DOCS, strict=True)
    assert [f"{f.code} {f.path}: {f.message}" for f in findings] == []


def test_archived_docs_carry_a_terminal_status():
    """`archive/` holds finished plans (the documentation standard), so a live
    status there is a plan nobody closed."""
    live = []
    for md in iter_markdown_files(DOCS / "archive"):
        fm = parse_note(md.read_text())[0] or {}
        vocab = STATUS_VOCAB.get(fm.get("type"), {})
        status = fm.get("status", vocab.get("default"))
        if status not in vocab.get("terminal", ()):
            live.append(f"{md.relative_to(DOCS)}: {fm.get('type')}/{status}")
    assert live == []
