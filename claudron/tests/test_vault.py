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
        """Behavioral (the S1 fix): the scaffolded gitignore ignores a `.env`
        at any depth — vault-root AND nested — and does NOT over-match
        `.env.example`. `*/.env` matched only subdirs; a pattern-set check
        can't catch a plausible pattern that silently fails to match root, so
        assert real `git check-ignore`.

        Hermetic: global/system/XDG ignore sources are neutralized so a
        developer's own `core.excludesFile` (which `git check-ignore` honors)
        can't mask a regressed pattern and make this false-pass. The negative
        control re-checks the OLD `*/.env` pattern to prove the test actually
        discriminates — it fails the root case exactly as the S1 bug did."""
        import os
        import shutil
        import subprocess

        if not shutil.which("git"):
            pytest.skip("git not available")
        from claudron.vault import _GITIGNORE_CONTENT

        env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(tmp_path),
            "XDG_CONFIG_HOME": str(tmp_path / "no-xdg"),
        }

        def ignored(rel: str) -> bool:
            return (
                subprocess.run(
                    ["git", "-C", str(tmp_path), "check-ignore", rel], env=env
                ).returncode
                == 0
            )

        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], env=env, check=True)

        # The real scaffold: ignores .env at root and nested; leaves .env.example.
        (tmp_path / ".gitignore").write_text(_GITIGNORE_CONTENT)
        assert ignored(".env"), "root .env not ignored by scaffolded .gitignore"
        assert ignored("fleet1/.env"), "nested .env not ignored by scaffolded .gitignore"
        assert not ignored(".env.example"), ".env.example must not be ignored"

        # Negative control: the OLD `*/.env` pattern fails the root case.
        (tmp_path / ".gitignore").write_text("*/.env\n")
        assert not ignored(".env"), "regression guard: */.env must NOT match root .env"
        assert ignored("fleet1/.env"), "*/.env still matches nested .env"

    def test_adopt_merges_gitignore_secrets_rules(self, tmp_path: Path):
        """`init --adopt` on a dir that already has a .gitignore APPENDS the
        vault secrets rules instead of silently skipping them — the adopt-path
        gap (`_write_if_absent` skips an existing file). The pre-existing rules
        are preserved; `.env`/`.claudron/` end up present."""
        target = tmp_path / "adopt-existing-gitignore"
        target.mkdir()
        (target / "existing.md").write_text("keep me")
        (target / ".gitignore").write_text("node_modules/\n")  # pre-existing, no .env
        init(target, adopt=True)
        lines = (target / ".gitignore").read_text().splitlines()
        assert "node_modules/" in lines  # preserved
        assert ".env" in lines  # secrets rule now present
        assert ".claudron/" in lines

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
