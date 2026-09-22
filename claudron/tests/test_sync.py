"""Tests for `claudron sync` + conflict quarantine (E2 PR3).

Git here is local-only (bare remote on tmp_path) — subprocess, no network,
within the conftest tmp_path convention.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from claudron.cli import main
from claudron.schema import has_conflict_markers
from claudron.sync import SyncTimeout, sync
from claudron.vault import detect


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

    def test_commits_without_a_configured_git_identity(self, tmp_path, monkeypatch):
        """#91: the engine commits on the operator's behalf, so a host with no
        git identity (fresh Pi / container / CI) must still commit — run_git
        injects a fallback identity for its own commits. Without the fix, git
        refuses to auto-guess and the commit is silently lost."""
        from claudron.sync import _has_git_identity, run_git, sync
        from claudron.vault import detect

        # Isolate from any ambient identity (global/system config + env vars).
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / "nogitconfig"))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(home / "nogitconfig-sys"))
        for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        root = tmp_path / "vault"
        (root / "_shared" / "knowledge").mkdir(parents=True)
        run_git(root, "init", "--initial-branch=main")
        # Forbid git from auto-deriving an identity from hostname/username, so a
        # missing identity truly fails a commit (as on a locked-down host).
        run_git(root, "config", "user.useConfigOnly", "true")
        assert not _has_git_identity(root)  # precondition: genuinely identity-less

        (root / "_shared" / "knowledge" / "n.md").write_text(
            "---\ntitle: N\ntype: knowledge\nstatus: current\n"
            "owner: t\ncreated: 2026-07-01\n---\n\n# N\n\nbody\n"
        )
        result = sync(detect(root), pull=False, push=False)
        assert result.committed, f"commit dropped on an identity-less host: {result.detail}"

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


class TestScaffoldTravels:
    def test_fresh_vault_clone_is_detectable(self, tmp_path: Path):
        """Live-verification catch #2: git doesn't track empty dirs, so a
        young vault's clone arrived with NO _shared/ — undetectable, and
        every hook silently no-opped on machine B. The scaffold must
        travel (_shared/ leaf .gitkeeps, CONVENTIONS.md, and projects/CLAUDE.md)."""
        from claudron.vault import detect

        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git(remote, "init", "--bare", "--initial-branch=main")
        a = tmp_path / "a"
        _git(tmp_path, "clone", str(remote), str(a))
        main(["init", str(a), "--adopt"])  # scaffold ONLY — no notes yet
        _git(a, "add", "-A")
        _git(a, "commit", "-m", "seed")
        _git(a, "push", "origin", "main")

        b = tmp_path / "b"
        _git(tmp_path, "clone", str(remote), str(b))
        vault = detect(b)
        assert vault is not None, "empty-tier vault clone lost _shared/"
        assert (b / "_shared" / "CONVENTIONS.md").is_file()  # E1 deliverable
        assert (b / "projects" / "CLAUDE.md").is_file()
        # The _shared/ tier leaves must travel too (.gitkeep per leaf) —
        # CONVENTIONS.md alone carries _shared/ but not its subdirs, and
        # the loop below is what makes the .gitkeep red-green cycle red.
        from claudron.vault import SCAFFOLD_TREE

        for leaf in SCAFFOLD_TREE:
            assert (b / "_shared" / leaf).is_dir(), f"tier leaf lost in clone: {leaf}"


class TestHookDrivenLoop:
    def test_pull_born_project_reaches_the_brief(
        self, synced_pair, tmp_path, capsys, monkeypatch
    ):
        """Live-verification catch: a project tier born on machine A must
        be visible to machine B's FIRST hook-driven brief — the hook must
        re-detect the vault after the pull (the pre-pull Vault snapshot
        and any index built from it cannot see a new tier)."""
        import io

        a, b = synced_pair
        # A: project-scoped capture + sync (project dir is born here)
        assert main(["--vault", str(a), "capture", "--type", "knowledge",
                     "--title", "Pool Exhaustion Fix",
                     "--body", "Set pool_timeout=10.",
                     "--project", "storydump", "--owner", "bot-a"]) == 0
        assert main(["--vault", str(a), "sync"]) == 0
        capsys.readouterr()
        # B: session runs inside a storydump checkout; ONE hook invocation
        work = tmp_path / "work" / "storydump" / "src"
        work.mkdir(parents=True)
        (tmp_path / "work" / "storydump" / ".git").mkdir()
        monkeypatch.chdir(work)
        monkeypatch.setenv("CLAUDRON_VAULT_PATH", str(b))
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        assert main(["hook", "session-start"]) == 0
        assert "Pool Exhaustion Fix" in capsys.readouterr().out


class TestBoundedScan:
    def test_noop_pull_reads_no_notes(self, synced_pair, monkeypatch):
        """Gauntlet (efficiency b): the steady-state SessionStart — a no-op
        pull — must not read the vault (scan is bounded to changed files)."""
        from claudron import vault as vault_mod
        from claudron.sync import sync
        from claudron.vault import detect

        a, _ = synced_pair
        reads: list[str] = []
        real = vault_mod.scan_quarantine

        def spy(v, paths=None):
            assert paths is not None, "unbounded full-vault scan on the pull path"
            reads.extend(paths)
            return real(v, paths)

        monkeypatch.setattr("claudron.sync.scan_quarantine", spy)
        result = sync(detect(a), pull=True, push=False)
        assert result.ok
        assert reads == []  # nothing changed → nothing read

    def test_validate_names_conflicts(self, synced_pair, capsys):
        """Gauntlet (altitude 1b): validate reports markers as the actual
        condition, not generic YAML breakage or a false all-clear."""
        a, _ = synced_pair
        note = a / "_shared" / "knowledge" / "shared-note.md"
        note.write_text(
            note.read_text() + "\n<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n"
        )
        rc = main(["validate", str(note)])
        assert rc == 1
        assert "conflict markers" in capsys.readouterr().out


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


def _note(title: str) -> str:
    return (
        f"---\ntitle: {title}\ntype: knowledge\nstatus: current\n"
        "owner: t\ncreated: 2026-07-01\nupdated: 2026-07-01\n"
        f"---\n\n# {title}\n\nBody.\n"
    )


@pytest.fixture
def feature_branch_vault(tmp_path: Path) -> Path:
    """Machine A on a feature branch that has its OWN upstream, while `main`
    has moved ahead on the remote.

    This is the shape #147 was found in, and the divergence asymmetry is the
    whole point: the branch is 1 commit ahead of *its own* upstream and 4
    ahead of *main*, so a rebase onto the wrong base is visible in the result
    rather than needing the command to be inspected.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")

    a = tmp_path / "machine-a"
    _git(tmp_path, "clone", str(remote), str(a))
    main(["init", str(a), "--adopt"])
    _git(a, "add", "-A")
    _git(a, "commit", "-m", "seed")
    _git(a, "push", "origin", "main")

    _git(a, "checkout", "-b", "feature")
    (a / "_shared" / "knowledge" / "feature-note.md").write_text(_note("Feature Note"))
    _git(a, "add", "-A")
    _git(a, "commit", "-m", "feature work")
    _git(a, "push", "-u", "origin", "feature")

    mover = tmp_path / "mover"
    _git(tmp_path, "clone", str(remote), str(mover))
    for i in range(3):
        (mover / f"main-only-{i}.md").write_text("x\n")
        _git(mover, "add", "-A")
        _git(mover, "commit", "-m", f"main-only-{i}")
    _git(mover, "push", "origin", "main")
    return a


