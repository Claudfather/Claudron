"""`claudron doctor`'s per-host checks (#204, #190's last two rows): the hook
entries installed in a Claude Code settings file against the current snippet
shape (D009), and whether each entry reaches a vault from where it runs (D010).

The settings file is declared, never sniffed: `--settings PATH` (repeatable),
or by default the file `hooks install --write` writes. Both checks are
read-only, and `--fix` acts on neither."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from claudron.cli import main
from claudron import doctor as doctor_mod
from claudron import hooks as hooks_mod
from claudron.hooks import merge_settings, settings_snippet
from claudron.vault import IDENTITY_FILE, detect, identity_text

EVENT_CMD = {
    "SessionStart": "session-start",
    "PreCompact": "pre-compact",
    "SessionEnd": "session-end",
}


def _exe(tmp_path: Path) -> str:
    """An executable that exists: the entry's executable check needs one."""
    exe = tmp_path / "bin" / "claudron"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


def _write(path: Path, settings: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def _installed(path: Path, exe: str, root: str) -> Path:
    """A settings file as `hooks install --write` leaves it."""
    return _write(path, merge_settings({}, settings_snippet(exe, root)))


def _codes(report, code: str) -> list:
    return [f for f in report.findings if f.code == code]


def _other_vault(tmp_path: Path) -> Path:
    other = tmp_path / "other-vault"
    (other / "_shared").mkdir(parents=True)
    (other / IDENTITY_FILE).write_text(identity_text(other.name, "_shared"))
    return other


class TestShape:
    """D009: the installed entries against the current snippet shape."""

    def test_a_fresh_install_is_clean(self, vault_dir, tmp_path):
        s = _installed(
            tmp_path / "settings.json", _exe(tmp_path), str(vault_dir.resolve())
        )
        report = doctor_mod.diagnose(detect(vault_dir), settings=[s])
        assert not _codes(report, "D009") and not _codes(report, "D010")
        (checked,) = report.hooks
        assert checked["path"] == str(s) and checked["declared"] is True
        assert checked["state"] == "ok"
        assert [e["event"] for e in checked["entries"]] == list(EVENT_CMD)
        assert all(e["vault"] == str(vault_dir.resolve()) for e in checked["entries"])
        assert all(
            e["resolves_to"] == str(vault_dir.resolve()) for e in checked["entries"]
        )

    def test_entries_installed_before_183_are_flagged(self, vault_dir, tmp_path):
        # The live shape (a composed settings file, 2026-09-29): absolute
        # executable, no --vault, beside a foreign hook on two events.
        exe = _exe(tmp_path)
        foreign = {
            "matcher": "",
            "hooks": [{"type": "command", "command": "/opt/fleet/own.sh"}],
        }
        hooks = {
            ev: ([foreign] if ev != "PreCompact" else [])
            + [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": f"{exe} hook {cmd}"}],
                }
            ]
            for ev, cmd in EVENT_CMD.items()
        }
        s = _write(tmp_path / "settings.json", {"hooks": hooks})
        report = doctor_mod.diagnose(detect(vault_dir), settings=[s])
        d009 = _codes(report, "D009")
        assert len(d009) == 3 and {f.severity for f in d009} == {"warning"}
        assert all("no --vault" in f.message for f in d009)
        assert all(
            f"--vault {vault_dir.resolve()} hooks install --write" in f.message
            for f in d009
        )
        assert all(f.path == str(s) for f in d009)
        assert not _codes(report, "D010")  # no address to resolve; D009 says so
        assert all(e["vault"] is None for e in report.hooks[0]["entries"])

    def test_a_missing_event_is_flagged(self, vault_dir, tmp_path):
        s = tmp_path / "settings.json"
        settings = merge_settings(
            {}, settings_snippet(_exe(tmp_path), str(vault_dir.resolve()))
        )
        del settings["hooks"]["PreCompact"]
        _write(s, settings)
        (d009,) = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D009")
        assert d009.message.startswith("PreCompact has no claudron hook entry")

    def test_a_duplicate_entry_is_flagged(self, vault_dir, tmp_path):
        s = tmp_path / "settings.json"
        settings = merge_settings(
            {}, settings_snippet(_exe(tmp_path), str(vault_dir.resolve()))
        )
        settings["hooks"]["SessionStart"] *= 2
        _write(s, settings)
        (d009,) = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D009")
        assert d009.message.startswith("SessionStart has 2 claudron hook entries")

    @pytest.mark.parametrize(
        "mutate,named",
        [
            (lambda g: g.update(matcher="*"), "matcher"),
            (lambda g: g["hooks"][0].update(timeout=30), "timeout"),
        ],
    )
    def test_a_drifted_entry_is_flagged(self, vault_dir, tmp_path, mutate, named):
        s = tmp_path / "settings.json"
        settings = merge_settings(
            {}, settings_snippet(_exe(tmp_path), str(vault_dir.resolve()))
        )
        mutate(settings["hooks"]["SessionEnd"][0])
        _write(s, settings)
        (d009,) = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D009")
        assert d009.message.startswith(
            "SessionEnd's claudron hook differs from the current snippet"
        )
        assert named in d009.message

    def test_a_declared_settings_file_that_is_missing_is_flagged(
        self, vault_dir, tmp_path
    ):
        report = doctor_mod.diagnose(detect(vault_dir), settings=[tmp_path / "nope.json"])
        (d009,) = _codes(report, "D009")
        assert d009.severity == "warning" and "not found" in d009.message
        assert report.hooks[0]["state"] == "absent"

    def test_an_unreadable_settings_file_is_flagged(self, vault_dir, tmp_path):
        s = tmp_path / "settings.json"
        s.write_text("{not json")
        report = doctor_mod.diagnose(detect(vault_dir), settings=[s])
        (d009,) = _codes(report, "D009")
        assert "cannot parse" in d009.message
        assert report.hooks[0]["state"] == "unreadable"

    def test_the_default_file_absent_is_not_a_finding(self, vault_dir):
        # No --settings: the default install target. A host that never ran
        # `hooks install` has no loop to check, which is not a defect.
        report = doctor_mod.diagnose(detect(vault_dir))
        assert not _codes(report, "D009") and not _codes(report, "D010")
        assert report.hooks == [
            {
                "path": str(hooks_mod.default_settings_path()),
                "declared": False,
                "state": "absent",
                "entries": [],
            }
        ]

    def test_the_default_file_is_checked_when_present(self, vault_dir, tmp_path):
        _installed(hooks_mod.default_settings_path(), _exe(tmp_path), str(tmp_path / "gone"))
        report = doctor_mod.diagnose(detect(vault_dir))
        assert report.hooks[0]["declared"] is False and report.hooks[0]["state"] == "ok"
        assert len(_codes(report, "D010")) == 3


