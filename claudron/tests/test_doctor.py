"""`claudron doctor` (#190 part A): read-only diagnosis, and the versioned,
idempotent migration runner behind `--fix`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claudron import CAPABILITIES
from claudron import doctor as doctor_mod
from claudron.cli import main
from claudron.doctor import (VAULT_FORMAT, Migration, MigrationRefused,
                             diagnose, fix, pending_migrations)
from claudron.structure import StructureError
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
                            (_file_migration("m901", 1, "marker"),))
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
        assert data["vault_format"] == 0 and data["engine_format"] == VAULT_FORMAT
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
                            (_file_migration("m901", 1, "marker"),))
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
        migrations = (_file_migration("m902", 2, "second"),
                      _file_migration("m901", 1, "first"))   # out of order on purpose
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
                            (_file_migration("m901", 1, "marker"),))
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
                            (_file_migration("m901", 1, "marker"),))
        fix(detect(vault_dir))
        assert _git(vault_dir, "show", "--name-only", "--format=", "HEAD").split() == ["marker"]
        assert "auth-patterns.md" in _git(vault_dir, "status", "--porcelain")

    def test_refusal_is_reported_and_stops_the_chain(self, vault_dir, monkeypatch):
        def refuse(v):
            raise MigrationRefused("two hubs; which one is canonical?")
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", 1, "decide", lambda v: True, refuse),
            _file_migration("m902", 2, "later"),
        ))
        report = fix(detect(vault_dir))
        assert report.applied == []
        assert not (vault_dir / "later").exists()
        d005 = [f for f in report.findings if f.code == "D005"]
        assert d005 and "which one is canonical" in d005[0].message

    def test_a_migration_that_stays_needed_is_caught(self, vault_dir, monkeypatch):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", 1, "never converges", lambda v: True, lambda v: []),
        ))
        report = fix(detect(vault_dir))
        assert any(f.code == "D006" for f in report.findings)

    def test_a_migration_writing_outside_the_root_aborts(self, vault_dir, monkeypatch, capsys):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS", (
            Migration("m901", 1, "escape", lambda v: True,
                      lambda v: [v.root.parent / "outside"]),
        ))
        with pytest.raises(StructureError):
            fix(detect(vault_dir))
        assert main(["--vault", str(vault_dir), "doctor", "--fix"]) == 1
        assert "--fix aborted" in capsys.readouterr().err

    def test_fix_on_a_plain_directory_writes_without_committing(self, vault_dir, monkeypatch):
        monkeypatch.setattr(doctor_mod, "MIGRATIONS",
                            (_file_migration("m901", 1, "marker"),))
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

    def test_no_pending_migrations_with_an_empty_registry(self, vault_dir: Path):
        assert pending_migrations(detect(vault_dir)) == []

    def test_doctor_is_a_declared_capability(self):
        assert "doctor" in CAPABILITIES


class TestValidateFixAlias:
    def test_validate_fix_still_repairs_and_points_at_doctor(self, vault_dir: Path, capsys):
        _make_fleet(vault_dir)
        main(["--vault", str(vault_dir), "validate", "--fix"])
        assert (vault_dir / "myfleet" / "shared").is_dir()
        assert "alias for `claudron doctor --fix`" in capsys.readouterr().err
