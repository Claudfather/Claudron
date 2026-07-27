"""Tests for knowledge retrieval engine."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent


from claudron.vault import SCHEMA_VERSION, clear_stale_cache, detect
from claudron.knowledge import (
    _collect_all_docs,
    _parse_doc,
    build_index,
    index_entry,
    load_index,
    lookup,
)

_NOTE = (
    "---\ntitle: {title}\ntype: knowledge\nstatus: current\nowner: c\n"
    "created: 2026-01-01\n---\n\n# {title}\n"
)


class TestNestedSystemUnion:
    """P1: a `.claudron-system` container is a recognized tier, never mis-pooled
    into the Tier-B `other:` union (Claudlobby#602)."""

    def test_system_not_mispooled_as_other(self, nested_system_vault: Path):
        (
            nested_system_vault / "sys1" / "shared" / "knowledge" / "sysnote.md"
        ).write_text(_NOTE.format(title="Sys Note"))
        docs = _collect_all_docs(detect(nested_system_vault))
        # never surfaces via the `other:` hatch ...
        assert not any(d.tier.startswith("other:") for d in docs)
        # ... and P1 does NOT add the system tier to this Tier-B union —
        # recall-union membership is deferred to #601/#47.
        assert not any(d.tier.startswith("system:") for d in docs)

    def test_genuinely_unknown_dir_still_other(self, nested_system_vault: Path):
        """The `other:` hatch still fires for a real unknown top-level dir — the
        system exclusion is targeted, not a blanket removal."""
        unknown = nested_system_vault / "experiments"
        unknown.mkdir()
        (unknown / "note.md").write_text(_NOTE.format(title="X"))
        docs = _collect_all_docs(detect(nested_system_vault))
        assert any(d.tier == "other:experiments" for d in docs)

    def test_nested_fleet_name_does_not_shadow_top_level_other(
        self, nested_fleet_shadow_vault: Path
    ):
        """Claudlobby#602 review: a nested fleet's bare name (`experiments`,
        folded into vault.fleets) must not shadow the unrelated TOP-LEVEL
        `experiments/` out of the Tier-B `other:` union — else its note
        silently vanishes from recall."""
        docs = _collect_all_docs(detect(nested_fleet_shadow_vault))
        assert any(d.tier == "other:experiments" for d in docs)


class TestScalarFrontmatterCoercion:
    """#101: a scalar `tags:` / `aliases:` is one value, never a character
    sequence — both parse paths (Tier-A `index_entry`, Tier-B `_parse_doc`)
    route through `_as_str_list`."""

    def _write_scalar_note(self, vault_dir: Path) -> None:
        (vault_dir / "_shared" / "knowledge" / "scalar-tagged.md").write_text(
            dedent("""\
            ---
            title: Scalar Tagged Note
            type: knowledge
            status: current
            tags: singleton
            ---

            Nothing else searchable here.
            """)
        )

    def test_scalar_tag_scores_as_a_tag(self, vault_dir: Path):
        """The #101 bug: the raw scalar char-exploded in scoring, so the
        full tag word could never match. Fails on the pre-fix code."""
        self._write_scalar_note(vault_dir)
        vault = detect(vault_dir)
        results = lookup("singleton", vault)
        assert results and results[0].match_type == "tag"

    def test_index_entry_coerces_scalar_tags(self):
        entry = index_entry({"tags": "solo"}, "b", Path("t.md"), "shared", Path("."))
        assert entry["tags"] == ["solo"]

    def test_index_entry_scalar_aliases_still_coerced(self):
        entry = index_entry({"aliases": "Foo"}, "b", Path("t.md"), "shared", Path("."))
        assert entry["aliases"] == ["Foo"]

    def test_non_string_scalar_does_not_crash_either_tier(self, vault_dir: Path):
        """`tags: 5` (YAML int): pre-fix Tier B iterated an int → TypeError;
        both tiers now coerce to ["5"]."""
        note = vault_dir / "_shared" / "knowledge" / "int-tagged.md"
        note.write_text(
            dedent("""\
            ---
            title: Int Tagged Note
            type: knowledge
            status: current
            tags: 5
            ---

            Body.
            """)
        )
        assert _parse_doc(note, "shared").tags == ["5"]
        assert index_entry({"tags": 5}, "b", Path("t.md"), "shared", Path("."))["tags"] == ["5"]

    def test_parse_doc_scalar_tags_unchanged(self, vault_dir: Path):
        self._write_scalar_note(vault_dir)
        note = vault_dir / "_shared" / "knowledge" / "scalar-tagged.md"
        assert _parse_doc(note, "shared").tags == ["singleton"]


class TestScoring:
    def test_lookup_exact_title(self, vault_dir: Path):
        vault = detect(vault_dir)
        results = lookup("Auth Patterns Across Services", vault)
        assert len(results) >= 1
        assert results[0].score == 100
        assert results[0].match_type == "title"

    def test_lookup_title_substring(self, vault_dir: Path):
        vault = detect(vault_dir)
        results = lookup("auth patterns", vault)
        assert len(results) >= 1
        assert results[0].score >= 80
        assert results[0].match_type == "title"

    def test_lookup_tag_exact(self, vault_dir: Path):
        vault = detect(vault_dir)
        results = lookup("jwt", vault)
        assert len(results) >= 1
        assert results[0].match_type == "tag"
        assert results[0].score >= 60

    def test_lookup_content_match(self, vault_dir: Path):
        vault = detect(vault_dir)
        results = lookup("RS256", vault)
        assert len(results) >= 1
        # Tier B body match
        assert results[0].match_type in ("content", "heading")

    def test_lookup_no_match(self, vault_dir: Path):
        vault = detect(vault_dir)
        results = lookup("kubernetes helm chart", vault)
        assert results == []

    def test_multiword_tokenization(self, vault_dir: Path):
        vault = detect(vault_dir)
        # "checklist deploy" is NOT a substring of "Deploy Checklist",
        # so phrase match fails and multi-word tokenization fires.
        results = lookup("checklist deploy", vault)
        assert len(results) >= 1
        top = results[0]
        assert "deploy checklist" in top.doc.title.lower()
        # Tokens accumulate across match types (#219)
        assert top.match_type == "title"
        assert top.score == 200

    def test_lookup_in_shared_vault(self, shared_vault: Path):
        """Lookup works in vaults using shared/ instead of _shared/."""
        vault = detect(shared_vault)
        results = lookup("Testing Guide", vault)
        assert len(results) >= 1
        assert results[0].score == 100


class TestTiers:
    def test_tier_ordering(self, vault_with_projects: Path):
        """Project-tier results sort before shared-tier at equal score."""
        # Add a shared doc with similar title
        (vault_with_projects / "_shared" / "knowledge" / "neon-general.md").write_text(
            dedent("""\
            ---
            title: Neon Connection Pooling
            type: knowledge
            status: active
            owner: mason
            tags: [neon, database]
            created: 2026-04-01
            updated: 2026-05-01
            ---

            # Neon Connection Pooling

            General neon pooling info.
        """)
        )
        vault = detect(vault_with_projects)
        results = lookup("neon", vault, project="storydump", limit=10)
        # Both should appear; project should be first (at equal score, project wins)
        project_results = [r for r in results if r.doc.tier.startswith("project:")]
        shared_results = [r for r in results if r.doc.tier == "shared"]
        assert len(project_results) >= 1
        assert len(shared_results) >= 1
        # First project result should come before first shared result
        first_project_idx = next(
            i for i, r in enumerate(results) if r.doc.tier.startswith("project:")
        )
        first_shared_idx = next(
            i for i, r in enumerate(results) if r.doc.tier == "shared"
        )
        # If scores are equal, project wins on tier priority
        if project_results[0].score == shared_results[0].score:
            assert first_project_idx < first_shared_idx


class TestLimits:
    def test_limit_respected(self, vault_dir: Path):
        # Add many docs
        for i in range(20):
            (vault_dir / "_shared" / "knowledge" / f"topic-{i}.md").write_text(
                dedent(f"""\
                ---
                title: Topic {i} About Auth
                type: knowledge
                status: active
                owner: alex
                tags: [auth, topic-{i}]
                created: 2026-04-01
                updated: 2026-05-01
                ---

                # Topic {i} About Auth

                Auth related content number {i}.
            """)
            )
        vault = detect(vault_dir)
        results = lookup("auth", vault, limit=5)
        assert len(results) <= 5


class TestFiltering:
    def test_skips_index_and_readme(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "INDEX.md").write_text(
            "# Index\n- stuff"
        )
        (vault_dir / "_shared" / "knowledge" / "README.md").write_text("# Readme")
        vault = detect(vault_dir)
        results = lookup("index", vault, limit=20)
        paths = [str(r.doc.source_path.name) for r in results]
        assert "INDEX.md" not in paths
        assert "README.md" not in paths

    def test_missing_frontmatter_uses_filename(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "no-frontmatter.md").write_text(
            "Just a plain markdown file about testing.\n"
        )
        vault = detect(vault_dir)
        results = lookup("no frontmatter", vault, limit=10)
        # Should find it by filename
        matching = [r for r in results if "no-frontmatter" in str(r.doc.source_path)]
        assert len(matching) >= 1
        assert matching[0].doc.title == "No frontmatter"

    def test_ratified_decision_visible_by_default(self, vault_dir: Path):
        """Pin (E1/PR2 guard): `ratified` is terminal for staleness but must
        NEVER enter the lookup-exclusion set — a ratified decision is the most
        authoritative note in the vault and stays searchable."""
        (vault_dir / "_shared" / "decisions" / "adr-sqlite.md").write_text(
            dedent("""\
                ---
                title: ADR SQLite Index Backend
                type: decision
                status: ratified
                owner: chris
                tags: [adr, index]
                created: 2026-07-01
                updated: 2026-07-01
                ---

                # ADR SQLite Index Backend

                The index mirror uses stdlib sqlite3.
            """)
        )
        vault = detect(vault_dir)
        results = lookup("ADR SQLite Index Backend", vault, limit=10)
        ratified = [r for r in results if r.doc.title == "ADR SQLite Index Backend"]
        assert len(ratified) == 1

    def test_shared_planning_docs_searchable(self, vault_dir: Path):
        """E1 (#4 reversal): vault-level planning docs are indexed and found."""
        active = vault_dir / "_shared" / "planning" / "active"
        active.mkdir(parents=True)
        (active / "sd-card-rollout.md").write_text(
            dedent("""\
                ---
                title: SD Card Rollout Plan
                type: plan
                status: active
                owner: chris
                tags: [rollout]
                created: 2026-07-01
                updated: 2026-07-01
                ---

                # SD Card Rollout Plan

                Ship recall and capture to both machines.
            """)
        )
        vault = detect(vault_dir)
        results = lookup("SD Card Rollout Plan", vault, limit=10)
        plans = [r for r in results if r.doc.title == "SD Card Rollout Plan"]
        assert len(plans) == 1
        assert plans[0].doc.tier == "shared"

    def test_excludes_archived_by_default(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "old-auth.md").write_text(
            dedent("""\
            ---
            title: Old Auth Approach
            type: knowledge
            status: archived
            owner: mason
            tags: [auth]
            created: 2026-01-01
            updated: 2026-02-01
            ---

            # Old Auth Approach

            We used to do basic auth. Don't anymore.
        """)
        )
        vault = detect(vault_dir)
        results = lookup("Old Auth Approach", vault, limit=10)
        archived = [r for r in results if r.doc.title == "Old Auth Approach"]
        assert len(archived) == 0

        # But with include_archived
        results = lookup("Old Auth Approach", vault, limit=10, include_archived=True)
        archived = [r for r in results if r.doc.title == "Old Auth Approach"]
        assert len(archived) >= 1

    def test_excludes_expired_by_default(self, vault_dir: Path):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        (vault_dir / "_shared" / "knowledge" / "expired-doc.md").write_text(
            dedent(f"""\
            ---
            title: Expired Knowledge
            type: knowledge
            status: active
            owner: alex
            tags: [expired-test]
            created: 2026-01-01
            updated: 2026-01-01
            expires: {yesterday}
            ---

            # Expired Knowledge

            This doc has expired.
        """)
        )
        vault = detect(vault_dir)
        results = lookup("Expired Knowledge", vault, limit=10)
        expired = [r for r in results if r.doc.title == "Expired Knowledge"]
        assert len(expired) == 0

        results = lookup("Expired Knowledge", vault, limit=10, include_expired=True)
        expired = [r for r in results if r.doc.title == "Expired Knowledge"]
        assert len(expired) >= 1


class TestScoreMerge:
    def test_tier_b_merges_with_tier_a(self, vault_dir: Path):
        """When a doc scores low in Tier A and also matches body, scores merge."""
        # filename match only -> score 30 (below TIER_A_THRESHOLD of 50)
        (vault_dir / "_shared" / "knowledge" / "caching.md").write_text(
            dedent("""\
            ---
            title: Caching Strategies
            type: knowledge
            status: active
            owner: alex
            tags: [performance]
            created: 2026-04-01
            updated: 2026-05-01
            ---

            # Caching Strategies

            Use caching for frequently accessed data.
        """)
        )
        vault = detect(vault_dir)
        # "caching" matches filename (30) in Tier A, and heading (70) in Tier B
        results = lookup("caching", vault, limit=10)
        caching_results = [r for r in results if "Caching" in r.doc.title]
        assert len(caching_results) >= 1
        # Score should be merged (30 + 70 = 100), not just 30
        assert caching_results[0].score > 30


class TestProjectVisibility:
    def test_unscoped_lookup_finds_project_docs(self, vault_with_projects: Path):
        """Tier B body search finds project docs even without --project."""
        vault = detect(vault_with_projects)
        # "serverless driver" appears only in the project doc body
        results = lookup("serverless driver", vault, limit=10)
        assert len(results) >= 1
        assert any(r.doc.tier.startswith("project:") for r in results)


class TestIndex:
    def test_index_build_and_load(self, vault_dir: Path):
        vault = detect(vault_dir)
        index = build_index(vault)
        assert "entries" in index
        assert len(index["entries"]) == 2  # auth-patterns + deploy-checklist

        loaded = load_index(vault)
        assert loaded is not None
        assert len(loaded["entries"]) == 2

    def test_index_stale_detection(self, vault_dir: Path):
        import time

        vault = detect(vault_dir)
        build_index(vault)
        loaded = load_index(vault)
        assert loaded is not None

        # Touch a file to make index stale
        time.sleep(0.05)
        (vault_dir / "_shared" / "knowledge" / "auth-patterns.md").write_text(
            (vault_dir / "_shared" / "knowledge" / "auth-patterns.md").read_text()
            + "\nupdate"
        )
        clear_stale_cache()
        loaded = load_index(vault)
        assert loaded is None  # stale

    def test_index_build_warns_on_unwritable_dir(self, vault_dir: Path):
        import warnings

        vault = detect(vault_dir)
        # Make .claudron unwritable
        claudron_dir = vault_dir / ".claudron"
        claudron_dir.mkdir(exist_ok=True)
        claudron_dir.chmod(0o444)
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                index = build_index(vault)
            # Should warn but still return the index
            assert len(w) == 1
            assert "could not write index" in str(w[0].message)
            assert "entries" in index
        finally:
            claudron_dir.chmod(0o755)


class TestSchemaVersion:
    def test_index_has_schema_version(self, vault_dir: Path):
        vault = detect(vault_dir)
        index = build_index(vault)
        assert "schema_version" in index
        assert index["schema_version"] == SCHEMA_VERSION

    def test_stale_schema_triggers_rebuild(self, vault_dir: Path):
        vault = detect(vault_dir)
        build_index(vault)
        # Tamper with version
        index_path = vault_dir / ".claudron" / "index.json"
        data = json.loads(index_path.read_text())
        data["schema_version"] = 0
        index_path.write_text(json.dumps(data))
        loaded = load_index(vault)
        assert loaded is None


class TestWordBoundary:
    def test_word_boundary_bonus(self, vault_dir: Path):
        """Full-word substring matches score higher than partial-word matches."""
        (vault_dir / "_shared" / "knowledge" / "auth-guide.md").write_text(
            dedent("""\
            ---
            title: Auth Guide
            tags: [security]
            ---

            # Auth Guide
        """)
        )
        (vault_dir / "_shared" / "knowledge" / "authentication-methods.md").write_text(
            dedent("""\
            ---
            title: Authentication Methods
            tags: [security]
            ---

            # Authentication Methods
        """)
        )
        vault = detect(vault_dir)
        results = lookup("auth", vault, limit=10)
        auth_guide = [r for r in results if r.doc.title == "Auth Guide"]
        auth_methods = [r for r in results if r.doc.title == "Authentication Methods"]
        assert len(auth_guide) >= 1
        assert len(auth_methods) >= 1
        # "auth" is a full word in "Auth Guide" but a prefix in "Authentication Methods"
        assert auth_guide[0].score > auth_methods[0].score


class TestMultiWordAccumulation:
    def test_tokens_accumulate_across_match_types(self, vault_dir: Path):
        """Multi-word tokens accumulate scores from title, tag, and filename."""
        vault = detect(vault_dir)
        results = lookup("checklist deploy", vault, limit=10)
        assert len(results) >= 1
        top = results[0]
        assert "deploy checklist" in top.doc.title.lower()
        # With if-chain (#219), tokens accumulate: title + tag + filename
        assert top.score > 100


class TestUnicode:
    def test_accented_characters(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "cafe-guide.md").write_text(
            dedent("""\
            ---
            title: "Caf\u00e9 Deployment Guide"
            tags: ["caf\u00e9", deploy]
            ---

            # Caf\u00e9 Deployment Guide

            D\u00e9ployer le caf\u00e9.
        """)
        )
        vault = detect(vault_dir)
        results = lookup("caf\u00e9", vault, limit=10)
        matching = [r for r in results if "Caf\u00e9" in r.doc.title]
        assert len(matching) >= 1

    def test_cjk_characters(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "db-guide-ja.md").write_text(
            dedent("""\
            ---
            title: "\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9\u30ac\u30a4\u30c9"
            tags: ["\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9"]
            ---

            # \u30c7\u30fc\u30bf\u30d9\u30fc\u30b9\u30ac\u30a4\u30c9

            \u30c7\u30fc\u30bf\u30d9\u30fc\u30b9\u306e\u8a2d\u8a08\u30d1\u30bf\u30fc\u30f3\u3002
        """)
        )
        vault = detect(vault_dir)
        results = lookup("\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9", vault, limit=10)
        matching = [
            r for r in results if "\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9" in r.doc.title
        ]
        assert len(matching) >= 1

    def test_emoji_in_content(self, vault_dir: Path):
        (vault_dir / "_shared" / "knowledge" / "security-keys.md").write_text(
            dedent("""\
            ---
            title: Security Key Guide
            tags: [security]
            ---

            # Security Key Guide

            Use \U0001f511 keys for authentication.
        """)
        )
        vault = detect(vault_dir)
        results = lookup("\U0001f511", vault, limit=10)
        matching = [r for r in results if r.doc.title == "Security Key Guide"]
        assert len(matching) >= 1


class TestGhostEntries:
    def test_deleted_note_drops_from_index_no_ghost(self, vault_dir: Path):
        """A note removed from disk must not linger as a ghost index entry
        (mtime-forward staleness never sees a deletion)."""
        from claudron.knowledge import build_index, ensure_index
        from claudron.vault import clear_stale_cache, detect

        vault = detect(vault_dir)
        build_index(vault)
        victim = vault_dir / "_shared" / "knowledge" / "deploy-checklist.md"
        rel = str(victim.relative_to(vault.root))
        victim.unlink()

        clear_stale_cache()
        index = ensure_index(vault)
        paths = [e["path"] for e in index["entries"]]
        assert rel not in paths, f"ghost entry survived deletion: {rel}"
