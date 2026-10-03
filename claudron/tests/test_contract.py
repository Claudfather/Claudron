"""`claudron contract`: the machine-readable contract consumers keep a copy of."""

from __future__ import annotations

import json
from pathlib import Path

from claudron import CAPABILITIES, __version__
from claudron.cli import main
from claudron.contract import CONTRACT_VERSION, contract
from claudron.schema import HOMES, MATURITY_VALUES, PERSON_DIR, RELATIONS, SOURCE_TYPES, TRUST_CLASSES, TYPES

CLI_CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "CLI_CONTRACT.md"


class TestPayload:
    def test_every_value_comes_from_the_module_that_owns_it(self):
        c = contract()
        assert c["contract_version"] == CONTRACT_VERSION == 1
        assert c["engine_version"] == __version__
        assert c["capabilities"] == list(CAPABILITIES)
        assert c["types"] == list(TYPES)
        assert c["homes"] == {h: list(s) for h, s in HOMES.items()}
        assert c["relations"] == list(RELATIONS)
        assert c["maturity"] == list(MATURITY_VALUES)
        assert c["source_types"] == list(SOURCE_TYPES)
        assert c["trust_classes"] == list(TRUST_CLASSES)
        assert c["person_dir"] == PERSON_DIR

    def test_it_is_plain_json_and_keeps_home_and_section_order(self):
        c = contract()
        assert json.loads(json.dumps(c)) == c
        assert list(c["homes"]) == list(HOMES)

    def test_it_declares_its_own_capability(self):
        assert "contract" in contract()["capabilities"]

    def test_the_documented_keys_are_the_payload_keys(self):
        """CLI_CONTRACT names the payload's keys: a key added or dropped here must be documented there."""
        text = CLI_CONTRACT.read_text(encoding="utf-8")
        entry = text[text.index("- `contract [--json]`"):]
        braces = entry[entry.index("`{") + 2:entry.index("}`")]
        documented = [k.strip() for k in braces.replace("\n", " ").split(",")]
        assert documented == list(contract())


class TestCli:
    def test_json_is_the_envelope_and_needs_no_vault(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)  # no vault anywhere above
        monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
        assert main(["contract", "--json"]) == 0
        env = json.loads(capsys.readouterr().out)
        assert env["ok"] is True and env["command"] == "contract"
        assert env["data"] == contract()

    def test_text_mode_prints_the_payload_unwrapped(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert main(["contract"]) == 0
        assert json.loads(capsys.readouterr().out) == contract()
