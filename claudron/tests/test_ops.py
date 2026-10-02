"""The operations log (#200 §5): per-run and per-session JSONL under .claudron/, and status's liveness.

The contract: every write a run makes is in that run's log (``write``, or
``write.uncommitted`` when it couldn't be committed), and so is everything it
asked for that didn't land (``write.refused``, ``write.routed``) and its
revert. A session's hooks log what recall served and how the push went.
``status --json`` reports the newest run, when one last applied cleanly, and
the last failure. Logging never fails the thing it logs, and never writes
outside ``.claudron/``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from claudron import ops
from claudron.cli import main
from claudron import hooks as hooks_mod
from claudron.hooks import hook_session_start
from claudron.vault import detect

from .test_capture import _cgit, git_vault  # noqa: F401 - the fixture


@pytest.fixture
def gvault(git_vault):  # noqa: F811 - the fixture
    """A git vault that keeps ``.claudron/`` out of commits, as `init` and `doctor --fix` leave one."""
    (git_vault / ".gitignore").write_text(".claudron/\n")
    return git_vault


def _events(root: Path, kind: str, ident: str) -> list[dict]:
    path = root / ".claudron" / kind / ident / "ops.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _capture(root: Path, monkeypatch, finding: dict, *args: str) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(finding)))
    return main(["--vault", str(root), "capture", "--stdin", "--json", *args])


def test_every_event_carries_the_shared_envelope(vault_dir):
    ops.record(detect(vault_dir), "recall.served", session_id="abc-123", trusted=["a.md"])
    (ev,) = _events(vault_dir, "sessions", "abc-123")
    assert {"v", "ts", "kind", "session_id", "run_id", "emitter", "event_id"} <= set(ev)
    assert (ev["v"], ev["emitter"], ev["kind"], ev["trusted"]) == (1, "claudron", "recall.served", ["a.md"])


@pytest.mark.parametrize("ident", ["../escape", "a/b", "..", "", ".hidden"])
def test_an_id_that_isnt_a_safe_directory_name_is_not_logged(vault_dir, ident):
    ops.record(detect(vault_dir), "write", run_id=ident)
    assert not (vault_dir / "escape").exists()
    assert not list((vault_dir / ".claudron").glob("runs/*")) if (vault_dir / ".claudron").exists() else True


def test_a_log_that_cant_be_written_never_fails_the_caller(vault_dir):
    (vault_dir / ".claudron").mkdir(exist_ok=True)
    (vault_dir / ".claudron" / "runs").write_text("a file where the directory should be")
    ops.record(detect(vault_dir), "write", run_id="r1")  # no exception


def test_only_the_newest_directories_are_kept(vault_dir, monkeypatch):
    monkeypatch.setattr(ops, "KEEP", 3)
    for n in range(5):
        ops.record(detect(vault_dir), "write", run_id=f"r{n}")
    assert len(list((vault_dir / ".claudron" / "runs").iterdir())) == 3


def test_a_runs_writes_refusals_and_revert_are_in_its_log(gvault, monkeypatch, capsys):
    root = gvault
    assert _capture(root, monkeypatch, {"type": "knowledge", "title": "Rate limits", "body": "Hourly reset.",
                                        "run_id": "h-1"}) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"note": "Nothing", "op": "append_fact", "run_id": "h-1"})))
    assert main(["--vault", str(root), "amend", "--stdin", "--json"]) == 2
    assert _capture(root, monkeypatch, {"type": "knowledge", "title": "Rate limits", "body": "Hourly reset.",
                                        "run_id": "h-1"}) == 0  # dedup routes the twin
    assert main(["--vault", str(root), "revert-run", "h-1"]) == 0
    capsys.readouterr()
    kinds = [e["kind"] for e in _events(root, "runs", "h-1")]
    assert kinds == ["write", "write.refused", "write.routed", "run.reverted"]
    write = _events(root, "runs", "h-1")[0]
    assert write["verb"] == "capture" and write["path"].endswith("rate-limits.md")


def test_status_reports_the_last_clean_run_and_the_last_failure(gvault, monkeypatch, capsys):
    root = gvault
    _capture(root, monkeypatch, {"type": "knowledge", "title": "Alpha", "body": "A.", "run_id": "ok-run"})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"note": "Nothing", "op": "x", "run_id": "bad-run"})))
    main(["--vault", str(root), "amend", "--stdin"])
    capsys.readouterr()
    main(["--vault", str(root), "status", "--json"])
    runs = json.loads(capsys.readouterr().out)["data"]["runs"]
    assert runs["last_run"]["run_id"] == "bad-run" and runs["last_run"]["failures"] == 1
    assert runs["last_ok_at"] and runs["last_failure"]["run_id"] == "bad-run"
    assert "no note matches" in runs["last_failure"]["reason"]


def test_a_vault_with_no_runs_reports_none(vault_dir, capsys):
    main(["--vault", str(vault_dir), "status", "--json"])
    assert json.loads(capsys.readouterr().out)["data"]["runs"] == {
        "last_run": None, "last_ok_at": None, "last_failure": None}


def test_session_start_logs_what_recall_served_by_trust(vault_dir, monkeypatch, capsys):
    note = vault_dir / "_shared" / "knowledge" / "web.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("---\ntitle: Web thing\ntype: knowledge\nstatus: current\nowner: t\ncreated: 2026-09-01\n"
                    "updated: 2026-09-01\nmaturity: draft\nsource_type: url\nsource_url: https://x.example\n"
                    "---\n\nBody.\n")
    monkeypatch.setattr("claudron.hooks.derive_project", lambda: None)
    hook_session_start(detect(vault_dir), {"session_id": "sess-1"})
    capsys.readouterr()
    (ev,) = _events(vault_dir, "sessions", "sess-1")
    assert ev["kind"] == "recall.served" and set(ev) >= {"trusted", "drafts", "unverified"}


def test_the_engine_declares_the_capability(vault_dir, capsys):
    main(["--vault", str(vault_dir), "status", "--json"])
    assert "ops-log" in json.loads(capsys.readouterr().out)["data"]["capabilities"]


def test_a_later_revert_does_not_make_an_old_run_the_newest(vault_dir):
    vault = detect(vault_dir)
    ops.record(vault, "write", run_id="first", verb="capture", path="a.md")
    ops.record(vault, "write", run_id="second", verb="capture", path="b.md")
    ops.record(vault, "run.reverted", run_id="first", commits=1)
    summary = ops.runs_summary(vault)
    assert summary["last_run"]["run_id"] == "second"
    assert summary["last_ok_at"] == _events(vault_dir, "runs", "second")[0]["ts"]


def test_a_git_vault_that_would_commit_the_logs_gets_none(git_vault):  # noqa: F811
    """Without the ignore rule, sync's straggler net would push session ids and note paths."""
    ops.record(detect(git_vault), "write", run_id="r1")
    assert not (git_vault / ".claudron" / "runs").exists()


