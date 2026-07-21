"""Tests for `claudron recall` — the session-start context brief (E2 PR1)."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from claudron.cli import main
from claudron.session import BRIEF_TOKEN_BUDGET, derive_project, recall


def _widget_notes(vault: Path, count: int = 40) -> None:
    """A note-heavy shared tier — enough to saturate BRIEF_TOKEN_BUDGET."""
    base = vault / "_shared" / "knowledge"
    for i in range(count):
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
        _widget_notes(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall", "--query", "widget",
                   "--limit", "40"])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out.split()) <= BRIEF_TOKEN_BUDGET

    def test_brief_carries_the_discovery_hint(self, vault_dir: Path, capsys):
        """§10.5.2: for any host running the engine's hooks, the recall brief
        IS the in-context discovery channel — the honest residual of parking
        MCP. One line names both doors."""
        from claudron.session import BRIEF_DISCOVERY_HINT

        rc = main(["--vault", str(vault_dir), "recall", "--query", "auth"])
        assert rc == 0
        assert BRIEF_DISCOVERY_HINT in capsys.readouterr().out

    def test_hint_names_real_cli_surface(self, capsys):
        """The hint hardcodes CLI verbs and flags inside an engine module, and
        nothing else pins them — a rename of `lookup` or `--stdin` would go
        stale silently, which is the exact drift class this contract work
        exists to close. Gate it against the real parser."""
        import re

        from claudron.session import BRIEF_DISCOVERY_HINT

        invocations = re.findall(r"`claudron ([a-z-]+)([^`]*)`", BRIEF_DISCOVERY_HINT)
        assert invocations, "the hint no longer names any claudron invocation"
        for verb, rest in invocations:
            with pytest.raises(SystemExit) as exc_info:
                main([verb, "--help"])
            assert exc_info.value.code == 0, f"`claudron {verb}` is not a subcommand"
            help_text = capsys.readouterr().out
            for flag in re.findall(r"--[a-z-]+", rest):
                assert flag in help_text, f"`claudron {verb}` has no {flag}"

    def test_empty_brief_carries_no_hint(self, empty_vault: Path, capsys):
        """An empty brief injects nothing at all — a lone hint line would be
        context spend with no recall behind it."""
        rc = main(["--vault", str(empty_vault), "recall"])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_hint_survives_a_full_budget(self, vault_dir: Path, capsys):
        """The hint's cost is reserved before notes are laid out, so a mature
        vault that saturates the budget still teaches the door (it costs at
        most one note). Regression guard for append-and-drop."""
        from claudron.session import BRIEF_DISCOVERY_HINT

        _widget_notes(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall", "--query", "widget",
                   "--limit", "40"])
        assert rc == 0
        out = capsys.readouterr().out
        assert BRIEF_DISCOVERY_HINT in out
        assert len(out.split()) <= BRIEF_TOKEN_BUDGET  # counted, not exempt

    def test_default_recall_is_index_only(self, vault_dir: Path, capsys):
        """The implicit default (bare project name, every SessionStart) must
        not trigger the O(vault) full-text fallback; an explicit --query
        buys it. Observable via a heading-only match — invisible to the
        index, found by full-text — for a term with zero Tier-A hits."""
        proj = vault_dir / "projects" / "flaxo"
        proj.mkdir(parents=True)
        (vault_dir / "_shared" / "knowledge" / "quirks.md").write_text(
            dedent("""\
                ---
                title: Platform Quirks
                type: knowledge
                status: current
                owner: t
                created: 2026-06-01
                updated: 2026-06-01
                ---

                # Platform Quirks

                ## flaxo ingestion quirks

                The ingest path retries on 429s.
            """)
        )
        # Implicit default: index has no 'flaxo' match and the full-text
        # fallback stays off — heading-only match must NOT surface.
        main(["--vault", str(vault_dir), "recall", "--project", "flaxo"])
        assert "Platform Quirks" not in capsys.readouterr().out
        # Explicit query: fallback allowed, heading match (70 ≥ floor) found.
        main(["--vault", str(vault_dir), "recall",
              "--project", "flaxo", "--query", "flaxo"])
        assert "Platform Quirks" in capsys.readouterr().out

    def test_json_note_shape_is_stable(self, vault_with_projects: Path, capsys):
        """Every note carries the same key set; score is None for
        membership (project) entries — the null is the signal."""
        main(["--vault", str(vault_with_projects), "recall",
              "--project", "storydump", "--query", "auth", "--json"])
        env = json.loads(capsys.readouterr().out)
        notes = env["data"]["notes"]
        keys = {"title", "path", "tier", "type", "status", "maturity",
                "updated", "summary", "score"}
        assert all(set(n) == keys for n in notes)
        by_tier = {n["tier"]: n for n in notes}
        assert by_tier["project:storydump"]["score"] is None
        assert isinstance(by_tier["shared"]["score"], int)

    def test_json_conventions_untransformed(self, vault_dir: Path, capsys):
        """recall() returns authentic data — the H1 strip is render-only."""
        _conventions(vault_dir)
        main(["--vault", str(vault_dir), "recall", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["conventions"].startswith("# Vault conventions")

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
