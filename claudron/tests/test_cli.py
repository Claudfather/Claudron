"""Tests for claudron CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main


class TestInit:
    def test_init_creates_vault(self, tmp_path: Path, capsys):
        target = tmp_path / "new-vault"
        rc = main(["init", str(target)])
        assert rc == 0
        assert (target / "_shared" / "knowledge").is_dir()
        out = capsys.readouterr().out
        assert "vault created" in out


class TestStatus:
    def test_status_output_human(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "docs:" in out
        assert "shared/knowledge:" in out

    def test_status_output_json(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "status" and env["ok"] is True
        assert env["data"]["total_docs"] == 2
        assert "tiers" in env["data"]

    def test_vault_flag_survives_subparser(self, vault_dir: Path, capsys):
        """py3.14 argparse regression guard: subparser defaults must not
        null the top-level --vault value (it did — and detect() then
        walked the filesystem from CWD)."""
        rc = main(["--vault", str(vault_dir), "status", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert env["data"]["root"] == str(vault_dir)
        # And the sub-level position parses too (CLI contract)
        rc = main(["status", "--vault", str(vault_dir), "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert env["data"]["root"] == str(vault_dir)


class TestLookup:
    def test_lookup_output_human(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "lookup", "auth"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Auth Patterns" in out

    def test_lookup_output_json(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "lookup", "--json", "auth"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "lookup"
        results = env["data"]["results"]
        assert len(results) >= 1
        assert results[0]["title"] == "Auth Patterns Across Services"

    def test_lookup_no_results(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "lookup", "nonexistent-topic-xyz"])
        assert rc == 0
        captured = capsys.readouterr()
        # Diagnostic goes to stderr; stdout stays clean (hook-injectable)
        assert captured.out == ""
        assert "no results" in captured.err

    def test_no_vault_error_message(self, tmp_path: Path, capsys):
        nowhere = tmp_path / "nowhere"
        nowhere.mkdir()
        # Point --vault at a dir with no _shared/
        with pytest.raises(SystemExit) as exc_info:
            main(["--vault", str(nowhere), "lookup", "anything"])
        assert exc_info.value.code == 3  # environment error (CLI contract 0.2.0)


class TestIndex:
    def test_index_builds(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "index"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "indexed" in err

    def test_index_full_flag(self, vault_dir: Path, capsys):
        # First build
        main(["--vault", str(vault_dir), "index"])
        capsys.readouterr()  # clear
        # Second call without --full should say up to date
        rc = main(["--vault", str(vault_dir), "index"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "up to date" in err
        # With --full, always rebuilds
        rc = main(["--vault", str(vault_dir), "index", "--full"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "indexed" in err

    def test_index_rebuilds_when_stale(self, vault_dir: Path, capsys):
        """Default index detects staleness and rebuilds without --full."""
        import time

        from claudron.vault import clear_stale_cache

        # Build initial index
        main(["--vault", str(vault_dir), "index"])
        capsys.readouterr()
        # Add a new doc after a brief delay to ensure mtime differs
        time.sleep(0.05)
        (vault_dir / "_shared" / "knowledge" / "new-doc.md").write_text(
            "---\ntitle: New Doc\ntype: knowledge\nstatus: active\n"
            "owner: test\ntags: [new]\ncreated: 2026-01-01\n"
            "updated: 2026-01-01\n---\n\n# New Doc\n"
        )
        clear_stale_cache()
        # Default index should detect staleness and rebuild
        rc = main(["--vault", str(vault_dir), "index"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "indexed" in err
        assert "3" in err

    def test_index_shared_vault(self, shared_vault: Path, capsys):
        """Index builds correctly on vaults using shared/ instead of _shared/."""
        rc = main(["--vault", str(shared_vault), "index"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "indexed" in err
        assert "1" in err


class TestVersion:
    def test_version_prints_semver(self, capsys):
        rc = main(["version"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "claudron" in out
        assert "0.1.0" in out


class TestValidateCommand:
    def test_validate_vault_clean(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "validate"])
        captured = capsys.readouterr()
        # conftest docs use legacy `status: active` -> W102 warnings only
        assert rc == 0
        assert "W102" in captured.out
        assert "error(s)" in captured.err  # summary is a diagnostic

    def test_validate_json_envelope_findings(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "validate", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "validate" and env["ok"] is True
        assert env["errors"] == []
        codes = {w["code"] for w in env["warnings"]}
        assert "W102" in codes
        # Each element is a full serialized Finding (machine carrier)
        sample = env["warnings"][0]
        assert set(sample) == {"code", "severity", "path", "field", "line", "message"}

    def test_validate_strict_escalates(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "validate", "--strict", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 1  # legacy statuses are errors on the authoring tier
        assert env["ok"] is False and len(env["errors"]) > 0

    def test_validate_single_file(self, vault_dir: Path, capsys):
        target = vault_dir / "_shared" / "knowledge" / "auth-patterns.md"
        rc = main(["validate", str(target), "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert {w["code"] for w in env["warnings"]} == {"W102"}

    def test_validate_missing_path_is_usage_error(self, capsys):
        rc = main(["validate", "/nonexistent/nowhere.md"])
        assert rc == 2
        assert "no such path" in capsys.readouterr().err


class TestChannelDiscipline:
    """stdout = payload only (docs/CLI_CONTRACT.md) — session hooks inject
    stdout verbatim, so a stray diagnostic there corrupts agent context."""

    def test_json_mode_stdout_is_single_envelope(self, vault_dir: Path, capsys):
        for argv in (
            ["--vault", str(vault_dir), "status", "--json"],
            ["--vault", str(vault_dir), "lookup", "--json", "auth"],
            ["--vault", str(vault_dir), "index", "--json"],
            ["--vault", str(vault_dir), "validate", "--json"],
            ["version", "--json"],
        ):
            main(argv)
            out = capsys.readouterr().out
            env = json.loads(out)  # exactly one JSON document
            assert set(env) == {"ok", "command", "data", "warnings", "errors"}, argv

    def test_diagnostics_never_on_stdout(self, empty_vault: Path, capsys):
        # empty vault: status emits its warning diagnostic -> stderr only
        rc = main(["--vault", str(empty_vault), "status"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "warning" not in captured.out
        assert "empty" in captured.err
        # index progress -> stderr only
        main(["--vault", str(empty_vault), "index"])
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_detect_rejects_case_insensitive_marker(self, tmp_path: Path):
        """macOS regression guard: /Users/Shared must not make /Users a
        vault. A dir whose real name differs in case is not a marker."""
        from claudron.vault import detect

        root = tmp_path / "not-a-vault"
        (root / "Shared").mkdir(parents=True)
        assert detect(root) is None
