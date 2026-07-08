"""Tests for `claudron recall` — the session-start context brief (E2 PR1)."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from claudron.cli import main
from claudron.session import BRIEF_TOKEN_BUDGET, derive_project


def _conventions(vault: Path) -> None:
    (vault / "_shared" / "CONVENTIONS.md").write_text(
        "# Vault conventions\n\n- Timezone: America/New_York.\n"
        "- Supersede, never delete.\n"
    )


class TestBrief:
    def test_conventions_always_injected(self, vault_dir: Path, capsys):
        """The always-loaded layer (F4/F6): present even for junk queries."""
        _conventions(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall",
                   "--query", "zzz-no-such-topic"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Supersede, never delete." in out

    def test_project_tier_first(self, vault_with_projects: Path, capsys):
        """Project notes are context by membership; they precede shared
        matches in the brief."""
        _conventions(vault_with_projects)
        rc = main(["--vault", str(vault_with_projects), "recall",
                   "--project", "storydump", "--query", "auth"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Neon Connection Pooling Gotchas" in out
        assert out.index("Neon Connection Pooling Gotchas") < out.index(
            "Auth Patterns Across Services"
        )

    def test_project_tier_recency_order(self, vault_dir: Path, capsys):
        proj = vault_dir / "projects" / "myrepo"
        proj.mkdir(parents=True)
        for name, updated in (("older", "2026-06-01"), ("newer", "2026-07-01")):
            (proj / f"{name}.md").write_text(
                dedent(f"""\
                    ---
                    title: {name.title()} Note
                    type: knowledge
                    status: current
                    owner: t
                    created: 2026-05-01
                    updated: {updated}
                    ---

                    # {name.title()} Note

                    Body of the {name} note.
                """)
            )
        rc = main(["--vault", str(vault_dir), "recall", "--project", "myrepo"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.index("Newer Note") < out.index("Older Note")

    def test_abstention_no_weak_shared_matches(self, vault_dir: Path, capsys):
        """Blind top-k injection harms; below-threshold shared matches
        inject nothing (02-session-loop.md deliverable 1)."""
        _conventions(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall",
                   "--query", "zzz-nothing-matches-this"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Auth Patterns" not in out
        assert "Deploy Checklist" not in out

    def test_budget_capped(self, vault_dir: Path, capsys):
        """Hard token budget on a note-heavy vault (acceptance criterion)."""
        base = vault_dir / "_shared" / "knowledge"
        for i in range(40):
            (base / f"widget-{i}.md").write_text(
                dedent(f"""\
                    ---
                    title: Widget Pattern {i}
                    type: knowledge
                    status: current
                    owner: t
                    tags: [widget]
                    created: 2026-06-01
                    updated: 2026-06-01
                    ---

                    # Widget Pattern {i}

                    A long body about widget pattern number {i} with plenty of
                    words to make summaries meaningful and the brief heavy.
                """)
            )
        rc = main(["--vault", str(vault_dir), "recall", "--query", "widget",
                   "--limit", "40"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.split()) <= BRIEF_TOKEN_BUDGET

    def test_empty_recall_is_silent_payload(self, empty_vault: Path, capsys):
        """No conventions, no matches → empty stdout (fail-open posture:
        inject nothing rather than something), diagnostic on stderr."""
        rc = main(["--vault", str(empty_vault), "recall"])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no context" in captured.err


class TestJsonAndChannels:
    def test_json_envelope(self, vault_with_projects: Path, capsys):
        _conventions(vault_with_projects)
        rc = main(["--vault", str(vault_with_projects), "recall",
                   "--project", "storydump", "--query", "auth", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "recall" and env["ok"] is True
        data = env["data"]
        assert data["project"] == "storydump"
        assert "Timezone" in data["conventions"]
        titles = [n["title"] for n in data["notes"]]
        assert "Neon Connection Pooling Gotchas" in titles
        sample = data["notes"][0]
        assert {"title", "path", "tier", "type", "status", "summary"} <= set(sample)

    def test_stdout_is_pure_payload(self, vault_dir: Path, capsys):
        """recall stdout is injected into sessions verbatim — diagnostics
        must never land there (CLI contract)."""
        _conventions(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall", "--query", "auth"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "vault:" not in captured.out  # no status-style chrome
        assert "Auth Patterns" in captured.out


class TestProjectDerivation:
    def test_derives_from_git_root_name(self, tmp_path: Path, monkeypatch):
        repo = tmp_path / "storydump"
        (repo / ".git").mkdir(parents=True)
        nested = repo / "src" / "deep"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert derive_project() == "storydump"

    def test_falls_back_to_cwd_name(self, tmp_path: Path, monkeypatch):
        plain = tmp_path / "just-a-dir"
        plain.mkdir()
        monkeypatch.chdir(plain)
        assert derive_project() == "just-a-dir"

    def test_cli_uses_derived_project(
        self, vault_with_projects: Path, tmp_path: Path, monkeypatch, capsys
    ):
        repo = tmp_path / "storydump"
        (repo / ".git").mkdir(parents=True)
        monkeypatch.chdir(repo)
        rc = main(["--vault", str(vault_with_projects), "recall"])
        assert rc == 0
        assert "Neon Connection Pooling Gotchas" in capsys.readouterr().out
