"""Tests for the wikilink graph — resolve_wikilinks over the JSON index (E4 C1).

The scale-free graph slice: `resolve_wikilinks` implements SCHEMA.md resolution
(title → alias → slug, case-insensitive; ambiguity → higher tier; unresolved is
first-class), over the existing index — no SQLite (that's the deferred scale bet).
"""

from __future__ import annotations

from pathlib import Path

from claudron import resolve_wikilinks
from claudron.knowledge import wikilink_targets
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
