"""Tests for vault detection, scanning, and scaffolding."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from claudron.vault import (
    VaultError,
    detect,
    init,
    is_within_root,
    note_tiers,
    status,
)


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

    def test_detect_from_nested_fleet_binds_true_root(self, nested_system_vault: Path):
        """B2: a system container's `shared/` must NOT bind as the vault root —
        detect keeps walking up past the `.claudron-system` container to the
        true global root (the `_shared/` dir), else the global _shared/ is lost."""
        deep = nested_system_vault / "sys1" / "fleetA"
        vault = detect(deep)
        assert vault is not None
        assert vault.root == nested_system_vault
        assert vault.shared == nested_system_vault / "_shared"

    def test_detect_from_system_shared_binds_true_root(self, nested_system_vault: Path):
        """Starting *inside* the container's own `shared/` still resolves to the
        global root, not the container."""
        vault = detect(nested_system_vault / "sys1" / "shared")
        assert vault is not None
        assert vault.root == nested_system_vault


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


class TestNestedSystemScan:
    """P1 nested-tolerant scanner: opt-in ``.claudron-system`` containers hold
    nested fleets + a ``shared/`` bucket, while flat vaults stay byte-identical
    (Claudlobby#602)."""

    def test_nested_fleet_and_system_discovered(self, nested_system_vault: Path):
        vault = detect(nested_system_vault)
        assert vault is not None
        # nested fleet is discovered under its BARE name (F5 global-unique key)
        assert "fleetA" in vault.fleets
        assert vault.fleets["fleetA"] == nested_system_vault / "sys1" / "fleetA"
        # the container is recorded as a system, never as a flat fleet
        assert "sys1" in vault.systems
        assert vault.systems["sys1"] == nested_system_vault / "sys1"
        assert "sys1" not in vault.fleets

    def test_flat_vault_has_empty_systems(self, vault_with_fleet: Path):
        """Backwards-compat: a vault with NO marker is flat — `systems` is
        explicitly empty and flat fleet discovery is unchanged."""
        vault = detect(vault_with_fleet)
        assert "test-fleet" in vault.fleets
        assert vault.systems == {}

    def test_note_tiers_classifies_system(self, nested_system_vault: Path):
        """The container's shared/ is a `system:` tier (parallels `fleet:`); the
        nested fleet flows through the fleet: loop; nothing is mis-pooled as the
        `other:` hatch."""
        vault = detect(nested_system_vault)
        pairs = list(note_tiers(vault))
        tags = [tier for _base, tier in pairs]
        assert (nested_system_vault / "sys1" / "shared", "system:sys1") in pairs
        assert (
            nested_system_vault / "sys1" / "fleetA" / "shared",
            "fleet:fleetA",
        ) in pairs
        assert not any(t.startswith("other:") for t in tags)  # no other:sys1

    def test_note_tiers_flat_vault_unchanged(self, vault_with_fleet: Path):
        """Backwards-compat: no `system:` tier appears for a flat vault."""
        tags = [tier for _base, tier in note_tiers(detect(vault_with_fleet))]
        assert not any(t.startswith("system:") for t in tags)
        assert "fleet:test-fleet" in tags


class TestNestedFleetNameShadow:
    """Claudlobby#602 review: `recognized_top_level` is PATH-aware — a nested
    fleet's bare name must never shadow a same-named TOP-LEVEL dir out of the
    ``other:``/S3 hatch. A name-based union folded nested fleet names in, so a
    genuine top-level dir sharing that name silently vanished (data loss)."""

    def test_recognized_top_level_excludes_nested_fleet_name(
        self, nested_fleet_shadow_vault: Path
    ):
        vault = detect(nested_fleet_shadow_vault)
        # The nested fleet is still discovered under its bare name (F5 key) ...
        assert "experiments" in vault.fleets
        assert (
            vault.fleets["experiments"]
            == nested_fleet_shadow_vault / "sys1" / "experiments"
        )
        # ... but recognized_top_level holds only TOP-LEVEL dir names: the
        # system container, NOT the nested fleet's bare name.
        assert vault.recognized_top_level == {"sys1"}

    def test_note_tiers_top_level_dir_not_shadowed(
        self, nested_fleet_shadow_vault: Path
    ):
        vault = detect(nested_fleet_shadow_vault)
        pairs = list(note_tiers(vault))
        tags = [tier for _base, tier in pairs]
        # The unrelated top-level experiments/ dir is STILL the other: hatch
        # (the collateral shadow the fix removes) ...
        assert (
            nested_fleet_shadow_vault / "experiments",
            "other:experiments",
        ) in pairs
        # ... while the nested fleet's own shared/ is still a fleet: tier, and
        # the container is still a system: tier — recognition is untouched.
        assert (
            nested_fleet_shadow_vault / "sys1" / "experiments" / "shared",
            "fleet:experiments",
        ) in pairs
        assert "system:sys1" in tags


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

    def test_adopt_backfill_scoped_to_note_tiers(self, tmp_path: Path):
        """`init --adopt` backfills `updated:` into note-tier files ONLY — never
        a fleet's library/voices/runtime overlay content. A plain root.rglob
        would rewrite Claudlobby files; backfill must share the indexer's tier
        scope (note_tiers). Reproduces + guards the adopt-scope bug."""
        root = tmp_path / "legacy-local"
        (root / "myfleet" / "library" / "skills").mkdir(parents=True)
        (root / "myfleet" / "shared" / "knowledge").mkdir(parents=True)
        (root / "myfleet" / "runtime" / "bots" / "bot1").mkdir(parents=True)
        (root / "myfleet" / "fleet.yaml").write_text("fleet: {name: myfleet}")
        note = root / "myfleet" / "shared" / "knowledge" / "note.md"
        note.write_text(
            "---\ntitle: N\ntype: knowledge\nstatus: current\nowner: c\n"
            "created: 2026-01-01\n---\n\n# N\n"
        )
        skill = root / "myfleet" / "library" / "skills" / "s.md"
        skill.write_text("---\ntitle: S\ndescription: d\n---\n\n# S\n")
        botmd = root / "myfleet" / "runtime" / "bots" / "bot1" / "CLAUDE.md"
        botmd.write_text("---\ntitle: B\n---\n\n# B\n")

        init(root, adopt=True)
        assert "updated:" in note.read_text()  # note tier — backfilled
        assert "updated:" not in skill.read_text()  # overlay — untouched
        assert "updated:" not in botmd.read_text()  # generated — untouched


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

    def test_status_reports_index_divergence(self, vault_dir: Path):
        """PR-H (Juncture D): status surfaces index-vs-vault drift — the silent
        failure the disposable mirror can introduce — as a number + a warning,
        and is clean on a fresh index."""
        from claudron.knowledge import build_index

        vault = detect(vault_dir)
        build_index(vault)  # index the two seed notes
        info = status(vault)
        assert info["divergence"] == {
            "missing": 0, "ghost": 0, "index_present": True, "corrupt": False,
        }
        assert not any("diverged" in w for w in info["warnings"])

        # A note appears on disk but the index isn't rebuilt → missing rises.
        (vault_dir / "_shared" / "knowledge" / "orphan.md").write_text(
            "---\ntitle: Orphan Note\ntype: knowledge\nstatus: current\n"
            "owner: t\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n\n"
            "# Orphan Note\n\nNot yet indexed.\n"
        )
        info2 = status(vault)
        assert info2["divergence"]["missing"] >= 1
        assert any("diverged" in w for w in info2["warnings"])

    def test_status_flags_corrupt_index(self, vault_dir: Path):
        """Review fix: a present-but-unparseable index.json must surface as a
        warning, not be scored clean (0/0) — that was the exact silent failure
        the divergence detector exists to catch."""
        from claudron.knowledge import build_index

        vault = detect(vault_dir)
        build_index(vault)
        (vault_dir / ".claudron" / "index.json").write_text("{ not json")
        info = status(vault)
        assert info["divergence"]["corrupt"] is True
        assert any("corrupt" in w for w in info["warnings"])

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


class TestContainment:
    """is_within_root — the shared containment primitive behind engine writes,
    capture --update, and validate --fix."""

    def test_inside_path_ok(self, tmp_path: Path):
        assert is_within_root(tmp_path / "a" / "b", tmp_path)

    def test_nonexistent_target_inside_ok(self, tmp_path: Path):
        # a to-be-created path with no symlinked component is fine
        assert is_within_root(tmp_path / "does" / "not" / "exist", tmp_path)

    def test_parent_escape_rejected(self, tmp_path: Path):
        assert not is_within_root(tmp_path / ".." / "evil", tmp_path)

    def test_symlink_pointing_out_rejected(self, tmp_path: Path):
        root = tmp_path / "vault"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "link").symlink_to(outside)
        assert not is_within_root(root / "link" / "note.md", root)  # guard 1

    def test_symlink_pointing_in_rejected(self, tmp_path: Path):
        """Guard 2: a symlinked component that resolves BACK inside is still
        rejected — a write must not be redirected through any symlink."""
        root = tmp_path / "vault"
        (root / "real").mkdir(parents=True)
        (root / "link").symlink_to(root / "real")
        # it DOES resolve inside...
        assert (root / "link").resolve().is_relative_to(root.resolve())
        # ...yet the symlinked component is refused
        assert not is_within_root(root / "link" / "note.md", root)

    def test_engine_write_path_rejects_symlinked_tier(self, vault_with_fleet: Path):
        """Integration: the shared primitive means the ENGINE write path now
        refuses a symlinked tier too (not just validate --fix) — the old
        is_relative_to-only guard allowed an inside-pointing symlink."""
        import shutil

        from claudron.engine import ScopeError, resolve_target_dir

        fleet_dir = vault_with_fleet / "test-fleet"
        shutil.rmtree(fleet_dir / "shared")
        (vault_with_fleet / "realshared").mkdir()
        (fleet_dir / "shared").symlink_to(vault_with_fleet / "realshared")
        vault = detect(vault_with_fleet)
        with pytest.raises(ScopeError):
            resolve_target_dir(vault, "decision", fleet="test-fleet")


