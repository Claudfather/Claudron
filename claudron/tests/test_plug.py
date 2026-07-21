"""Tests for plug/unplug/config commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main


@pytest.fixture
def claudlobby_root(tmp_path: Path) -> Path:
    """Fake claudlobby root with library/ + lib/ markers."""
    root = tmp_path / "claudlobby"
    (root / "library").mkdir(parents=True)
    (root / "lib").mkdir()
    return root


@pytest.fixture
def vault_for_plug(tmp_path: Path) -> Path:
    """Vault to plug into claudlobby."""
    vault = tmp_path / "vault"
    (vault / "_shared" / "knowledge").mkdir(parents=True)
    return vault


class TestPlug:
    def test_plug_writes_config(
        self, claudlobby_root: Path, vault_for_plug: Path, capsys
    ):
        rc = main(
            [
                "plug",
                str(vault_for_plug),
                "--claudlobby",
                str(claudlobby_root),
            ]
        )
        assert rc == 0
        config = claudlobby_root / ".claudron"
        assert config.is_file()
        content = config.read_text()
        assert f"vault={vault_for_plug}" in content
        out = capsys.readouterr().out
        assert "plugged" in out

    def test_plug_not_a_vault(self, claudlobby_root: Path, tmp_path: Path, capsys):
        not_vault = tmp_path / "nope"
        not_vault.mkdir()
        rc = main(
            [
                "plug",
                str(not_vault),
                "--claudlobby",
                str(claudlobby_root),
            ]
        )
        assert rc == 2
        assert "not a vault" in capsys.readouterr().err

    def test_plug_warns_on_overwrite(
        self, claudlobby_root: Path, vault_for_plug: Path, tmp_path: Path, capsys
    ):
        # First plug
        main(["plug", str(vault_for_plug), "--claudlobby", str(claudlobby_root)])
        capsys.readouterr()

        # Second plug with different vault
        vault2 = tmp_path / "vault2"
        (vault2 / "_shared").mkdir(parents=True)
        rc = main(["plug", str(vault2), "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "replacing existing config" in out
        assert str(vault_for_plug) in out

    def test_plug_no_claudlobby_root(
        self, vault_for_plug: Path, tmp_path: Path, capsys
    ):
        nowhere = tmp_path / "nowhere"
        nowhere.mkdir()
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "plug",
                    str(vault_for_plug),
                    "--claudlobby",
                    str(nowhere),
                ]
            )
        assert exc_info.value.code == 3  # environment error (CLI contract 0.2.0)
        err = capsys.readouterr().err
        assert "could not find claudlobby root" in err
        assert "plug requires a claudlobby installation" in err

    def test_plug_shared_vault(self, claudlobby_root: Path, tmp_path: Path, capsys):
        """plug accepts vaults using shared/ (no underscore)."""
        vault = tmp_path / "shared-vault"
        (vault / "shared" / "knowledge").mkdir(parents=True)
        rc = main(["plug", str(vault), "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        assert "plugged" in capsys.readouterr().out


class TestUnplug:
    def test_unplug_removes_config(
        self, claudlobby_root: Path, vault_for_plug: Path, capsys
    ):
        # First plug
        main(
            [
                "plug",
                str(vault_for_plug),
                "--claudlobby",
                str(claudlobby_root),
            ]
        )
        capsys.readouterr()

        # Then unplug
        rc = main(["unplug", "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        assert not (claudlobby_root / ".claudron").exists()
        assert "unplugged" in capsys.readouterr().out

    def test_unplug_no_config(self, claudlobby_root: Path, capsys):
        rc = main(["unplug", "--claudlobby", str(claudlobby_root)])
        assert rc == 1
        assert "no .claudron config" in capsys.readouterr().err


class TestConfig:
    def test_config_shows_resolved(
        self, claudlobby_root: Path, vault_for_plug: Path, capsys
    ):
        main(
            [
                "plug",
                str(vault_for_plug),
                "--claudlobby",
                str(claudlobby_root),
            ]
        )
        capsys.readouterr()

        rc = main(["config", "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert str(claudlobby_root) in out
        assert str(vault_for_plug) in out

    def test_config_json(self, claudlobby_root: Path, vault_for_plug: Path, capsys):
        main(
            [
                "plug",
                str(vault_for_plug),
                "--claudlobby",
                str(claudlobby_root),
            ]
        )
        capsys.readouterr()

        rc = main(["config", "--json", "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "config"
        assert env["data"]["claudlobby_root"] == str(claudlobby_root)
        assert env["data"]["vault"] == str(vault_for_plug)

    def test_config_not_plugged(self, claudlobby_root: Path, capsys):
        rc = main(["config", "--claudlobby", str(claudlobby_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "not plugged" in out


class TestTreeWalkDeprecation:
    """The second R5 violation (boundary spec §10.2: "the engine never knows a
    consumer by name"). `_detect_claudlobby_root` infers a consumer from its
    tree shape (`library/` + `lib/`); the declared alternative — `--claudlobby`
    — already exists, so the walk is deprecated here and removed on the F3
    schedule. Deprecate-only: resolution behavior is unchanged."""

    def test_tree_walk_resolution_warns(
        self, claudlobby_root: Path, vault_for_plug: Path, monkeypatch, capsys
    ):
        monkeypatch.chdir(claudlobby_root)
        rc = main(["plug", str(vault_for_plug)])
        assert rc == 0
        err = capsys.readouterr().err
        assert "deprecated" in err
        assert "--claudlobby" in err
        assert (claudlobby_root / ".claudron").is_file()  # still resolved

    def test_explicit_flag_is_silent(
        self, claudlobby_root: Path, vault_for_plug: Path, monkeypatch, capsys
    ):
        monkeypatch.chdir(claudlobby_root)  # walk would succeed — flag preempts it
        rc = main([
            "plug", str(vault_for_plug), "--claudlobby", str(claudlobby_root),
        ])
        assert rc == 0
        assert "deprecated" not in capsys.readouterr().err

    def test_config_warns_on_tree_walk(
        self, claudlobby_root: Path, monkeypatch, capsys
    ):
        """Every command sharing the helper warns — `config` reads the root
        through the same walk `plug` writes through."""
        monkeypatch.chdir(claudlobby_root)
        rc = main(["config"])
        assert rc == 0
        assert "deprecated" in capsys.readouterr().err

    def test_no_warning_when_walk_finds_nothing(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        """A failed walk emits the not-found error, not a deprecation for a
        path that was never taken."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        rc = main(["config"])
        assert rc == 0
        assert "deprecated" not in capsys.readouterr().err
