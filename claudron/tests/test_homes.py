"""Memory homes (#200 §2): what a note is about decides its type, sections, place and policy.

The contract: the five new home types (plus `decision`) are ordinary types; a
home files one folder level per `kind` and `new` scaffolds its sections; the
closed relation set is indexed and `part_of` draws the INDEX.md tree; a
`person` note lives only in the personal tier, takes only user-asserted
facts, and `person/me.md` is injected into every brief. `knowledge` and
`runbook` stay valid: nothing migrates.
"""

from __future__ import annotations

import io
import json

import pytest

from claudron.amend import AmendError, amend
from claudron.cli import main
from claudron.knowledge import ensure_index
from claudron.navigation import render_navigation
from claudron.schema import HOMES, TYPES
from claudron.session import recall, render_brief
from claudron.subjects import subjects
from claudron.vault import PERSONAL_HUB, detect, note_tiers


def _new(vault_dir, capsys, *args) -> str:
    assert main(["--vault", str(vault_dir), "new", *args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)["data"]["path"]


def test_every_home_is_a_type_with_its_sections():
    assert set(HOMES) <= set(TYPES)
    assert HOMES["entity"][:2] == ("Summary", "Facts")


def test_a_home_files_one_level_per_kind_and_starts_with_its_sections(vault_dir, capsys):
    path = _new(vault_dir, capsys, "entity", "Payments API", "--kind", "API")
    assert path.endswith("_shared/entity/api/payments-api.md")
    text = open(path).read()
    assert "kind: API" in text and "## Summary" in text and "## Open questions" in text


def test_a_home_without_a_kind_files_at_the_home(vault_dir, capsys):
    assert _new(vault_dir, capsys, "practice", "Squash merges").endswith("_shared/practice/squash-merges.md")


def test_capture_takes_kind_and_relations_and_the_index_carries_them(vault_dir, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "type": "concept", "title": "Idempotency key", "body": "A key that makes a retry safe.", "owner": "t",
        "kind": "pattern", "relations": {"part_of": ["[[Payments API]]"], "related": "Retries", "nope": ["x"]}})))
    assert main(["--vault", str(vault_dir), "capture", "--stdin", "--json"]) == 0
    capsys.readouterr()
    (entry,) = [e for e in ensure_index(detect(vault_dir))["entries"] if e["title"] == "Idempotency key"]
    assert entry["path"] == "_shared/concept/pattern/idempotency-key.md" and entry["kind"] == "pattern"
    assert entry["relations"] == {"part_of": ["Payments API"], "related": ["Retries"]}


def test_subjects_filter_by_home_and_kind(vault_dir, capsys):
    _new(vault_dir, capsys, "entity", "Payments API", "--kind", "api")
    _new(vault_dir, capsys, "entity", "Billing DB", "--kind", "dataset")
    assert [s.title for s in subjects(detect(vault_dir), note_type="entity", kind="API")] == ["Payments API"]
    assert main(["--vault", str(vault_dir), "subjects", "--home", "entity", "--kind", "dataset", "--json"]) == 0
    assert [s["title"] for s in json.loads(capsys.readouterr().out)["data"]["subjects"]] == ["Billing DB"]


def test_a_person_lives_only_in_the_personal_tier(vault_dir, capsys):
    path = _new(vault_dir, capsys, "person", "Dana")
    assert path.endswith(f"{PERSONAL_HUB}/person/dana.md")
    assert main(["--vault", str(vault_dir), "new", "person", "Sam", "--project", "webapp"]) == 2
    assert "personal tier" in capsys.readouterr().err
    assert ("personal" in {tier for _, tier in note_tiers(detect(vault_dir))})


def test_a_person_takes_only_user_asserted_facts(vault_dir, capsys):
    path = _new(vault_dir, capsys, "person", "Dana")
    vault = detect(vault_dir)
    req = {"op": "append_fact", "section": "Preferences", "fact": "Prefers async reviews.",
           "evidence": {"ref": "session:a:1", "asserted_by": "agent"}}
    with pytest.raises(AmendError, match="user-asserted"):
        amend(vault, detect(vault_dir).root / path.split(str(vault_dir) + "/", 1)[1], req, no_commit=True)
    ok = {**req, "evidence": {"ref": "session:a:1", "asserted_by": "user"}}
    assert amend(vault, vault.root / path.split(str(vault_dir) + "/", 1)[1], ok, no_commit=True).action == "updated"


def _me(vault_dir, extra=""):
    me = vault_dir / PERSONAL_HUB / "person" / "me.md"
    me.parent.mkdir(parents=True, exist_ok=True)
    me.write_text("---\ntitle: Me\ntype: person\nstatus: current\nowner: t\ncreated: 2026-09-01\n" + extra
                  + "---\n\n# Me\n\nI review on Tuesdays.\n")


def test_person_me_is_injected_into_every_brief(vault_dir):
    _me(vault_dir)
    data = recall(detect(vault_dir))
    assert data["me"] == "I review on Tuesdays." and "## About me" in render_brief(data)


def test_an_external_draft_never_speaks_for_the_operator(vault_dir):
    _me(vault_dir, "maturity: draft\nsource_type: session\n")
    assert recall(detect(vault_dir))["me"] is None


def test_part_of_draws_the_index_tree(vault_dir, capsys, monkeypatch):
    _new(vault_dir, capsys, "entity", "Payments API", "--kind", "api")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
        "type": "entity", "title": "Refunds endpoint", "body": "POST /refunds.", "owner": "t", "kind": "api",
        "relations": {"part_of": ["Payments API"]}})))
    main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
    capsys.readouterr()
    vault = detect(vault_dir)
    text = render_navigation(vault, vault.shared / "entity" / "api", ensure_index(vault)).text
    lines = [ln for ln in text.splitlines() if "](" in ln]
    assert lines[0].startswith("- [Payments API]") and lines[1].startswith("  - [Refunds endpoint]")


def test_the_engine_declares_the_capability(vault_dir, capsys):
    main(["--vault", str(vault_dir), "status", "--json"])
    assert "memory-homes" in json.loads(capsys.readouterr().out)["data"]["capabilities"]