class TestScopedStaleness:
    def test_overlay_file_outside_note_tiers_does_not_stale_index(
        self, vault_with_fleet: Path
    ):
        """A newer file under a fleet's runtime/ (Claudlobby overlay, never
        indexed) must not perpetually stale the index; a newer real note in
        an indexed tier still must (the whole-tree-rglob regression)."""
        import os

        from claudron.knowledge import build_index
        from claudron.vault import clear_stale_cache, detect, index_is_stale

        vault = detect(vault_with_fleet)
        index_path = vault.root / ".claudron" / "index.json"
        build_index(vault)
        idx_mtime = index_path.stat().st_mtime

        # Non-eligible overlay content (fleet runtime), made newer than the index.
        overlay = vault.root / "test-fleet" / "runtime" / "bots" / "memory.md"
        overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_text("# a bot memory, not a vault note\n")
        os.utime(overlay, (idx_mtime + 100, idx_mtime + 100))
        clear_stale_cache()
        assert index_is_stale(vault, index_path) is False

        # Control: a newer real note in an indexed tier still stales the index.
        note = vault.root / "_shared" / "knowledge" / "brand-new.md"
        note.write_text(
            "---\ntitle: Brand New\ntype: knowledge\nstatus: current\n"
            "owner: t\ncreated: 2026-01-01\n---\n\n# Brand New\n\nbody\n"
        )
        os.utime(note, (idx_mtime + 200, idx_mtime + 200))
        clear_stale_cache()
        assert index_is_stale(vault, index_path) is True
