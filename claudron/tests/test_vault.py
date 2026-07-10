"""Tests for vault detection, scanning, and scaffolding."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from claudron.vault import VaultError, detect, init, status


class TestDetect:
    def test_detect_from_root(self, vault_dir: Path):
        vault = detect(vault_dir)
        assert vault is not None
        assert vault.root == vault_dir

    def test_detect_from_nested_dir(self, vault_dir: Path):
        nested = vault_dir / "_shared" / "knowledge"
        vault = detect(nested)
        assert vault is not None
        assert vault.root == vault_dir

    def test_detect_from_fleet_dir(self, vault_with_fleet: Path):
        fleet_dir = vault_with_fleet / "test-fleet" / "shared"
        vault = detect(fleet_dir)
        assert vault is not None
        assert vault.root == vault_with_fleet

    def test_detect_no_vault(self, tmp_path: Path):
        nowhere = tmp_path / "random" / "place"
        nowhere.mkdir(parents=True)
        vault = detect(nowhere)
        assert vault is None

    def test_detect_nested_vaults(self, vault_dir: Path):
        inner = vault_dir / "nested"
        (inner / "_shared").mkdir(parents=True)
        vault = detect(inner / "_shared")
        assert vault is not None
        assert vault.root == inner  # inner wins

    def test_detect_shared_is_file(self, tmp_path: Path):
        root = tmp_path / "fake"
        root.mkdir()
        (root / "_shared").write_text("not a directory")
        vault = detect(root)
        assert vault is None

    def test_detect_shared_no_underscore(self, shared_vault: Path):
        """Vault with shared/ (no underscore) is detected."""
        vault = detect(shared_vault)
        assert vault is not None
        assert vault.root == shared_vault
        assert vault.shared == shared_vault / "shared"

    def test_detect_prefers_underscore_shared(self, tmp_path: Path):
        """When both _shared/ and shared/ exist, _shared/ wins."""
        root = tmp_path / "both"
        (root / "_shared" / "knowledge").mkdir(parents=True)
        (root / "shared" / "knowledge").mkdir(parents=True)
        vault = detect(root)
        assert vault is not None
        assert vault.shared == root / "_shared"


class TestScan:
    def test_scan_discovers_fleets(self, vault_with_fleet: Path):
        vault = detect(vault_with_fleet)
        assert "test-fleet" in vault.fleets
        assert vault.fleets["test-fleet"] == vault_with_fleet / "test-fleet"

    @pytest.mark.parametrize("reserved", [".git", "_packs"])
    def test_scan_ignores_reserved_dir(self, vault_dir: Path, reserved: str):
        """A SKIP_DIRS member carrying a fleet.yaml is never discovered as a
        fleet (.git = infra dotdir; _packs = E6 pack container). Both short-
        circuit at the same SKIP_DIRS gate in _scan_vault."""
        d = vault_dir / reserved
        d.mkdir()
        (d / "fleet.yaml").write_text("fleet: {name: x}")
        assert reserved not in detect(vault_dir).fleets

    def test_empty_vault_valid(self, empty_vault: Path):
        vault = detect(empty_vault)
        assert vault is not None
        assert vault.projects == {}
        assert vault.fleets == {}

    def test_scan_discovers_projects(self, vault_with_projects: Path):
        vault = detect(vault_with_projects)
        assert "storydump" in vault.projects


class TestInit:
    def test_init_creates_structure(self, tmp_path: Path):
        target = tmp_path / "new-vault"
        root = init(target)
        assert root == target.resolve()
        assert (root / "_shared" / "knowledge").is_dir()
        assert (root / "_shared" / "decisions").is_dir()
        assert (root / "_shared" / "runbooks").is_dir()
        # planning/ scaffolds nested (SCHEMA.md taxonomy, E1 — reverses #4)
        assert (root / "_shared" / "planning" / "active").is_dir()
        assert (root / "_shared" / "planning" / "completed").is_dir()
        assert (root / "projects").is_dir()
        assert (root / ".gitignore").is_file()

    def test_scaffolded_gitignore_ignores_env_at_any_depth(self, tmp_path: Path):
        """Behavioral (the S1 fix): a vault-root .env AND a nested one are
        actually git-ignored by the scaffolded gitignore. `*/.env` matched only
        subdirs; a pattern-set check can't catch a plausible pattern that
        silently fails to match root, so assert real `git check-ignore`."""
        import shutil
        import subprocess

        if not shutil.which("git"):
            pytest.skip("git not available")
        from claudron.vault import _GITIGNORE_CONTENT

        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        (tmp_path / ".gitignore").write_text(_GITIGNORE_CONTENT)
        (tmp_path / ".env").write_text("SECRET=1\n")
        (tmp_path / "fleet1").mkdir()
        (tmp_path / "fleet1" / ".env").write_text("SECRET=1\n")
        for rel in (".env", "fleet1/.env"):
            result = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", rel])
            assert result.returncode == 0, f"{rel} not ignored by scaffolded .gitignore"

    def test_init_existing_nonempty_errors(self, tmp_path: Path):
        target = tmp_path / "nonempty"
        target.mkdir()
        (target / "somefile.txt").write_text("stuff")
        with pytest.raises(VaultError, match="not empty"):
            init(target)

    def test_init_existing_vault_errors(self, vault_dir: Path):
        with pytest.raises(VaultError, match="already exists"):
            init(vault_dir)

    def test_init_existing_shared_vault_errors(self, shared_vault: Path):
        with pytest.raises(VaultError, match="already exists"):
            init(shared_vault)

    def test_init_adopt_nonempty(self, tmp_path: Path):
        target = tmp_path / "adopt-me"
        target.mkdir()
        (target / "existing.md").write_text("keep me")
        root = init(target, adopt=True)
        assert (root / "_shared" / "knowledge").is_dir()
        assert (root / "existing.md").is_file()  # preserved


class TestStatus:
    def test_status_counts_docs(self, vault_dir: Path):
        vault = detect(vault_dir)
        info = status(vault)
        assert info["total_docs"] == 2
        assert info["tiers"]["shared/knowledge"]["docs"] == 2

    def test_status_walks_shared_planning(self, vault_dir: Path):
        """Docs under _shared/planning/active count in the shared/planning tier (E1, reverses #4)."""
        active = vault_dir / "_shared" / "planning" / "active"
        active.mkdir(parents=True)
        (active / "q3-roadmap.md").write_text(
            dedent("""\
                ---
                title: Q3 Roadmap
                type: plan
                status: active
                owner: chris
                tags: [roadmap]
                created: 2026-07-01
                updated: 2026-07-01
                ---

                # Q3 Roadmap
            """)
        )
        vault = detect(vault_dir)
        info = status(vault)
        assert info["tiers"]["shared/planning"]["docs"] == 1
        assert info["total_docs"] == 3

    def test_status_empty_vault_warns(self, empty_vault: Path):
        vault = detect(empty_vault)
        info = status(vault)
        assert info["total_docs"] == 0
        assert any("empty" in w for w in info["warnings"])

    def test_status_includes_fleet(self, vault_with_fleet: Path):
        vault = detect(vault_with_fleet)
        info = status(vault)
        assert "test-fleet" in info["fleets"]
        assert "test-fleet/shared" in info["tiers"]

    def test_status_shared_vault(self, shared_vault: Path):
        vault = detect(shared_vault)
        info = status(vault)
        assert info["total_docs"] == 1
        assert info["tiers"]["shared/knowledge"]["docs"] == 1
