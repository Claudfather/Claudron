"""`claudron doctor` (#190 part A): read-only diagnosis, and the versioned,
idempotent migration runner behind `--fix`."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from claudron import CAPABILITIES
from claudron import doctor as doctor_mod
from claudron.cli import main
from claudron.doctor import (VAULT_FORMAT, Migration, MigrationRefused,
                             diagnose, fix, pending_migrations)

# Synthetic migrations sit ABOVE the engine format, so fixture vaults (which are
# current) still have them pending.
V1, V2 = VAULT_FORMAT + 1, VAULT_FORMAT + 2
from claudron.structure import StructureError
from claudron.tests.doc_parity import code_values, doc_table
from claudron.vault import detect


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout


def _repo(root: Path) -> Path:
    _git(root, "init", "-q", "--initial-branch=main")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


def _make_fleet(root: Path, name: str = "myfleet") -> Path:
    """A fleet dir with a fleet.yaml but no shared/ — so S1 fires."""
    fleet = root / name
    fleet.mkdir()
    (fleet / "fleet.yaml").write_text(f"fleet: {{name: {name}}}")
    return fleet


def _fingerprint(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under the root (``.git`` included) → (size, mtime_ns)."""
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _file_migration(mid: str, version: int, rel: str, text: str = "x\n") -> Migration:
    """A well-behaved migration: creates one file, idempotently."""
    def needed(v):
        return not (v.root / rel).is_file()

    def apply(v):
        (v.root / rel).write_text(text)
        return [Path(rel)]
    return Migration(mid, version, f"create {rel}", needed, apply)


class TestReadOnly:
    def test_diagnosis_writes_nothing(self, vault_dir: Path, capsys):
        """The acceptance line: doctor is read-only unless --fix is passed."""
        _make_fleet(vault_dir)
        _repo(vault_dir)
        (vault_dir / "_shared" / "knowledge" / "loose.md").write_text("no frontmatter\n")
        before = _fingerprint(vault_dir)
        rc = main(["--vault", str(vault_dir), "doctor"])
        after = _fingerprint(vault_dir)
        assert before == after
        assert rc == 1                      # the loose note is a schema error
        out = capsys.readouterr().out
        assert "[S1]" in out and "[D002]" in out

    def test_diagnosis_with_a_pending_migration_writes_nothing(self, vault_dir, monkeypatch):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", V1, "marker"),))
        before = _fingerprint(vault_dir)
        report = diagnose(detect(vault_dir))
        assert [m.id for m in report.pending] == ["m901"]
        assert _fingerprint(vault_dir) == before


