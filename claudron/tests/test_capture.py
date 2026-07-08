"""Tests for the write engine and `claudron capture` (E2 PR2)."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from claudron.cli import main
from claudron.schema import parse_note


def _existing(vault: Path, *, status: str = "current", aliases: str | None = None) -> Path:
    """A pre-existing shared note for dedup scenarios."""
    alias_line = f"aliases: [{aliases}]\n" if aliases else ""
    path = vault / "_shared" / "knowledge" / "retry-strategy.md"
    path.write_text(
        "---\n"
        "title: Retry Strategy\n"
        "type: knowledge\n"
        f"status: {status}\n"
        f"{alias_line}"
        "owner: mason\n"
        "created: 2026-06-01\n"
        "updated: 2026-06-10\n"
        "---\n\n# Retry Strategy\n\nExponential backoff everywhere.\n"
    )
    return path


class TestCaptureCreates:
    def test_round_trip_strict_valid_draft(self, vault_dir: Path, capsys):
        """The write-path guarantee: capture output is strict-valid on disk
        and enters at maturity: draft (agent write, SCHEMA.md)."""
        rc = main(["--vault", str(vault_dir), "capture",
                   "--type", "knowledge", "--title", "Circuit Breakers",
                   "--body", "Trip after 5 consecutive failures.",
                   "--tags", "resilience", "--owner", "bot-1", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "created"
        path = Path(env["data"]["path"])
        fm, body, err = parse_note(path.read_text())
        assert err is None
        assert fm["maturity"] == "draft"
        assert fm["owner"] == "bot-1"
        assert "Trip after 5" in body
        assert main(["validate", str(path), "--strict"]) == 0

    def test_project_scope_and_yaml_special_title(self, vault_with_projects: Path, capsys):
        rc = main(["--vault", str(vault_with_projects), "capture",
                   "--type", "knowledge", "--title", "Pooling: 2026 findings",
                   "--body", "B.", "--project", "storydump", "--owner", "b", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        path = Path(env["data"]["path"])
        assert "projects/storydump" in str(path)
        fm, _, err = parse_note(path.read_text())
        assert err is None and fm["title"] == "Pooling: 2026 findings"

    def test_owner_derived_when_absent(self, vault_dir: Path, capsys, monkeypatch):
        monkeypatch.setenv("USER", "cap-user")
        import subprocess
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Ownerless Capture", "--body", "B.", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        assert fm["owner"] == "cap-user"

    def test_stdin_json_mode(self, vault_dir: Path, capsys, monkeypatch):
        import io
        finding = {"type": "decision", "title": "Use Backoff",
                   "body": "Decided.", "owner": "bot-2", "tags": ["adr"]}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(finding)))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "created"
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        assert fm["type"] == "decision" and fm["tags"] == ["adr"]


class TestCaptureDedup:
    """Dedup routes, never hard-rejects (E3 contract, cycle-1 fold)."""

    def test_exact_title_suggests_update(self, vault_dir: Path, capsys):
        existing = _existing(vault_dir)
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "New angle.",
                   "--owner", "b", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "suggest_update"
        assert env["data"]["path"].endswith("retry-strategy.md")
        assert "Retry Strategy" in env["data"]["reason"]
        # Nothing new written
        assert (vault_dir / "_shared" / "knowledge" / "retry-strategy.md").read_text().count("Addendum") == 0
        assert existing.read_text().count("New angle") == 0

    def test_alias_match_suggests_update(self, vault_dir: Path, capsys):
        _existing(vault_dir, aliases="Backoff Policy")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Backoff Policy", "--body", "B.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "suggest_update"

    def test_stale_match_suggests_supersede(self, vault_dir: Path, capsys):
        _existing(vault_dir, status="stale")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Fresh truth.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "suggest_supersede"

    def test_terminal_match_does_not_attract(self, vault_dir: Path, capsys):
        """A superseded note is done — same title creates fresh."""
        _existing(vault_dir, status="superseded")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Successor.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "created"
        # slug taken by the superseded note → suffixed
        assert env["data"]["path"].endswith("retry-strategy-2.md")

    def test_force_creates_despite_duplicate(self, vault_dir: Path, capsys):
        _existing(vault_dir)
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Deliberate twin.",
                   "--owner", "b", "--force", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "created"
        assert env["data"]["path"].endswith("retry-strategy-2.md")


class TestCaptureUpdate:
    def test_update_appends_addendum_and_bumps_updated(self, vault_dir: Path, capsys):
        existing = _existing(vault_dir)
        rel = "_shared/knowledge/retry-strategy.md"
        rc = main(["--vault", str(vault_dir), "capture",
                   "--update", rel, "--body", "Jitter matters too.", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "updated"
        text = existing.read_text()
        fm, body, err = parse_note(text)
        assert err is None
        assert "## Addendum" in body and "Jitter matters too." in body
        assert str(fm["updated"]) != "2026-06-10"  # bumped
        assert "Exponential backoff everywhere." in body  # original intact
        assert main(["validate", str(existing)]) == 0

    def test_update_missing_note_is_usage_error(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "capture",
                   "--update", "_shared/knowledge/nope.md", "--body", "X."])
        assert rc == 2
        assert "no such note" in capsys.readouterr().err


class TestCaptureValidation:
    def test_invalid_finding_rejected_with_findings(self, vault_dir: Path, capsys, monkeypatch):
        """Schema-invalid input → exit 1, Finding elements in the envelope,
        nothing written (the write-path guarantee's other half)."""
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
            {"type": "memo", "title": "Bad", "body": "B.", "owner": "b"})))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
        assert rc == 1
        env = json.loads(capsys.readouterr().out)
        assert env["ok"] is False
        assert any(f["code"] == "E002" for f in env["errors"])
        assert not list((vault_dir / "_shared" / "knowledge").glob("bad*"))

    def test_capture_scope_containment(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Esc", "--body", "B.", "--owner", "b",
                   "--project", "../../escaped"])
        assert rc == 2
        assert "escapes the vault root" in capsys.readouterr().err
        assert not (vault_dir.parent / "escaped").exists()
