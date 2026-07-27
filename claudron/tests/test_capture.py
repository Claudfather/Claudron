"""Tests for the write engine and `claudron capture` (E2 PR2)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from textwrap import dedent

import pytest

from claudron.cli import main
from claudron.schema import parse_note


def _existing(vault: Path, *, status: str = "current", aliases: str | None = None) -> Path:
    """A pre-existing shared note for dedup scenarios."""
    alias_line = f"aliases: [{aliases}]\n" if aliases else ""
    path = vault / "_shared" / "knowledge" / "retry-strategy.md"
    path.write_text(
        "---\n"
        "title: Retry Strategy\n"
        "type: knowledge\n"
        f"status: {status}\n"
        f"{alias_line}"
        "owner: mason\n"
        "created: 2026-06-01\n"
        "updated: 2026-06-10\n"
        "---\n\n# Retry Strategy\n\nExponential backoff everywhere.\n"
    )
    return path


class TestCaptureCreates:
    def test_round_trip_strict_valid_draft(self, vault_dir: Path, capsys):
        """The write-path guarantee: capture output is strict-valid on disk
        and enters at maturity: draft (agent write, SCHEMA.md)."""
        rc = main(["--vault", str(vault_dir), "capture",
                   "--type", "knowledge", "--title", "Circuit Breakers",
                   "--body", "Trip after 5 consecutive failures.",
                   "--tags", "resilience", "--owner", "bot-1", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "created"
        path = Path(env["data"]["path"])
        fm, body, err = parse_note(path.read_text())
        assert err is None
        assert fm["maturity"] == "draft"
        assert fm["owner"] == "bot-1"
        assert "Trip after 5" in body
        assert main(["validate", str(path), "--strict"]) == 0

    def test_project_scope_and_yaml_special_title(self, vault_with_projects: Path, capsys):
        rc = main(["--vault", str(vault_with_projects), "capture",
                   "--type", "knowledge", "--title", "Pooling: 2026 findings",
                   "--body", "B.", "--project", "storydump", "--owner", "b", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        path = Path(env["data"]["path"])
        assert "projects/storydump" in str(path)
        fm, _, err = parse_note(path.read_text())
        assert err is None and fm["title"] == "Pooling: 2026 findings"

    def test_owner_derived_when_absent(self, vault_dir: Path, capsys, monkeypatch):
        monkeypatch.setenv("USER", "cap-user")
        import subprocess
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Ownerless Capture", "--body", "B.", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        assert fm["owner"] == "cap-user"

    def test_stdin_json_mode(self, vault_dir: Path, capsys, monkeypatch):
        import io
        finding = {"type": "decision", "title": "Use Backoff",
                   "body": "Decided.", "owner": "bot-2", "tags": ["adr"]}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(finding)))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "created"
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        assert fm["type"] == "decision" and fm["tags"] == ["adr"]


class TestCaptureProvenance:
    """`source_url` / `source_type` carried into frontmatter (Claudron #44).

    SCHEMA.md has typed both fields since v1; capture dropped them, so every
    consumer with a provenance to record folded it into a body line — coupling
    itself to how `session.py:_summary` picks a summary. The fields are the
    transport; the body line was never one.
    """

    def _capture(self, vault_dir: Path, capsys, *extra: str) -> dict:
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Pool Exhaustion", "--body", "Ship it.",
                   "--owner", "bot-1", "--json", *extra])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        fm, _, err = parse_note(Path(env["data"]["path"]).read_text())
        assert err is None
        return fm

    def test_flags_land_in_frontmatter_and_strict_validate(
        self, vault_dir: Path, capsys
    ):
        fm = self._capture(
            vault_dir, capsys,
            "--source-url", "https://example.com/a?x=1", "--source-type", "url",
        )
        assert fm["source_url"] == "https://example.com/a?x=1"
        assert fm["source_type"] == "url"
        assert main(["validate", "--strict",
                     str(vault_dir / "_shared" / "knowledge")]) == 0

    def test_stdin_keys_land_too(self, vault_dir: Path, capsys, monkeypatch):
        """Programmatic writers pass JSON on stdin; the fields must reach them
        by the same door as every other capture field."""
        import io

        finding = {"type": "knowledge", "title": "Ingested Article",
                   "body": "B.", "owner": "bot-2",
                   "source_url": "https://example.com/b", "source_type": "url"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(finding)))
        assert main(["--vault", str(vault_dir), "capture", "--stdin", "--json"]) == 0
        env = json.loads(capsys.readouterr().out)
        fm, _, _ = parse_note(Path(env["data"]["path"]).read_text())
        assert fm["source_url"] == "https://example.com/b"
        assert fm["source_type"] == "url"

    def test_absent_when_not_supplied(self, vault_dir: Path, capsys):
        """Optional means absent, not empty. A blank `source_url:` would make
        every unsourced note look sourced-but-unknown."""
        fm = self._capture(vault_dir, capsys)
        assert "source_url" not in fm and "source_type" not in fm

    def test_url_needing_yaml_quoting_round_trips(self, vault_dir: Path, capsys):
        """Frontmatter is hand-assembled; a URL that YAML would re-read as
        something else must come back byte-identical."""
        tricky = "https://example.com/a #b"
        fm = self._capture(vault_dir, capsys, "--source-url", tricky)
        assert fm["source_url"] == tricky

    def test_source_type_is_the_schema_vocabulary(self, vault_dir: Path, capsys):
        """SCHEMA.md types the field `url | file | inline`. The door does not
        mint values outside its own ratified vocabulary — an out-of-vocabulary
        value is a usage error, not an unvalidatable note on disk."""
        with pytest.raises(SystemExit) as exc:
            main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                  "--title", "T", "--body", "B.", "--source-type", "article"])
        assert exc.value.code == 2

    def test_stdin_source_type_obeys_the_same_vocabulary(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        """The *machine* spelling is the one that has to hold.

        `choices` on the flag guards the human path; the contract sends every
        programmatic writer through `--stdin`, so a check that lives only in
        argparse leaves the door that matters wide open — and writes a note
        whose `source_type` the schema does not define.
        """
        import io

        finding = {"type": "knowledge", "title": "Smuggled Type", "body": "B.",
                   "owner": "bot-3", "source_type": "article"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(finding)))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin"])
        assert rc == 2
        assert "source_type" in capsys.readouterr().err
        assert not list((vault_dir / "_shared" / "knowledge").glob("smuggled*"))

    def test_no_last_verified_stamp(self, vault_dir: Path, capsys):
        """Deferred to #54/#55 — the field's meaning is 'structurally verified',
        and nothing here verifies anything. Stamping it at capture time would
        make every unverified note claim verification."""
        fm = self._capture(vault_dir, capsys, "--source-url", "https://x/y")
        assert "last_verified" not in fm


class TestCaptureDedup:
    """Dedup routes, never hard-rejects (E3 contract, cycle-1 fold)."""

    def test_exact_title_suggests_update(self, vault_dir: Path, capsys):
        existing = _existing(vault_dir)
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "New angle.",
                   "--owner", "b", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "suggest_update"
        assert env["data"]["path"].endswith("retry-strategy.md")
        assert "Retry Strategy" in env["data"]["reason"]
        # Nothing new written
        assert (vault_dir / "_shared" / "knowledge" / "retry-strategy.md").read_text().count("Addendum") == 0
        assert existing.read_text().count("New angle") == 0

    def test_alias_match_suggests_update(self, vault_dir: Path, capsys):
        _existing(vault_dir, aliases="Backoff Policy")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Backoff Policy", "--body", "B.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "suggest_update"

    def test_written_flag_distinguishes_a_save_from_a_suggestion(
        self, vault_dir: Path, capsys
    ):
        """PR-H (Juncture B): a dedup suggestion succeeds (exit 0, ok:true)
        having written nothing — `written` is the signal a CLI-wrapping skill
        must branch on, or it silently drops the finding."""
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "First.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "created"
        assert env["data"]["written"] is True

        # Same title again → dedup routes to suggest_*; nothing written.
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Second.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["ok"] is True          # command succeeded
        assert env["data"]["action"].startswith("suggest_")
        assert env["data"]["written"] is False        # …but no note landed

    def test_stale_match_suggests_supersede(self, vault_dir: Path, capsys):
        _existing(vault_dir, status="stale")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Fresh truth.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "suggest_supersede"

    def test_ratified_decision_attracts_dedup(self, vault_dir: Path, capsys):
        """Gauntlet fix: a ratified decision is authoritative — a same-title
        capture must suggest updating it, never silently twin it (dedup
        skips DEDUP_EXEMPT, not the staleness set)."""
        (vault_dir / "_shared" / "decisions" / "retry-strategy.md").write_text(
            "---\ntitle: Retry Strategy\ntype: decision\nstatus: ratified\n"
            "owner: chris\ncreated: 2026-06-01\nupdated: 2026-06-01\n"
            "---\n\n# Retry Strategy\n\nRatified.\n"
        )
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Twin attempt.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "suggest_update"

    def test_write_path_keeps_index_fresh(self, vault_dir: Path, capsys):
        """Gauntlet fix (Θ(N²)): capture maintains the index — after a
        write, the index loads fresh (no rebuild) and already contains the
        new note's entry."""
        from claudron.knowledge import load_index
        from claudron.vault import clear_stale_cache, detect

        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Fresh Index Proof", "--body", "B.",
                   "--owner", "b", "--json"])
        assert rc == 0
        capsys.readouterr()
        clear_stale_cache()
        index = load_index(detect(vault_dir))
        assert index is not None, "index stale after capture — rebuild-per-write regression"
        assert any(e["title"] == "Fresh Index Proof" for e in index["entries"])

    def test_terminal_match_does_not_attract(self, vault_dir: Path, capsys):
        """A superseded note is done — same title creates fresh."""
        _existing(vault_dir, status="superseded")
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Successor.",
                   "--owner", "b", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "created"
        # slug taken by the superseded note → suffixed
        assert env["data"]["path"].endswith("retry-strategy-2.md")

    def test_force_creates_despite_duplicate(self, vault_dir: Path, capsys):
        _existing(vault_dir)
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Retry Strategy", "--body", "Deliberate twin.",
                   "--owner", "b", "--force", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert rc == 0 and env["data"]["action"] == "created"
        assert env["data"]["path"].endswith("retry-strategy-2.md")


