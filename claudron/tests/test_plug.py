"""Tests for plug/unplug/config: the .claudron bridge file at a declared root."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main


@pytest.fixture
def consumer_root(tmp_path: Path) -> Path:
    """A consumer's root: any directory the caller names with --root."""
    root = tmp_path / "consumer"
    root.mkdir()
    return root


@pytest.fixture
def plugged(consumer_root: Path, empty_vault: Path, capsys) -> Path:
    """A consumer root already plugged into ``empty_vault``."""
    assert main(["plug", str(empty_vault), "--root", str(consumer_root)]) == 0
    capsys.readouterr()
    return consumer_root


class TestPlug:
    def test_plug_writes_config(self, consumer_root: Path, empty_vault: Path, capsys):
        rc = main(["plug", str(empty_vault), "--root", str(consumer_root)])
        assert rc == 0
        config = consumer_root / ".claudron"
        assert config.is_file()
        assert f"vault={empty_vault}" in config.read_text()
        assert "plugged" in capsys.readouterr().out

    def test_plug_not_a_vault(self, consumer_root: Path, tmp_path: Path, capsys):
        not_vault = tmp_path / "nope"
        not_vault.mkdir()
        rc = main(["plug", str(not_vault), "--root", str(consumer_root)])
        assert rc == 2
        assert "not a vault" in capsys.readouterr().err

    def test_plug_warns_on_overwrite(
        self, plugged: Path, empty_vault: Path, shared_vault: Path, capsys
    ):
        rc = main(["plug", str(shared_vault), "--root", str(plugged)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "replacing existing config" in out
        assert str(empty_vault) in out

    def test_plug_root_must_be_a_directory(
        self, empty_vault: Path, tmp_path: Path, capsys
    ):
        missing = tmp_path / "missing"
        with pytest.raises(SystemExit) as exc_info:
            main(["plug", str(empty_vault), "--root", str(missing)])
        assert exc_info.value.code == 2  # usage error (CLI_CONTRACT.md)
        assert "not a directory" in capsys.readouterr().err
        assert not missing.exists()

    def test_plug_shared_vault(self, consumer_root: Path, shared_vault: Path, capsys):
        """plug accepts vaults using shared/ (no underscore)."""
        rc = main(["plug", str(shared_vault), "--root", str(consumer_root)])
        assert rc == 0
        assert "plugged" in capsys.readouterr().out


class TestUnplug:
    def test_unplug_removes_config(self, plugged: Path, capsys):
        rc = main(["unplug", "--root", str(plugged)])
        assert rc == 0
        assert not (plugged / ".claudron").exists()
        assert "unplugged" in capsys.readouterr().out

    def test_unplug_no_config(self, consumer_root: Path, capsys):
        rc = main(["unplug", "--root", str(consumer_root)])
        assert rc == 1
        assert "no .claudron config" in capsys.readouterr().err


class TestConfig:
    def test_config_shows_resolved(self, plugged: Path, empty_vault: Path, capsys):
        rc = main(["config", "--root", str(plugged)])
        assert rc == 0
        out = capsys.readouterr().out
        assert str(plugged) in out
        assert str(empty_vault) in out

    def test_config_json(self, plugged: Path, empty_vault: Path, capsys):
        rc = main(["config", "--json", "--root", str(plugged)])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "config"
        assert env["data"]["consumer_root"] == str(plugged)
        assert env["data"]["vault"] == str(empty_vault)
        assert env["data"]["config_file"] == str(plugged / ".claudron")

    def test_config_not_plugged(self, consumer_root: Path, capsys):
        rc = main(["config", "--root", str(consumer_root)])
        assert rc == 0
        assert "not plugged" in capsys.readouterr().out


class TestDeclaredRoot:
    """The consumer root is declared with --root, never discovered (#243)."""

    @pytest.mark.parametrize("argv", [["plug", "VAULT"], ["unplug"], ["config"]])
    def test_root_is_required_even_inside_a_consumer_shaped_tree(
        self, argv, empty_vault: Path, tmp_path: Path, monkeypatch, capsys
    ):
        shaped = tmp_path / "shaped"  # the tree shape the removed walk looked for
        (shaped / "library").mkdir(parents=True)
        (shaped / "lib").mkdir()
        monkeypatch.chdir(shaped)
        argv = [str(empty_vault) if a == "VAULT" else a for a in argv]
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2  # usage error: --root is required
        assert "--root" in capsys.readouterr().err
        assert not (shaped / ".claudron").exists()

    def test_the_consumer_named_flag_is_gone(
        self, consumer_root: Path, empty_vault: Path, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["plug", str(empty_vault), "--root", str(consumer_root),
                  "--claudlobby", str(consumer_root)])
        assert exc_info.value.code == 2
        assert "unrecognized arguments: --claudlobby" in capsys.readouterr().err
        assert not (consumer_root / ".claudron").exists()

    def test_migrate_is_gone(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["migrate", "--fleet", "f"])
        assert exc_info.value.code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_the_engine_declares_the_capability(self):
        from claudron import CAPABILITIES

        assert "declared-root" in CAPABILITIES