class TestRefusesToStartABadRebase:
    """#147 — `sync` must not begin a rebase it cannot safely finish."""

    def test_pull_rebases_onto_own_upstream_not_the_remote_default(
        self, feature_branch_vault
    ):
        """THE regression test. `origin HEAD` resolves HEAD *on the remote* —
        a symbolic ref to the default branch — so the old refspec rebased a
        feature branch onto origin/main and queued the entire divergence."""
        a = feature_branch_vault
        before = _git(a, "rev-parse", "HEAD").stdout.strip()

        # --branch since C1 (#152): a side-branch sync is deliberate-only now.
        # This test's subject is which UPSTREAM a rebase targets, not whether a
        # side branch may be synced, so it says so explicitly and keeps
        # testing the refspec.
        rc = main(["--vault", str(a), "sync", "--pull", "--branch", "feature"])

        assert rc == 0
        assert _git(a, "symbolic-ref", "--short", "HEAD").stdout.strip() == "feature"
        log = _git(a, "log", "--oneline").stdout
        assert "main-only-0" not in log, "main's commits were replayed onto the branch"
        assert _git(a, "rev-parse", "HEAD").stdout.strip() == before
        assert not (a / ".git" / "rebase-merge").exists()

    def test_detached_head_refuses_and_makes_no_commit(self, synced_pair):
        """The near-miss: a detached HEAD does not refuse writes, so the old
        code committed there and produced history reachable from no branch."""
        a, _ = synced_pair
        _git(a, "checkout", "--detach")
        (a / "_shared" / "knowledge" / "orphan.md").write_text(_note("Orphan"))
        head_before = _git(a, "rev-parse", "HEAD").stdout.strip()

        result = sync(detect(a), pull=True, push=True)

        assert not result.ok
        assert "refusing to sync" in result.detail
        assert not result.committed and not result.pulled and not result.pushed
        assert _git(a, "rev-parse", "HEAD").stdout.strip() == head_before
        assert _git(a, "status", "--porcelain").stdout.strip(), "change was consumed"

    def test_dirty_tree_after_a_failed_commit_skips_the_pull(
        self, synced_pair, monkeypatch
    ):
        """Defect 2: the pull was unconditional on index state, so a failed
        commit was followed by a rebase attempt against a dirty tree."""
        from claudron import sync as sync_mod

        a, _ = synced_pair
        (a / "_shared" / "knowledge" / "pending.md").write_text(_note("Pending"))
        real = sync_mod.run_git

        def fake(root, *args, **kw):
            if args and args[0] == "commit":
                return subprocess.CompletedProcess([], 1, stdout="", stderr="refused")
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", fake)
        result = sync_mod.sync(detect(a), pull=True, push=False)

        assert not result.ok
        assert "working tree is not clean" in result.detail
        assert not result.pulled

    def test_branch_without_upstream_skips_pull_but_still_pushes(self, synced_pair):
        """A never-pushed branch has nothing to rebase onto. The old refspec
        hid that state by rebasing onto the remote default instead."""
        a, _ = synced_pair
        _git(a, "checkout", "-b", "never-pushed")
        (a / "_shared" / "knowledge" / "fresh.md").write_text(_note("Fresh"))

        # branch= since C1 (#152), for the same reason as the test above: the
        # subject is the missing upstream, not the branch policy.
        result = sync(detect(a), pull=True, push=True, branch="never-pushed")

        assert not result.pulled
        assert "no upstream" in result.detail
        assert result.committed and result.pushed


