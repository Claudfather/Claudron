"""Tests for the hook pack + `claudron hooks install` (E2 PR3)."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.hooks import (
    HOOK_EVENTS,
    SESSION_END_PUSH_TIMEOUT,
    SESSION_START_PULL_TIMEOUT,
    settings_snippet,
)
from claudron.tests.doc_parity import code_values, doc_table, fenced_block, section

CONTRACT = "docs/CLI_CONTRACT.md"
PROTOCOL = "Session-loop protocol"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch):
    """A HOME the transitional shim can glob for real.

    The shim reads `~/.claude/plugins`; stubbing the function under test
    would pin nothing about the mechanism the removal release deletes.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


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

    def test_fail_open_no_vault(
        self, tmp_path: Path, capsys, monkeypatch, no_vault_env
    ):
        """THE hook contract: a broken environment must never break a
        session start — exit 0, empty stdout, error logged."""
        nowhere = tmp_path / "not-a-vault"
        nowhere.mkdir()
        monkeypatch.chdir(nowhere)
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
    """F1's transitional-state matrix (boundary program C2).

    The engine **always prompts** where its PreCompact hook is installed and
    never sniffs a consumer — with exactly one exception, the transitional
    shim, which survives only until the front-end's defer release ships
    (`CLI_CONTRACT.md` §Session-loop protocol). Both cells are pinned so the
    removal release is a visible behavior change, not a silent one.
    """

    def _run(self, vault_dir: Path, capsys, monkeypatch, session=None) -> str:
        """One PreCompact run; returns its stdout. The session id is unique
        per call by default — the once-per-session marker lives in the
        process-global tmp dir (tempfile caches gettempdir, so monkeypatching
        TMPDIR is inert)."""
        payload = json.dumps({"session_id": session or f"sess-{uuid.uuid4()}"})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert main(["--vault", str(vault_dir), "hook", "pre-compact"]) == 0
        return capsys.readouterr().out

    def test_prompts_when_no_front_end_is_installed(
        self, vault_dir: Path, capsys, monkeypatch, fake_home
    ):
        """Shim finds nothing ⇒ the engine prompts. Bare-Claudron install."""
        out = json.loads(self._run(vault_dir, capsys, monkeypatch))
        assert out["decision"] == "block"
        assert "claudron capture --stdin" in out["reason"]
        assert "/reflect" not in out["reason"]  # retired skill, never referenced

    def test_prompt_names_no_front_end(
        self, vault_dir: Path, capsys, monkeypatch, fake_home
    ):
        """R5 at the surface that reaches an agent: the block reason routes
        through *your* capture door, whichever it is. A front-end name here
        would make the engine's own prompt the thing that knows a consumer."""
        out = json.loads(self._run(vault_dir, capsys, monkeypatch))
        assert "claudna" not in out["reason"].lower()
        assert "capture door" in out["reason"]  # the neutral routing phrase

    def test_shim_defers_while_it_lives(
        self, vault_dir: Path, capsys, monkeypatch, fake_home
    ):
        """The transitional shim, pinned by its real mechanism: a plugin dir
        present ⇒ the engine yields, so a front-end still shipping its own
        unconditional prompt doesn't double up before its defer release."""
        (fake_home / ".claude" / "plugins" / "marketplace" / "claudna").mkdir(
            parents=True
        )
        assert self._run(vault_dir, capsys, monkeypatch) == ""

    @pytest.mark.skip(
        reason="F1 end state: flips on in the release that deletes the shim — "
        "which must precede or accompany the front-end's defer release"
    )
    def test_end_state_prompts_in_both_cells(
        self, vault_dir: Path, capsys, monkeypatch, fake_home
    ):
        """Written now, enabled by the removal release: with the shim gone the
        engine prompts in *both* cells and the plugin dir stops mattering."""
        (fake_home / ".claude" / "plugins" / "marketplace" / "claudna").mkdir(
            parents=True
        )
        out = json.loads(self._run(vault_dir, capsys, monkeypatch))
        assert out["decision"] == "block"

    def test_second_compaction_passes(
        self, vault_dir: Path, capsys, monkeypatch, fake_home
    ):
        session = f"sess-{uuid.uuid4()}"
        assert "block" in self._run(vault_dir, capsys, monkeypatch, session)
        assert self._run(vault_dir, capsys, monkeypatch, session) == ""

    def test_fail_open_without_vault(
        self, tmp_path: Path, capsys, monkeypatch, no_vault_env
    ):
        monkeypatch.chdir(tmp_path)
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


class TestSessionProtocolDocParity:
    """CLI_CONTRACT §Session-loop protocol is the ONE normative statement of
    the loop (boundary spec §10.4 contract #5). It is also the surface a fleet
    composer renders hook entries against — so drift here ships stale hooks to
    every vault-wired bot. This is the engine-side half of that gate; the
    composer-side half is L4's.
    """

    def test_role_table_names_exactly_the_engine_events(self):
        """Every event the role table assigns is a real handler, and every
        handler is assigned a role. A role whose event nobody dispatches is a
        promise with no code behind it."""
        rows = doc_table(CONTRACT, "SESSION_ROLES")
        assigned = {ev for row in rows for ev in code_values(row[3])}
        assert assigned == set(HOOK_EVENTS)

    def test_front_end_role_claims_no_engine_event(self):
        """R-continuity is the front-end's whole job — the engine ships no
        handler for it, and the table must not imply one."""
        rows = doc_table(CONTRACT, "SESSION_ROLES")
        continuity = [r for r in rows if "R-continuity" in r[0]]
        assert len(continuity) == 1
        assert code_values(continuity[0][3]) == ()

    def test_snippet_shape_matches_the_installer(self):
        """The composed-hook shape, pinned structurally rather than by prose.
        A consumer emitting these entries is a rendered copy (R3); this is the
        text it renders against."""
        raw = fenced_block(CONTRACT, PROTOCOL)
        body = raw.split("\n", 1)[1] if raw.lstrip().startswith("json") else raw
        assert json.loads(body) == settings_snippet("<absolute-executable>")

    def test_timeout_budgets_match_the_constants(self):
        rows = doc_table(CONTRACT, "HOOK_TIMEOUTS")
        budgets = {
            row[0].strip("`"): code_values(row[2])[0]
            for row in rows
            if code_values(row[2])
        }
        assert budgets == {
            "session-start": f"{SESSION_START_PULL_TIMEOUT}s",
            "session-end": f"{SESSION_END_PUSH_TIMEOUT}s",
        }

    def test_identity_rule_is_the_one_the_installer_applies(self):
        """`merge_settings` replaces a prior entry by matching the command's
        `hook <event>` suffix; a consumer that rewrites the command without
        preserving it gets a duplicate hook, not a replacement.

        Asserting the section merely *mentions* the rule would pass on a
        section that stated it backwards. So take the documented suffix at its
        word and run it through the matcher: a command ending in it is ours, a
        command carrying it anywhere else is not.
        """
        from claudron.hooks import _is_claudron_hook

        body = section(CONTRACT, PROTOCOL)
        assert "hook <event>" in body and "merge_settings" in body

        def entry(command: str) -> dict:
            return {"hooks": [{"type": "command", "command": command}]}

        assert _is_claudron_hook(entry("/anywhere/claudron hook pre-compact"),
                                 "pre-compact")
        assert not _is_claudron_hook(entry("/x hook pre-compact --extra"),
                                     "pre-compact")
        assert not _is_claudron_hook(entry("/x hook session-end"), "pre-compact")


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
