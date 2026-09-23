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
from claudron.navigation import (HEADER, PRESERVED_HEADING, _META_LABELS,
                                 _fmt_entry, classify_existing,
                                 existing_descriptions, render_navigation,
                                 write_navigation)


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
        r = render_navigation(
            vault, d, idx, existing_text="- [Hand](README.md) — mine\n")
        assert r.preserved and PRESERVED_HEADING in r.text
        assert "- [Hand](README.md) — mine" in r.text


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
        a = render_navigation(
            vault, d, idx,
            existing_text="- [Shared Note](shared-note.md) — OURS\n").text
        b = render_navigation(
            vault, d, idx,
            existing_text="- [Shared Note](shared-note.md) — THEIRS\n").text
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


class TestTheRenderAndTheParserRoundTrip:
    """`_fmt_entry` writes the line and `existing_descriptions` reads it back.
    They are a PAIR, and nothing else pins them together — when they drifted,
    the clause stopped being stripped, was read back as the description, and a
    fresh one was appended on every run (unbounded growth, measured on a real
    vault). This is the property that makes that drift a test failure rather
    than a defect found in production."""

    @pytest.mark.parametrize("desc", [
        "plain prose",
        "prose ending in an aside (like this)",
        "an em-dash — inside the description",
        "parens (nested (twice)) mid-sentence",
        "a colon: and a (status: lookalike) in the prose",
        "trailing punctuation.",
    ])
    def test_a_rendered_description_reads_back_identically(self, desc):
        e = {"title": "T", "path": "d/n1.md", "filename": "n1",
             "description": desc, "status": "current", "owner": "someone",
             "tags": ["a", "b"]}
        line = _fmt_entry(e, desc)
        assert existing_descriptions(line) == {"n1.md": desc}

    def test_it_round_trips_when_a_metadata_VALUE_contains_parens(self):
        """The real note that broke it carries
        `status: draft — lens input for ari's 3-lens synthesis (NO PR yet)`."""
        e = {"title": "T", "path": "d/n1.md", "filename": "n1",
             "description": "real prose", "status": "draft (NO PR yet)",
             "owner": "alex", "tags": ["x"]}
        assert existing_descriptions(_fmt_entry(e, "real prose")) == {"n1.md": "real prose"}

    def test_every_rendered_label_is_strippable(self):
        """The structural half: `_META_TAIL_RE` is built from `_META_LABELS`, so
        a field added to the renderer cannot be one the parser fails to strip.
        Asserted rather than assumed, because the coupling is the whole guard."""
        for label in _META_LABELS:
            e = {"title": "T", "path": "d/n1.md", "filename": "n1", label: "v"}
            assert existing_descriptions(_fmt_entry(e, "prose")) == {"n1.md": "prose"}, (
                f"a line carrying only `{label}` did not round-trip")


class TestTheDoorNeverReachesPastTheNoteTiers:
    """This door is a WRITER; it must not reach further than the indexer that
    feeds it. `vault.note_tiers` is that shared scope, and its docstring names a
    bare `root.rglob` as the bug it exists to prevent — a fleet's
    `library/`/`voices/`/`runtime/` are Claudlobby overlay content, not notes.

    Neither the unit suite nor a dry run against a copied vault could see this:
    the copy excluded `runtime/`, which is exactly where it manifests."""

    def _fleet_with_overlays(self, root: Path) -> Path:
        fleet = root / "myfleet"
        (fleet / "shared" / "knowledge").mkdir(parents=True, exist_ok=True)
        (fleet / "fleet.yaml").write_text("name: myfleet\n")
        for overlay in ("library", "voices", "runtime"):
            d = fleet / overlay / "sub"
            d.mkdir(parents=True, exist_ok=True)
            (d / "INDEX.md").write_text(
                "# Index: sub\n\n- [Hand written](note.md) — human prose\n")
        proj = fleet / "runtime" / "bots" / "b1" / "projects" / "somerepo"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "INDEX.md").write_text(
            "# Index: somerepo\n\n- [Repo doc](doc.md) — real content\n")
        return fleet

    def test_overlay_and_runtime_index_files_are_never_written(self, tmp_path):
        """Measured before the fix: four files written, including a bot's
        checkout of an unrelated repo, each hand-written entry replaced by
        `_No indexed notes in this directory._` — no index entry can live
        there, so every entry is dangling by construction."""
        _note(tmp_path / "_shared" / "knowledge", "real")
        fleet = self._fleet_with_overlays(tmp_path)
        r = write_navigation(_vault(tmp_path))
        touched = [str(p.relative_to(tmp_path)) for p in r.written + r.unchanged]
        offenders = [t for t in touched
                     if {"library", "voices", "runtime"} & set(t.split("/"))]
        assert not offenders, f"wrote into overlay/runtime content: {offenders}"
        assert (fleet / "library" / "sub" / "INDEX.md").read_text().strip().endswith(
            "human prose"), "overlay INDEX.md was rewritten"
        assert (fleet / "runtime" / "bots" / "b1" / "projects" / "somerepo"
                / "INDEX.md").read_text().strip().endswith(
            "real content"), "a bot's repo checkout was rewritten"

    def test_a_stale_index_INSIDE_a_tier_is_still_swept(self, tmp_path):
        """The positive control. Scoping must not cost the second half of
        `_candidate_directories` its purpose: a directory whose notes were all
        deleted still carries a stale file full of dangling entries, and it is
        the emptiest files that most need visiting."""
        _note(tmp_path / "_shared" / "knowledge", "real")
        stale = tmp_path / "_shared" / "knowledge" / "emptied"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "INDEX.md").write_text(
            "# Index: emptied\n\n- [Gone](gone.md) — dangling\n")
        r = write_navigation(_vault(tmp_path))
        swept = [str(p) for p in r.written + r.unchanged]
        assert any("emptied" in s for s in swept), "stale in-tier file not swept"
        assert any("emptied" in k for k in r.dropped), "dangling entry not reported"


