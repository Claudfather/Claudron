"""Tests for the vault directory-structure lens (P2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.structure import (
    _INFRA_SKIP,
    USER_RESERVED,
    StructureError,
    check_structure,
    fix_structure,
    is_fixable,
)
from claudron.vault import SKIP_DIRS, detect, init


def _codes(findings) -> list[str]:
    return [f.code for f in findings]


def _make_fleet(root: Path, name: str = "myfleet") -> Path:
    """A fleet dir with a fleet.yaml but no shared/ — so S1 fires. Returns it."""
    fleet = root / name
    fleet.mkdir()
    (fleet / "fleet.yaml").write_text(f"fleet: {{name: {name}}}")
    return fleet


class TestConforming:
    def test_minimal_vault_is_clean(self, vault_dir: Path):
        assert check_structure(detect(vault_dir)) == []

    def test_vault_with_fleet_is_clean(self, vault_with_fleet: Path):
        # The fixture fleet already has shared/ — no S1.
        assert check_structure(detect(vault_with_fleet)) == []

    def test_shared_no_underscore_is_clean(self, shared_vault: Path):
        assert check_structure(detect(shared_vault)) == []

    def test_reference_vault_is_clean(self, reference_vault: Path):
        """Golden: the shipped exemplar conforms to its own contract."""
        assert check_structure(detect(reference_vault)) == []

    def test_validate_exits_zero(self, vault_dir: Path, capsys):
        assert main(["--vault", str(vault_dir), "validate"]) == 0

    def test_reference_vault_validates_clean_via_cli(
        self, reference_vault: Path, capsys
    ):
        """The golden no-op through the CLI (not just check_structure): the
        shipped exemplar passes `validate` end-to-end, exit 0."""
        assert main(["--vault", str(reference_vault), "validate"]) == 0


class TestS1FleetMissingShared:
    def _vault_with_bare_fleet(self, vault_dir: Path) -> Path:
        _make_fleet(vault_dir)
        return vault_dir

    def test_s1_warns(self, vault_dir: Path):
        vault = detect(self._vault_with_bare_fleet(vault_dir))
        findings = check_structure(vault)
        assert _codes(findings) == ["S1"]
        assert findings[0].severity == "warning"
        assert is_fixable(findings[0])

    def test_s1_does_not_gate_default_but_gates_strict(self, vault_dir: Path):
        self._vault_with_bare_fleet(vault_dir)
        assert main(["--vault", str(vault_dir), "validate"]) == 0
        assert main(["--vault", str(vault_dir), "validate", "--strict"]) == 1

    def test_fix_creates_shared_and_exits_zero(self, vault_dir: Path, capsys):
        self._vault_with_bare_fleet(vault_dir)
        rc = main(["--vault", str(vault_dir), "validate", "--fix"])
        assert rc == 0
        created = vault_dir / "myfleet" / "shared"
        assert created.is_dir()
        assert created.resolve().is_relative_to(vault_dir.resolve())
        # Durable: scaffolds the tier tree + .gitkeep so git tracks it (a bare
        # empty shared/ would vanish on clone → S1 recurs on machine B).
        assert (created / "knowledge").is_dir()
        assert (created / "knowledge" / ".gitkeep").is_file()
        # Idempotent: a second --fix is a clean no-op, still 0.
        assert main(["--vault", str(vault_dir), "validate", "--fix"]) == 0
        assert check_structure(detect(vault_dir)) == []

    def test_footer_names_fix_when_not_fixing(self, vault_dir: Path, capsys):
        self._vault_with_bare_fleet(vault_dir)
        main(["--vault", str(vault_dir), "validate"])
        err = capsys.readouterr().err
        assert "--fix" in err


class TestFixContainment:
    def test_symlink_escape_is_rejected(self, vault_dir: Path, tmp_path: Path):
        """A fleet `shared` that is a symlink out of the vault is refused —
        the resolved target escapes root, so --fix aborts and creates nothing
        outside. (Replaces a 'git status clean' check, which can't see this.)"""
        outside = tmp_path / "escape-target"  # deliberately outside the vault
        fleet = _make_fleet(vault_dir, "evilfleet")
        # dangling symlink → outside: not is_dir(), so S1 fires and --fix runs.
        (fleet / "shared").symlink_to(outside)

        vault = detect(vault_dir)
        findings = check_structure(vault)
        assert "S1" in _codes(findings)
        with pytest.raises(StructureError):
            fix_structure(vault, findings)
        assert not outside.exists()  # nothing created outside the vault

    def test_fix_aborts_cleanly_via_cli(self, vault_dir: Path, tmp_path: Path, capsys):
        outside = tmp_path / "escape-target"
        fleet = _make_fleet(vault_dir, "evilfleet")
        (fleet / "shared").symlink_to(outside)
        rc = main(["--vault", str(vault_dir), "validate", "--fix"])
        assert rc == 1
        assert "aborted" in capsys.readouterr().err
        assert not outside.exists()

    def test_non_directory_shared_is_skipped_not_crashed(
        self, vault_dir: Path, capsys
    ):
        """A fleet whose `shared` is a regular file: S1 fires, but --fix must
        skip it cleanly (reporting why) and still repair the OTHER fleets —
        never a raw FileExistsError traceback, never a silent partial batch.
        (general + structural + adversarial consensus Major.)"""
        _make_fleet(vault_dir, "goodfleet")
        bad = _make_fleet(vault_dir, "badfleet")
        (bad / "shared").write_text("a file, not a dir")
        rc = main(["--vault", str(vault_dir), "validate", "--fix"])
        assert rc == 0  # a clean return, not an uncaught exception
        assert (vault_dir / "goodfleet" / "shared").is_dir()  # sibling repaired
        assert (vault_dir / "badfleet" / "shared").is_file()  # untouched
        err = capsys.readouterr().err
        assert "skipped" in err and "badfleet" in err


class TestS2ReservedCollision:
    def test_reserved_dir_with_fleet_yaml_errors(self, vault_dir: Path):
        """projects/ is reserved; a fleet.yaml under it is the audit backstop
        for the vector `fleet add` guards. _scan_vault filters it out, so a
        raw walk is required to see it at all."""
        (vault_dir / "projects" / "fleet.yaml").write_text("fleet: {name: x}")
        vault = detect(vault_dir)
        assert "projects" not in vault.fleets  # pre-filtered
        findings = check_structure(vault)
        assert _codes(findings) == ["S2"]
        assert findings[0].severity == "error"
        assert not is_fixable(findings[0])

    def test_s2_gates_exit(self, vault_dir: Path):
        (vault_dir / "projects" / "fleet.yaml").write_text("fleet: {name: x}")
        assert main(["--vault", str(vault_dir), "validate"]) == 1


class TestS3UnknownDir:
    def test_unknown_top_level_dir_warns(self, vault_dir: Path):
        (vault_dir / "experiments").mkdir()
        findings = check_structure(detect(vault_dir))
        assert _codes(findings) == ["S3"]
        assert findings[0].severity == "warning"

    def test_s3_does_not_gate_and_fix_leaves_it(self, vault_dir: Path):
        (vault_dir / "experiments").mkdir()
        assert main(["--vault", str(vault_dir), "validate"]) == 0
        # --fix must not touch it (not fixable); dir still there, still 0.
        assert main(["--vault", str(vault_dir), "validate", "--fix"]) == 0
        assert (vault_dir / "experiments").is_dir()


class TestSystemContainer:
    """P1: a `.claudron-system` container is a recognized top-level dir, not an
    S3 'unrecognized top-level dir'; its nested fleets are recognized too
    (Claudlobby#602)."""

    def test_system_container_not_flagged_s3(self, nested_system_vault: Path):
        vault = detect(nested_system_vault)
        assert "S3" not in _codes(check_structure(vault))
        # holds under --strict too (where S3 would gate the exit)
        assert "S3" not in _codes(check_structure(vault, strict=True))

    def test_nested_system_vault_is_clean(self, nested_system_vault: Path):
        """The whole nested arrangement conforms — no findings at all (the
        nested fleet has its shared/, so not even S1)."""
        assert check_structure(detect(nested_system_vault)) == []

    def test_unknown_dir_beside_system_still_s3(self, nested_system_vault: Path):
        """Recognition is targeted: a genuinely-unknown top-level dir beside the
        container still yields S3."""
        (nested_system_vault / "experiments").mkdir()
        assert "S3" in _codes(check_structure(detect(nested_system_vault)))

    def test_nested_fleet_name_does_not_suppress_top_level_s3(
        self, nested_fleet_shadow_vault: Path
    ):
        """Claudlobby#602 review: a nested fleet's bare name must not shadow a
        same-named TOP-LEVEL dir out of the S3 walk. The top-level
        `experiments/` (no fleet.yaml) is genuinely unrecognized, so S3 fires —
        the nested `sys1/experiments` fleet must not wrongly suppress it."""
        findings = check_structure(detect(nested_fleet_shadow_vault))
        s3 = [f for f in findings if f.code == "S3"]
        assert [f.path for f in s3] == [
            str(nested_fleet_shadow_vault / "experiments")
        ]


class TestS4DualHub:
    def test_both_markers_warn(self, vault_dir: Path):
        (vault_dir / "shared" / "knowledge").mkdir(parents=True)  # + existing _shared/
        findings = check_structure(detect(vault_dir))
        assert _codes(findings) == ["S4"]
        assert findings[0].severity == "warning"


class TestJsonEnvelope:
    def test_structure_findings_in_json(self, vault_dir: Path, capsys):
        (vault_dir / "projects" / "fleet.yaml").write_text("fleet: {name: x}")
        rc = main(["--vault", str(vault_dir), "validate", "--json"])
        assert rc == 1
        env = json.loads(capsys.readouterr().out)
        # S2 rode through schema.Finding into the standard errors[] array — a
        # divergent shape (no .to_dict()) would vanish from --json.
        assert any(f["code"] == "S2" for f in env["errors"])
        assert env["ok"] is False


class TestReservedSingleSource:
    def test_user_reserved_is_derived_subset(self):
        assert USER_RESERVED == SKIP_DIRS - _INFRA_SKIP
        assert USER_RESERVED == {"_shared", "shared", "projects", "_packs"}
        assert USER_RESERVED < SKIP_DIRS  # genuine subset

    def test_infra_names_never_user_facing(self):
        for infra in (".git", ".github", ".claudron", "__pycache__"):
            assert infra not in USER_RESERVED


class TestInitValidateNoOp:
    def test_fresh_init_then_validate_is_clean(self, tmp_path: Path, capsys):
        root = init(tmp_path / "fresh")
        assert check_structure(detect(root)) == []
        assert main(["--vault", str(root), "validate"]) == 0


class TestCaseInsensitiveReserved:
    def test_capitalized_reserved_dir_not_flagged_unknown(self, tmp_path: Path):
        """On a case-insensitive FS a capitalized reserved dir (Projects/) IS
        the reserved tier, not an unknown dir — no false S3 (adversarial F1).
        On a case-sensitive FS it is a genuinely distinct dir, so the collision
        the fix targets does not exist there; skip."""
        root = tmp_path / "vault"
        (root / "_shared" / "knowledge").mkdir(parents=True)
        (root / "Projects").mkdir()  # a capitalized real directory
        if not (root / "projects").is_dir():
            pytest.skip("case-sensitive FS: Projects/ is a distinct dir, no collision")
        findings = check_structure(detect(root))
        assert "S3" not in _codes(findings)


class TestPathBranch:
    """The positional-PATH branch of cmd_validate (works today; these lock the
    wiring most likely to regress silently under refactor)."""

    def test_path_at_vault_root_runs_structure_lens(self, vault_dir: Path, capsys):
        _make_fleet(vault_dir)  # bare fleet → S1 (warning)
        rc = main(["validate", str(vault_dir), "--json"])
        env = json.loads(capsys.readouterr().out)
        assert any(f["code"] == "S1" for f in env["warnings"])
        assert rc == 0  # a lone warning does not gate

    def test_path_inner_subtree_skips_structure_lens(self, vault_dir: Path, capsys):
        _make_fleet(vault_dir)  # would be S1 at the root
        inner = vault_dir / "_shared" / "knowledge"
        rc = main(["validate", str(inner), "--json"])
        env = json.loads(capsys.readouterr().out)
        findings = env["errors"] + env["warnings"]
        assert not any(f["code"].startswith("S") for f in findings)
        assert rc == 0

    def test_fix_on_single_file_errors(self, vault_dir: Path, capsys):
        note = vault_dir / "_shared" / "knowledge" / "auth-patterns.md"
        rc = main(["validate", str(note), "--fix"])
        assert rc == 2
        assert "needs a whole vault" in capsys.readouterr().err