class TestCaptureUpdate:
    def test_update_appends_addendum_and_bumps_updated(self, vault_dir: Path, capsys):
        existing = _existing(vault_dir)
        rel = "_shared/knowledge/retry-strategy.md"
        rc = main(["--vault", str(vault_dir), "capture",
                   "--update", rel, "--body", "Jitter matters too.", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["action"] == "updated"
        text = existing.read_text()
        fm, body, err = parse_note(text)
        assert err is None
        assert "## Addendum" in body and "Jitter matters too." in body
        assert str(fm["updated"]) != "2026-06-10"  # bumped
        assert "Exponential backoff everywhere." in body  # original intact
        assert main(["validate", str(existing)]) == 0

    def test_update_keeps_index_fresh(self, vault_dir: Path, capsys):
        from claudron.knowledge import load_index
        from claudron.vault import clear_stale_cache, detect

        _existing(vault_dir)
        main(["--vault", str(vault_dir), "capture",
              "--update", "_shared/knowledge/retry-strategy.md",
              "--body", "Addendum body."])
        capsys.readouterr()
        clear_stale_cache()
        index = load_index(detect(vault_dir))
        assert index is not None
        entry = next(e for e in index["entries"]
                     if e["path"] == "_shared/knowledge/retry-strategy.md")
        assert entry["updated"] != "2026-06-10"  # bumped in the index too

    def test_update_missing_note_is_usage_error(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "capture",
                   "--update", "_shared/knowledge/nope.md", "--body", "X."])
        assert rc == 2
        assert "no such note" in capsys.readouterr().err


class TestCaptureValidation:
    def test_invalid_finding_rejected_with_findings(self, vault_dir: Path, capsys, monkeypatch):
        """Schema-invalid input → exit 1, Finding elements in the envelope,
        nothing written (the write-path guarantee's other half)."""
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
            {"type": "memo", "title": "Bad", "body": "B.", "owner": "b"})))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
        assert rc == 1
        env = json.loads(capsys.readouterr().out)
        assert env["ok"] is False
        assert any(f["code"] == "E002" for f in env["errors"])
        assert not list((vault_dir / "_shared" / "knowledge").glob("bad*"))

    def test_capture_scope_containment(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "capture", "--type", "knowledge",
                   "--title", "Esc", "--body", "B.", "--owner", "b",
                   "--project", "../../escaped"])
        assert rc == 2
        assert "escapes the vault root" in capsys.readouterr().err
        assert not (vault_dir.parent / "escaped").exists()