class TestFindings:
    def test_clean_vault_is_clean(self, vault_dir: Path, capsys):
        _repo(vault_dir)
        assert main(["--vault", str(vault_dir), "doctor", "--json"]) == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "doctor" and env["ok"] is True
        data = env["data"]
        assert data["pending"] == [] and data["fixable"] == []
        assert data["vault_format"] == data["engine_format"] == VAULT_FORMAT
        assert data["git"]["state"] == "clean"
        assert data["fixed"] is False

    def test_plain_directory_vault_is_not_a_git_finding(self, vault_dir: Path, capsys):
        main(["--vault", str(vault_dir), "doctor", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["git"] is None
        assert "D004" not in {f["code"] for f in env["warnings"] + env["errors"]}

    def test_dirty_clone_is_a_git_warning_not_an_error(self, vault_dir: Path, capsys):
        _repo(vault_dir)
        (vault_dir / "_shared" / "knowledge" / "auth-patterns.md").write_text("changed")
        main(["--vault", str(vault_dir), "doctor", "--json"])
        env = json.loads(capsys.readouterr().out)
        assert "D004" in {f["code"] for f in env["warnings"]}

    def test_pending_migration_is_an_error_naming_the_fix(self, vault_dir, monkeypatch, capsys):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", V1, "marker"),))
        assert main(["--vault", str(vault_dir), "doctor", "--json"]) == 1
        env = json.loads(capsys.readouterr().out)
        assert [e["code"] for e in env["errors"]] == ["D001"]
        assert env["data"]["fixable"] == ["m901"]
        assert "doctor --fix" in env["errors"][0]["message"]

    def test_structure_fixability_is_surfaced(self, vault_dir: Path, capsys):
        _make_fleet(vault_dir)
        main(["--vault", str(vault_dir), "doctor"])
        assert "→ fixable: S1 — run: claudron doctor --fix" in capsys.readouterr().err


class TestFix:
    def test_fix_applies_in_order_and_makes_one_commit(self, vault_dir, monkeypatch, capsys):
        _make_fleet(vault_dir)
        _repo(vault_dir)
        migrations = (_file_migration("m902", V2, "second"),
                      _file_migration("m901", V1, "first"))   # out of order on purpose
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", migrations)
        head = _git(vault_dir, "rev-parse", "HEAD").strip()

        assert main(["--vault", str(vault_dir), "doctor", "--fix", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)["data"]
        assert data["applied"] == ["m901", "m902"]
        assert data["commit"]["committed"] is True
        assert data["pending"] == [] and data["fixable"] == []

        log = _git(vault_dir, "log", "--format=%s", f"{head}..HEAD").splitlines()
        assert log == ["migrate(S1,m901,m902): claudron doctor --fix"]
        changed = set(_git(vault_dir, "show", "--name-only", "--format=", "HEAD").split())
        assert {"first", "second"} < changed
        assert all(p in {"first", "second"} or p.startswith("myfleet/shared/")
                   for p in changed)

    def test_fix_twice_is_a_no_op(self, vault_dir, monkeypatch):
        """The acceptance line: every migration is idempotent — run it twice."""
        _repo(vault_dir)
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", V1, "marker"),))
        first = fix(detect(vault_dir))
        head = _git(vault_dir, "rev-parse", "HEAD")
        before = _fingerprint(vault_dir)
        second = fix(detect(vault_dir))
        assert first.applied == ["m901"] and second.applied == []
        assert second.commit is None
        assert _git(vault_dir, "rev-parse", "HEAD") == head
        # The write lock's own mtime moves every time it is taken; that is the
        # lock working, not the vault changing.
        lock = ".claudron/write.lock"
        after = _fingerprint(vault_dir)
        before.pop(lock, None), after.pop(lock, None)
        assert after == before

    def test_fix_stages_only_what_it_wrote(self, vault_dir, monkeypatch):
        _repo(vault_dir)
        other = vault_dir / "_shared" / "knowledge" / "auth-patterns.md"
        other.write_text(other.read_text() + "\nsomeone's half-finished edit\n")
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", V1, "marker"),))
        fix(detect(vault_dir))
        assert _git(vault_dir, "show", "--name-only", "--format=", "HEAD").split() == ["marker"]
        assert "auth-patterns.md" in _git(vault_dir, "status", "--porcelain")

    def test_refusal_is_reported_and_stops_the_chain(self, vault_dir, monkeypatch):
        def refuse(v):
            raise MigrationRefused("two hubs; which one is canonical?")
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", V1, "decide", lambda v: True, refuse),
            _file_migration("m902", V2, "later"),
        ))
        report = fix(detect(vault_dir))
        assert report.applied == []
        assert not (vault_dir / "later").exists()
        d005 = [f for f in report.findings if f.code == "D005"]
        assert d005 and "which one is canonical" in d005[0].message

    def test_a_migration_that_stays_needed_is_caught(self, vault_dir, monkeypatch):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", V1, "never converges", lambda v: True, lambda v: []),
        ))
        report = fix(detect(vault_dir))
        assert any(f.code == "D006" for f in report.findings)

    def test_a_migration_writing_outside_the_root_aborts(self, vault_dir, monkeypatch, capsys):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", V1, "escape", lambda v: True,
                      lambda v: [v.root.parent / "outside"]),
        ))
        with pytest.raises(StructureError):
            fix(detect(vault_dir))
        assert main(["--vault", str(vault_dir), "doctor", "--fix"]) == 1
        assert "--fix aborted" in capsys.readouterr().err

    def test_fix_on_a_plain_directory_writes_without_committing(self, vault_dir, monkeypatch):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", V1, "marker"),))
        report = fix(detect(vault_dir))
        assert (vault_dir / "marker").is_file()
        assert report.commit == {"committed": False, "error": None,
                                 "message": "migrate(m901): claudron doctor --fix"}


class TestRegistry:
    """The shipped registry obeys the rules the runner assumes."""

    def test_ids_unique_and_versions_within_the_engine_format(self):
        ids = [m.id for m in doctor_mod.MIGRATIONS]
        assert len(ids) == len(set(ids))
        assert all(1 <= m.version <= VAULT_FORMAT for m in doctor_mod.MIGRATIONS)

    def test_a_current_vault_has_nothing_pending(self, vault_dir: Path):
        assert pending_migrations(detect(vault_dir)) == []

    def test_the_engine_format_is_reached_by_a_registered_migration(self):
        assert max(m.version for m in doctor_mod.MIGRATIONS) == VAULT_FORMAT

    def test_the_contract_d_table_matches_the_code(self):
        """docs/CLI_CONTRACT.md's doctor table, code by code and severity by
        severity, is the registry `_finding` enforces (#204)."""
        rows = doc_table("docs/CLI_CONTRACT.md", "DOCTOR_CODES")
        doc = {code_values(r[0])[0]: frozenset(s.strip() for s in r[1].split("/"))
               for r in rows}
        assert doc == doctor_mod.CODES

    def test_every_code_doctor_emits_is_registered(self):
        src = Path(doctor_mod.__file__).read_text()
        emitted = set(re.findall(r'_finding\(\s*"(D\d{3})"', src))
        assert emitted and emitted <= set(doctor_mod.CODES)

    def test_an_unregistered_code_or_severity_is_refused(self):
        with pytest.raises(ValueError):
            doctor_mod._finding("D999", "error", "x")
        with pytest.raises(ValueError):
            doctor_mod._finding("D003", "error", "x")  # D003 is warning-only

    def test_doctor_is_a_declared_capability(self):
        assert "doctor" in CAPABILITIES


