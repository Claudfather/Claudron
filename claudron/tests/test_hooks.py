"""Tests for the hook pack + `claudron hooks install` (E2 PR3)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from claudron.cli import main


class TestSessionStartHook:
    def test_emits_brief_on_stdout(self, vault_dir: Path, capsys, monkeypatch):
        (vault_dir / "_shared" / "CONVENTIONS.md").write_text(
            "# Conventions\n\n- Supersede, never delete.\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["--vault", str(vault_dir), "hook", "session-start"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Supersede, never delete." in out

    def test_fail_open_no_vault(self, tmp_path: Path, capsys, monkeypatch):
        """THE hook contract: a broken environment must never break a
        session start — exit 0, empty stdout, error logged."""
        nowhere = tmp_path / "not-a-vault"
        nowhere.mkdir()
        monkeypatch.chdir(nowhere)
        monkeypatch.delenv("CLAUDRON_VAULT", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["hook", "session-start"])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_fail_open_logs_errors(self, vault_dir: Path, capsys, monkeypatch):
        """Errors land in .claudron/hooks.log, never in the session."""
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        # A vault that is not a git repo: sync fails, recall still serves,
        # and the sync failure is logged — fail-open all the way down.
        rc = main(["--vault", str(vault_dir), "hook", "session-start"])
        assert rc == 0
        log = vault_dir / ".claudron" / "hooks.log"
        assert log.is_file()
        assert "sync" in log.read_text().lower()


class TestPreCompactHook:
    def test_blocks_once_with_capture_prompt(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        import uuid

        # Unique per run: the marker lives in the process-global tmp dir
        # (tempfile caches gettempdir, so TMPDIR monkeypatching is inert)
        payload = json.dumps({"session_id": f"sess-{uuid.uuid4()}"})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = main(["--vault", str(vault_dir), "hook", "pre-compact"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert "claudron capture" in out["reason"]

    def test_second_compaction_passes(
        self, vault_dir: Path, capsys, monkeypatch, tmp_path
    ):
        import uuid

        session = f"sess-{uuid.uuid4()}"  # marker dir is process-global tmp
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps({"session_id": session}))
        )
        assert main(["--vault", str(vault_dir), "hook", "pre-compact"]) == 0
        assert "block" in capsys.readouterr().out  # first: block-and-instruct
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps({"session_id": session}))
        )
        assert main(["--vault", str(vault_dir), "hook", "pre-compact"]) == 0
        assert capsys.readouterr().out == ""  # second: pass silently

    def test_fail_open_without_vault(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDRON_VAULT", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["hook", "pre-compact"])
        assert rc == 0


class TestSessionEndHook:
    def test_pushes_fail_open(self, vault_dir: Path, capsys, monkeypatch):
        """Non-git vault: push fails, hook still exits 0 (fail open)."""
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["--vault", str(vault_dir), "hook", "session-end"])
        assert rc == 0


class TestGauntletPins:
    def test_conflicted_conventions_not_injected(self, vault_dir: Path, capsys):
        """Gauntlet (altitude 1a): CONVENTIONS.md bypasses the tier walker,
        so a conflicted one would inject raw markers into EVERY brief —
        recall must quarantine it explicitly."""
        (vault_dir / "_shared" / "CONVENTIONS.md").write_text(
            "# Conventions\n\n<<<<<<< HEAD\nA's rules.\n=======\n"
            "B's rules.\n>>>>>>> origin/main\n"
        )
        rc = main(["--vault", str(vault_dir), "recall", "--query", "auth"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "<<<<<<<" not in out and "Vault conventions" not in out

    def test_run_hook_is_the_failopen_boundary(self, vault_dir: Path, capsys, monkeypatch):
        """Gauntlet (altitude 2): exception classes the inner guards never
        anticipated still exit 0 with clean stdout."""
        import claudron.hooks as hooks_mod

        def _boom(vault):
            raise PermissionError("git exists but is not executable")

        monkeypatch.setitem(hooks_mod._HOOK_HANDLERS, "session-start", _boom)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main(["--vault", str(vault_dir), "hook", "session-start"])
        assert rc == 0
        assert capsys.readouterr().out == ""
        assert "failed open" in (vault_dir / ".claudron" / "hooks.log").read_text()

    def test_moved_executable_replaces_not_duplicates(self, vault_dir: Path, tmp_path, capsys, monkeypatch):
        """Gauntlet (altitude 3): a venv move must replace the stale entry,
        not append a second hook that runs every session."""
        from claudron import hooks as hooks_mod

        settings = tmp_path / "settings.json"
        settings.write_text("{}")
        main(["--vault", str(vault_dir), "hooks", "install",
              "--write", "--settings", str(settings)])
        capsys.readouterr()
        monkeypatch.setattr(
            hooks_mod, "resolve_executable", lambda: "/new/venv/bin/claudron"
        )
        monkeypatch.setattr(
            "claudron.cli.resolve_executable", lambda: "/new/venv/bin/claudron"
        )
        main(["--vault", str(vault_dir), "hooks", "install",
              "--write", "--settings", str(settings)])
        merged = json.loads(settings.read_text())
        starts = merged["hooks"]["SessionStart"]
        assert len(starts) == 1  # replaced, not appended
        assert starts[0]["hooks"][0]["command"].startswith("/new/venv/")


class TestHooksInstall:
    def test_print_snippet_default(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "hooks", "install"])
        assert rc == 0
        out = capsys.readouterr().out
        snippet = json.loads(out)
        events = snippet["hooks"]
        assert {"SessionStart", "PreCompact", "SessionEnd"} <= set(events)
        cmd = events["SessionStart"][0]["hooks"][0]["command"]
        assert cmd.startswith("/")  # absolute executable path (venv-proof)
        assert "session-start" in cmd

    def test_write_merges_and_is_idempotent(self, vault_dir: Path, tmp_path, capsys):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps(
            {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash",
             "hooks": [{"type": "command", "command": "existing"}]}]}}
        ))
        rc = main(["--vault", str(vault_dir), "hooks", "install",
                   "--write", "--settings", str(settings)])
        assert rc == 0
        merged = json.loads(settings.read_text())
        assert merged["model"] == "opus"  # untouched
        assert merged["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "existing"
        assert "SessionStart" in merged["hooks"]
        capsys.readouterr()
        # Idempotent: second --write adds nothing
        rc = main(["--vault", str(vault_dir), "hooks", "install",
                   "--write", "--settings", str(settings)])
        assert rc == 0
        again = json.loads(settings.read_text())
        assert again == merged
