"""Tests for `claudron recall` — the session-start context brief (E2 PR1)."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from claudron.cli import main
from claudron.schema import count_tokens
from claudron.session import BRIEF_TOKEN_BUDGET, derive_project, recall
from claudron.vault import detect


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
                maturity: verified
                created: 2026-06-01
                updated: 2026-06-01
                ---

                # Widget Pattern {i}

                A long body about widget pattern number {i} with plenty of
                words to make summaries meaningful and the brief heavy.
            """)
        )


def _conventions(vault: Path) -> None:
    """A reviewed CONVENTIONS.md: the brief carries it only at a reviewed maturity."""
    (vault / "_shared" / "CONVENTIONS.md").write_text(
        "---\nmaturity: verified\n---\n\n"
        "# Vault conventions\n\n- Timezone: America/New_York.\n"
        "- Supersede, never delete.\n"
    )


def _reviewed(vault: Path) -> Path:
    """Mark every note with frontmatter reviewed. The brief carries only reviewed notes as
    context, and the tests that call this are about tiers, order, budget and shape, not trust."""
    for md in vault.rglob("*.md"):
        text = md.read_text()
        head = text.split("\n---", 1)[0]
        if text.startswith("---\n") and "\nmaturity:" not in head:
            md.write_text(text.replace("---\n", "---\nmaturity: verified\n", 1))
    return vault


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
        _conventions(_reviewed(vault_with_projects))
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
        rc = main(["--vault", str(_reviewed(vault_dir)), "recall", "--project", "myrepo"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.index("Newer Note") < out.index("Older Note")

    def test_abstention_no_weak_shared_matches(self, vault_dir: Path, capsys):
        """Blind top-k injection harms; below-threshold shared matches
        inject nothing (02_session-loop.md deliverable 1)."""
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
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET

    def test_a_saturated_brief_holds_the_bytes_its_tokens_allow(self, vault_dir: Path, capsys):
        """The cap is in tokens, and a token is about 2.5 bytes of brief text: a saturated brief
        holds no more bytes than its budget allows (#172). A whitespace word count let it fill
        several times that, each vault path in backticks counted as one token."""
        from claudron.schema import BYTES_PER_TOKEN

        _widget_notes(vault_dir)
        rc = main(["--vault", str(vault_dir), "recall", "--query", "widget",
                   "--limit", "40"])
        assert rc == 0
        brief = capsys.readouterr().out.removesuffix("\n")
        assert "Widget Pattern" in brief
        assert len(brief.encode("utf-8")) <= BRIEF_TOKEN_BUDGET * BYTES_PER_TOKEN

    def test_brief_carries_the_discovery_hint(self, vault_dir: Path, capsys):
        """§10.5.2: for any host running the engine's hooks, the recall brief
        IS the in-context discovery channel — the honest residual of parking
        MCP. One line names both doors."""
        from claudron.session import BRIEF_DISCOVERY_HINT

        rc = main(["--vault", str(_reviewed(vault_dir)), "recall", "--query", "auth"])
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
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET  # counted, not exempt

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
        main(["--vault", str(_reviewed(vault_with_projects)), "recall",
              "--project", "storydump", "--query", "auth", "--json"])
        env = json.loads(capsys.readouterr().out)
        notes = env["data"]["notes"]
        keys = {"title", "path", "tier", "type", "status", "maturity",
                "trust", "trusted", "source_url", "updated", "summary", "score"}
        assert all(set(n) == keys for n in notes)
        assert env["data"]["unverified"] == [] and env["data"]["unverified_more"] == 0
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
        _conventions(_reviewed(vault_with_projects))
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


class TestBriefBudgetEdges:
    """`render_brief`'s hint reservation, unit-tested at the boundary.

    Reserving room for the hint before laying out notes is right — a saturated
    brief is where the agent most needs to know it can ask for more. But the
    reservation must never cost a whole *section*: if holding room for the hint
    is what makes the last note not fit, the notes win. Recalled context is the
    payload; the hint is only the pointer.

    Driven through `render_brief` directly rather than through a sized vault —
    the interesting inputs are a few tokens wide, and deriving them from note
    bodies and CONVENTIONS.md makes the test about the fixture, not the rule.
    """

    @staticmethod
    def _data(conventions_tokens: int, notes: int = 3):
        from claudron.schema import BYTES_PER_TOKEN

        return {
            "project": None,
            "query": "q",
            # A conventions body that count_tokens reads as exactly that many tokens.
            "conventions": "# C\n\n" + "w" * int(conventions_tokens * BYTES_PER_TOKEN),
            "notes": [
                {"title": f"N{i}", "type": "knowledge", "maturity": None,
                 "summary": "s", "path": f"p{i}.md"}
                for i in range(notes)
            ],
        }

    def test_notes_win_when_the_reservation_would_empty_the_section(self):
        """The dead zone this guards: conventions large enough that exactly one
        note fits *without* the hint and none fit *with* it. Reserving must not
        turn that into no recalled context at all."""
        from claudron.session import BRIEF_DISCOVERY_HINT, render_brief

        # The largest conventions block beside which one note still renders: a token more and it
        # would not fit even without the hint, so at this size it fits only without it.
        conv = max(c for c in range(BRIEF_TOKEN_BUDGET) if "N0" in render_brief(self._data(c, notes=1)))
        out = render_brief(self._data(conv, notes=1))

        assert "Recalled context" in out, "the section must not vanish"
        assert "N0" in out, "the note that fits must render"
        assert BRIEF_DISCOVERY_HINT not in out, "the hint yields, not the notes"
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET

    @pytest.mark.parametrize("pad", range(5))
    def test_the_cap_holds_on_the_brief_as_joined(self, pad: int):
        """count_tokens counts bytes, so the line breaks between note lines cost too: the cap is
        checked on the brief as it is injected, never on its pieces summed (#172). Each pad gives
        the note lines another length, so one of them leaves no rounding slack for the breaks."""
        from claudron.session import render_brief

        data = self._data(0, notes=0)
        data["notes"] = [
            {"title": f"N{i:03d}", "type": "knowledge", "maturity": None,
             "summary": "s" * (10 + pad), "path": f"p{i:03d}.md"}
            for i in range(200)
        ]
        out = render_brief(data)
        assert "N000" in out and "N199" not in out  # saturated
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET

    def test_the_cap_holds_with_the_unverified_block(self):
        """The Unverified block fills what the budget has left, the line that counts the notes it
        leaves out included: whatever size comes before it, the cap holds (#172)."""
        from claudron.session import render_brief

        for conv in range(600, 890):  # past 890 the conventions block alone is over (the stated exception)
            data = self._data(conv, notes=0)
            data["unverified"] = [
                {"title": f"U{i}", "type": "knowledge", "maturity": "draft", "path": f"u{i}.md", "source_url": ""}
                for i in range(3)
            ]
            data["unverified_more"] = 40
            assert count_tokens(render_brief(data)) <= BRIEF_TOKEN_BUDGET, conv

    def test_hint_present_when_there_is_room(self):
        from claudron.session import BRIEF_DISCOVERY_HINT, render_brief

        out = render_brief(self._data(20))
        assert "Recalled context" in out
        assert BRIEF_DISCOVERY_HINT in out
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET

    def test_hint_never_renders_without_notes(self):
        """A lone hint is context spend with no recall behind it."""
        from claudron.session import BRIEF_DISCOVERY_HINT, render_brief

        data = self._data(20, notes=0)
        out = render_brief(data)
        assert BRIEF_DISCOVERY_HINT not in out

    @pytest.mark.parametrize("conv", [0, 20, 400, 800, 890])
    def test_budget_holds_across_the_reservation_branches(self, conv: int):
        """Whichever branch the reservation takes, the cap is never exceeded.

        Bounded to conventions within their own budget regime — see
        `test_oversized_conventions_is_the_stated_exception` for past it.
        """
        from claudron.session import render_brief

        out = render_brief(self._data(conv, notes=10))
        assert count_tokens(out) <= BRIEF_TOKEN_BUDGET, conv

    def test_oversized_conventions_is_the_stated_exception(self):
        """The one documented way the brief exceeds its cap, enforced.

        `CLI_CONTRACT.md` §Session-loop protocol states the budget honestly:
        the cap holds *given a `CONVENTIONS.md` within its own budget*. That
        block is the always-loaded layer — recall injects it unconditionally,
        so past W105's ceiling (160) it can carry the brief over on its own,
        and the engine will not silently drop the layer a vault declared
        always-loaded. Nothing hard-enforces the cap: W105 warns in *both*
        validation tiers, so `validate --strict` surfaces an over-budget
        `CONVENTIONS.md` and still exits 0 — a consumer needing a hard ceiling
        gates on the warning code itself.

        Two halves, both contract: the overflow is bounded to that one block,
        and everything below it still degrades correctly — zero notes, no hint,
        rather than compounding. Previously pinned as an unowned pre-existing
        gap (Claudron #81); C2 gave it an owner in the contract, so it now
        gates the sentence instead of recording a surprise.
        """
        from claudron.session import BRIEF_DISCOVERY_HINT, render_brief

        out = render_brief(self._data(BRIEF_TOKEN_BUDGET + 300, notes=10))
        assert count_tokens(out) > BRIEF_TOKEN_BUDGET  # the gap, stated
        assert "Recalled context" not in out  # but notes degrade to nothing
        assert BRIEF_DISCOVERY_HINT not in out


def _note(path: Path, title: str, updated: str = "2026-09-01") -> None:
    """A reviewed knowledge note."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\ntype: knowledge\nstatus: current\nowner: t\n"
                    f"created: 2026-09-01\nupdated: {updated}\nmaturity: verified\n---\n\n"
                    f"# {title}\n\nWhat {title.lower()} says.\n")


class TestPerTierLimit:
    """`recall --limit N` is N notes per tier (#172): the project's own notes come through the
    project tier, and past its limit the shared pass never picks them up again."""

    def test_the_shared_pass_never_re_selects_the_projects_own_notes(self, vault_dir: Path):
        for n in range(8):
            _note(vault_dir / "projects" / "webapp" / f"w{n}.md", f"Webapp note {n}", f"2026-09-0{n + 1}")
        _note(vault_dir / "_shared" / "knowledge" / "webapp-guide.md", "Webapp guide")
        notes = recall(detect(vault_dir), project="webapp", limit=5)["notes"]
        own = [n["title"] for n in notes if n["tier"] == "project:webapp"]
        assert own == [f"Webapp note {n}" for n in (7, 6, 5, 4, 3)]  # the newest five, once
        assert "Webapp guide" in [n["title"] for n in notes]  # the shared pass still runs

    def test_a_shared_match_ranked_below_the_projects_notes_still_comes(self, vault_dir: Path):
        """The overfetch makes room for the project's notes it now skips. The guide scores as each
        of them does (on its title alone), and at an equal score a project's note ranks first, so
        all nine come before it: a window of limit * 2 would hold none but theirs."""
        from claudron import lookup

        for n in range(9):
            _note(vault_dir / "projects" / "webapp" / f"w{n}.md", f"Webapp note {n}", f"2026-09-0{n + 1}")
        _note(vault_dir / "_shared" / "knowledge" / "guide.md", "Webapp guide")
        vault = detect(vault_dir)
        ranked = [r.doc.title for r in lookup("webapp", vault, limit=20, tier_b=False)]
        assert ranked.index("Webapp guide") == 9, ranked  # the premise: below all nine
        notes = recall(vault, project="webapp", limit=2)["notes"]
        assert [n["tier"] for n in notes].count("project:webapp") == 2
        assert "Webapp guide" in [n["title"] for n in notes]


class TestSummary:
    """A note's one-line summary (#172): at most 140 characters, cut after a whole word, marked."""

    def test_a_long_line_is_cut_after_a_whole_word_and_marked(self):
        from claudron.session import SUMMARY_CUT_MARK, _summary

        line = " ".join(f"word{i:02d}" for i in range(40))
        out = _summary(line)
        assert out.endswith(SUMMARY_CUT_MARK) and len(out) <= 140
        kept = out[: -len(SUMMARY_CUT_MARK)]
        assert line.startswith(kept) and line[len(kept)] == " ", "it ends at a word's end"
        assert len(kept) + len(" word00") + len(SUMMARY_CUT_MARK) > 140, "no word that fit was dropped"

    def test_a_line_that_fits_is_whole_and_unmarked(self):
        from claudron.session import _summary

        assert _summary("a" * 140) == "a" * 140
        assert _summary("# Heading\n\n  Short line.  \n") == "Short line."

    def test_one_word_longer_than_the_limit_is_cut_inside_it_and_marked(self):
        from claudron.session import SUMMARY_CUT_MARK, _summary

        assert _summary("z" * 200) == "z" * 139 + SUMMARY_CUT_MARK

    def test_the_brief_line_carries_the_mark(self, vault_dir: Path):
        from claudron.session import SUMMARY_CUT_MARK, render_brief

        path = vault_dir / "projects" / "webapp" / "long.md"
        _note(path, "Long note")
        path.write_text(path.read_text().replace("What long note says.", "Words on the topic. " * 20))
        brief = render_brief(recall(detect(vault_dir), project="webapp"))
        (line,) = [ln for ln in brief.splitlines() if "**Long note**" in ln]
        assert SUMMARY_CUT_MARK + " `projects/webapp/long.md`" in line
