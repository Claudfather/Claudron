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


class TestVaultResolution:
    """The CLI resolution chain (docs/CLI_CONTRACT.md §Environment):
    --vault → $CLAUDRON_VAULT_PATH → walk-up. `CLAUDRON_VAULT` was removed
    in 0.3.0 (boundary program F3, hard cut): with both set and disagreeing
    the two names resolved *different vaults* across the ecosystem, so the
    alias is not read at all — only named back on the failure path."""

    def test_claudron_vault_path_resolves_from_outside(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)  # cwd outside the vault (the bot-runtime case)
        monkeypatch.delenv("CLAUDRON_VAULT", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT_PATH", str(vault_dir))
        rc = main(["status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["root"] == str(vault_dir)

    def test_removed_alias_never_read_when_canonical_set(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        """Both set and disagreeing: the canonical var wins outright. The
        alias pointing at a *valid* second vault must still lose."""
        other = tmp_path / "other-vault"
        (other / "_shared" / "knowledge").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDRON_VAULT", str(other))           # not read
        monkeypatch.setenv("CLAUDRON_VAULT_PATH", str(vault_dir))  # wins
        rc = main(["status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["root"] == str(vault_dir)

    def test_removed_alias_alone_exits_3_with_hint(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        """The F3 softener: the dotfile straggler set the dead var and there
        is no vault to walk up to — exit 3 names the removal and the new var."""
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(vault_dir))
        with pytest.raises(SystemExit) as exc_info:
            main(["status"])
        assert exc_info.value.code == 3
        captured = capsys.readouterr()
        assert "CLAUDRON_VAULT is no longer read" in captured.err
        assert "CLAUDRON_VAULT_PATH" in captured.err
        assert captured.out == ""  # the hint is a diagnostic (§Channels)

    def test_no_hint_when_removed_alias_unset(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """No dead var set ⇒ the plain no-vault message, unchanged."""
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDRON_VAULT", raising=False)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            main(["status"])
        assert exc_info.value.code == 3
        err = capsys.readouterr().err
        assert "no vault found" in err
        assert "no longer read" not in err

    def test_walk_up_unchanged_when_no_env(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """Neither var set ⇒ walk-up from CWD, exactly as before."""
        monkeypatch.delenv("CLAUDRON_VAULT", raising=False)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.chdir(vault_dir)
        rc = main(["status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["root"] == str(vault_dir)


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

    def test_status_json_carries_engine_version(self, vault_dir: Path, capsys):
        """The capability probe (docs/INTEGRATION.md step 0): consumers read
        the engine's version off the envelope they already parse, rather than
        each maintaining a private detection ladder."""
        from claudron import __version__

        rc = main(["--vault", str(vault_dir), "status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["engine_version"] == __version__

    def test_status_json_envelope_shape_unchanged(self, vault_dir: Path, capsys):
        """engine_version is additive — the documented field set survives."""
        rc = main(["--vault", str(vault_dir), "status", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert set(env) == {"ok", "command", "data", "warnings", "errors"}
        for field in ("root", "total_docs", "total_stale", "tiers",
                      "fleets", "projects", "engine_version"):
            assert field in env["data"], field

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
            "---\ntitle: New Doc\ntype: knowledge\nstatus: current\n"
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
        # Compare against the installed metadata — both sides read one
        # source, so this is release-proof AND verifies the exact render
        # contract (label + version), which a shape regex would miss.
        from importlib.metadata import version

        assert f"claudron {version('claudron')}" in out


def _write_legacy_note(vault_dir: Path) -> Path:
    """A claudlobby-style note: legacy status, no updated (W101+W102)."""
    path = vault_dir / "_shared" / "knowledge" / "legacy-note.md"
    path.write_text(
        "---\ntitle: Legacy Note\ntype: knowledge\nstatus: active\n"
        "owner: branden\ncreated: 2026-05-01\n---\n\n# Legacy Note\n"
    )
    return path


class TestValidateCommand:
    def test_validate_vault_clean(self, vault_dir: Path, capsys):
        # conftest fixtures are canonical since PR3 — zero findings
        rc = main(["--vault", str(vault_dir), "validate"])
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == ""
        assert "0 error(s), 0 warning(s)" in captured.err

    def test_validate_json_envelope_findings(self, vault_dir: Path, capsys):
        _write_legacy_note(vault_dir)
        rc = main(["--vault", str(vault_dir), "validate", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "validate" and env["ok"] is True
        assert env["errors"] == []
        codes = {w["code"] for w in env["warnings"]}
        assert codes == {"W101", "W102"}
        # Each element is a full serialized Finding (machine carrier)
        sample = env["warnings"][0]
        assert set(sample) == {"code", "severity", "path", "field", "line", "message"}

    def test_validate_strict_escalates(self, vault_dir: Path, capsys):
        _write_legacy_note(vault_dir)
        rc = main(["--vault", str(vault_dir), "validate", "--strict", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 1  # legacy statuses are errors on the authoring tier
        assert env["ok"] is False and len(env["errors"]) > 0

    def test_validate_single_file(self, vault_dir: Path, capsys):
        target = _write_legacy_note(vault_dir)
        rc = main(["validate", str(target), "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert {w["code"] for w in env["warnings"]} == {"W101", "W102"}

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

    def test_removed_var_hint_never_on_stdout(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(vault_dir))
        with pytest.raises(SystemExit):
            main(["lookup", "auth"])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no longer read" in captured.err

    def test_tree_walk_deprecation_never_on_stdout(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        cl_root = tmp_path / "claudlobby"
        (cl_root / "library").mkdir(parents=True)
        (cl_root / "lib").mkdir()
        vault = tmp_path / "vault"
        (vault / "_shared" / "knowledge").mkdir(parents=True)
        monkeypatch.chdir(cl_root)
        rc = main(["plug", str(vault)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "deprecated" in captured.err
        assert "deprecated" not in captured.out
        assert "plugged" in captured.out  # payload survives on stdout

    def test_detect_rejects_case_insensitive_marker(self, tmp_path: Path):
        """macOS regression guard: /Users/Shared must not make /Users a
        vault. A dir whose real name differs in case is not a marker."""
        from claudron.vault import detect

        root = tmp_path / "not-a-vault"
        (root / "Shared").mkdir(parents=True)
        assert detect(root) is None


def _contract_table(marker: str) -> list[list[str]]:
    """Extract the doc-parity table following *marker* in docs/CLI_CONTRACT.md.

    Same shape as test_schema.py's SCHEMA.md reader — the contract docs use
    one parity mechanism, not two.
    """
    from pathlib import Path as _Path

    repo_root = _Path(__file__).resolve().parents[2]
    text = (repo_root / "docs" / "CLI_CONTRACT.md").read_text()
    section = text.split(f"<!-- doc-parity: {marker} -->")[1]
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not set(cells[0]) <= {"-", " "}:  # skip separator row
                rows.append(cells)
        elif rows:
            break
    return rows[1:]  # drop header


class TestEnvironmentDocParity:
    """CLI_CONTRACT §Environment is the ONE normative statement of the
    vault-address contract (boundary spec §10.4 contract #4). The engine's
    resolution ladder and the table cannot drift: consumers on three repos
    build against the table, and the last time doc and code disagreed the
    two names resolved different vaults (Claudron #30)."""

    def test_env_rows_match_code_ladder_in_order(self):
        from claudron.cli import VAULT_ENV_VARS

        rows = _contract_table("ENVIRONMENT")
        documented = tuple(
            _first_code(row[1]) for row in rows if row[2] == "env"
        )
        assert documented == VAULT_ENV_VARS

    def test_removed_rows_match_removal_constant(self):
        from claudron.cli import REMOVED_VAULT_ENV_VARS

        rows = _contract_table("ENVIRONMENT")
        documented = tuple(
            _first_code(row[1]) for row in rows if row[2].startswith("removed")
        )
        assert documented == REMOVED_VAULT_ENV_VARS

    def test_removed_vars_are_not_read_by_the_resolver(self):
        """The hard cut, pinned structurally: a removed name may appear in the
        failure-path hint but never in the resolution chain."""
        import inspect

        from claudron.cli import REMOVED_VAULT_ENV_VARS, _detect_vault

        source = inspect.getsource(_detect_vault)
        for var in REMOVED_VAULT_ENV_VARS:
            assert var not in source, var

    def test_table_is_precedence_ordered(self):
        """Rows 1..N are the live ladder in precedence order; removed rows
        carry no rank."""
        rows = _contract_table("ENVIRONMENT")
        ranks = [row[0] for row in rows if row[0].isdigit()]
        assert ranks == [str(i) for i in range(1, len(ranks) + 1)]
        assert rows[0][2] == "flag"  # --vault always wins
        assert rows[len(ranks) - 1][2] == "discovery"  # walk-up is last

    def test_flags_section_defers_to_the_table(self):
        """§Flags must point at §Environment, never restate the order (R3
        applied at home — one normative statement, one parity gate)."""
        from pathlib import Path as _Path

        repo_root = _Path(__file__).resolve().parents[2]
        text = (repo_root / "docs" / "CLI_CONTRACT.md").read_text()
        flags = text.split("## Flags", 1)[1].split("\n## ", 1)[0]
        assert "§Environment" in flags
        assert "CLAUDRON_VAULT_PATH" not in flags


def _first_code(cell: str) -> str:
    """First backticked value in a table cell."""
    import re

    return re.findall(r"`([^`]+)`", cell)[0]