class TestResolution:
    """D010: whether each entry reaches a vault from where it runs."""

    def test_a_missing_executable_is_an_error(self, vault_dir, tmp_path):
        s = _installed(
            tmp_path / "settings.json",
            str(tmp_path / "gone" / "claudron"),
            str(vault_dir.resolve()),
        )
        d010 = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"error"}
        assert all("does not exist or is not executable" in f.message for f in d010)

    def test_a_bare_executable_is_a_warning(self, vault_dir, tmp_path):
        s = _installed(tmp_path / "settings.json", "claudron", str(vault_dir.resolve()))
        d010 = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"warning"}
        assert all("bare" in f.message for f in d010)

    def test_an_address_that_resolves_to_nothing_is_an_error(self, vault_dir, tmp_path):
        s = _installed(
            tmp_path / "settings.json", _exe(tmp_path), str(tmp_path / "moved-away")
        )
        d010 = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"error"}
        assert all("is not a vault" in f.message for f in d010)

    def test_an_address_inside_another_vault_binds_that_vault(
        self, vault_dir, tmp_path
    ):
        # Measured on #203: walk-up from a stale address under a vault's tree
        # binds that vault, so the hooks sync it instead.
        stale = vault_dir / "projects" / "moved-away"
        s = _installed(tmp_path / "settings.json", _exe(tmp_path), str(stale))
        d010 = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"error"}
        assert all(f"binds {vault_dir.resolve()}" in f.message for f in d010)

    def test_a_relative_address_is_a_warning(self, vault_dir, tmp_path):
        s = _installed(tmp_path / "settings.json", _exe(tmp_path), "~/vault")
        d010 = _codes(doctor_mod.diagnose(detect(vault_dir), settings=[s]), "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"warning"}
        assert all("not absolute" in f.message for f in d010)

    def test_hooks_for_another_vault_are_a_warning(self, vault_dir, tmp_path):
        other = _other_vault(tmp_path)
        s = _installed(tmp_path / "settings.json", _exe(tmp_path), str(other.resolve()))
        report = doctor_mod.diagnose(detect(vault_dir), settings=[s])
        d010 = _codes(report, "D010")
        assert len(d010) == 3 and {f.severity for f in d010} == {"warning"}
        assert all(
            f"syncs {other.resolve()}, not this vault" in f.message for f in d010
        )
        assert all(
            e["resolves_to"] == str(other.resolve()) for e in report.hooks[0]["entries"]
        )


class TestReadOnlyAndCli:
    def test_the_hook_checks_write_nothing(self, vault_dir, tmp_path):
        s = _installed(
            tmp_path / "settings.json", _exe(tmp_path), str(tmp_path / "moved-away")
        )
        before = (s.read_bytes(), s.stat().st_mtime_ns)
        doctor_mod.diagnose(detect(vault_dir), settings=[s])
        assert (s.read_bytes(), s.stat().st_mtime_ns) == before

    def test_fix_acts_on_neither(self, vault_dir, tmp_path):
        s = _installed(
            tmp_path / "settings.json", "claudron", str(tmp_path / "moved-away")
        )
        before = s.read_bytes()
        report = doctor_mod.fix(detect(vault_dir), settings=[s])
        assert s.read_bytes() == before
        assert "D009" not in report.fixable and "D010" not in report.fixable
        assert _codes(report, "D010")  # the re-diagnosis still sees them

    def test_settings_is_repeatable_and_reported(self, vault_dir, tmp_path, capsys):
        good = _installed(tmp_path / "a.json", _exe(tmp_path), str(vault_dir.resolve()))
        stale = _installed(
            tmp_path / "b.json", _exe(tmp_path), str(tmp_path / "moved-away")
        )
        rc = main(
            [
                "--vault",
                str(vault_dir),
                "doctor",
                "--json",
                "--settings",
                str(good),
                "--settings",
                str(stale),
            ]
        )
        env = json.loads(capsys.readouterr().out)
        assert rc == 1  # D010 errors
        assert [h["path"] for h in env["data"]["hooks"]] == [str(good), str(stale)]
        assert {f["code"] for f in env["errors"]} == {"D010"}

    def test_the_text_report_names_each_file_checked(self, vault_dir, tmp_path, capsys):
        s = _installed(
            tmp_path / "settings.json", _exe(tmp_path), str(vault_dir.resolve())
        )
        main(["--vault", str(vault_dir), "doctor", "--settings", str(s)])
        out = capsys.readouterr().out
        assert f"hooks: {s} — 3 claudron entries" in out
        main(["--vault", str(vault_dir), "doctor"])
        out = capsys.readouterr().out
        assert (
            f"hooks: {hooks_mod.default_settings_path()} — absent (the default install target)"
            in out
        )

    def test_a_relative_settings_path_is_reported_absolute(
        self, vault_dir, tmp_path, monkeypatch, capsys
    ):
        _installed(tmp_path / "settings.json", _exe(tmp_path), str(vault_dir.resolve()))
        monkeypatch.chdir(tmp_path)
        main(
            [
                "--vault",
                str(vault_dir),
                "doctor",
                "--json",
                "--settings",
                "settings.json",
            ]
        )
        env = json.loads(capsys.readouterr().out)
        assert env["data"]["hooks"][0]["path"] == os.path.join(
            str(tmp_path), "settings.json"
        )