class TestValidateFixAlias:
    def test_validate_fix_still_repairs_and_points_at_doctor(self, vault_dir: Path, capsys):
        _make_fleet(vault_dir)
        main(["--vault", str(vault_dir), "validate", "--fix"])
        assert (vault_dir / "myfleet" / "shared").is_dir()
        assert "alias for `claudron doctor --fix`" in capsys.readouterr().err


def _legacy_vault(root: Path) -> Path:
    """A vault as 0.5.x left it: a hub, the old three-line .gitignore, no
    identity file."""
    (root / "_shared" / "knowledge").mkdir(parents=True)
    (root / "_shared" / "knowledge" / "n.md").write_text(
        "---\ntitle: N\ntype: knowledge\nstatus: current\nowner: t\n"
        "created: 2026-07-01\nupdated: 2026-07-01\n---\n\n# N\n\nBody.\n")
    (root / ".gitignore").write_text("# claudron vault\n*/runtime/\n.env\n.claudron/\nlocal-extra\n")
    return root


class TestFirstMigrations:
    """#190's own "test it on yourself" flow, on a legacy vault."""

    def test_legacy_vault_lists_m001_and_m002_read_only(self, tmp_path, capsys):
        v = _repo(_legacy_vault(tmp_path / "legacy"))
        before = _fingerprint(v)
        assert main(["--vault", str(v), "doctor", "--json"]) == 1
        data = json.loads(capsys.readouterr().out)["data"]
        assert [p["id"] for p in data["pending"]] == ["m001", "m002"]
        assert data["vault_format"] == 0
        assert _fingerprint(v) == before

    def test_fix_is_one_commit_touching_only_identity_and_gitignore(self, tmp_path, capsys):
        v = _repo(_legacy_vault(tmp_path / "legacy"))
        head = _git(v, "rev-parse", "HEAD").strip()
        assert main(["--vault", str(v), "doctor", "--fix", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)["data"]
        assert data["applied"] == ["m001", "m002"] and data["pending"] == []
        assert data["vault_format"] == VAULT_FORMAT
        log = _git(v, "log", "--format=%s", f"{head}..HEAD").splitlines()
        assert log == ["migrate(m001,m002): claudron doctor --fix"]
        changed = set(_git(v, "show", "--name-only", "--format=", "HEAD").split())
        assert changed == {".claudron-vault", ".gitignore"}

        ident = (v / ".claudron-vault").read_text()
        assert f"claudron: {VAULT_FORMAT}" in ident
        assert "name: legacy" in ident and "hub: _shared" in ident
        gi = (v / ".gitignore").read_text()
        assert gi.startswith("# claudron vault\n*/runtime/\n.env\n.claudron/\nlocal-extra\n")
        for rule in ("**/runtime/", "**/data/events/fleet-*.jsonl",
                     "**/data/.last-tool-call", "**/data/.idle", "*.bak"):
            assert rule in gi.splitlines()

        # Re-run: nothing pending, and plain walk-up now binds it.
        assert main(["--vault", str(v), "doctor"]) == 0
        assert detect(v / "_shared" / "knowledge").root == v

    def test_nested_fleet_runtime_is_ignored_after_m002(self, tmp_path):
        v = _repo(_legacy_vault(tmp_path / "legacy"))
        fix(detect(v))
        for p in ("sys/fleet/runtime/bots/b/x", "fleet/data/events/fleet-1.jsonl",
                  "fleet/data/.idle", "fleet/fleet.yaml.bak"):
            assert subprocess.run(["git", "-C", str(v), "check-ignore", "-q", p]).returncode == 0, p
        assert subprocess.run(["git", "-C", str(v), "check-ignore", "-q",
                               "fleet/fleet.yaml"]).returncode == 1

    def test_hub_is_recorded_as_found(self, tmp_path):
        v = tmp_path / "old"
        (v / "shared" / "knowledge").mkdir(parents=True)
        fix(detect(v))
        assert "hub: shared" in (v / ".claudron-vault").read_text()

    def test_an_existing_identity_file_is_never_overwritten(self, tmp_path):
        v = _legacy_vault(tmp_path / "legacy")
        (v / ".claudron-vault").write_text("# mine\nclaudron: 1\nname: kept\nhub: _shared\nextra: yes\n")
        report = fix(detect(v))
        assert report.applied == ["m002"]
        text = (v / ".claudron-vault").read_text()
        assert text == f"# mine\nclaudron: {VAULT_FORMAT}\nname: kept\nhub: _shared\nextra: yes\n"

    def test_format_behind_with_nothing_to_migrate_is_recorded(self, vault_dir):
        (vault_dir / ".claudron-vault").write_text("claudron: 1\nname: vault\nhub: _shared\n")
        (vault_dir / ".gitignore").write_text("\n".join(doctor_mod.missing_gitignore_rules(vault_dir)) + "\n")
        report = diagnose(detect(vault_dir))
        assert report.pending == [] and any(f.code == "D001" for f in report.findings)
        fixed = fix(detect(vault_dir))
        assert fixed.vault_format == VAULT_FORMAT
        assert not any(f.code == "D001" for f in fixed.findings)


class TestIdentityChecks:
    def test_unreadable_identity_is_reported_not_guessed(self, vault_dir):
        (vault_dir / ".claudron-vault").write_text("claudron: [not, an, int\n")
        report = diagnose(detect(vault_dir))
        d007 = [f for f in report.findings if f.code == "D007"]
        assert d007 and d007[0].severity == "error"

    def test_vault_newer_than_engine_is_a_warning(self, vault_dir):
        (vault_dir / ".claudron-vault").write_text(
            f"claudron: {VAULT_FORMAT + 5}\nname: vault\nhub: _shared\n")
        report = diagnose(detect(vault_dir))
        assert [f.severity for f in report.findings if f.code == "D007"] == ["warning"]

    def test_tracked_but_ignored_files_are_named_for_a_human(self, tmp_path):
        v = _legacy_vault(tmp_path / "legacy")
        (v / "fleet" / "data").mkdir(parents=True)
        (v / "fleet" / "data" / ".idle").write_text("x")
        _repo(v)                                    # .idle committed before m002
        report = fix(detect(v))
        d008 = [f for f in report.findings if f.code == "D008"]
        assert d008 and "fleet/data/.idle" in d008[0].message
        assert (v / "fleet" / "data" / ".idle").exists()      # never untracked for you
        assert "fleet/data/.idle" in _git(v, "ls-files")


class TestDetectionCutover:
    """#183 / F6: walk-up binds only a directory carrying .claudron-vault."""

    def test_a_stray_home_shared_no_longer_binds(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "shared").mkdir(parents=True)          # clauDNA's old default
        repo = home / "code" / "myrepo"
        repo.mkdir(parents=True)
        monkeypatch.chdir(repo)
        assert detect() is None

    def test_walk_up_binds_by_identity(self, vault_dir, monkeypatch):
        deep = vault_dir / "_shared" / "knowledge"
        monkeypatch.chdir(deep)
        assert detect().root == vault_dir

    def test_legacy_vault_binds_only_when_addressed(self, tmp_path, monkeypatch):
        v = _legacy_vault(tmp_path / "legacy")
        assert detect(v).root == v                     # explicit: still opens
        monkeypatch.chdir(v / "_shared")
        assert detect() is None                        # walk-up: no longer binds

    def test_no_vault_message_names_the_migration(self, tmp_path, monkeypatch, capsys,
                                                  no_vault_env):
        v = _legacy_vault(tmp_path / "legacy")
        monkeypatch.chdir(v / "_shared" / "knowledge")
        with pytest.raises(SystemExit) as exc:
            main(["status"])
        assert exc.value.code == 3
        err = capsys.readouterr().err
        assert f"claudron doctor --vault {v} --fix" in err

    def test_identity_in_a_fleet_dir_does_not_bind(self, vault_dir):
        fleet = vault_dir / "f"
        (fleet / "shared" / "knowledge").mkdir(parents=True)
        (fleet / "fleet.yaml").write_text("fleet: {name: f}")
        (fleet / ".claudron-vault").write_text("claudron: 2\nname: f\nhub: shared\n")
        assert detect(fleet / "shared" / "knowledge").root == vault_dir

    def test_init_writes_a_current_vault(self, tmp_path):
        from claudron.vault import init
        root = init(tmp_path / "fresh")
        assert detect(root / "_shared").root == root
        report = diagnose(detect(root))
        assert report.vault_format == VAULT_FORMAT and report.pending == []