def test_pruning_keeps_the_logs_still_being_written(vault_dir, monkeypatch):
    import os
    import time

    monkeypatch.setattr(ops, "KEEP", 3)
    vault = detect(vault_dir)
    ops.record(vault, "write", run_id="long")
    for n in range(3):
        time.sleep(0.01)
        ops.record(vault, "write", run_id=f"r{n}")
        os.utime(vault_dir / ".claudron" / "runs" / "long" / "ops.jsonl")  # still being appended to
        ops.record(vault, "write", run_id="long")
    assert len(_events(vault_dir, "runs", "long")) == 4


def test_pruning_never_removes_what_it_did_not_write(vault_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "KEEP", 1)
    precious = tmp_path / "precious"
    for n in range(3):
        (precious / f"keep{n}").mkdir(parents=True)
        (precious / f"keep{n}" / "data.txt").write_text("mine")
    (vault_dir / ".claudron").mkdir(exist_ok=True)
    (vault_dir / ".claudron" / "sessions").symlink_to(precious)
    vault = detect(vault_dir)
    ops.record(vault, "recall.served", session_id="s1")
    ops.record(vault, "recall.served", session_id="s2")
    assert all((precious / f"keep{n}" / "data.txt").exists() for n in range(3))


def test_recall_served_logs_only_what_the_brief_kept(vault_dir, monkeypatch, capsys):
    """The budget drops notes: the log says what the session was shown, not what recall found."""
    knowledge = vault_dir / "projects" / "webapp"
    knowledge.mkdir(parents=True, exist_ok=True)
    for n in range(6):
        (knowledge / f"n{n}.md").write_text(f"---\ntitle: Rate limit note {n}\ntype: knowledge\nstatus: current\n"
                                            f"owner: t\ncreated: 2026-09-01\nupdated: 2026-09-0{n + 1}\n---\n\n"
                                            + "Words about rate limits. " * 30 + "\n")
    monkeypatch.setattr("claudron.hooks.derive_project", lambda: "webapp")
    monkeypatch.setattr("claudron.session.BRIEF_TOKEN_BUDGET", 120)
    brief = hooks_mod.session_start_brief(detect(vault_dir), "sess-2")
    (ev,) = _events(vault_dir, "sessions", "sess-2")
    assert all(f"`{p}`" in brief for p in ev["trusted"])
    assert 0 < len(ev["trusted"]) < 6


def test_a_path_quoted_in_a_summary_is_not_counted_as_shown(vault_dir, monkeypatch):
    knowledge = vault_dir / "projects" / "webapp"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "a.md").write_text("---\ntitle: A\ntype: knowledge\nstatus: current\nowner: t\ncreated: 2026-09-01\n"
                                    "updated: 2026-09-09\n---\n\nSee `projects/webapp/b.md` for more.\n")
    (knowledge / "b.md").write_text("---\ntitle: B" + " wordy" * 200 + "\ntype: knowledge\nstatus: current\nowner: t\ncreated: 2026-09-01\n"
                                    "updated: 2026-09-01\n---\n\n" + "Long words. " * 400 + "\n")
    monkeypatch.setattr("claudron.hooks.derive_project", lambda: "webapp")
    monkeypatch.setattr("claudron.session.BRIEF_TOKEN_BUDGET", 60)
    hooks_mod.session_start_brief(detect(vault_dir), "sess-3")
    (ev,) = _events(vault_dir, "sessions", "sess-3")
    assert ev["trusted"] == ["projects/webapp/a.md"]


def test_a_revert_of_a_pruned_run_is_not_the_newest_run(vault_dir):
    vault = detect(vault_dir)
    ops.record(vault, "write", run_id="current", verb="capture", path="a.md")
    ops.record(vault, "run.reverted", run_id="long-gone", commits=1)
    assert ops.runs_summary(vault)["last_run"]["run_id"] == "current"


def test_a_vault_nested_in_a_repo_without_the_rule_gets_no_logs(tmp_path):
    from .test_capture import _cgit

    repo = tmp_path / "repo"
    (repo / "vault" / "_shared" / "knowledge").mkdir(parents=True)
    (repo / "vault" / "projects").mkdir()
    _cgit(repo, "init", "-q")
    from .conftest import _identify

    _identify(repo / "vault")
    vault = detect(repo / "vault")
    ops.record(vault, "write", run_id="r1")
    assert not (repo / "vault" / ".claudron" / "runs").exists()
