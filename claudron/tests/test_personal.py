"""Tests for `claudron init --personal` — the two-command bootstrap (E2 PR4)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.schema import parse_note


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True
    )


class TestInitPersonal:
    def test_creates_vault_git_repo_with_seed_commit(self, tmp_path: Path):
        target = tmp_path / "my-vault"
        rc = main(["init", str(target), "--personal", "--owner", "tester"])
        assert rc == 0
        # --owner flows to the bootstrap note (live battery caught the
        # flag missing from the parser while the code read args.owner)
        note = next((target / "_shared" / "knowledge").glob("vault-bootstrap*.md"))
        fm, _, _ = parse_note(note.read_text())
        assert fm["owner"] == "tester"
        # Vault scaffold present
        assert (target / "_shared" / "CONVENTIONS.md").is_file()
        # It's a git repo with the scaffold committed (the SD card must
        # be clone-able immediately — scaffold-travels, PR3)
        assert _git(target, "rev-parse", "--git-dir").returncode == 0
        assert _git(target, "status", "--porcelain").stdout.strip() == ""
        log = _git(target, "log", "--oneline").stdout
        assert log.strip() != ""

    def test_bootstrap_note_recall_smoke(self, tmp_path: Path, capsys):
        """The doctor-style smoke test is a REAL first note: capture it,
        prove recall finds it — the loop verified at bootstrap."""
        target = tmp_path / "my-vault"
        main(["init", str(target), "--personal"])
        capsys.readouterr()
        rc = main(["--vault", str(target), "recall", "--query", "vault bootstrap"])
        assert rc == 0
        assert "Vault Bootstrap" in capsys.readouterr().out
        # And it's a valid note (strict tier — engine-written)
        notes = list((target / "_shared" / "knowledge").glob("vault-bootstrap*.md"))
        assert len(notes) == 1
        fm, _, err = parse_note(notes[0].read_text())
        assert err is None and fm["maturity"] == "draft"

    def test_prints_next_steps(self, tmp_path: Path, capsys):
        """Machine-B guidance: hooks install + remote + clone one-liners."""
        target = tmp_path / "my-vault"
        rc = main(["init", str(target), "--personal"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "hooks install" in out
        assert "remote add" in out  # remote setup one-liner (uses git -C)
        assert "git clone" in out
        assert "smoke test: recall found the bootstrap note" in out

    def test_json_envelope(self, tmp_path: Path, capsys):
        target = tmp_path / "my-vault"
        rc = main(["init", str(target), "--personal", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "init" and env["ok"] is True
        assert env["data"]["personal"] is True
        assert env["data"]["smoke_test"] == "passed"

    def test_idempotent_inside_existing_repo(self, tmp_path: Path):
        """--personal --adopt inside an existing git repo must not re-init
        or commit over the user's history."""
        target = tmp_path / "existing"
        target.mkdir()
        _git(target, "init", "--initial-branch=main")
        (target / "notes.md").write_text("mine")
        _git(target, "add", "-A")
        subprocess.run(
            ["git", "-C", str(target), "-c", "user.name=t", "-c",
             "user.email=t@t", "commit", "-qm", "user history"],
            capture_output=True,
        )
        rc = main(["init", str(target), "--personal", "--adopt"])
        assert rc == 0
        log = _git(target, "log", "--oneline").stdout
        assert "user history" in log  # preserved
        assert (target / "_shared" / "CONVENTIONS.md").is_file()

    def test_smoke_failure_is_reported_not_hidden(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """If the loop is broken at bootstrap, say so — exit 1, named step."""
        import claudron.cli as cli_mod

        def _broken(*a, **k):
            raise RuntimeError("engine exploded")

        monkeypatch.setattr(cli_mod, "capture", _broken)
        target = tmp_path / "my-vault"
        rc = main(["init", str(target), "--personal"])
        assert rc == 1
        assert "smoke test failed" in capsys.readouterr().err
