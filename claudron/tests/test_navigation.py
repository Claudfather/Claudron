"""#155: `INDEX.md` as a derived navigation file.

THE PROPERTY THIS FILE EXISTS FOR is not that generation works — it is that
generation NEVER SILENTLY DELETES. Existing INDEX.md files carry hand-written
entries and hand-written descriptions in a vault whose entire purpose is
durable knowledge, so an entry the index does not know about must have a
decided fate, enforced here rather than described in a comment.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from claudron.knowledge import build_index, index_entry
from claudron.navigation import (HEADER, NAVIGATION_ENGINE_VERSION,
                                 PRESERVED_HEADING, classify_existing,
                                 render_navigation, write_navigation)


def _note(d: Path, stem: str, *, description="", owner="", tags=("x",),
          status="current", updated="2026-07-01") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    fm = [f"title: {stem.replace('-', ' ').title()}", "type: knowledge",
          f"status: {status}", f"owner: {owner or 't'}",
          "created: 2026-07-01", f"updated: {updated}",
          "tags: [" + ", ".join(tags) + "]"]
    if description:
        fm.append(f"description: {description}")
    p = d / f"{stem}.md"
    p.write_text("---\n" + "\n".join(fm) + "\n---\n\n# " + stem + "\n\nbody\n")
    return p


class TestTheIndexLearnedTheFieldsFirst:
    """Order is the issue's own requirement: generating before the index can
    hold a description means generating from a source without the data."""

    def test_index_entry_carries_description_and_owner(self, tmp_path):
        p = _note(tmp_path, "a-note", description="what it is for", owner="ravi")
        from claudron.vault import parse_frontmatter
        fm, body = parse_frontmatter(p.read_text())
        e = index_entry(fm, body, p, "shared", tmp_path)
        assert e["description"] == "what it is for"
        assert e["owner"] == "ravi"

    def test_a_missing_description_is_empty_not_absent(self, tmp_path):
        """A consumer reading `e["description"]` must not have to guard the
        key — absent and empty are the same fact here and only one shape."""
        p = _note(tmp_path, "b-note")
        from claudron.vault import parse_frontmatter
        fm, body = parse_frontmatter(p.read_text())
        e = index_entry(fm, body, p, "shared", tmp_path)
        assert e["description"] == ""


class TestAnEntryTheIndexDoesNotKnowIsNEVERSilentlyDropped:
    """THE BLOCKER. A generator that drops what it does not know about is a
    silent deletion, and this vault is the worst place for one."""

    def test_a_live_target_not_in_the_index_is_PRESERVED(self, tmp_path):
        (tmp_path / "README.md").write_text("# readme\n")
        keep, drop = classify_existing(
            "- [Readme](README.md) — hand written, matters\n",
            tmp_path, known_targets=set())
        assert drop == []
        assert keep == ["- [Readme](README.md) — hand written, matters"], (
            "a hand-written entry pointing at a file that EXISTS was discarded "
            "— that text is knowledge somebody wrote and nothing else holds it")

    def test_a_DANGLING_target_is_dropped_and_REPORTED(self, tmp_path):
        keep, drop = classify_existing(
            "- [Gone](vanished.md) — was a note once\n",
            tmp_path, known_targets=set())
        assert keep == []
        assert drop == ["[Gone](vanished.md)"], (
            "a dangling entry must be reported by name, not merely removed")

    def test_an_entry_the_index_HAS_is_regenerated_not_preserved(self, tmp_path):
        """The other half: without this, 'preserve everything' passes the two
        tests above and the file never actually becomes derived."""
        (tmp_path / "known.md").write_text("x")
        keep, drop = classify_existing(
            "- [Known](known.md) — STALE TEXT\n", tmp_path,
            known_targets={"known.md"})
        assert keep == [] and drop == []

    def test_the_preserved_section_is_MARKED_in_the_rendered_file(self, tmp_path):
        """A preserved line rendered indistinguishably from a derived one would
        read as generated and quietly become untrustworthy."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "real-note")
        (d / "README.md").write_text("# hand\n")
        vault = _vault(tmp_path)
        idx = build_index(vault)
        text, preserved, dropped = render_navigation(
            vault, d, idx, existing_text="- [Hand](README.md) — mine\n")
        assert preserved and PRESERVED_HEADING in text
        assert "- [Hand](README.md) — mine" in text


