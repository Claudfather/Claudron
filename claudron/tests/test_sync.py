"""Tests for `claudron sync` + conflict quarantine (E2 PR3).

Git here is local-only (bare remote on tmp_path) — subprocess, no network,
within the conftest tmp_path convention.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.schema import has_conflict_markers


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def synced_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two clones of one bare remote, each a valid vault — machines A and B."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")

    a = tmp_path / "machine-a"
    _git(tmp_path, "clone", str(remote), str(a))
    main(["init", str(a), "--adopt"])
    note = a / "_shared" / "knowledge" / "shared-note.md"
    note.write_text(
        "---\ntitle: Shared Note\ntype: knowledge\nstatus: current\n"
        "owner: t\ncreated: 2026-07-01\nupdated: 2026-07-01\n"
        "---\n\n# Shared Note\n\nOriginal line.\n"
    )
    _git(a, "add", "-A")
    _git(a, "commit", "-m", "seed")
    _git(a, "push", "origin", "main")

    b = tmp_path / "machine-b"
    _git(tmp_path, "clone", str(remote), str(b))
    return a, b


class TestSyncRoundTrip:
    def test_sd_card_loop(self, synced_pair, capsys):
        """THE acceptance test: a finding captured on machine A reaches
        machine B through sync and surfaces in B's recall."""
        a, b = synced_pair
        rc = main(["--vault", str(a), "capture", "--type", "knowledge",
                   "--title", "Machine A Finding", "--body",
                   "Discovered on A.", "--owner", "bot-a"])
        assert rc == 0
        capsys.readouterr()
        assert main(["--vault", str(a), "sync"]) == 0
        capsys.readouterr()
        assert main(["--vault", str(b), "sync", "--pull"]) == 0
        capsys.readouterr()
        rc = main(["--vault", str(b), "recall", "--query", "machine finding"])
        assert rc == 0
        assert "Machine A Finding" in capsys.readouterr().out

    def test_sync_commits_unstaged_vault_changes(self, synced_pair, capsys):
        """Captures don't git-commit; sync owns the commit+push so notes
        actually travel."""
        a, _ = synced_pair
        (a / "_shared" / "knowledge" / "loose.md").write_text(
            "---\ntitle: Loose Note\ntype: knowledge\nstatus: current\n"
            "owner: t\ncreated: 2026-07-01\nupdated: 2026-07-01\n---\n\n# L\n"
        )
        assert main(["--vault", str(a), "sync"]) == 0
        status = _git(a, "status", "--porcelain").stdout
        assert status.strip() == ""  # committed and pushed

    def test_sync_not_a_git_repo_is_env_error(self, vault_dir: Path, capsys):
        rc = main(["--vault", str(vault_dir), "sync"])
        assert rc == 3
        assert "not a git repository" in capsys.readouterr().err

    def test_sync_json_envelope(self, synced_pair, capsys):
        a, _ = synced_pair
        rc = main(["--vault", str(a), "sync", "--json"])
        assert rc == 0
        import json
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "sync" and env["ok"] is True
        assert {"pulled", "pushed", "quarantined"} <= set(env["data"])


class TestConflictQuarantine:
    def _make_conflict(self, synced_pair, capsys) -> tuple[Path, Path]:
        a, b = synced_pair
        note_rel = "_shared/knowledge/shared-note.md"
        (a / note_rel).write_text(
            (a / note_rel).read_text().replace("Original line.", "A's truth.")
        )
        assert main(["--vault", str(a), "sync"]) == 0
        capsys.readouterr()
        (b / note_rel).write_text(
            (b / note_rel).read_text().replace("Original line.", "B's truth.")
        )
        return b, b / note_rel

    def test_conflict_reports_and_quarantines(self, synced_pair, capsys):
        b, note = self._make_conflict(synced_pair, capsys)
        rc = main(["--vault", str(b), "sync"])
        assert rc == 1  # findings: conflict left for the human
        err = capsys.readouterr().err
        assert "conflict" in err.lower()
        assert has_conflict_markers(note.read_text())

    def test_quarantined_note_excluded_from_recall_and_lookup(
        self, synced_pair, capsys
    ):
        b, note = self._make_conflict(synced_pair, capsys)
        main(["--vault", str(b), "sync"])
        capsys.readouterr()
        rc = main(["--vault", str(b), "lookup", "Shared Note"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Shared Note" not in captured.out  # quarantined, not served

    def test_status_surfaces_quarantine(self, synced_pair, capsys):
        b, _ = self._make_conflict(synced_pair, capsys)
        main(["--vault", str(b), "sync"])
        capsys.readouterr()
        rc = main(["--vault", str(b), "status"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "quarantined" in (captured.out + captured.err).lower()

    def test_resolution_is_stateless(self, synced_pair, capsys):
        """Fix the file → it leaves quarantine with no bookkeeping step."""
        b, note = self._make_conflict(synced_pair, capsys)
        main(["--vault", str(b), "sync"])
        capsys.readouterr()
        note.write_text(
            "---\ntitle: Shared Note\ntype: knowledge\nstatus: current\n"
            "owner: t\ncreated: 2026-07-01\nupdated: 2026-07-02\n"
            "---\n\n# Shared Note\n\nMerged truth.\n"
        )
        rc = main(["--vault", str(b), "lookup", "Shared Note"])
        assert rc == 0
        assert "Shared Note" in capsys.readouterr().out


class TestConflictMarkers:
    def test_real_markers_detected(self):
        text = (
            "---\ntitle: X\n---\n\n<<<<<<< HEAD\nA's truth.\n=======\n"
            "B's truth.\n>>>>>>> origin/main\n"
        )
        assert has_conflict_markers(text)

    def test_prose_about_markers_not_detected(self):
        text = (
            "---\ntitle: Git Guide\n---\n\n# Git Guide\n\n"
            "Conflicts insert `<<<<<<< HEAD` at line starts.\n"
        )
        assert not has_conflict_markers(text)
