"""Tests for the wikilink graph — resolve_wikilinks over the JSON index (E4 C1).

The scale-free graph slice: `resolve_wikilinks` implements SCHEMA.md resolution
(title → alias → slug, case-insensitive; ambiguity → higher tier; unresolved is
first-class), over the existing index — no SQLite (that's the deferred scale bet).
"""

from __future__ import annotations

import json
from pathlib import Path

from claudron import resolve_wikilinks
from claudron.cli import main
from claudron.knowledge import (
    link_report,
    related,
    resolve_note_ref,
    wikilink_targets,
)
from claudron.vault import detect


def _note(
    vault: Path, tier_dir: str, filename: str, title: str, *,
    aliases: str = "", slug: str = "",
) -> None:
    d = vault / tier_dir
    d.mkdir(parents=True, exist_ok=True)
    alias_line = f"aliases: [{aliases}]\n" if aliases else ""
    slug_line = f"slug: {slug}\n" if slug else ""
    (d / filename).write_text(
        f"---\ntitle: {title}\ntype: knowledge\nstatus: current\n"
        f"{alias_line}{slug_line}owner: t\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
        f"---\n\n# {title}\n\nbody\n"
    )


class TestWikilinkTargets:
    def test_extracts_dedups_and_drops_label(self):
        text = "See [[Auth Patterns]] and [[Auth Patterns|the doc]] plus [[Deploy]]."
        assert wikilink_targets(text) == ["Auth Patterns", "Deploy"]

    def test_ignores_code_fences_and_inline(self):
        text = "real [[Live]] but `[[inline]]` and\n```\n[[fenced]]\n```\n"
        assert wikilink_targets(text) == ["Live"]

    def test_ignores_unclosed_fence_to_eof(self):
        # CommonMark: an unterminated fence is code through EOF (review finding)
        text = "keep [[Real]]\n```python\ncode [[ShouldBeCode]]\nmore [[AlsoCode]]"
        assert wikilink_targets(text) == ["Real"]

    def test_ignores_tilde_fence(self):
        text = "keep [[Real]]\n~~~\n[[TildeFenced]]\n~~~\n"
        assert wikilink_targets(text) == ["Real"]

    def test_target_does_not_span_newline(self):
        # a stray `[[` must not bind to a `]]` on a later line and swallow text
        assert wikilink_targets("stray [[ oops\nlater [[Real]] here ]]") == ["Real"]


