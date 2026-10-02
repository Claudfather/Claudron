"""Trust-aware reads (#200 §1): maturity × origin decides what lookup and recall show.

The contract: every trusted note ranks above every draft, whatever the score;
an authored draft is shown and labelled; an external draft (from the web or a
session transcript) is withheld from default lookup and only ever appears in
recall's capped Unverified block — never among the notes a session treats as
context. The fixture gives the drafts the *top* score on purpose: ranking
alone would put them first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.knowledge import lookup
from claudron.schema import trust_class
from claudron.session import UNVERIFIED_LIMIT, recall, render_brief
from claudron.vault import IDENTITY_FILE, Vault, detect, identity_text

from .conftest import _identify


def _note(root: Path, stem: str, title: str, *, maturity: str | None = None, source_type: str | None = None,
          source_url: str | None = None, tags: tuple[str, ...] = (), updated: str = "2026-09-01",
          body: str = "Rate limits reset hourly.") -> None:
    fm = [f"title: {json.dumps(title)}", "type: knowledge", "status: current", "owner: tester", f"created: {updated}",
          f"updated: {updated}", f"tags: [{', '.join(tags)}]"]
    fm += [f"maturity: {maturity}"] if maturity else []
    fm += [f"source_type: {source_type}"] if source_type else []
    fm += [f"source_url: {source_url}"] if source_url else []
    (root / "_shared" / "knowledge" / f"{stem}.md").write_text("---\n" + "\n".join(fm) + f"\n---\n\n{body}\n")


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    root = tmp_path / "vault"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    (root / "projects").mkdir()
    _identify(root)
    # A vault from before format 3, so `doctor --fix` still owes it m003.
    (root / IDENTITY_FILE).write_text(identity_text(root.name, "_shared", fmt=2))
    # Exact-title matches for "rate limits" score highest: give them to the drafts.
    _note(root, "web", "Rate Limits", maturity="draft", source_type="url", source_url="https://x.example/limits")
    _note(root, "harvested", "rate limits", maturity="draft", source_type="session",
          source_url="session:abc:3", updated="2026-09-03")
    _note(root, "legacy-harvest", "Rate limits", maturity="draft", source_type="inline",
          tags=("origin:session-harvest",), updated="2026-09-02")
    _note(root, "plan", "Rate limits rollout plan", maturity="draft")
    _note(root, "verified", "API notes: rate limits and quotas", maturity="verified")
    _note(root, "legacy", "Gateway rate limits overview")  # unrated: trusted
    return detect(root)


def _titles(results) -> list[str]:
    return [r.doc.title for r in results]


@pytest.mark.parametrize("maturity,source_type,expected", [
    ("verified", "url", "trusted"),
    ("canonical", "session", "trusted"),
    ("", "url", "trusted"),           # unrated legacy
    ("contested", "url", "trusted"),  # off the ladder reads as unrated
    ("draft", "", "draft"),
    ("draft", "file", "draft"),
    ("draft", "inline", "draft"),
    ("draft", "url", "external"),
    ("draft", "session", "external"),
])
def test_trust_class(maturity, source_type, expected):
    assert trust_class(maturity, source_type) == expected


def _migrate(vault) -> None:
    """m003 moves the pre-``session`` harvest tag to ``source_type: session``."""
    assert main(["--vault", str(vault.root), "doctor", "--fix", "--json"]) in (0, 1)


def test_doctor_m003_moves_tagged_harvest_drafts_to_source_type_session(vault, capsys):
    legacy = vault.root / "_shared" / "knowledge" / "legacy-harvest.md"
    assert "Rate limits" in _titles(lookup("rate limits", vault, limit=10))  # an authored draft until migrated
    _migrate(vault)
    capsys.readouterr()
    assert "source_type: session" in legacy.read_text()
    assert "Rate limits" not in _titles(lookup("rate limits", vault, limit=10))


def test_lookup_ranks_every_trusted_note_above_every_draft(vault):
    titles = _titles(lookup("rate limits", vault, limit=10))
    assert titles.index("API notes: rate limits and quotas") < titles.index("Rate limits rollout plan")
    assert titles.index("Gateway rate limits overview") < titles.index("Rate limits rollout plan")


def test_lookup_withholds_external_drafts_by_default(vault, capsys):
    _migrate(vault)
    titles = _titles(lookup("rate limits", vault, limit=10))
    assert "Rate Limits" not in titles and "rate limits" not in titles and "Rate limits" not in titles
    assert "Rate limits rollout plan" in titles  # an authored draft stays visible


def test_lookup_include_external_brings_them_back_still_after_the_trusted(vault, capsys):
    _migrate(vault)
    results = lookup("rate limits", vault, limit=10, include_external=True)
    trust = [r.doc.trust for r in results]
    assert trust.count("external") == 3
    assert trust.index("draft") > trust.index("trusted") and min(
        i for i, t in enumerate(trust) if t == "external") > max(i for i, t in enumerate(trust) if t == "trusted")


def test_recall_never_puts_an_external_draft_among_the_notes(vault, capsys):
    _migrate(vault)
    data = recall(vault, query="rate limits", limit=10)
    assert {n["trust"] for n in data["notes"]} <= {"trusted", "draft"}
    assert [n["title"] for n in data["unverified"]] == ["rate limits", "Rate limits", "Rate Limits"]  # newest first
    assert data["unverified"][0]["source_url"] == "session:abc:3"


def test_the_brief_shows_unverified_after_trusted_with_provenance_and_no_summary(vault):
    brief = render_brief(recall(vault, query="rate limits", limit=10))
    trusted, _, unverified = brief.partition("## Unverified")
    assert "rate limits rollout plan".lower() in trusted.lower() and "(knowledge, draft)" in trusted
    assert "Rate Limits" not in trusted.replace("Rate limits rollout plan", "")
    assert "from https://x.example/limits" in unverified and "Never cite one as fact" in unverified
    assert "Rate limits reset hourly" not in unverified  # the body never rides along


def test_the_unverified_block_is_capped(tmp_path):
    root = tmp_path / "v"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    (root / "projects").mkdir()
    _identify(root)
    for n in range(UNVERIFIED_LIMIT + 2):
        _note(root, f"web{n}", f"Rate limits {n}", maturity="draft", source_type="url", updated=f"2026-09-0{n + 1}")
    data = recall(detect(root), query="rate limits", limit=10)
    assert len(data["unverified"]) == UNVERIFIED_LIMIT and data["unverified_more"] == 2
    assert "… 2 more awaiting review" in render_brief(data)


def test_a_promoted_note_is_trusted_whatever_its_origin(vault):
    main(["--vault", str(vault.root), "promote", "_shared/knowledge/web.md", "--to", "verified", "--json"])
    assert "Rate Limits" in _titles(lookup("rate limits", vault, limit=10))


def test_lookup_json_carries_maturity_and_trust(vault, capsys):
    main(["--vault", str(vault.root), "lookup", "rate", "limits", "--limit", "10", "--include-external", "--json"])
    results = json.loads(capsys.readouterr().out)["data"]["results"]
    assert all({"maturity", "trust", "trusted"} <= set(r) for r in results)
    assert {r["trust"] for r in results} == {"trusted", "draft", "external"}
    assert all(r["trusted"] == (r["trust"] == "trusted") for r in results)


def test_lookup_text_labels_drafts(vault, capsys):
    main(["--vault", str(vault.root), "lookup", "rate", "limits", "--limit", "10", "--include-external"])
    out = capsys.readouterr().out
    assert "(draft)" in out and "(unverified draft)" in out


def test_capture_accepts_the_session_source_type(vault, capsys):
    main(["--vault", str(vault.root), "capture", "--type", "knowledge", "--title", "Harvested fact",
          "--body", "The deploy runs on Fridays.", "--source-type", "session", "--no-commit", "--json"])
    assert json.loads(capsys.readouterr().out)["data"]["action"] == "created"
    assert lookup("Harvested fact", vault) == []


def test_the_engine_declares_the_capability(capsys, vault):
    main(["--vault", str(vault.root), "status", "--json"])
    assert "trust-aware-reads" in json.loads(capsys.readouterr().out)["data"]["capabilities"]
