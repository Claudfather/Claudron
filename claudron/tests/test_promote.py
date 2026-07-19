"""Tests for maturity promotion (E5 PR1 — the curation half of the graph slice).

The trust ladder: draft → verified → canonical, stamped with provenance, ranked
by lookup, and metered by `claudron status`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.engine import ScopeError
from claudron.knowledge import ensure_index, lookup
from claudron.promote import promote
from claudron.schema import parse_note
from claudron.vault import detect, status


def _capture(vault_dir: Path, title: str, body: str | None = None) -> Path:
    # Body defaults to something title-derived + unique so content-dedup (#52,
    # byte-identical bodies collide) never swallows a second fixture note.
    main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
          "--title", title, "--body", body or f"notes about {title}",
          "--owner", "t"])
    slug = title.lower().replace(" ", "-")
    return next((vault_dir / "_shared" / "knowledge").glob(f"{slug}*.md"))


class TestPromoteEngine:
    def test_promote_stamps_maturity_and_provenance(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        result = promote(vault, note, to_maturity="verified", actor="chris")
        assert result.action == "promoted"
        assert (result.from_maturity, result.to_maturity) == ("draft", "verified")
        fm, _, _ = parse_note(note.read_text())
        assert fm["maturity"] == "verified"
        assert fm["promoted_by"] == "chris"
        assert fm["promoted_at"]  # dated

    def test_promote_is_idempotent(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        promote(vault, note, to_maturity="verified", actor="t")
        again = promote(vault, note, to_maturity="verified", actor="t")
        assert again.action == "unchanged"

    def test_demote_is_derived_not_a_separate_flag(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        promote(vault, note, to_maturity="canonical", actor="t")
        result = promote(vault, note, to_maturity="draft", actor="t")
        assert result.action == "demoted"  # direction derived from the ladder

    def test_any_jump_allowed(self, vault_dir: Path):
        """The human is the gate (v1): draft → canonical in one step, no stepwise
        adjacency enforcement."""
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        result = promote(vault, note, to_maturity="canonical", actor="t")
        assert result.action == "promoted" and result.to_maturity == "canonical"

    def test_bad_maturity_rejected(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        with pytest.raises(ValueError):
            promote(detect(vault_dir), note, to_maturity="gold", actor="t")

    def test_escape_guard(self, vault_dir: Path):
        vault = detect(vault_dir)
        with pytest.raises(ScopeError):
            promote(vault, vault_dir.parent / "outside.md",
                    to_maturity="verified", actor="t")

    def test_index_maturity_refreshed(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        promote(vault, note, to_maturity="canonical", actor="t")
        rel = str(note.relative_to(vault_dir))
        entry = next(e for e in ensure_index(vault)["entries"] if e["path"] == rel)
        assert entry["maturity"] == "canonical"  # refreshed without a full rebuild


class TestMaturityRanking:
    def test_canonical_outranks_draft_at_equal_score(self, vault_dir: Path):
        """Two notes matching a query equally — the canonical one ranks first
        (trust axis breaks the tie above tier)."""
        # Distinct bodies (dedup-safe) that both match "backoff" equally strongly.
        a = _capture(vault_dir, "Backoff Alpha", "retry backoff notes for alpha")
        b = _capture(vault_dir, "Backoff Beta", "retry backoff notes for beta")
        vault = detect(vault_dir)
        promote(vault, b, to_maturity="canonical", actor="t")  # b is canonical, a is draft
        results = lookup("backoff", detect(vault_dir), limit=5)
        top = [r.doc.source_path.name for r in results][:2]
        assert top[0] == "backoff-beta.md"  # canonical wins the tie


class TestStatusLifecycleMetric:
    def test_status_reports_maturity_breakdown(self, vault_dir: Path):
        _capture(vault_dir, "Draft Note")
        note = _capture(vault_dir, "Verified Note")
        vault = detect(vault_dir)
        promote(vault, note, to_maturity="verified", actor="t")
        info = status(detect(vault_dir))
        m = info["lifecycle"]["maturity"]
        assert m["verified"] == 1
        assert m["draft"] >= 1
        # promoted_pct = verified+canonical / rated
        assert info["lifecycle"]["promoted_pct"] > 0


class TestPromoteCLI:
    def test_cli_promote_json(self, vault_dir: Path, capsys):
        _capture(vault_dir, "Retry Rules")
        capsys.readouterr()
        rc = main(["--vault", str(vault_dir), "promote", "Retry Rules",
                   "--to", "verified", "--by", "chris", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "promote"
        assert env["data"]["action"] == "promoted"
        assert env["data"]["to"] == "verified" and env["data"]["promoted_by"] == "chris"
        assert env["data"]["written"] is True  # shared success-signal (mirrors WriteResult)

    def test_written_flag_false_when_nothing_changed(self, vault_dir: Path):
        note = _capture(vault_dir, "Retry Rules")
        vault = detect(vault_dir)
        promote(vault, note, to_maturity="verified", actor="t")
        assert promote(vault, note, to_maturity="verified", actor="t").written is False

    def test_cli_promote_resolves_by_title(self, vault_dir: Path, capsys):
        _capture(vault_dir, "Retry Rules")
        rc = main(["--vault", str(vault_dir), "promote", "Retry Rules", "--to", "canonical"])
        assert rc == 0
        assert "canonical" in capsys.readouterr().out

    def test_cli_promote_no_match(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "promote", "No Such Note", "--to", "verified"])
        assert rc == 1
        assert "no note matches" in capsys.readouterr().err
