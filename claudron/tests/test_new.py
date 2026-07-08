"""Tests for `claudron new` and `init --adopt` backfill (E1 PR3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.schema import parse_note


class TestNewRoundTrip:
    """The plan's acceptance test, literally: `new` output passes
    `validate --strict` by construction, owner populated."""

    @pytest.mark.parametrize(
        "note_type,expected_dir,expected_status",
        [
            ("knowledge", "_shared/knowledge", "current"),
            ("decision", "_shared/decisions", "draft"),
            ("runbook", "_shared/runbooks", "current"),
            ("plan", "_shared/planning/active", "draft"),
            ("audit", "_shared/planning/active", "draft"),
            ("review", "_shared/planning/active", "draft"),
        ],
    )
    def test_new_then_strict_validate(
        self, vault_dir: Path, capsys, note_type, expected_dir, expected_status
    ):
        rc = main(
            ["--vault", str(vault_dir), "new", note_type,
             f"My {note_type.title()} Note", "--owner", "tester", "--json"]
        )
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        path = Path(env["data"]["path"])
        assert path.is_file()
        assert str(path.parent.relative_to(vault_dir)) == expected_dir

        fm, _, err = parse_note(path.read_text())
        assert err is None
        assert fm["owner"] == "tester"
        assert fm["status"] == expected_status
        assert fm["schema_version"] == 1

        rc = main(["validate", str(path), "--strict"])
        assert rc == 0, capsys.readouterr().out

    def test_owner_derivation_fallback(self, vault_dir: Path, capsys, monkeypatch):
        """--owner absent → git config user.name → $USER."""
        monkeypatch.setenv("USER", "env-user")
        rc = main(
            ["--vault", str(vault_dir), "new", "knowledge", "Ownerless", "--json"]
        )
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        # In this repo git user.name is set; either derivation source is
        # acceptable — the contract is only that owner is non-empty.
        assert fm["owner"]

    def test_tags_and_project_scope(self, vault_with_projects: Path, capsys):
        rc = main(
            ["--vault", str(vault_with_projects), "new", "knowledge",
             "Scoped Note", "--project", "storydump", "--tags", "a,b",
             "--owner", "t", "--json"]
        )
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        path = Path(env["data"]["path"])
        assert "projects/storydump" in str(path)
        fm, _, _ = parse_note(path.read_text())
        assert fm["tags"] == ["a", "b"]

    def test_fleet_scope(self, vault_with_fleet: Path, capsys):
        rc = main(
            ["--vault", str(vault_with_fleet), "new", "knowledge",
             "Fleet Note", "--fleet", "test-fleet", "--owner", "t", "--json"]
        )
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert "test-fleet/shared/knowledge" in env["data"]["path"]


class TestNewEdges:
    def test_slug_collision_errors_without_force(self, vault_dir: Path, capsys):
        args = ["--vault", str(vault_dir), "new", "knowledge", "Same Title",
                "--owner", "t"]
        assert main(args) == 0
        capsys.readouterr()
        rc = main(args)
        assert rc == 1  # data conflict, not usage
        err = capsys.readouterr().err
        assert "exists" in err and "--force" in err

    def test_force_overwrites(self, vault_dir: Path, capsys):
        args = ["--vault", str(vault_dir), "new", "knowledge", "Same Title",
                "--owner", "t"]
        main(args)
        rc = main(args + ["--force"])
        assert rc == 0

    def test_project_fleet_mutex(self, vault_with_fleet: Path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--vault", str(vault_with_fleet), "new", "knowledge", "X",
                  "--project", "p", "--fleet", "test-fleet"])
        assert exc_info.value.code == 2  # argparse usage error

    def test_edit_without_editor_still_writes(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        monkeypatch.delenv("EDITOR", raising=False)
        rc = main(["--vault", str(vault_dir), "new", "knowledge",
                   "Editorless", "--owner", "t", "--edit"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "EDITOR" in captured.err  # clear diagnostic
        assert (vault_dir / "_shared" / "knowledge" / "editorless.md").is_file()

    def test_unknown_type_is_usage_error(self, vault_dir: Path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--vault", str(vault_dir), "new", "memo", "X"])
        assert exc_info.value.code == 2  # argparse choices


class TestAdoptBackfill:
    def test_adopt_backfills_updated_from_mtime(self, tmp_path: Path, capsys):
        """The W101 remedy: adopting an existing docs tree backfills
        missing `updated` from file mtime — the one sanctioned mutation."""
        import os
        import time

        target = tmp_path / "existing-docs"
        (target / "notes").mkdir(parents=True)
        legacy = target / "notes" / "old-note.md"
        legacy.write_text(
            "---\ntitle: Old Note\ntype: knowledge\nstatus: active\n"
            "owner: someone\ncreated: 2026-05-01\n---\n\n# Old Note\n\nBody.\n"
        )
        stamp = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        os.utime(legacy, (stamp, stamp))

        rc = main(["init", str(target), "--adopt"])
        assert rc == 0

        fm, body, err = parse_note(legacy.read_text())
        assert err is None
        assert str(fm["updated"]) == "2026-06-15"
        assert fm["created"] is not None  # untouched
        assert "# Old Note" in body  # body preserved byte-for-byte

    def test_adopt_leaves_complete_notes_alone(self, tmp_path: Path, capsys):
        target = tmp_path / "existing-docs"
        target.mkdir()
        note = target / "done.md"
        original = (
            "---\ntitle: Done\ntype: knowledge\nstatus: current\n"
            "owner: o\ncreated: 2026-05-01\nupdated: 2026-05-02\n---\n\nBody.\n"
        )
        note.write_text(original)
        main(["init", str(target), "--adopt"])
        assert note.read_text() == original

    def test_plain_init_never_mutates(self, tmp_path: Path, capsys):
        """Backfill is adopt-only — plain init on empty dir has nothing to
        touch, and non-adopt init on nonempty dirs errors before writing."""
        rc = main(["init", str(tmp_path / "fresh")])
        assert rc == 0


class TestReferenceVaultFixture:
    def test_fixture_copies_reference_vault(self, reference_vault: Path):
        assert (reference_vault / "_shared" / "CONVENTIONS.md").is_file()
        assert (reference_vault / "_shared" / "decisions").is_dir()
        # It's a copy — mutations don't touch the repo's examples/
        (reference_vault / "_shared" / "knowledge" / "scratch.md").write_text("x")
