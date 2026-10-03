"""`claudron contract`: the machine-readable contract consumers keep a copy of."""

from __future__ import annotations

import json

from claudron import CAPABILITIES
from claudron.cli import main
from claudron.contract import CONTRACT_VERSION, contract
from claudron.schema import HOMES, STATUS_VOCAB, TYPE_DIRS

from .doc_parity import section


def _entry() -> str:
    """CLI_CONTRACT's `contract` bullet, up to the next bullet."""
    text = section("docs/CLI_CONTRACT.md", "Command-specific contracts")
    start = text.index("- `contract [--json]`")
    end = text.find("\n- `", start + 1)
    return text[start:end if end != -1 else None]


def _cli_payload(argv: list[str], tmp_path, monkeypatch, capsys) -> dict:
    monkeypatch.chdir(tmp_path)  # no vault anywhere above
    monkeypatch.delenv("CLAUDRON_VAULT_PATH", raising=False)
    assert main(argv) == 0
    return json.loads(capsys.readouterr().out)


class TestPayload:
    def test_it_carries_no_engine_version(self):
        """A consumer's copy changes when the contract does, not on every release."""
        assert "engine_version" not in contract()
        assert contract()["contract_version"] == CONTRACT_VERSION == 1

    def test_it_declares_its_own_capability(self):
        assert contract()["capabilities"] == list(CAPABILITIES)
        assert "contract" in CAPABILITIES

    def test_the_mappings_keep_the_schemas_order(self):
        c = contract()
        assert list(c["homes"]) == list(HOMES) and list(c["statuses"]) == list(STATUS_VOCAB)
        assert c["type_dirs"] == TYPE_DIRS
        assert all(c["homes"][h] == list(s) for h, s in HOMES.items())

    def test_every_type_has_a_status_vocabulary_and_a_folder(self):
        c = contract()
        assert set(c["statuses"]) == set(c["types"]) == set(c["type_dirs"])
        for vocab in c["statuses"].values():
            assert vocab["default"] in vocab["canonical"]
            assert set(vocab["terminal"]) <= set(vocab["canonical"])

    def test_the_documented_keys_are_the_payload_keys(self):
        """CLI_CONTRACT names the payload's keys: a key added or dropped here must be documented there."""
        entry = _entry()
        braces = entry[entry.index("`{") + 2:entry.index("}`")]
        assert [k.strip() for k in braces.replace("\n", " ").split(",")] == list(contract())


class TestCli:
    def test_json_is_the_envelope_and_needs_no_vault(self, tmp_path, monkeypatch, capsys):
        env = _cli_payload(["contract", "--json"], tmp_path, monkeypatch, capsys)
        assert env["ok"] is True and env["command"] == "contract"
        assert env["data"] == contract()
        # dict equality ignores order: check it survives serialization
        assert list(env["data"]["homes"]) == list(HOMES)
        assert list(env["data"]["statuses"]) == list(STATUS_VOCAB)
        assert list(env["data"]) == list(contract())

    def test_text_mode_prints_the_payload_unwrapped(self, tmp_path, monkeypatch, capsys):
        assert _cli_payload(["contract"], tmp_path, monkeypatch, capsys) == contract()
