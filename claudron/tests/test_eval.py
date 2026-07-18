"""Tests for the retrieval eval harness (the G1/F2 instrument).

These do NOT gate a recall threshold — the seed is small and the reference vault
tiny, so a hard bar would be noise. They pin the harness's integrity (every
`expects` names a real, non-hidden note; the runner scores correctly) and record
today's numbers so a regression in `lookup` ranking shows up as a changed recall.
"""

from __future__ import annotations

from pathlib import Path

from claudron.eval import format_report, load_seed, run_eval
from claudron.knowledge import lookup
from claudron.vault import detect

REF_VAULT = Path(__file__).parent.parent.parent / "examples" / "reference-vault"


def test_every_expected_note_exists_and_is_retrievable(tmp_path):
    """Seed integrity: each `expects` is a real file AND is reachable by lookup
    (not superseded/hidden) — else the seed measures the wrong thing (the bug
    the first run caught: two queries targeted a status:superseded note)."""
    seed = load_seed()
    vault = detect(REF_VAULT.resolve())
    for q in seed["queries"]:
        note = REF_VAULT / q["expects"]
        assert note.is_file(), f"seed points at a missing note: {q['expects']}"
        # Reachable by SOME query — a note lookup can never return is untestable
        reachable = any(
            str(r.doc.source_path.relative_to(vault.root)) == q["expects"]
            for probe in (q["query"], note.stem.replace("-", " "))
            for r in lookup(probe, vault, limit=10)
        )
        assert reachable, f"seed expects an unreachable note: {q['expects']}"


def test_recall_is_recorded_and_reasonable(capsys):
    """Records today's heuristic recall (printed for the dogfood log) and guards
    a floor so a real ranking regression fails CI — not a tight bar, a sanity
    net. Current baseline (2026-07): ~95% overall, literal 100%, paraphrase 90%."""
    vault = detect(REF_VAULT.resolve())
    result = run_eval(vault)
    print("\n" + format_report(result))  # visible with -s / on failure
    assert result.total >= 15  # the seed didn't shrink to meaninglessness
    assert result.recall >= 0.75  # a floor: below this, ranking regressed
    assert result.kind_recall("literal") >= 0.90  # a literal title/tag miss = bug


def test_runner_scores_a_known_hit_and_miss(tmp_path):
    """The runner itself: a query that must hit and one that must miss score
    right (guards the harness, independent of the seed)."""
    vault = detect(REF_VAULT.resolve())
    seed = {"k": 5, "queries": [
        {"kind": "literal", "query": "JWT validation gotchas",
         "expects": "_shared/knowledge/jwt-validation-gotchas.md"},
        {"kind": "literal", "query": "xyzzy nonexistent quux",
         "expects": "_shared/knowledge/jwt-validation-gotchas.md"},
    ]}
    result = run_eval(vault, seed)
    assert result.hits == 1 and result.total == 2
    assert result.misses[0]["query"] == "xyzzy nonexistent quux"
