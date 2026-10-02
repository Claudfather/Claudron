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
from claudron.hooks import hook_session_start
from claudron.vault import detect

from .test_capture import _cgit, git_vault  # noqa: F401 - the fixture


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


def test_a_runs_writes_refusals_and_revert_are_in_its_log(git_vault, monkeypatch, capsys):  # noqa: F811
    root = git_vault
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


def test_status_reports_the_last_clean_run_and_the_last_failure(git_vault, monkeypatch, capsys):  # noqa: F811
    root = git_vault
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