class TestItIsDerivedAndDeterministic:
    def test_two_hand_edited_variants_regenerate_to_IDENTICAL_bytes(self, tmp_path):
        """The acceptance criterion straight from the outage: the same entry
        carried different description text in different versions, so no
        line-based merge could resolve it. Both must converge on the
        frontmatter's."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "shared-note", description="the frontmatter's description")
        vault = _vault(tmp_path)
        idx = build_index(vault)
        a, _, _ = render_navigation(vault, d, idx,
                                    existing_text="- [Shared Note](shared-note.md) — OURS\n")
        b, _, _ = render_navigation(vault, d, idx,
                                    existing_text="- [Shared Note](shared-note.md) — THEIRS\n")
        assert a == b
        assert "the frontmatter's description" in a
        assert "OURS" not in a and "THEIRS" not in a

    def test_writing_twice_changes_nothing(self, tmp_path):
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1")
        vault = _vault(tmp_path)
        first = write_navigation(vault)
        assert first.written, "nothing was written on the first pass"
        before = (d / "INDEX.md").read_text()
        second = write_navigation(vault)
        assert second.written == [], "a second run rewrote files"
        assert (d / "INDEX.md").read_text() == before

    def test_the_header_is_on_every_generated_file(self, tmp_path):
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1")
        write_navigation(_vault(tmp_path))
        assert (d / "INDEX.md").read_text().startswith(HEADER)


class TestItStatesItsBounds:
    """#1742, estate-wide now."""

    def test_the_bound_names_source_skips_and_the_unresolved(self, tmp_path):
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1")
        (d / "README.md").write_text("x")
        (d / "INDEX.md").write_text("- [Keep](README.md) — mine\n"
                                    "- [Gone](nope.md) — dangling\n")
        r = write_navigation(_vault(tmp_path))
        text = " ".join(r.bound_lines())
        assert "GENERATED FROM" in text and "the index" in text
        assert "PRESERVED" in text and "DROPPED" in text
        assert "README.md" in text, "a preserved entry is not named in the bound"
        assert "nope.md" in text, "a dropped entry is not named in the bound"

    def test_the_bound_says_so_when_NOTHING_was_unaccounted_for(self, tmp_path):
        """Silence is ambiguous exactly when there is nothing to report."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1")
        r = write_navigation(_vault(tmp_path))
        assert "nothing in any file was unaccounted for" in " ".join(r.bound_lines())

    def test_an_UNREADABLE_existing_file_is_skipped_not_treated_as_empty(
            self, tmp_path, monkeypatch):
        """Unreadable is not empty: reading it as empty would discard every
        hand-written entry, which is the harm the preserve ruling prevents."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1")
        (d / "INDEX.md").write_text("- [Keep](README.md) — mine\n")
        real = Path.read_text

        def boom(self, *a, **k):
            if self.name == "INDEX.md":
                raise OSError("nope")
            return real(self, *a, **k)

        monkeypatch.setattr(Path, "read_text", boom)
        r = write_navigation(_vault(tmp_path))
        assert r.skipped, "an unreadable INDEX.md was not reported as skipped"
        assert "unreadable" in " ".join(r.skipped.values())


class TestTheEngineVersionIsAnInterface:
    def test_it_is_declared_and_non_empty(self):
        """Claudlobby #1723 gates on this; it is the interface another repo is
        waiting on, not a nicety."""
        assert NAVIGATION_ENGINE_VERSION and NAVIGATION_ENGINE_VERSION.strip()

    def test_a_result_carries_the_version_so_a_consumer_need_not_import_it(
            self, tmp_path):
        _note(tmp_path / "_shared" / "knowledge", "n1")
        r = write_navigation(_vault(tmp_path))
        assert r.engine_version == NAVIGATION_ENGINE_VERSION


def _vault(root: Path):
    """Through the shipped detector, never a hand-built dataclass — a private
    construction would diverge from what production hands the door."""
    from claudron.vault import detect, init
    if not (root / ".claudron").exists() and not (root / "_shared").exists():
        init(root, adopt=True)
    (root / "_shared").mkdir(parents=True, exist_ok=True)
    return detect(root)