class TestTimeoutIsReportedNotRaised:
    """#147 defect 3 — a timeout raised past the failure handler, so the one
    failure that can leave the repository inconsistent was the one that said
    nothing."""

    def test_pull_timeout_returns_a_reported_result(self, synced_pair, monkeypatch):
        from claudron import sync as sync_mod

        a, _ = synced_pair
        real = sync_mod.run_git

        def fake(root, *args, **kw):
            if args and args[0] == "pull":
                raise SyncTimeout("git pull --rebase timed out")
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", fake)
        result = sync_mod.sync(detect(a), pull=True, push=False)

        assert not result.ok
        assert "timed out" in result.detail

    def test_pull_timeout_names_the_rebase_it_left_behind(
        self, synced_pair, monkeypatch
    ):
        """A mid-replay kill leaves zero unmerged paths, so the debris is
        invisible to every porcelain check. The detail line is the only thing
        that can say it happened."""
        from claudron import sync as sync_mod

        a, _ = synced_pair
        real = sync_mod.run_git

        def fake(root, *args, **kw):
            if args and args[0] == "pull":
                (Path(root) / ".git" / "rebase-merge").mkdir(parents=True, exist_ok=True)
                raise SyncTimeout("git pull --rebase timed out")
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", fake)
        result = sync_mod.sync(detect(a), pull=True, push=False)

        assert not result.ok
        assert "stopped part-way" in result.detail
        assert "left for the human" in result.detail

    def test_timeout_is_still_a_syncerror_for_existing_callers(self):
        """Subclass, not a sibling: hooks.py and cli.py both catch SyncError
        and must keep catching timeouts."""
        from claudron.sync import SyncError

        assert issubclass(SyncTimeout, SyncError)


