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
def vault_for_plug(tmp_path: Path) -> Path:
    """Vault to plug into a consumer root."""
    vault = tmp_path / "vault"
    (vault / "_shared" / "knowledge").mkdir(parents=True)
    return vault


class TestPlug:
    def test_plug_writes_config(
        self, consumer_root: Path, vault_for_plug: Path, capsys
    ):
        rc = main(["plug", str(vault_for_plug), "--root", str(consumer_root)])
        assert rc == 0
        config = consumer_root / ".claudron"
        assert config.is_file()
        content = config.read_text()
        assert f"vault={vault_for_plug}" in content
        out = capsys.readouterr().out
        assert "plugged" in out

    def test_plug_not_a_vault(self, consumer_root: Path, tmp_path: Path, capsys):
        not_vault = tmp_path / "nope"
        not_vault.mkdir()
        rc = main(["plug", str(not_vault), "--root", str(consumer_root)])
        assert rc == 2
        assert "not a vault" in capsys.readouterr().err

    def test_plug_warns_on_overwrite(
        self, consumer_root: Path, vault_for_plug: Path, tmp_path: Path, capsys
    ):
        # First plug
        main(["plug", str(vault_for_plug), "--root", str(consumer_root)])
        capsys.readouterr()

        # Second plug with different vault
        vault2 = tmp_path / "vault2"
        (vault2 / "_shared").mkdir(parents=True)
        rc = main(["plug", str(vault2), "--root", str(consumer_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "replacing existing config" in out
        assert str(vault_for_plug) in out

    def test_plug_root_must_be_a_directory(
        self, vault_for_plug: Path, tmp_path: Path, capsys
    ):
        missing = tmp_path / "missing"
        with pytest.raises(SystemExit) as exc_info:
            main(["plug", str(vault_for_plug), "--root", str(missing)])
        assert exc_info.value.code == 2  # usage error (CLI_CONTRACT.md)
        assert "not a directory" in capsys.readouterr().err
        assert not missing.exists()

    def test_plug_shared_vault(self, consumer_root: Path, tmp_path: Path, capsys):
        """plug accepts vaults using shared/ (no underscore)."""
        vault = tmp_path / "shared-vault"
        (vault / "shared" / "knowledge").mkdir(parents=True)
        rc = main(["plug", str(vault), "--root", str(consumer_root)])
        assert rc == 0
        assert "plugged" in capsys.readouterr().out


class TestUnplug:
    def test_unplug_removes_config(
        self, consumer_root: Path, vault_for_plug: Path, capsys
    ):
        # First plug
        main(["plug", str(vault_for_plug), "--root", str(consumer_root)])
        capsys.readouterr()

        # Then unplug
        rc = main(["unplug", "--root", str(consumer_root)])
        assert rc == 0
        assert not (consumer_root / ".claudron").exists()
        assert "unplugged" in capsys.readouterr().out

    def test_unplug_no_config(self, consumer_root: Path, capsys):
        rc = main(["unplug", "--root", str(consumer_root)])
        assert rc == 1
        assert "no .claudron config" in capsys.readouterr().err


class TestConfig:
    def test_config_shows_resolved(
        self, consumer_root: Path, vault_for_plug: Path, capsys
    ):
        main(["plug", str(vault_for_plug), "--root", str(consumer_root)])
        capsys.readouterr()

        rc = main(["config", "--root", str(consumer_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert str(consumer_root) in out
        assert str(vault_for_plug) in out

    def test_config_json(self, consumer_root: Path, vault_for_plug: Path, capsys):
        main(["plug", str(vault_for_plug), "--root", str(consumer_root)])
        capsys.readouterr()

        rc = main(["config", "--json", "--root", str(consumer_root)])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "config"
        assert env["data"]["root"] == str(consumer_root)
        assert env["data"]["vault"] == str(vault_for_plug)
        assert env["data"]["config_file"] == str(consumer_root / ".claudron")

    def test_config_not_plugged(self, consumer_root: Path, capsys):
        rc = main(["config", "--root", str(consumer_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "not plugged" in out


class TestDeclaredRoot:
    """The consumer root is declared, never discovered (#243). The engine used
    to walk up for a `library/` + `lib/` tree shape, which a current Claudlobby
    checkout no longer has, and to take the root under a flag named for that
    consumer. Both were boundary violations (`claudron/CLAUDE.md`: no consumer
    names or tree shapes), and the walk had become a breakage too."""

    @pytest.mark.parametrize("argv", [["plug", "VAULT"], ["unplug"], ["config"]])
    def test_root_is_required_even_inside_a_consumer_shaped_tree(
        self, argv, vault_for_plug: Path, tmp_path: Path, monkeypatch, capsys
    ):
        shaped = tmp_path / "shaped"
        (shaped / "library").mkdir(parents=True)
        (shaped / "lib").mkdir()
        monkeypatch.chdir(shaped)
        argv = [str(vault_for_plug) if a == "VAULT" else a for a in argv]
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2  # usage error: --root is required
        assert "--root" in capsys.readouterr().err
        assert not (shaped / ".claudron").exists()

    def test_the_consumer_named_flag_is_gone(
        self, consumer_root: Path, vault_for_plug: Path
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(["plug", str(vault_for_plug), "--claudlobby", str(consumer_root)])
        assert exc_info.value.code == 2
        assert not (consumer_root / ".claudron").exists()

    def test_migrate_is_gone(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["migrate", "--fleet", "f"])
        assert exc_info.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