class TestADescriptionIsNotSilentlyDeleted:
    """The ruling one level down. The entry-level rule protects an entry the
    index does not know about; it does NOT protect the DESCRIPTION of an entry
    the index does know about, and the index only carries one when the note has
    `description:` frontmatter.

    Found by running the door against a copy of this estate's real vault, not by
    a fixture: of 476 entries across 22 hand-maintained `INDEX.md` files, 457
    carried a hand-written description and 235 would have been deleted -- while
    the run reported `nothing in any file was unaccounted for`."""

    def _existing(self, d: Path, target: str, desc: str, title="T"):
        d.mkdir(parents=True, exist_ok=True)
        (d / "INDEX.md").write_text(
            f"# Index: {d.name}\n\n- [{title}]({target}) — {desc} "
            "(status: current, owner: someone, tags: x)\n")

    def test_a_hand_written_description_survives_when_the_note_has_none(
            self, tmp_path):
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="")          # no frontmatter description
        self._existing(d, "n1.md", "hand-written prose nobody can regenerate")
        r = write_navigation(_vault(tmp_path))
        text = (d / "INDEX.md").read_text()
        assert "hand-written prose nobody can regenerate" in text, (
            "a description the note does not carry was DELETED -- the silent "
            "deletion this class exists to prevent")
        assert r.carried, "the carry was not reported"

    def test_the_notes_own_description_wins_over_the_files(self, tmp_path):
        """The note is the source of truth WHEN IT HAS ONE -- that disagreement
        is the conflict class #155 removes, so carrying must not resurrect it."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="the frontmatter's own words")
        self._existing(d, "n1.md", "stale text from the old file")
        r = write_navigation(_vault(tmp_path))
        text = (d / "INDEX.md").read_text()
        assert "the frontmatter's own words" in text
        assert "stale text from the old file" not in text
        assert not r.carried, "nothing should be carried when the note has one"

    def test_carrying_is_idempotent(self, tmp_path):
        """A carried description is rendered back into the file, so the next run
        reads it again. If that did not hold, every run would rewrite."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="")
        self._existing(d, "n1.md", "kept prose")
        v = _vault(tmp_path)
        write_navigation(v)
        first = (d / "INDEX.md").read_text()
        r2 = write_navigation(v)
        assert (d / "INDEX.md").read_text() == first
        assert not r2.written, "second run rewrote a file it should have left alone"

    def test_a_description_ending_in_parentheses_is_not_truncated(self, tmp_path):
        """`_META_TAIL_RE` must anchor on a KNOWN LABEL, not on any trailing
        `(...)`, or a description that ends in parentheses loses its tail.

        THE FIXTURE HAS NO `(status: …)` CLAUSE, deliberately. With one present a
        label-blind regex still strips only the LAST group -- the metadata --
        and the mutant survives; the discriminating state is a description whose
        parenthesis IS the final group. Measured: the first version of this test
        carried the metadata tail and a `\\([^()]*\\)$` mutant passed it."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="")
        d.mkdir(parents=True, exist_ok=True)
        (d / "INDEX.md").write_text(
            "# Index: knowledge\n\n- [T](n1.md) — prose ending in an aside "
            "(like this)\n")
        write_navigation(_vault(tmp_path))
        assert "prose ending in an aside (like this)" in (d / "INDEX.md").read_text()

    def test_a_metadata_value_containing_parentheses_does_not_grow_the_line(
            self, tmp_path):
        """REGRESSION, found on a real vault and not reachable from a tidy
        fixture. A frontmatter VALUE may contain parentheses -- a real note here
        carries `status: draft — lens input (NO PR yet)`. If the metadata-tail
        pattern cannot cross that inner `)`, the clause is never stripped, the
        whole of it is read back as the description, and a fresh clause is
        appended on every run: the line grows without bound. Before the fix one
        file was rewritten on every pass, five copies and counting."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="", status="draft (NO PR yet)")
        d.mkdir(parents=True, exist_ok=True)
        (d / "INDEX.md").write_text(
            "# Index: knowledge\n\n- [T](n1.md) — real prose "
            "(status: draft (NO PR yet), owner: alex, tags: x)\n")
        v = _vault(tmp_path)
        write_navigation(v)
        first = (d / "INDEX.md").read_text()
        write_navigation(v)
        second = (d / "INDEX.md").read_text()
        assert second == first, "the line grew on a second run"
        assert first.count("status:") == 1, (
            f"metadata clause duplicated: {first.count('status:')} copies")

    def test_the_bound_names_the_carry(self, tmp_path):
        """Reported, never silent -- the defect was that the bound said
        `nothing in any file was unaccounted for` while prose was destroyed."""
        d = tmp_path / "_shared" / "knowledge"
        _note(d, "n1", description="")
        self._existing(d, "n1.md", "kept prose")
        r = write_navigation(_vault(tmp_path))
        bound = " ".join(r.bound_lines())
        assert "CARRIED" in bound
        assert "nothing in any file was unaccounted for" not in bound