class TestKilledRebaseIsAbortedButAConflictIsNot:
    """C1 (#152). The discrimination is the whole issue.

    A rebase KILLED by the per-op timeout has no markers and nothing for a
    human to resolve; leaving it is how a live tree sat detached for twelve
    days with the wrong files checked out. A rebase stopped on a CONFLICT has
    markers a human is meant to see and may already be working on; aborting
    that destroys their resolution, which is worse than the bug.

    So every test here comes in a pair: the kill is repaired, the conflict is
    untouched. A fix that aborted both would pass half of them.
    """

    def _plant_killed_rebase(self, repo: Path) -> str:
        """The on-disk signature measured on the clone that produced the
        outage: a todo list and `done`, NO stopped-sha, zero unmerged paths."""
        orig = _git(repo, "rev-parse", "HEAD").stdout.strip()
        head_name = _git(repo, "symbolic-ref", "HEAD").stdout.strip()
        rd = repo / ".git" / "rebase-merge"
        rd.mkdir(parents=True)
        (rd / "git-rebase-todo").write_text("pick deadbee some queued commit\n")
        (rd / "done").write_text("pick cafebabe already replayed\n")
        (rd / "head-name").write_text(head_name + "\n")
        (rd / "onto").write_text(orig + "\n")
        (rd / "orig-head").write_text(orig + "\n")
        _git(repo, "checkout", "--detach", orig)
        return orig

    def test_a_killed_rebase_is_recognised(self, synced_pair):
        a, _ = synced_pair
        from claudron.sync import _killed_rebase
        self._plant_killed_rebase(a)
        assert _killed_rebase(a, a / ".git", 10.0) is True

    def test_a_stopped_sha_makes_it_a_CONFLICT_not_a_kill(self, synced_pair):
        """`stopped-sha` means git stopped ON a commit — that is a conflict,
        and it must never be aborted even with no unmerged paths left (a human
        part-way through resolving has already staged some)."""
        a, _ = synced_pair
        from claudron.sync import _killed_rebase
        self._plant_killed_rebase(a)
        (a / ".git" / "rebase-merge" / "stopped-sha").write_text("deadbee\n")
        assert _killed_rebase(a, a / ".git", 10.0) is False

    def test_unmerged_paths_make_it_a_CONFLICT_not_a_kill(self, synced_pair, capsys):
        """The real conflict path, through the real flow, not a planted tree."""
        a, b = synced_pair
        from claudron.sync import _killed_rebase, _interrupted_state
        note_rel = "_shared/knowledge/shared-note.md"
        (a / note_rel).write_text(
            (a / note_rel).read_text().replace("Original line.", "A's truth."))
        assert main(["--vault", str(a), "sync"]) == 0
        capsys.readouterr()
        (b / note_rel).write_text(
            (b / note_rel).read_text().replace("Original line.", "B's truth."))
        main(["--vault", str(b), "sync"])
        capsys.readouterr()
        if _interrupted_state(b, b / ".git", 10.0) is not None:
            assert _killed_rebase(b, b / ".git", 10.0) is False, (
                "a real conflict must never be classified as a kill"
            )

    def test_no_rebase_at_all_is_not_a_kill(self, synced_pair):
        a, _ = synced_pair
        from claudron.sync import _killed_rebase
        assert _killed_rebase(a, a / ".git", 10.0) is False


class TestSideBranchIsRefusedBeforeAnythingIsWritten:
    """A clone on a side branch is where captures look durable in `git log` and
    exist on no other machine: 59 commits accrued on one, 53 reaching no
    remote. The refusal has to come before the commit, or each refused sync
    strands one more."""

    def test_the_default_branch_is_not_refused(self, synced_pair):
        """The control, and the one that would fire on every healthy host if
        the `origin/` strip were missing."""
        a, _ = synced_pair
        from claudron.sync import _default_branch, _refuse_off_default
        assert _default_branch(a, 10.0) == "main"
        assert _refuse_off_default(a, 10.0, None) is None

    def test_default_branch_strips_the_remote_prefix(self, synced_pair):
        """Pinned on its own: `symbolic-ref refs/remotes/origin/HEAD` answers
        `origin/main` while `symbolic-ref HEAD` answers `main`, so an
        unstripped comparison refuses every clone."""
        a, _ = synced_pair
        from claudron.sync import _default_branch
        assert not _default_branch(a, 10.0).startswith("origin/")

    def test_a_side_branch_is_refused_and_nothing_is_committed(self, synced_pair, capsys):
        a, _ = synced_pair
        _git(a, "switch", "-c", "docs/side")
        note = a / "_shared" / "knowledge" / "stranded.md"
        note.write_text(
            "---\ntitle: Stranded\ntype: knowledge\nstatus: current\nowner: t\n"
            "created: 2026-07-01\nupdated: 2026-07-01\n---\n\n# Stranded\n\nx\n")
        rc = main(["--vault", str(a), "sync"])
        capsys.readouterr()
        assert rc != 0
        dirty = _git(a, "status", "--porcelain").stdout
        assert "stranded.md" in dirty, (
            "the refusal must precede the commit — the note is still uncommitted"
        )

    def test_the_refusal_names_BOTH_branches(self, synced_pair):
        a, _ = synced_pair
        from claudron.sync import _refuse_off_default
        _git(a, "switch", "-c", "docs/side")
        text = _refuse_off_default(a, 10.0, None)
        assert text and "docs/side" in text and "main" in text
        assert "--branch" in text, "the refusal must name its own override"

    def test_the_branch_flag_allows_a_deliberate_side_branch(self, synced_pair):
        a, _ = synced_pair
        from claudron.sync import _refuse_off_default
        _git(a, "switch", "-c", "docs/side")
        assert _refuse_off_default(a, 10.0, "docs/side") is None

    def test_the_flag_must_name_the_branch_actually_checked_out(self, synced_pair):
        """`--branch` is a deliberate override for THIS branch, not a blanket
        opt-out: naming a different branch must still refuse."""
        a, _ = synced_pair
        from claudron.sync import _refuse_off_default
        _git(a, "switch", "-c", "docs/side")
        assert _refuse_off_default(a, 10.0, "docs/other") is not None
