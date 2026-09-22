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
from claudron.sync import SyncError, SyncTimeout, check, sync
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
    # A REAL CLONE OF A NON-EMPTY REPOSITORY HAS THIS REF; this one is cloned
    # while the remote is still empty, so git never wrote it. Without it
    # `_default_branch` cannot determine anything and the side-branch tests
    # below were green only because the old implementation GUESSED "main",
    # which happens to be this fixture's branch name -- so the predicate they
    # exist to pin was never actually exercised. `set-head --auto` asks the
    # remote, which is the same mechanism `git clone` uses.
    _git(a, "remote", "set-head", "origin", "--auto")

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


class TestCheck:
    """#154 — the read-only health door, one test per verdict.

    The door this replaces is `status --json`, which walks every note and
    WRITES the index to answer "is this healthy" — so asking mutated the thing
    being asked about, and could not be asked at all of a wedged or read-only
    tree. Read-only is therefore the point rather than a courtesy, and it is
    PINNED below rather than promised.

    The states are the deliverable. Two consumers key on them, so every one
    gets its own test: a vocabulary nobody exercised is a vocabulary that
    drifts the first time the implementation is rewritten.
    """

    def _vault(self, root: Path):
        return detect(root)

    # --- the vocabulary itself ---------------------------------------------

    def test_every_state_in_the_table_has_a_test_here(self):
        """The meta-check. `CHECK_STATES` is the contract, so a value added to
        it without a test is caught here rather than in a consumer."""
        from claudron.sync import CHECK_STATES
        names = {n for n in dir(self) if n.startswith("test_")}
        covered = {
            "unknown": "test_unknown_when_git_cannot_answer",
            "stale-lock": "test_stale_lock",
            "rebase-conflict": "test_rebase_conflict",
            "rebase-killed": "test_rebase_killed",
            "merge": "test_merge_in_progress",
            "detached": "test_detached",
            "side-branch": "test_side_branch_with_and_without_upstream",
            "dirty": "test_dirty",
            "divergent": "test_divergent",
            "behind": "test_behind",
            "ahead": "test_ahead",
            "unreachable": "test_unreachable_only_with_reach",
            "clean": "test_clean",
        }
        assert set(covered) == set(CHECK_STATES), (
            "a state was added or renamed without updating this map"
        )
        for state, test in covered.items():
            assert test in names, f"{state} has no test named {test}"

    def test_precedence_is_the_table_order(self):
        """The order in `CHECK_STATES` IS the precedence, so it is asserted
        rather than left as a comment: a stale lock outranks a dirty tree
        because a locked vault cannot commit its way out."""
        from claudron.sync import CHECK_STATES
        assert CHECK_STATES.index("stale-lock") < CHECK_STATES.index("dirty")
        assert CHECK_STATES.index("rebase-conflict") < CHECK_STATES.index("detached")
        assert CHECK_STATES.index("side-branch") < CHECK_STATES.index("dirty")
        assert CHECK_STATES[-1] == "clean"

    def test_unknown_is_not_ok(self):
        """The whole reason `unknown` exists. A consumer that treated it as
        healthy would rebuild the silence this door was built to end."""
        from claudron.sync import CheckResult
        assert CheckResult(state="unknown").ok is False
        assert CheckResult(state="clean").ok is True
        assert CheckResult(state="behind").ok is False

    def test_unknown_survives_serialisation(self):
        from claudron.sync import CheckResult
        d = CheckResult(state="unknown", detail="git is unavailable").to_dict()
        assert d["check"] is True
        assert d["state"] == "unknown"
        assert "git is unavailable" in d["detail"]

    # --- one per state ------------------------------------------------------

    def test_clean(self, synced_pair):
        a, _ = synced_pair
        r = check(self._vault(a))
        assert r.state == "clean", r.to_dict()
        assert r.branch == "main" and r.default_branch == "main"
        assert r.ahead == 0 and r.behind == 0

    def test_ahead(self, synced_pair):
        a, _ = synced_pair
        (a / "_shared" / "knowledge" / "ahead.md").write_text(_note("Ahead"))
        _git(a, "add", "-A")
        _git(a, "commit", "-m", "local")
        r = check(self._vault(a))
        assert r.state == "ahead" and r.ahead == 1 and r.behind == 0

    def test_behind(self, synced_pair):
        a, b = synced_pair
        (b / "_shared" / "knowledge" / "theirs.md").write_text(_note("Theirs"))
        _git(b, "add", "-A")
        _git(b, "commit", "-m", "remote")
        _git(b, "push", "origin", "main")
        _git(a, "fetch", "origin")       # check() never fetches: it is offline
        r = check(self._vault(a))
        assert r.state == "behind" and r.behind == 1 and r.ahead == 0

    def test_divergent(self, synced_pair):
        a, b = synced_pair
        (b / "_shared" / "knowledge" / "theirs.md").write_text(_note("Theirs"))
        _git(b, "add", "-A")
        _git(b, "commit", "-m", "remote")
        _git(b, "push", "origin", "main")
        (a / "_shared" / "knowledge" / "mine.md").write_text(_note("Mine"))
        _git(a, "add", "-A")
        _git(a, "commit", "-m", "local")
        _git(a, "fetch", "origin")
        r = check(self._vault(a))
        assert r.state == "divergent" and r.ahead == 1 and r.behind == 1

    def test_dirty(self, synced_pair):
        a, _ = synced_pair
        (a / "_shared" / "knowledge" / "wip.md").write_text(_note("WIP"))
        r = check(self._vault(a))
        assert r.state == "dirty" and r.uncommitted == 1
        assert r.uncommitted_oldest_age_s is not None

    def test_side_branch_with_and_without_upstream(self, synced_pair):
        """S5 and S6 share the verdict ON PURPOSE — the `upstream` field is
        what tells them apart, which is why thirteen design states need only
        twelve of these values."""
        a, _ = synced_pair
        _git(a, "switch", "-c", "docs/side")
        no_upstream = check(self._vault(a))
        assert no_upstream.state == "side-branch"
        assert no_upstream.upstream is None, "S6 has no upstream"

        _git(a, "push", "-u", "origin", "docs/side")
        with_upstream = check(self._vault(a))
        assert with_upstream.state == "side-branch", "S5 shares S6's verdict"
        assert with_upstream.upstream == "origin/docs/side"

    def test_detached(self, synced_pair):
        a, _ = synced_pair
        _git(a, "switch", "--detach")
        r = check(self._vault(a))
        assert r.state == "detached" and r.branch is None

    def test_rebase_conflict(self, synced_pair):
        """A rebase stopped ON a commit: markers a human is meant to see."""
        a, _ = synced_pair
        rd = a / ".git" / "rebase-merge"
        rd.mkdir(parents=True)
        (rd / "git-rebase-todo").write_text("pick deadbee queued\n")
        (rd / "stopped-sha").write_text("deadbee\n")
        r = check(self._vault(a))
        assert r.state == "rebase-conflict"
        assert r.interrupted and "rebase" in r.interrupted

    def test_rebase_killed(self, synced_pair):
        """The outage's own signature: a todo list, no stopped-sha, no
        unmerged paths. Collapsing this into `rebase-conflict` is exactly the
        silence the design doc forbids — they need opposite responses."""
        a, _ = synced_pair
        rd = a / ".git" / "rebase-merge"
        rd.mkdir(parents=True)
        (rd / "git-rebase-todo").write_text("pick deadbee queued\n")
        (rd / "done").write_text("pick cafebabe replayed\n")
        r = check(self._vault(a))
        assert r.state == "rebase-killed"

    def test_merge_in_progress(self, synced_pair):
        a, _ = synced_pair
        (a / ".git" / "MERGE_HEAD").write_text(
            _git(a, "rev-parse", "HEAD").stdout)
        r = check(self._vault(a))
        assert r.state == "merge"

    def test_stale_lock(self, synced_pair):
        """Reported on AGE ALONE, while `sync()` deletes only what is also
        provably ownerless. The bar for acting is higher than the bar for
        telling someone: reporting only the provable ones goes silent on a
        wedged vault whose host cannot name the holder, which is how the
        original sat for ten and a half days."""
        a, _ = synced_pair
        lock = a / ".git" / "index.lock"
        lock.write_bytes(b"")
        old = time.time() - 3600
        os.utime(lock, (old, old))
        r = check(self._vault(a))
        assert r.state == "stale-lock"
        assert r.lock_age_s is not None and r.lock_age_s >= 3600

    def test_a_young_lock_is_not_a_verdict(self, synced_pair):
        """The control on the one above. An ordinary concurrent write holds a
        lock for a moment; a watchdog that flipped state for it would flap."""
        a, _ = synced_pair
        (a / ".git" / "index.lock").write_bytes(b"")
        r = check(self._vault(a))
        assert r.state == "clean"
        assert r.lock_age_s is not None, "still reported, just not a verdict"

    def test_unreachable_only_with_reach(self, synced_pair):
        """S12. Off by default so the verdict is computed offline — a watchdog
        polling this must not be gated on the network being up."""
        a, _ = synced_pair
        _git(a, "remote", "set-url", "origin", str(a / "no" / "such" / "remote.git"))
        assert check(self._vault(a)).state == "clean", "offline by default"
        assert check(self._vault(a), reach=True).state == "unreachable"

    def test_unknown_when_git_cannot_answer(self, synced_pair, monkeypatch):
        """A reader that cannot reach its source must not answer the same as
        one that looked and found nothing wrong."""
        a, _ = synced_pair
        import claudron.sync as sync_mod

        def boom(*_a, **_k):
            raise SyncError("git is unavailable: no such file")

        monkeypatch.setattr(sync_mod, "run_git", boom)
        r = check(self._vault(a))
        assert r.state == "unknown"
        assert "git is unavailable" in r.detail

    # --- the properties the door exists for --------------------------------

    def test_check_never_walks_notes(self, synced_pair, monkeypatch):
        """`status --json` walks every note to answer this question; on a
        10k-note vault that is the difference between a probe and an outage."""
        a, _ = synced_pair
        import claudron.vault as vault_mod

        def boom(*_a, **_k):
            raise AssertionError("check() must never walk a knowledge tier")

        if hasattr(vault_mod, "walk_knowledge_tier"):
            monkeypatch.setattr(vault_mod, "walk_knowledge_tier", boom)
        r = check(self._vault(a))
        assert r.state == "clean"

    def test_check_runs_only_read_only_git(self, synced_pair, monkeypatch):
        """THE read-only pin, and it is a whitelist of verbs rather than an
        after-the-fact mtime check: a mutation that happened to change nothing
        would pass the second and fail this one."""
        a, _ = synced_pair
        import claudron.sync as sync_mod
        real = sync_mod.run_git
        seen: list[str] = []
        READ_ONLY = {
            "rev-parse", "symbolic-ref", "rev-list", "status", "config",
            "diff", "ls-remote",
        }

        def spy(root, *args, **kw):
            # the first NON-flag argument is the subcommand; the door passes
            # `--no-optional-locks` ahead of it
            seen.append(next(a for a in args if not a.startswith("-")))
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", spy)
        check(self._vault(a), reach=True)
        assert seen, "the door ran no git at all — the pin would be vacuous"
        assert set(seen) <= READ_ONLY, f"a writing verb was run: {set(seen) - READ_ONLY}"

    def test_check_touches_neither_the_index_nor_the_journal(self, synced_pair):
        a, _ = synced_pair
        index = a / ".git" / "index"
        before = index.stat().st_mtime_ns
        journal = a / ".claudron" / "sync.json"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text('{"last_ok_at": "2026-01-01T00:00:00+00:00"}\n')
        j_before = journal.stat().st_mtime_ns

        r = check(self._vault(a))

        assert index.stat().st_mtime_ns == before, "check() wrote the index"
        assert journal.stat().st_mtime_ns == j_before, "check() wrote the journal"
        assert r.last_sync_ok_at == "2026-01-01T00:00:00+00:00", "but it READ it"

    def test_check_answers_on_a_read_only_tree(self, synced_pair):
        """The wedged-vault case: the door has to work exactly when the thing
        it reports on cannot be written."""
        a, _ = synced_pair
        gitdir = a / ".git"
        mode = gitdir.stat().st_mode
        os.chmod(gitdir, 0o500)
        try:
            r = check(self._vault(a))
        finally:
            os.chmod(gitdir, mode)
        assert r.state in {"clean", "dirty"}, r.to_dict()
        assert r.state != "unknown", "a read-only tree is still answerable"

    def test_check_default_branch_is_stripped(self, synced_pair):
        """`symbolic-ref --short refs/remotes/origin/HEAD` answers
        `origin/main` while HEAD answers `main`; an unstripped compare would
        make every healthy clone read `side-branch`."""
        a, _ = synced_pair
        r = check(self._vault(a))
        assert r.default_branch == "main"
        assert not r.default_branch.startswith("origin/")

    def _mature_vault_that_lost_origin_head(self, tmp_path):
        """A vault with real shared history, on a GENUINE side branch, whose
        `origin/HEAD` has gone. Built rather than argued: the ref is lost to a
        pruned remote ref, a reclone or a hand-rolled `remote add`, none of
        which are exotic, and none of which make the clone a bootstrap."""
        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git(remote, "init", "--bare", "--initial-branch=main")
        v = tmp_path / "v"
        _git(tmp_path, "clone", str(remote), str(v))
        main(["init", str(v), "--adopt"])
        (v / "_shared" / "knowledge" / "seed.md").write_text(_note("Seed"))
        _git(v, "add", "-A")
        _git(v, "commit", "-m", "seed")
        _git(v, "push", "origin", "main")
        _git(v, "remote", "set-head", "origin", "--auto")

        _git(v, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        _git(v, "switch", "-c", "docs/side")
        for i in (1, 2, 3):
            (v / "_shared" / "knowledge" / f"w{i}.md").write_text(_note(f"W{i}"))
            _git(v, "add", "-A")
            _git(v, "commit", "-m", f"work {i}")
        return v

    def test_the_bootstrap_pass_does_not_cover_a_mature_side_branch(self, tmp_path):
        """**The adversarial case, and it was a real gap.** Reproduced before
        the fix: this vault was committed AND pushed with no refusal at all,
        and `sync` created `docs/side` on the remote. `origin/HEAD` being unset
        cannot be the discriminator -- a mature vault loses it too, and in that
        state the guard C1 exists to provide was simply absent."""
        v = self._mature_vault_that_lost_origin_head(tmp_path)
        from claudron.sync import _refuse_off_default
        text = _refuse_off_default(v, 10.0, None)
        assert text is not None, "a mature vault on a side branch must refuse"
        assert "docs/side" in text
        assert "--branch" in text, "the refusal must name its own override"
        assert "set-head" in text, "and the remedy that actually fixes it"

    def test_the_health_door_agrees_with_the_refusal_door(self, tmp_path):
        """One clone must not read healthy to the probe while `sync` refuses
        it -- that divergence is how a wedged vault stayed invisible."""
        v = self._mature_vault_that_lost_origin_head(tmp_path)
        assert check(self._vault(v)).state == "side-branch"

    def test_the_commits_really_are_reachable_from_a_remote(self, tmp_path):
        """Why the obvious predicate fails, pinned so nobody reinstates it.

        `rev-list --count HEAD --not --remotes` reads ZERO here once the side
        branch has been pushed -- the history is on a remote, just on the wrong
        branch. That is the outage's own shape, so "holds unpushed commits"
        cannot be the second fact."""
        v = self._mature_vault_that_lost_origin_head(tmp_path)
        _git(v, "push", "-u", "origin", "docs/side")
        unpushed = _git(v, "rev-list", "--count", "HEAD", "--not", "--remotes")
        assert unpushed.stdout.strip() == "0", "precondition for the point below"
        from claudron.sync import _refuse_off_default
        assert _refuse_off_default(v, 10.0, None) is not None, (
            "still stranded, and still refused"
        )

    def test_both_facts_must_agree_before_the_guard_stands_down(self):
        """The pure predicate, the twin of `_is_expirable`. Ambiguity is not a
        bootstrap, so it refuses."""
        from claudron.sync import _is_bootstrap
        assert _is_bootstrap(None, True) is True        # undetermined + alone
        assert _is_bootstrap(None, False) is False      # other branches exist
        assert _is_bootstrap("main", True) is False     # determined: not our case
        assert _is_bootstrap("main", False) is False

    def test_a_genuine_bootstrap_still_syncs(self, tmp_path):
        """The control. The whole reason the pass exists: a vault bootstrapped
        with `git init` + `remote add` + `push -u` on a host that defaults to
        `master` must not be refused forever."""
        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git(remote, "init", "--bare")
        v = tmp_path / "v"
        v.mkdir()
        _git(v, "init")
        main(["init", str(v), "--adopt"])
        _git(v, "add", "-A")
        _git(v, "commit", "-m", "seed")
        _git(v, "remote", "add", "origin", str(remote))
        _git(v, "push", "-u", "origin", "HEAD")
        from claudron.sync import _refuse_off_default, _alone_in_its_history
        assert _alone_in_its_history(v, 10.0) is True
        assert _refuse_off_default(v, 10.0, None) is None

    def test_an_unreadable_ref_list_is_not_a_bootstrap(self, synced_pair, monkeypatch):
        """Cannot-establish falls to the safe side, like every other both-facts
        predicate here."""
        a, _ = synced_pair
        import claudron.sync as sync_mod
        real = sync_mod.run_git

        def fake(root, *args, **kw):
            if args and args[0] == "for-each-ref":
                return subprocess.CompletedProcess(["git"], 128, "", "boom")
            return real(root, *args, **kw)

        monkeypatch.setattr(sync_mod, "run_git", fake)
        from claudron.sync import _alone_in_its_history
        assert _alone_in_its_history(a, 10.0) is False

    def test_an_undetermined_default_branch_is_null_not_a_guess(self, tmp_path):
        """The bootstrap shape: `git init` + `git remote add` + `git push -u`
        leaves origin/HEAD unset, and a host may have no init.defaultBranch.
        Guessing `main` there made every `claudron sync` refuse a clone that
        was on `master` — a new vault that could never sync at all."""
        remote = tmp_path / "remote.git"
        remote.mkdir()
        _git(remote, "init", "--bare")
        v = tmp_path / "v"
        v.mkdir()
        _git(v, "init")
        main(["init", str(v), "--adopt"])
        _git(v, "add", "-A")
        _git(v, "commit", "-m", "seed")
        _git(v, "remote", "add", "origin", str(remote))
        _git(v, "push", "-u", "origin", "HEAD")
        r = check(self._vault(v))
        assert r.default_branch is None, "undetermined must not be a guess"
        assert r.state != "side-branch", "and must not manufacture a verdict"

    def test_sync_writes_the_journal_and_check_only_reads_it(self, synced_pair):
        a, _ = synced_pair
        journal = a / ".claudron" / "sync.json"
        assert not journal.exists()
        assert check(self._vault(a)).last_sync_ok_at is None, (
            "absent journal reads as null, never as a fabricated timestamp"
        )
        (a / "_shared" / "knowledge" / "j.md").write_text(_note("J"))
        sync(self._vault(a), pull=False, push=False)
        assert journal.exists(), "sync() writes it"
        stamped = check(self._vault(a)).last_sync_ok_at
        assert stamped, "check() reads it"

    def test_a_refusal_counts_as_an_attempt(self, synced_pair):
        """A clone refusing for a week and one nobody has asked to sync look
        identical without this, and telling them apart is the denominator."""
        import json as _json
        a, _ = synced_pair
        _git(a, "switch", "-c", "docs/side")
        (a / "_shared" / "knowledge" / "r.md").write_text(_note("R"))
        result = sync(self._vault(a), pull=False, push=False)
        assert not result.ok, "precondition: this sync is refused"
        data = _json.loads((a / ".claudron" / "sync.json").read_text())
        assert data["last_state"] == "refused"
        assert data.get("last_attempt_at")
        assert "last_ok_at" not in data, "a refusal is not a success"


class TestCheckCLI:
    """The door as a consumer meets it (#154). Two are already waiting on it,
    so the exit-code contract is pinned here rather than left to the parser."""

    def test_check_with_pull_or_push_is_a_usage_error(self, synced_pair):
        """`--check` changes nothing and `--pull`/`--push` change things, so
        the combination has no meaning. argparse's own mutually-exclusive
        refusal exits 2, which is the CLI contract's usage code — asserted
        because a later hand-rolled check could silently pick a different one.
        """
        a, _ = synced_pair
        for other in ("--pull", "--push"):
            with pytest.raises(SystemExit) as exc:
                main(["--vault", str(a), "sync", "--check", other])
            assert exc.value.code == 2, f"--check {other} must be a usage error"

    def test_a_bad_verdict_is_still_exit_zero(self, synced_pair, capsys):
        """THE contract for consumers: the state lives in the envelope, never
        in the exit code. Conflating them would force a caller to choose
        between "the check ran" and "the clone is healthy", which are the two
        questions this door exists to separate."""
        a, _ = synced_pair
        _git(a, "switch", "-c", "docs/side")
        rc = main(["--vault", str(a), "sync", "--check", "--json"])
        out = capsys.readouterr().out
        assert rc == 0, "a bad verdict is not a failed command"
        assert '"state": "side-branch"' in out

    def test_json_carries_the_check_discriminator(self, synced_pair, capsys):
        """`command` stays `sync`, so `check: true` is how a consumer tells a
        verdict envelope from a sync envelope."""
        import json as _json
        a, _ = synced_pair
        main(["--vault", str(a), "sync", "--check", "--json"])
        env = _json.loads(capsys.readouterr().out)
        assert env["command"] == "sync"
        assert env["data"]["check"] is True
        assert env["data"]["state"] == "clean"

    def test_plain_mode_prints_one_line_on_stdout(self, synced_pair, capsys):
        a, _ = synced_pair
        main(["--vault", str(a), "sync", "--check"])
        cap = capsys.readouterr()
        lines = [ln for ln in cap.out.splitlines() if ln.strip()]
        assert len(lines) == 1, cap.out
        assert lines[0].startswith("sync check: clean (main vs origin/main")
