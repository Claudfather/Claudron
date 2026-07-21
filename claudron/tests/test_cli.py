"""Tests for claudron CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from .doc_parity import code_values, doc_table, section
from claudron.cli import (
    REMOVED_VAULT_ENV_VARS,
    VAULT_ENV_VARS,
    _detect_vault,
    main,
)

CONTRACT = "docs/CLI_CONTRACT.md"


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

    def test_hint_fires_when_a_different_vault_resolves(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        """The damaging case, and the one exit-3 never covers: the dead var
        points at vault A, walk-up finds vault B, and 0.2.x would have used A.
        Exit 0 with a note landing somewhere the caller did not intend is
        worse than failing — so the softener fires here too."""
        other = tmp_path / "elsewhere"
        (other / "_shared" / "knowledge").mkdir(parents=True)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(other))
        monkeypatch.chdir(vault_dir)  # walk-up resolves vault_dir, not `other`
        rc = main(["status", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["data"]["root"] == str(vault_dir)
        assert "no longer read" in captured.err  # and it says so
        assert "no longer read" not in captured.out  # §Channels

    def test_no_hint_when_removed_alias_agrees_with_resolution(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """Set but pointing at the vault we used anyway — nothing is confusing,
        so nothing is said. Keeps the softener from becoming ambient noise."""
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(vault_dir))
        monkeypatch.chdir(vault_dir)
        rc = main(["status", "--json"])
        assert rc == 0
        assert "no longer read" not in capsys.readouterr().err

    def test_agreement_is_by_resolution_not_by_string(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """A value naming a *subdirectory* of the vault still addressed that
        vault under 0.2.x — the same detector ran on it. Comparing raw strings
        warned this user, who has nothing to fix. Agreement is decided by what
        the dead name would have resolved to, not by how it was spelled."""
        sub = vault_dir / "projects" / "foo"
        sub.mkdir(parents=True)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(sub))
        monkeypatch.chdir(sub)
        rc = main(["status", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["data"]["root"] == str(vault_dir)
        assert "no longer read" not in captured.err

    def test_agreement_survives_a_case_insensitive_filesystem(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """On macOS's default case-insensitive APFS, `.../VAULT` and
        `.../vault` are the same directory (same inode). A string compare
        warned; resolving through the detector does not. Skipped where the
        filesystem really is case-sensitive."""
        shouty = vault_dir.parent / vault_dir.name.upper()
        if vault_dir.name == shouty.name or not shouty.is_dir():
            pytest.skip("case-sensitive filesystem — no aliasing to test")
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(shouty))
        monkeypatch.chdir(vault_dir)
        rc = main(["status", "--json"])
        assert rc == 0
        assert "no longer read" not in capsys.readouterr().err

    @pytest.mark.parametrize(
        "bad_value",
        ["~nosuchuser42/vault", "relative/not/absolute", "~" * 300, ""],
        ids=["unexpandable-user", "relative", "absurd-tilde", "empty"],
    )
    def test_hostile_removed_var_never_raises(
        self, vault_dir: Path, monkeypatch, capsys, bad_value: str
    ):
        """Whatever the dead name holds, resolution must not explode.

        The comparison behind the softener runs on the hook path, *outside*
        `run_hook`'s fail-open guard. `~nouser/x` raises RuntimeError from
        `expanduser()`, which turned a stale dotfile into a broken session
        start — a louder version of the silent failure the hint exists to
        prevent. Whether a given value warns is decided by resolution (see the
        agreement tests); what this pins is that none of them raise.
        """
        monkeypatch.chdir(vault_dir)  # a vault DOES resolve — the risky branch
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", bad_value)
        rc = main(["status", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["data"]["root"] == str(vault_dir)
        assert "Traceback" not in captured.err

    def test_unresolvable_removed_var_shadows(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """A value that cannot name any vault cannot name the one we used, so
        it shadows and warns — the dotfile-straggler case."""
        monkeypatch.chdir(vault_dir)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", "~nosuchuser42/vault")
        rc = main(["status", "--json"])
        assert rc == 0
        assert "no longer read" in capsys.readouterr().err

    def test_hook_stays_fail_open_on_unparseable_removed_var(
        self, vault_dir: Path, monkeypatch, capsys
    ):
        """The same input on the hook path: exit 0, clean stdout, no traceback."""
        import io

        monkeypatch.chdir(vault_dir)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", "~nosuchuser42/vault")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["hook", "session-start"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert "RuntimeError" not in captured.err

    def test_hook_path_warns_and_stays_fail_open(
        self, vault_dir: Path, tmp_path: Path, monkeypatch, capsys
    ):
        """A dotfile still exporting the dead name loses every session brief.
        The hook must still exit 0 with clean stdout (fail-open + §Channels),
        but the reason belongs on stderr — not only in a log nobody reads."""
        import io

        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        monkeypatch.setenv("CLAUDRON_VAULT", str(vault_dir))
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["hook", "session-start"])
        assert rc == 0  # fail-open, always
        captured = capsys.readouterr()
        assert captured.out == ""  # injected verbatim — must stay clean
        assert "no longer read" in captured.err

    def test_no_hint_when_removed_alias_unset(
        self, tmp_path: Path, monkeypatch, capsys, no_vault_env
    ):
        """No dead var set ⇒ the plain no-vault message, unchanged."""
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(outside)
        with pytest.raises(SystemExit) as exc_info:
            main(["status"])
        assert exc_info.value.code == 3
        err = capsys.readouterr().err
        assert "no vault found" in err
        assert "no longer read" not in err

    def test_walk_up_unchanged_when_no_env(
        self, vault_dir: Path, monkeypatch, capsys, no_vault_env
    ):
        """Neither var set ⇒ walk-up from CWD, exactly as before."""
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
            # The write door too: provenance fields are carried inside `data`,
            # so adding them must not have grown the envelope a fleet parses.
            ["--vault", str(vault_dir), "capture", "--json", "--type",
             "knowledge", "--title", "Envelope Shape", "--body", "B.",
             "--owner", "bot", "--source-url", "https://x",
             "--source-type", "url"],
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


def _env_table() -> list[list[str]]:
    return doc_table(CONTRACT, "ENVIRONMENT")


class _RecordingEnv(dict):
    """An `os.environ` stand-in that remembers which names were looked up.

    Records the three *single-name* access forms — `.get`, `env["X"]` and
    `"X" in env` — because a resolver using any of them would otherwise be
    invisible to the gate (verified: `.get`-only was). Bulk reads
    (`dict(env)`, `.copy()`, `.items()`) are **not** recorded and would slip
    past; that shape is not how a resolver reads a named variable, so the gate
    is scoped to what it can honestly promise rather than pretending
    otherwise.
    """

    def __init__(self, base):
        super().__init__(base)
        self.queried: list[str] = []

    def get(self, key, default=None):
        self.queried.append(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.queried.append(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.queried.append(key)
        return super().__contains__(key)

    def claudron_lookups(self) -> list[str]:
        """Queried `CLAUDRON_*` names, in order, de-duplicated."""
        seen: dict[str, None] = {}
        for key in self.queried:
            if key.startswith("CLAUDRON_"):
                seen.setdefault(key)
        return list(seen)


class TestEnvironmentDocParity:
    """CLI_CONTRACT §Environment is the ONE normative statement of the
    vault-address contract (boundary spec §10.4 contract #4). The engine's
    resolution ladder and the table cannot drift: consumers on three repos
    build against the table, and the last time doc and code disagreed the
    two names resolved different vaults (Claudron #30)."""

    def test_env_rows_match_code_ladder_in_order(self):
        documented = tuple(
            code_values(row[1])[0] for row in _env_table() if row[2] == "env"
        )
        assert documented == VAULT_ENV_VARS

    def test_removed_rows_match_removal_constant(self):
        documented = tuple(
            code_values(row[1])[0]
            for row in _env_table()
            if row[2].startswith("removed")
        )
        assert documented == REMOVED_VAULT_ENV_VARS

    def test_removal_version_matches_the_table(self):
        """The removal version appears in four places (the constant, the table
        cell, the migration prose, the CHANGELOG). Pin the two that a machine
        consumer reads: the runtime hint's version and the table's."""
        import re

        from claudron.cli import _ALIAS_REMOVED_IN

        cells = [row[2] for row in _env_table() if row[2].startswith("removed")]
        assert cells, "no removed row in the table"
        for cell in cells:
            found = re.search(r"(\d+\.\d+\.\d+)", cell)
            assert found, f"removed row states no version: {cell}"
            assert found.group(1) == _ALIAS_REMOVED_IN

    def test_resolver_reads_exactly_the_contract_env_names(
        self, tmp_path: Path, monkeypatch, no_vault_env
    ):
        """The hard cut, pinned by what the resolver actually *reads*.

        Grepping `_detect_vault`'s source is not enough: re-adding the removed
        name by iterating `REMOVED_VAULT_ENV_VARS` leaves no literal behind and
        slips a text check (verified — it does). Recording the lookups catches
        both spellings, and pins the ladder to the table in the same assert.
        """
        recorder = _RecordingEnv(os.environ)
        monkeypatch.setattr(os, "environ", recorder)
        monkeypatch.chdir(tmp_path)  # nothing to walk up to

        _detect_vault(SimpleNamespace(vault=None))

        assert recorder.claudron_lookups() == list(VAULT_ENV_VARS)

    def test_flag_beats_env(self, tmp_path: Path, monkeypatch):
        """Row 1 actually outranks row 2, pinned by resolution not by reading.

        The other gates in this class pin the table's *env* rung — that the
        names and their order match `VAULT_ENV_VARS`. None of them exercised
        the top row, so "the first that yields a path wins" was documented and
        untested precisely where disagreement is most expensive: two real
        vaults, both resolvable, and the caller's explicit answer losing to an
        ambient one (Claudron #81).
        """
        flagged, ambient = tmp_path / "flagged", tmp_path / "ambient"
        for root in (flagged, ambient):
            (root / "_shared").mkdir(parents=True)
        monkeypatch.setenv(VAULT_ENV_VARS[0], str(ambient))
        monkeypatch.chdir(ambient)  # and the walk-up rung agrees with the env

        resolved = _detect_vault(SimpleNamespace(vault=str(flagged)))

        assert resolved is not None and resolved.root == flagged.resolve()

    def test_table_is_precedence_ordered(self):
        """Rows 1..N are the live ladder in precedence order; removed rows
        carry no rank."""
        rows = _env_table()
        ranks = [row[0] for row in rows if row[0].isdigit()]
        assert ranks == [str(i) for i in range(1, len(ranks) + 1)]
        assert rows[0][2] == "flag"  # --vault always wins
        assert rows[len(ranks) - 1][2] == "discovery"  # walk-up is last

    def test_flags_section_defers_to_the_table(self):
        """§Flags must point at §Environment, never restate the order (R3
        applied at home — one normative statement, one parity gate)."""
        flags = section(CONTRACT, "Flags")
        assert "§Environment" in flags
        assert "CLAUDRON_VAULT_PATH" not in flags

    def test_integration_guide_names_only_contract_vars(self):
        """INTEGRATION.md's 'Resolve a vault' section gives readers the short
        form, so it *can* drift from the table. Gate it: every env name it
        spells there must be a live contract name. A removed name reappearing
        in the front door is the #30 failure re-created for integrators."""
        resolve = section("docs/INTEGRATION.md", "Resolve a vault")
        assert "§Environment" in resolve  # still points at the normative text
        spelled = {v for v in code_values(resolve) if v.startswith("CLAUDRON_")}
        assert spelled == set(VAULT_ENV_VARS)