class TestResolveWikilinks:
    def _vault(self, tmp_path: Path):
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "auth-patterns.md", "Auth Patterns",
              aliases='"JWT Guide"')
        _note(v, "_shared/knowledge", "deploy-doc.md", "Deploy Checklist",
              slug="deploy")
        return detect(v)

    def test_resolves_by_title_case_insensitive(self, tmp_path: Path):
        vault = self._vault(tmp_path)
        r = resolve_wikilinks("see [[auth patterns]]", vault)
        assert r["[[auth patterns]]"]["path"].endswith("auth-patterns.md")
        assert r["[[auth patterns]]"]["title"] == "Auth Patterns"

    def test_resolves_by_alias(self, tmp_path: Path):
        r = resolve_wikilinks("[[JWT Guide]]", self._vault(tmp_path))
        assert r["[[JWT Guide]]"]["path"].endswith("auth-patterns.md")

    def test_resolves_by_explicit_slug(self, tmp_path: Path):
        # filename is deploy-doc.md but slug: deploy — the override must resolve
        r = resolve_wikilinks("[[deploy]]", self._vault(tmp_path))
        assert r["[[deploy]]"]["path"].endswith("deploy-doc.md")

    def test_unresolved_is_first_class(self, tmp_path: Path):
        r = resolve_wikilinks("[[Nonexistent Thing]]", self._vault(tmp_path))
        assert r["[[Nonexistent Thing]]"] == {"path": None, "title": None, "tier": None}

    def test_title_beats_alias_across_notes(self, tmp_path: Path):
        """Resolution ORDER: a note whose TITLE matches wins over one whose
        ALIAS matches the same target."""
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "real.md", "Backoff")           # title match
        _note(v, "_shared/knowledge", "other.md", "Other", aliases='"Backoff"')
        r = resolve_wikilinks("[[Backoff]]", detect(v))
        assert r["[[Backoff]]"]["path"].endswith("real.md")

    def test_ambiguity_prefers_higher_tier(self, tmp_path: Path):
        """Same title in shared AND a project → the project tier wins."""
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "retry.md", "Retry Strategy")
        _note(v, "projects/app", "retry.md", "Retry Strategy")
        r = resolve_wikilinks("[[Retry Strategy]]", detect(v))
        assert r["[[Retry Strategy]]"]["tier"].startswith("project")

    def test_no_links_returns_empty(self, tmp_path: Path):
        assert resolve_wikilinks("plain text, no links", self._vault(tmp_path)) == {}

    def test_resolves_by_kebab_filename_slug(self, tmp_path: Path):
        """SCHEMA step 3: the default slug is the KEBAB-CASE filename stem, so a
        note filed `API Guide.md` (no explicit slug) resolves `[[api-guide]]`."""
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "API Guide.md", "API Guide")
        r = resolve_wikilinks("[[api-guide]]", detect(v))
        assert r["[[api-guide]]"]["path"].endswith("API Guide.md")

    def test_scalar_alias_resolves(self, tmp_path: Path):
        """A scalar `aliases: JWT` (a YAML string, not a list) must resolve as
        the whole alias, not be walked character-by-character."""
        v = tmp_path / "v"
        d = v / "_shared" / "knowledge"
        d.mkdir(parents=True)
        (d / "auth.md").write_text(
            "---\ntitle: Auth\ntype: knowledge\nstatus: current\naliases: JWT\n"
            "owner: t\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n\n# Auth\n\nx\n"
        )
        r = resolve_wikilinks("[[JWT]] not [[J]]", detect(v))
        assert r["[[JWT]]"]["path"].endswith("auth.md")
        assert r["[[J]]"]["path"] is None  # a single letter is NOT an alias

    def test_title_beats_alias_across_tiers(self, tmp_path: Path):
        """Resolution ORDER dominates tier: a TITLE match in shared wins over an
        ALIAS match in a higher-priority project tier (title step resolves first)."""
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "backoff.md", "Backoff")            # title, shared
        _note(v, "projects/app", "other.md", "Other", aliases='"Backoff"')  # alias, project
        r = resolve_wikilinks("[[Backoff]]", detect(v))
        assert r["[[Backoff]]"]["path"].endswith("backoff.md")
        assert r["[[Backoff]]"]["tier"] == "shared"

    def test_same_tier_tiebreak_is_deterministic(self, tmp_path: Path):
        """Same title in two project tiers (equal rank) resolves deterministically
        by path, independent of walk order."""
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "projects/web", "retry.md", "Retry Strategy")
        _note(v, "projects/api", "retry.md", "Retry Strategy")
        r = resolve_wikilinks("[[Retry Strategy]]", detect(v))
        # api < web by path → the api note wins, stably
        assert "projects/api" in r["[[Retry Strategy]]"]["path"]


