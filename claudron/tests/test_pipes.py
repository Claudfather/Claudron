"""The harvest pipes (#200 §4): subjects, resolve, amend, and one commit per run.

Mechanical, no model: ``subjects`` and ``resolve`` read the index and never
pick; ``amend`` files a fact where it is told, idempotently; a run's writes
land as one commit that ``revert-run`` undoes exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudron.amend import AmendError, amend, fact_id
from claudron.cli import main
from claudron.runs import RunError, commit_run, revert_run
from claudron.subjects import resolve, subjects
from claudron.vault import detect

from .test_capture import _cgit, git_vault  # noqa: F401 - the fixture

NOTE = """\
---
title: Deploy Pipeline
type: knowledge
status: current
owner: tester
created: 2026-09-01
updated: 2026-09-01
aliases: [ci deploys]
tags: [deploy]
---

# Deploy Pipeline

How code reaches production.

## Facts

## History
"""


@pytest.fixture
def vault(vault_dir: Path):
    (vault_dir / "_shared" / "knowledge" / "deploy-pipeline.md").write_text(NOTE)
    return detect(vault_dir)


def _ev(ref: str = "session:abc:3", **extra) -> dict:
    return {"ref": ref, "date": "2026-10-02", **extra}


def _note(vault) -> str:
    return (vault.root / "_shared" / "knowledge" / "deploy-pipeline.md").read_text()


def _path(vault) -> Path:
    return vault.root / "_shared" / "knowledge" / "deploy-pipeline.md"


def _sections(vault) -> list[str]:
    return next(s.sections for s in subjects(vault) if s.title == "Deploy Pipeline")


# --- subjects / resolve ---------------------------------------------------------------------------

def test_subjects_lists_live_notes_with_their_sections(vault):
    found = {s.title: s for s in subjects(vault)}
    assert found["Deploy Pipeline"].sections == ["Facts", "History"]
    assert found["Deploy Pipeline"].aliases == ["ci deploys"] and found["Deploy Pipeline"].type == "knowledge"


def test_subjects_filters_by_type(vault):
    assert {s.type for s in subjects(vault, note_type="knowledge")} == {"knowledge"}
    assert subjects(vault, note_type="plan") == []


@pytest.mark.parametrize("name,kind", [("Deploy Pipeline", "title"), ("ci deploys", "alias"),
                                       ("deploy-pipeline", "slug")])
def test_resolve_ranks_exact_alias_and_slug_matches(vault, name, kind):
    [best, *_] = resolve(vault, name)
    assert best.title == "Deploy Pipeline" and best.match_type == kind


def test_resolve_tries_the_aliases_too(vault):
    [best, *_] = resolve(vault, "the release flow", aliases=["ci deploys"])
    assert best.title == "Deploy Pipeline" and best.match_type == "alias"


def test_resolve_context_never_brings_in_a_note_on_its_own(vault):
    assert resolve(vault, "zzz-nothing", context="deploy pipeline production") == []


def test_resolve_cli_json(vault, capsys):
    assert main(["--vault", str(vault.root), "resolve", "--name", "Deploy Pipeline", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["candidates"][0]["path"] == "_shared/knowledge/deploy-pipeline.md"
    assert {"score", "match_type", "sections", "trust"} <= set(data["candidates"][0])


# --- amend ----------------------------------------------------------------------------------------

def test_append_fact_files_a_bullet_with_its_id_and_evidence(vault):
    result = amend(vault, _path(vault), {"op": "append_fact", "section": "Facts", "fact": "Deploys freeze on Fridays.",
                                          "evidence": _ev(asserted_by="user")}, no_commit=True)
    assert result.action == "updated" and result.outcome == "fact_added" and result.written
    fid = fact_id("Deploys freeze on Fridays.")
    assert f"- Deploys freeze on Fridays. <!-- fact:{fid} -->\n  - evidence: session:abc:3 · 2026-10-02 · " \
           "asserted by user" in _note(vault)
    assert _note(vault).index("Deploys freeze") < _note(vault).index("## History")


def test_the_same_fact_and_ref_again_is_a_no_op(vault):
    req = {"op": "append_fact", "section": "Facts", "fact": "Deploys freeze on Fridays.", "evidence": _ev()}
    amend(vault, _path(vault), req, no_commit=True)
    before = _note(vault)
    again = amend(vault, _path(vault), {**req, "fact": "  deploys FREEZE on fridays. "}, no_commit=True)
    assert again.action == "unchanged" and not again.written and _note(vault) == before


def test_the_same_fact_with_a_new_ref_adds_only_the_evidence(vault):
    req = {"op": "append_fact", "section": "Facts", "fact": "Deploys freeze on Fridays.", "evidence": _ev()}
    amend(vault, _path(vault), req, no_commit=True)
    result = amend(vault, _path(vault), {**req, "evidence": _ev("session:def:1")}, no_commit=True)
    assert result.outcome == "evidence_added"
    assert _note(vault).count("Deploys freeze on Fridays.") == 1 and _note(vault).count("  - evidence:") == 2


def test_a_missing_section_is_created_before_history(vault):
    amend(vault, _path(vault), {"op": "append_fact", "section": "Operating it", "fact": "Rollback is one click.",
                                "evidence": _ev()}, no_commit=True)
    text = _note(vault)
    assert text.index("## Operating it") < text.index("## History")
    assert _sections(vault) == ["Facts", "Operating it", "History"]  # the index saw the new section


def test_add_evidence_by_id_and_refuses_an_unknown_one(vault):
    amend(vault, _path(vault), {"op": "append_fact", "section": "Facts", "fact": "A.", "evidence": _ev()},
          no_commit=True)
    ok = amend(vault, _path(vault), {"op": "add_evidence", "fact_id": fact_id("A."), "evidence": _ev("x:1")},
               no_commit=True)
    assert ok.outcome == "evidence_added"
    with pytest.raises(AmendError, match="no live fact"):
        amend(vault, _path(vault), {"op": "add_evidence", "fact_id": "0" * 12, "evidence": _ev()}, no_commit=True)


def test_supersede_moves_the_old_fact_to_history(vault):
    amend(vault, _path(vault), {"op": "append_fact", "section": "Facts", "fact": "Deploys run on Jenkins.",
                                "evidence": _ev()}, no_commit=True)
    old = fact_id("Deploys run on Jenkins.")
    result = amend(vault, _path(vault), {"op": "supersede_fact", "fact_id": old, "fact": "Deploys run on GitHub "
                                         "Actions.", "evidence": _ev("session:new:1")}, no_commit=True)
    assert result.outcome == "fact_superseded"
    facts, history = _note(vault).split("## History")
    assert "GitHub Actions" in facts and "Jenkins" not in facts
    assert f"Deploys run on Jenkins. — superseded 2026-10-02 by fact:{result.fact_id}" in history
    with pytest.raises(AmendError, match="no live fact"):  # a superseded fact is not live
        amend(vault, _path(vault), {"op": "add_evidence", "fact_id": old, "evidence": _ev("y")}, no_commit=True)


def test_add_alias_is_idempotent_and_updates_the_index(vault):
    first = amend(vault, _path(vault), {"op": "add_alias", "alias": "release pipeline"}, no_commit=True)
    again = amend(vault, _path(vault), {"op": "add_alias", "alias": "Release Pipeline"}, no_commit=True)
    assert first.outcome == "alias_added" and again.action == "unchanged"
    assert resolve(vault, "release pipeline")[0].match_type == "alias"


def test_add_alias_rewrites_a_block_list_cleanly(vault):
    _path(vault).write_text(NOTE.replace("aliases: [ci deploys]", "aliases:\n  - ci deploys"))
    amend(vault, _path(vault), {"op": "add_alias", "alias": "release pipeline"}, no_commit=True)
    assert 'aliases: ["ci deploys", "release pipeline"]' in _note(vault) or \
        "aliases: [ci deploys, release pipeline]" in _note(vault)
    assert "  - ci deploys" not in _note(vault)


@pytest.mark.parametrize("request_,match", [
    ({"op": "explode"}, "unknown op"),
    ({"op": "append_fact", "section": "Facts", "fact": "", "evidence": _ev()}, "fact is required"),
    ({"op": "append_fact", "section": "Facts", "fact": "x <!-- y -->", "evidence": _ev()}, "may not contain"),
    ({"op": "append_fact", "section": "Facts", "fact": "x", "evidence": {"ref": "a · b"}}, "may not contain"),
    ({"op": "append_fact", "section": "History", "fact": "x", "evidence": _ev()}, "superseded facts"),
])
def test_malformed_requests_write_nothing(vault, request_, match):
    before = _note(vault)
    with pytest.raises(AmendError, match=match):
        amend(vault, _path(vault), request_, no_commit=True)
    assert _note(vault) == before


def test_amend_cli(vault, capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"note": "Deploy Pipeline", "op": "append_fact", "section": "Facts", "fact": "B.", "evidence": _ev()})))
    assert main(["--vault", str(vault.root), "amend", "--no-commit", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["outcome"] == "fact_added" and data["written"] is True and data["fact_id"] == fact_id("B.")


def test_amend_cli_bad_request_exits_2(vault, capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"note": "Deploy Pipeline", "op": "nope"})))
    assert main(["--vault", str(vault.root), "amend", "--json"]) == 2


# --- runs -----------------------------------------------------------------------------------------

@pytest.fixture
def gvault(git_vault):  # noqa: F811 - the fixture
    (git_vault / "_shared" / "knowledge" / "deploy-pipeline.md").write_text(NOTE)
    _cgit(git_vault, "add", "-A")
    _cgit(git_vault, "commit", "-qm", "note")
    return detect(git_vault)


def _log(v) -> list[str]:
    return _cgit(v.root, "log", "--format=%s").stdout.splitlines()


def test_a_run_lands_as_one_commit_with_its_trailer(gvault, capsys):
    head = len(_log(gvault))
    for n, fact in enumerate(["A.", "B."]):
        amend(gvault, _path(gvault), {"op": "append_fact", "section": "Facts", "fact": fact,
                                      "evidence": _ev(f"s:{n}")}, run_id="run-1")
    assert main(["--vault", str(gvault.root), "capture", "--type", "knowledge", "--title", "Harvested thing",
                 "--body", "It is so.", "--run-id", "run-1"]) == 0
    assert len(_log(gvault)) == head  # nothing committed yet
    result = commit_run(gvault, "run-1")
    assert result.action == "committed" and len(result.paths) == 2
    assert len(_log(gvault)) == head + 1
    body = _cgit(gvault.root, "log", "-1", "--format=%B").stdout
    assert "Claudron-Run: run-1" in body
    assert commit_run(gvault, "run-1").action == "unchanged"


def test_revert_run_undoes_exactly_the_run(gvault):
    amend(gvault, _path(gvault), {"op": "append_fact", "section": "Facts", "fact": "Bad fact.",
                                  "evidence": _ev()}, run_id="bad-run")
    commit_run(gvault, "bad-run")
    assert "Bad fact." in _note(gvault)
    result = revert_run(gvault, "bad-run")
    assert result.action == "reverted" and "Bad fact." not in _note(gvault)
    assert revert_run(gvault, "bad-run").action == "unchanged"
    assert _sections(gvault) == ["Facts", "History"]


def test_revert_run_refuses_an_uncommitted_run_and_names_its_notes(gvault):
    amend(gvault, _path(gvault), {"op": "append_fact", "section": "Facts", "fact": "X.", "evidence": _ev()},
          run_id="pending")
    with pytest.raises(RunError, match="never committed.*deploy-pipeline.md"):
        revert_run(gvault, "pending")


def test_a_conflicting_revert_is_aborted_and_the_tree_left_alone(gvault):
    amend(gvault, _path(gvault), {"op": "append_fact", "section": "Facts", "fact": "X.", "evidence": _ev()},
          run_id="r1")
    commit_run(gvault, "r1")
    _path(gvault).write_text(_note(gvault).replace("- X.", "- X, edited by a person."))
    _cgit(gvault.root, "commit", "-qam", "person edits the harvested line")
    before = _note(gvault)
    with pytest.raises(RunError, match="conflicts with later edits and was aborted"):
        revert_run(gvault, "r1")
    assert _note(gvault) == before
    assert _cgit(gvault.root, "status", "--porcelain", "--untracked-files=no").stdout.strip() == ""


@pytest.mark.parametrize("bad", ["", "-x", "a b", "a/b", "x" * 65])
def test_a_bad_run_id_is_refused_before_anything_is_written(vault, bad):
    before = _note(vault)
    with pytest.raises(RunError, match="invalid run id"):
        amend(vault, _path(vault), {"op": "append_fact", "section": "Facts", "fact": "Z.", "evidence": _ev()},
              run_id=bad or "-")
    assert _note(vault) == before


def test_run_verbs_cli(gvault, capsys):
    amend(gvault, _path(gvault), {"op": "append_fact", "section": "Facts", "fact": "Y.", "evidence": _ev()},
          run_id="cli-run")
    assert main(["--vault", str(gvault.root), "run-commit", "cli-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["action"] == "committed"
    assert main(["--vault", str(gvault.root), "revert-run", "cli-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["action"] == "reverted"
    assert main(["--vault", str(gvault.root), "revert-run", "never-was"]) == 1


def test_the_engine_declares_the_pipe_capabilities(vault, capsys):
    main(["--vault", str(vault.root), "status", "--json"])
    caps = json.loads(capsys.readouterr().out)["data"]["capabilities"]
    assert {"subjects", "amend", "runs"} <= set(caps)