class TestStaleLock:
    """C2 (#153). An OWNERLESS lock expires; a LIVE one is refused.

    Git never expires `index.lock` — it assumes the process that made it will
    remove it. A host reset that catches a git write leaves one behind, and
    from then on every write in the vault fails while every READ keeps working:
    `status --porcelain` needs no lock, so the tree reads "merely dirty" and
    sync blamed the dirty tree. One such lock sat for ten and a half days.

    Deleting someone's lock is the one destructive act here, so the shape
    mirrors `_killed_rebase`: BOTH facts must agree — old AND provably
    ownerless — and ambiguity resolves to "leave it alone". A naive
    "delete any lock" passes the happy path and corrupts a concurrent write;
    the live-lock tests below are what catch it.
    """

    def _plant(self, repo: Path, *, age_s: int) -> Path:
        lock = repo / ".git" / "index.lock"
        lock.write_bytes(b"")
        old = time.time() - age_s
        os.utime(lock, (old, old))
        return lock

    def _dirty(self, repo: Path) -> Path:
        note = repo / "_shared" / "knowledge" / "locked.md"
        note.write_text(_note("Locked"))
        return note

    # --- the predicate ----------------------------------------------------

    def test_both_facts_must_agree_before_anything_is_deleted(self):
        from claudron.sync import _is_expirable
        assert _is_expirable(3600, False, 600) is True      # old + ownerless
        assert _is_expirable(1, False, 600) is False        # fresh
        assert _is_expirable(3600, True, 600) is False      # held
        assert _is_expirable(3600, None, 600) is False      # unknowable

    def test_unknown_ownership_is_not_the_same_as_no_owner(self):
        """`None` must never behave like `False`. This is the whole fail-safe
        direction: a probe that cannot answer means "someone is working"."""
        from claudron.sync import _is_expirable
        assert _is_expirable(10**6, None, 600) is False

    def test_lsof_semantics_are_the_ones_we_rely_on(self, tmp_path):
        """Measured rather than assumed, because the predicate is built on it:
        exit 1 for an unheld file, exit 0 with a pid for a held one. Skipped
        where lsof is absent rather than asserted from memory."""
        import shutil as _sh
        if not _sh.which("lsof"):
            pytest.skip("lsof not on PATH")
        from claudron.sync import _lock_holder
        f = tmp_path / "unheld"
        f.write_text("")
        assert _lock_holder(f) is False

    def test_a_genuinely_held_file_reads_as_held(self, tmp_path):
        import shutil as _sh
        if not _sh.which("lsof"):
            pytest.skip("lsof not on PATH")
        from claudron.sync import _lock_holder
        f = tmp_path / "held"
        f.write_text("")
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,time; f=open(sys.argv[1]); time.sleep(30)", str(f)])
        try:
            for _ in range(100):
                if _lock_holder(f) is True:
                    break
                time.sleep(0.05)
            assert _lock_holder(f) is True
        finally:
            proc.kill()
            proc.wait(timeout=10)

    # --- sync's behaviour --------------------------------------------------

    def test_an_ownerless_old_lock_is_expired_and_the_sync_proceeds(self, synced_pair):
        a, _ = synced_pair
        self._dirty(a)
        lock = self._plant(a, age_s=3600)
        result = sync(detect(a), pull=False, push=False)
        assert not lock.exists(), "an old ownerless lock must be removed"
        assert result.committed
        assert "expired stale index.lock" in result.detail, (
            "a repair this run performed must be reported, not silent"
        )

    def test_a_FRESH_lock_is_refused_and_left_alone(self, synced_pair):
        """THE positive control for the naive fix. A lock made a moment ago is
        a concurrent write; deleting it corrupts the index."""
        a, _ = synced_pair
        self._dirty(a)
        lock = self._plant(a, age_s=0)
        result = sync(detect(a), pull=False, push=False)
        assert lock.exists(), "a fresh lock must NOT be deleted"
        assert not result.ok and not result.committed
        assert "index.lock" in result.detail

    def test_a_HELD_lock_is_refused_even_when_old(self, synced_pair):
        """Age alone is not licence: a slow write on a loaded disk is old and
        live."""
        import shutil as _sh
        if not _sh.which("lsof"):
            pytest.skip("lsof not on PATH")
        a, _ = synced_pair
        self._dirty(a)
        lock = self._plant(a, age_s=3600)
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,time; f=open(sys.argv[1]); time.sleep(30)", str(lock)])
        try:
            from claudron.sync import _lock_holder
            for _ in range(100):
                if _lock_holder(lock) is True:
                    break
                time.sleep(0.05)
            result = sync(detect(a), pull=False, push=False)
            assert lock.exists(), "a held lock must never be deleted"
            assert not result.ok
            assert "held" in result.detail
        finally:
            proc.kill()
            proc.wait(timeout=10)

    def test_UNKNOWN_ownership_refuses_and_keeps_the_lock(self, synced_pair, monkeypatch):
        a, _ = synced_pair
        self._dirty(a)
        lock = self._plant(a, age_s=3600)
        import claudron.sync as sync_mod
        monkeypatch.setattr(sync_mod, "_lock_holder", lambda _p: None)
        result = sync(detect(a), pull=False, push=False)
        assert lock.exists()
        assert not result.ok
        assert "unknown" in result.detail

    def test_no_lock_at_all_is_unremarkable(self, synced_pair):
        """The control on the control: the new code must not change a normal
        sync, which is every sync."""
        a, _ = synced_pair
        self._dirty(a)
        result = sync(detect(a), pull=False, push=False)
        assert result.committed
        assert "index.lock" not in (result.detail or "")

    def test_a_side_branch_is_refused_before_any_lock_is_touched(self, synced_pair):
        """Where C1's refusal and C2's repair meet, and the order is a choice.

        `_refuse_off_default` only reads; expiring a lock DELETES. A sync that
        is going to refuse anyway must not perform the one destructive act on
        its way out. The off-default refusal also assigns `detail` directly
        rather than composing it, so a repair performed first would be dropped
        from the report — the same silence the expiry note exists to end.
        """
        a, _ = synced_pair
        _git(a, "switch", "-c", "docs/side")
        self._dirty(a)
        lock = self._plant(a, age_s=3600)
        result = sync(detect(a), pull=False, push=False)
        assert not result.ok and not result.committed
        assert "HEAD is on 'docs/side'" in result.detail
        assert lock.exists(), "an expirable lock must survive a refused sync"
        assert "index.lock" not in result.detail

    def test_a_failed_add_names_gits_own_message_not_the_dirty_tree(self, synced_pair, monkeypatch):
        """The misdirection that hid the lock for ten days: an unchecked `add`
        fell through to a failing commit, and the porcelain re-read then
        reported "not clean after the pre-pull commit" — true, useless, and
        pointing at the tree rather than the cause."""
        a, _ = synced_pair
        self._dirty(a)
        import claudron.sync as sync_mod
        real = sync_mod.run_git
        calls: list[str] = []

        def fake(root, *args, **kw):
            calls.append(args[0])
            if args[0] == "add":
                return subprocess.CompletedProcess(
                    ["git", "add"], 128, "",
                    "fatal: Unable to create '.git/index.lock': File exists.")
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", fake)
        result = sync(detect(a), pull=False, push=False)
        assert not result.ok
        assert "index.lock" in result.detail and "Unable to create" in result.detail
        assert "commit" not in calls, "a failed add must return before commit"