class TestRelatedAndLinks:
    def _graph_vault(self, tmp_path: Path):
        v = tmp_path / "v"
        d = v / "_shared" / "knowledge"
        d.mkdir(parents=True)

        def note(fn: str, title: str, body: str) -> None:
            (d / fn).write_text(
                f"---\ntitle: {title}\ntype: knowledge\nstatus: current\n"
                f"owner: t\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n\n"
                f"# {title}\n\n{body}\n"
            )

        note("a.md", "Note A", "links to [[Note B]] and [[Missing Thing]]")
        note("b.md", "Note B", "links to [[Note C]]")
        note("c.md", "Note C", "no links here")
        note("d.md", "Note D", "orphan, no links")
        return v

    def test_related_direct_direction(self, tmp_path: Path):
        vault = detect(self._graph_vault(tmp_path))
        out = related(vault, "_shared/knowledge/a.md", hops=1)
        assert {r["path"] for r in out} == {"_shared/knowledge/b.md"}
        assert out[0]["direction"] == "out"
        b = {r["path"]: r["direction"]
             for r in related(vault, "_shared/knowledge/b.md", hops=1)}
        assert b["_shared/knowledge/a.md"] == "in"    # A links to B
        assert b["_shared/knowledge/c.md"] == "out"   # B links to C

    def test_related_two_hops(self, tmp_path: Path):
        vault = detect(self._graph_vault(tmp_path))
        by_hops = {r["path"]: r["hops"]
                   for r in related(vault, "_shared/knowledge/a.md", hops=2)}
        assert by_hops["_shared/knowledge/b.md"] == 1
        assert by_hops["_shared/knowledge/c.md"] == 2  # A→B→C

    def test_link_report_broken_and_orphans(self, tmp_path: Path):
        rep = link_report(detect(self._graph_vault(tmp_path)))
        assert {"src": "_shared/knowledge/a.md", "target": "Missing Thing"} in rep["broken"]
        assert "_shared/knowledge/d.md" in rep["orphans"]  # nothing links to D
        assert "_shared/knowledge/b.md" not in rep["orphans"]  # A links to B
        # A links OUT but nothing links to it → still an orphan (the surprising,
        # intended semantics: orphan = no INBOUND edge, not zero-degree).
        assert "_shared/knowledge/a.md" in rep["orphans"]

    def test_self_link_note_is_still_an_orphan(self, tmp_path: Path):
        """A note that links only to itself is not linked-to by anything else,
        so a self-edge must not hide it from the orphan report."""
        v = tmp_path / "v"
        d = v / "_shared" / "knowledge"
        d.mkdir(parents=True)
        (d / "hub.md").write_text(
            "---\ntitle: Hub\ntype: knowledge\nstatus: current\nowner: t\n"
            "created: 2026-01-01\nupdated: 2026-01-01\n---\n\n# Hub\n\nsee [[Hub]]\n"
        )
        rep = link_report(detect(v))
        assert "_shared/knowledge/hub.md" in rep["orphans"]

    def test_related_both_direction_and_2hop_label(self, tmp_path: Path):
        """Pin the two unasserted direction strings: 'both' for a mutual pair,
        and 'N-hop' for a farther neighbor."""
        v = tmp_path / "v"
        d = v / "_shared" / "knowledge"
        d.mkdir(parents=True)

        def note(fn, title, body):
            (d / fn).write_text(
                f"---\ntitle: {title}\ntype: knowledge\nstatus: current\nowner: t\n"
                f"created: 2026-01-01\nupdated: 2026-01-01\n---\n\n# {title}\n\n{body}\n"
            )
        note("x.md", "X", "to [[Y]]")          # X ↔ Y mutual, X → ... → Z at 2 hops
        note("y.md", "Y", "to [[X]] and [[Z]]")
        note("z.md", "Z", "leaf")
        out = {r["path"]: r for r in related(detect(v), "_shared/knowledge/x.md", hops=2)}
        assert out["_shared/knowledge/y.md"]["direction"] == "both"  # X↔Y
        assert out["_shared/knowledge/z.md"]["direction"] == "2-hop"

    def test_cli_related_resolves_by_title(self, tmp_path: Path, capsys):
        vault_dir = self._graph_vault(tmp_path)
        rc = main(["--vault", str(vault_dir), "related", "Note A", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "related"
        assert any(r["path"] == "_shared/knowledge/b.md" for r in env["data"]["related"])

    def test_cli_links_reports_broken(self, tmp_path: Path, capsys):
        vault_dir = self._graph_vault(tmp_path)
        rc = main(["--vault", str(vault_dir), "links", "--broken", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert any(b["target"] == "Missing Thing" for b in env["data"]["broken"])

    def test_resolve_note_ref_by_title_and_path(self, tmp_path: Path):
        """The engine ref-resolver (public, shared by CLI + future MCP): a title
        or an already vault-relative path both resolve; a miss is None."""
        vault = detect(self._graph_vault(tmp_path))
        assert resolve_note_ref(vault, "Note A") == "_shared/knowledge/a.md"
        assert resolve_note_ref(vault, "_shared/knowledge/a.md") == "_shared/knowledge/a.md"
        assert resolve_note_ref(vault, "No Such Note") is None

    def test_resolve_note_ref_by_alias_and_slug(self, tmp_path: Path):
        v = tmp_path / "v"
        (v / "_shared" / "knowledge").mkdir(parents=True)
        _note(v, "_shared/knowledge", "auth-patterns.md", "Auth Patterns",
              aliases='"JWT Guide"')
        _note(v, "_shared/knowledge", "deploy-doc.md", "Deploy Checklist", slug="deploy")
        vault = detect(v)
        assert resolve_note_ref(vault, "JWT Guide").endswith("auth-patterns.md")  # alias
        assert resolve_note_ref(vault, "deploy").endswith("deploy-doc.md")        # slug

    def test_resolve_note_ref_path_beats_title(self, tmp_path: Path):
        """A path-shaped ref matches the literal path first, so an explicit path
        is never redirected to a note that carries that string as its title."""
        v = tmp_path / "v"
        d = v / "_shared" / "knowledge"
        d.mkdir(parents=True)
        _note(v, "_shared/knowledge", "target.md", "Real Target")
        # a decoy note whose TITLE is literally the other note's path
        _note(v, "_shared/knowledge", "decoy.md", "_shared/knowledge/target.md")
        vault = detect(v)
        assert resolve_note_ref(vault, "_shared/knowledge/target.md") == \
            "_shared/knowledge/target.md"

    def test_cli_links_json_shape_is_stable(self, tmp_path: Path, capsys):
        """--json always carries both keys regardless of --broken/--orphans, so
        a machine consumer never hits a flag-dependent KeyError."""
        vault_dir = self._graph_vault(tmp_path)
        main(["--vault", str(vault_dir), "links", "--broken", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert "broken" in env["data"] and "orphans" in env["data"]