class TestContentAwareDedup:
    def test_identical_content_under_a_different_title_is_not_silently_created(
        self, vault_dir: Path
    ):
        """Byte-identical body under a new title must route to dedup, not
        silently create a twin (the content-blind-dedup regression)."""
        from claudron.engine import capture
        from claudron.vault import clear_stale_cache, detect

        vault = detect(vault_dir)
        body = "One exact body, captured twice under two unrelated titles."
        first = capture(
            vault, note_type="knowledge", title="Alpha One", body=body, owner="tester"
        )
        assert first.action == "created"

        clear_stale_cache()
        second = capture(
            vault,
            note_type="knowledge",
            title="Beta Two Unrelated",
            body=body,
            owner="tester",
        )
        assert (
            second.action != "created"
        ), f"identical content under a new title silently duplicated: {second.action}"
        assert second.action in ("suggest_update", "suggest_supersede")


class TestCaptureStdinTags:
    """`tags` takes one grammar on both spellings (docs/CLI_CONTRACT.md): the
    --stdin key normalizes exactly like the --tags flag — a comma string
    splits, an array passes element-wise, a scalar is one tag. Never a
    character sequence walked into the note."""

    def _capture_fm(self, vault_dir, capsys, monkeypatch, title, tags_value):
        payload = {"type": "knowledge", "title": title, "body": "Body.",
                   "owner": "t", "tags": tags_value}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        rc = main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        p = Path(env["data"]["path"])
        note = p if p.is_absolute() else vault_dir / p
        fm, _, err = parse_note(note.read_text())
        assert err is None
        return fm

    def test_stdin_comma_string_splits_not_char_explodes(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        fm = self._capture_fm(
            vault_dir, capsys, monkeypatch, "Comma Probe", "alpha,beta"
        )
        assert fm["tags"] == ["alpha", "beta"]

    def test_stdin_array_passes_element_wise(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        fm = self._capture_fm(vault_dir, capsys, monkeypatch, "Array Probe", ["x", "y"])
        assert fm["tags"] == ["x", "y"]

    def test_stdin_scalar_is_one_tag_not_a_crash(
        self, vault_dir: Path, capsys, monkeypatch
    ):
        fm = self._capture_fm(vault_dir, capsys, monkeypatch, "Scalar Probe", 5)
        assert fm["tags"] == ["5"]
