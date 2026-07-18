"""Tests for the retrieval eval harness (the G1/F2 instrument).

Uses the `reference_vault` fixture (a writable tmp copy) so a run's index write
never mutates the committed exemplar. The floors are sanity nets against a
`lookup` ranking regression, not a research bar — but they DO guard the metric
the harness exists for (paraphrase recall), not just the easy literal case.
"""

from __future__ import annotations

from pathlib import Path

from .eval_harness import format_report, load_seed, run_eval
from ..knowledge import lookup
from ..vault import detect

VALID_KINDS = {"literal", "paraphrase"}


def test_seed_is_well_formed(reference_vault: Path):
    """Seed integrity: required keys present, kind is known, no duplicate
    queries, and each `expects` is a real, reachable (non-hidden) note — the
    class of bug the first run caught (queries targeting a status:superseded
    note that lookup correctly hides)."""
    seed = load_seed()
    vault = detect(reference_vault)
    seen: set[tuple[str, str]] = set()
    for i, q in enumerate(seed["queries"]):
        assert {"kind", "query", "expects"} <= q.keys(), f"query {i} missing a key"
        assert q["kind"] in VALID_KINDS, f"query {i} has unknown kind {q['kind']!r}"
        pair = (q["query"], q["expects"])
        assert pair not in seen, f"duplicate seed query: {pair}"
        seen.add(pair)
        assert (reference_vault / q["expects"]).is_file(), \
            f"seed points at a missing note: {q['expects']}"
        # The target must be RETRIEVABLE AT ALL — probe by its own filename stem,
        # which any live note matches. A status:superseded / hidden note returns
        # for nothing, so this catches the seed error the first run hit. (Whether
        # a specific *query* retrieves it is measurement, not integrity — an
        # expected paraphrase miss must not fail here; it shows up in the floors.)
        stem = Path(q["expects"]).stem.replace("-", " ")
        got = [str(r.doc.source_path.relative_to(vault.root))
               for r in lookup(stem, vault, limit=10)]
        assert q["expects"] in got, \
            f"seed target not reachable (hidden/superseded?): {q['expects']}"


def test_recall_floors(reference_vault, capsys):
    """Record today's recall and guard a floor per kind so a ranking regression
    fails CI. Baseline (2026-07): overall ~95%, literal 100%, paraphrase 90%."""
    result = run_eval(detect(reference_vault))
    print("\n" + format_report(result))  # visible with -s / on failure
    assert result.total >= 15  # the seed didn't shrink to meaninglessness
    # literal (exact title/tag/body words) must ALL hit — a literal miss is a
    # ranking bug, not a retrieval limitation. At the current seed size this is a
    # zero-miss bar, stated explicitly rather than hidden behind a 0.9x float.
    assert result.kind_recall("literal") == 1.0
    # paraphrase is the metric this harness EXISTS to measure (the F2 trigger).
    # Floor it near baseline so a paraphrase-ranking collapse can't hide behind a
    # high literal score — the exact regression the tool is meant to expose.
    assert result.kind_recall("paraphrase") >= 0.80
    assert result.recall >= 0.85  # overall, near the 0.95 baseline


def test_runner_scores_a_known_hit_and_miss(reference_vault):
    """The runner itself: a query that must hit and one that must miss score
    right (guards the harness, independent of the seed)."""
    vault = detect(reference_vault)
    seed = {"k": 5, "queries": [
        {"kind": "literal", "query": "JWT validation gotchas",
         "expects": "_shared/knowledge/jwt-validation-gotchas.md"},
        {"kind": "literal", "query": "xyzzy nonexistent quux",
         "expects": "_shared/knowledge/jwt-validation-gotchas.md"},
    ]}
    result = run_eval(vault, seed)
    assert result.hits == 1 and result.total == 2
    assert result.misses[0]["query"] == "xyzzy nonexistent quux"