class TestTheConsumerContractIsTheDeclaredCapability:
    """Claudlobby #1723 detects this door by NAME -- `"navigation" in
    status --json -> data.capabilities` -- and by nothing else.

    NOT by an engine-version floor: `engine_version` is `X.Y.Z.devN` on a build
    of the branch that ships a feature and the PREVIOUS release otherwise, and
    PEP 440 sorts a dev release before its release, so the `>= 0.5.0` an earlier
    draft of the CHANGELOG invited is satisfied by neither and can never pass.
    NOT by the `index --navigation --help` probe #1723's body proposes, which
    cannot fail. Register rule R5: capability is declared, never inferred."""

    def test_the_engine_declares_the_navigation_capability(self):
        """THE GATE. Removing the door must remove the name, or a consumer is
        told a door is there when it is not."""
        from claudron import CAPABILITIES
        assert "navigation" in CAPABILITIES

    def test_status_json_carries_the_declaration(self, tmp_path, capsys):
        """The declaration has to reach the consumer through the envelope it
        already parses -- a constant no door exposes gates nothing."""
        import json
        from claudron.cli import main
        _note(tmp_path / "_shared" / "knowledge", "n1")
        _vault(tmp_path)
        assert main(["--vault", str(tmp_path), "status", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)["data"]
        assert "navigation" in data["capabilities"], data.get("capabilities")

    def test_the_version_is_not_the_gate(self, tmp_path, capsys):
        """Pinned because an earlier draft of the CHANGELOG said it was, and a
        consumer wrote `>= 0.5.0` against a value that never reaches it. The
        version is still REPORTED -- it is identity and health -- it is just not
        what anyone gates on."""
        import json
        from claudron.cli import main
        _note(tmp_path / "_shared" / "knowledge", "n1")
        _vault(tmp_path)
        assert main(["--vault", str(tmp_path), "status", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)["data"]
        assert data["engine_version"]            # reported...
        assert "capabilities" in data            # ...but this is the gate

    def test_index_advertises_the_navigation_flag(self, capsys):
        """The capability the CHANGELOG's version declaration promises.

        Asserted against the HELP TEXT, not against an exit code: a
        `--navigation --help` invocation exits 0 whether or not the flag exists
        (the test below), so an rc assertion here would pass on an engine with
        no door -- and did, until a mutation that deleted the flag outright left
        every test in this file green. The help text is what actually
        discriminates; it is how claudron 0.4.0 was measured to lack the door."""
        from claudron.cli import main
        with pytest.raises(SystemExit):
            main(["index", "--help"])
        assert "--navigation" in capsys.readouterr().out

    def test_a_help_probe_cannot_detect_whether_the_flag_exists(self):
        """THE REFUTATION, pinned so nobody wires this into a compat floor.

        argparse fires `--help` as a parse action and exits 0 BEFORE it reports
        unknown arguments, so `--help` returns 0 for a flag that does not exist
        -- the probe passes on every engine ever shipped. Measured against
        claudron 0.4.0, which has no navigation door (`index --help` contains no
        "navigation") and still exits 0 for `index --navigation --help`."""
        from claudron.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["index", "--definitely-not-a-real-flag", "--help"])
        assert exc.value.code == 0, (
            "argparse no longer short-circuits on --help; #1723's help probe "
            "may have become viable -- re-measure before relying on it")

    def test_the_control_the_same_unknown_flag_without_help_is_rejected(self):
        """The control that attributes the failure. argparse DOES reject the
        unknown flag; it is `--help` short-circuiting that destroys the probe,
        not a permissive parser. Without this arm the test above is equally
        explained by "claudron accepts anything", which would be a different
        and much worse defect."""
        from claudron.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["index", "--definitely-not-a-real-flag"])
        assert exc.value.code == 2


def _vault(root: Path):
    """Through the shipped detector, never a hand-built dataclass — a private
    construction would diverge from what production hands the door."""
    from claudron.vault import detect, init
    if not (root / ".claudron").exists() and not (root / "_shared").exists():
        init(root, adopt=True)
    (root / "_shared").mkdir(parents=True, exist_ok=True)
    return detect(root)
