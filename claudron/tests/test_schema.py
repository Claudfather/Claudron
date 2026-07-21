"""Tests for the schema module: fixture manifest, doc parity, parsing."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from .doc_parity import REPO_ROOT, code_values, doc_table, fenced_block
from claudron.schema import (
    CATALOG,
    LOOKUP_EXCLUDED,
    STALENESS_DONE,
    STATUS_VOCAB,
    TYPE_DIRS,
    Finding,
    parse_note,
    validate_note,
    validate_path,
)

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "expected.json").read_text())


def _run_fixture(record: dict, tier: str, tmp_path: Path) -> list[Finding]:
    """Execute one manifest record at the given tier, per its target type."""
    strict = tier == "strict"
    src = FIXTURES / record["path"]
    if record["target"] == "directory":
        return validate_path(src, strict=strict, vault_root=FIXTURES)
    if "as" in record:
        # Path-contextual rule: place the file at its vault-relative `as`
        # path inside a scratch vault, then validate at file scope.
        dest = tmp_path / "as-vault" / record["as"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return validate_path(dest, strict=strict, vault_root=tmp_path / "as-vault")
    return validate_path(src, strict=strict, vault_root=FIXTURES)


class TestFixtureManifest:
    """Every fixture produces exactly its documented code set, both tiers.

    This is the red-first gate PR1 staged: the manifest was committed
    before the validator existed.
    """

    @pytest.mark.parametrize(
        "record",
        MANIFEST["fixtures"],
        ids=[r["path"] for r in MANIFEST["fixtures"]],
    )
    @pytest.mark.parametrize("tier", ["lenient", "strict"])
    def test_expected_codes(self, record: dict, tier: str, tmp_path: Path):
        findings = _run_fixture(record, tier, tmp_path)
        got = sorted(f.code for f in findings)
        assert got == sorted(record["expect"][tier]), (
            f"{record['path']} [{tier}]: expected {record['expect'][tier]}, "
            f"got {[(f.code, f.message) for f in findings]}"
        )

    def test_full_finding_element(self, tmp_path: Path):
        """The one pinned full Finding — codes-as-API needs its machine
        carrier asserted, not just the code (devex blocker fold)."""
        pinned = next(r for r in MANIFEST["fixtures"] if "full_finding" in r)
        spec = pinned["full_finding"]
        findings = _run_fixture(pinned, spec["tier"], tmp_path)
        match = [f for f in findings if f.code == spec["finding"]["code"]]
        assert len(match) == 1
        assert match[0].to_dict() == spec["finding"]


class TestReferenceVault:
    """The shipped exemplar is strict-clean — zero findings, both tiers."""

    @pytest.mark.parametrize("strict", [False, True], ids=["lenient", "strict"])
    def test_reference_vault_clean(self, strict: bool):
        vault = REPO_ROOT / "examples" / "reference-vault"
        findings = validate_path(vault, strict=strict, vault_root=vault)
        assert findings == [], [(f.code, f.path, f.message) for f in findings]


def _doc_table(marker: str) -> list[list[str]]:
    """The doc-parity table following *marker* in SCHEMA.md."""
    return doc_table("SCHEMA.md", marker)


class TestDocParity:
    """SCHEMA.md's normative tables and schema.py cannot drift (devex
    major: the SSOT epic must not re-create doc-vs-code drift internally).
    Parity covers codes + tier behavior + status vocabularies, not prose.
    """

    def test_status_table_matches_vocab(self):
        rows = _doc_table("STATUS_TABLE")
        assert {r[0] for r in rows} == set(STATUS_VOCAB)
        for note_type, canonical, terminal, legacy in rows:
            vocab = STATUS_VOCAB[note_type]
            assert code_values(canonical) == vocab["canonical"], note_type
            assert code_values(terminal) == vocab["terminal"], note_type
            doc_aliases = set(re.findall(r"`(\w+)` →", legacy))
            assert doc_aliases == set(vocab["legacy"]), note_type

    def test_error_catalog_matches(self):
        rows = _doc_table("ERROR_CATALOG")
        assert {r[0] for r in rows} == set(CATALOG)
        for code, _condition, lenient, strict in rows:
            for tier, cell in (("lenient", lenient), ("strict", strict)):
                expected = CATALOG[code][tier]
                if cell.startswith("→"):
                    assert expected == f"→ {cell.split()[-1]}", (code, tier)
                elif cell.startswith("n/a"):
                    assert expected is None, (code, tier)
                else:
                    assert expected == cell.split()[0], (code, tier)

    def test_source_types_match_the_optional_field_row(self):
        """`SOURCE_TYPES` is SCHEMA.md's vocabulary, read rather than restated.

        The write door refuses values outside it (`capture --source-type`), so
        a widened doc row with a stale constant would reject a value the schema
        now defines — the drift is silent and only shows up as a usage error.
        The Optional-fields table carries no parity marker; this reads its one
        typed row directly.
        """
        from claudron.schema import SOURCE_TYPES

        from .doc_parity import section

        rows = [
            line for line in section("SCHEMA.md", "Frontmatter fields").splitlines()
            if line.startswith("| `source_type`")
        ]
        assert len(rows) == 1, "SCHEMA.md: expected one `source_type` row"
        documented = tuple(
            v.strip() for v in code_values(rows[0])[1].split(r"\|")
        )
        assert documented == SOURCE_TYPES

    def test_terminal_vs_lookup_split_documented(self):
        # The blocker fix, pinned both ways: ratified staleness-done but
        # never lookup-hidden.
        assert "ratified" in STALENESS_DONE
        assert "ratified" not in LOOKUP_EXCLUDED
        assert LOOKUP_EXCLUDED < STALENESS_DONE

    def test_vault_structure_tree_matches_schema_tiers(self):
        """SCHEMA.md's taxonomy tree and VAULT-STRUCTURE.md's directory tree
        cannot silently diverge: both must draw every note-tier dir schema.py's
        TYPE_DIRS defines. Closes the gap VAULT-STRUCTURE.md discloses (the two
        trees were previously unguarded — only the tables above were)."""
        tiers = {d.split("/", 1)[0] for d in TYPE_DIRS.values()}
        schema_tree = fenced_block("SCHEMA.md", "Vault directory taxonomy")
        vault_tree = fenced_block("VAULT-STRUCTURE.md", "Directory contract")
        for tier in tiers:
            # whole dir entry, not a loose substring: `x_runbooks/` must not
            # satisfy `runbooks/` (a lookbehind rejects a leading name char).
            pat = re.compile(rf"(?<![\w-]){re.escape(tier)}/")
            assert pat.search(schema_tree), f"{tier}/ absent from SCHEMA.md tree"
            assert pat.search(vault_tree), f"{tier}/ absent from VAULT-STRUCTURE.md tree"

    def test_schema_and_vault_structure_cross_reference(self):
        """The two SSOT docs must exist and point at each other — the human
        half of the F3 drift guard (tree-parity above is the machine half). A
        one-way or dangling pointer is the failure mode this catches."""
        vault_structure = REPO_ROOT / "VAULT-STRUCTURE.md"
        assert vault_structure.is_file(), "VAULT-STRUCTURE.md missing"
        assert "VAULT-STRUCTURE.md" in (REPO_ROOT / "SCHEMA.md").read_text()
        assert "SCHEMA.md" in vault_structure.read_text()


class TestConventionsTemplate:
    def test_shipped_template_fits_its_own_budget(self):
        """The init default must satisfy the budget it lives beside —
        SCHEMA.md would flag any vault it scaffolds otherwise."""
        from claudron.schema import (
            CONVENTIONS_BUDGET,
            CONVENTIONS_TEMPLATE,
            count_tokens,
        )

        assert count_tokens(CONVENTIONS_TEMPLATE) <= CONVENTIONS_BUDGET


class TestParseNote:
    def test_no_frontmatter_is_empty_not_error(self):
        fm, body, err = parse_note("Just prose.\n")
        assert fm == {} and err is None and body == "Just prose.\n"

    def test_broken_yaml_is_error_not_empty(self):
        fm, _, err = parse_note("---\ntags: [unclosed\n---\n\nbody\n")
        assert fm is None and err is not None

    def test_unclosed_fence_is_error(self):
        fm, _, err = parse_note("---\ntitle: X\n")
        assert fm is None and "never closed" in err

    def test_non_mapping_frontmatter_is_error(self):
        fm, _, err = parse_note("---\n- just\n- a list\n---\nbody\n")
        assert fm is None and err is not None


class TestDateEdges:
    """SCHEMA.md date semantics: date objects pass, ISO strings pass,
    everything else is a finding — and nothing crashes."""

    @pytest.mark.parametrize(
        "value,ok",
        [
            ("2026-07-07", True),
            ("2026-13-45", False),
            (20260707, False),
            ("July 7", False),
        ],
    )
    def test_created_variants(self, value, ok):
        fm = {"title": "T", "type": "knowledge", "status": "current",
              "owner": "x", "created": value, "updated": "2026-07-07"}
        findings = validate_note(fm, "", strict=True, path="t.md")
        codes = {f.code for f in findings}
        assert ("E005" in codes) is (not ok)

    def test_yaml_date_object_passes(self):
        import yaml
        fm = yaml.safe_load("created: 2026-07-07\nupdated: 2026-07-07")
        fm.update({"title": "T", "type": "knowledge", "status": "current", "owner": "x"})
        findings = validate_note(fm, "", strict=True, path="t.md")
        assert not [f for f in findings if f.code == "E005"]


class TestDocParityReaders:
    """The readers behind every parity gate. A reader that silently returns the
    wrong text makes its gate pass vacuously — worse than having no gate."""

    def test_fenced_block_never_reaches_into_a_later_section(self, tmp_path, monkeypatch):
        from claudron.tests import doc_parity

        monkeypatch.setattr(doc_parity, "REPO_ROOT", tmp_path)
        (tmp_path / "T.md").write_text(
            "## Directory contract\n\nProse only, no fence here.\n\n"
            "## Something else\n\n```\nWRONG-BLOCK\n```\n"
        )
        with pytest.raises(AssertionError, match="no fenced block of its own"):
            doc_parity.fenced_block("T.md", "Directory contract")

    def test_fenced_block_tolerates_a_heading_inside_the_fence(
        self, tmp_path, monkeypatch
    ):
        from claudron.tests import doc_parity

        monkeypatch.setattr(doc_parity, "REPO_ROOT", tmp_path)
        (tmp_path / "T.md").write_text(
            "## Directory contract\n\n```\nvault/\n## not-a-heading\n  runbooks/\n```\n"
            "\n## Next\n"
        )
        block = doc_parity.fenced_block("T.md", "Directory contract")
        assert "runbooks/" in block  # not truncated at the in-fence '## '

    def test_section_rejects_ambiguity(self, tmp_path, monkeypatch):
        from claudron.tests import doc_parity

        monkeypatch.setattr(doc_parity, "REPO_ROOT", tmp_path)
        (tmp_path / "D.md").write_text("## Flags\n\nstale\n\n## Flags\n\nreal\n")
        with pytest.raises(AssertionError, match="expected exactly one"):
            doc_parity.section("D.md", "Flags")
