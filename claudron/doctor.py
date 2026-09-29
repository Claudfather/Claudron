"""Vault doctor (#190): diagnose a vault against THIS engine's rules, and bring
it current with ordered, versioned migrations.

**Read-only unless asked.** :func:`diagnose` only reads — structure, schema,
index drift and git health are all gathered through read-only doors (`sync
--check`, the raw index read, the structure and schema lenses). The test suite
pins that by fingerprinting the whole tree around a diagnosis rather than
trusting this paragraph. :func:`fix` is the one door that writes.

**Why migrations, and why versioned.** Every change to what a vault must
contain (an identity file, an ignore pattern, a directory rule) used to ship as
a bespoke manual step, which is exactly how a vault silently falls behind its
engine. The rule now (docs/CLAUDE.md): *a vault-shape change ships a migration
in the same PR*. A vault records the format it is at; an engine knows the
format it writes (:data:`VAULT_FORMAT`); "is this vault current?" is then one
comparison instead of a pile of heuristics, and `--fix` runs exactly the
migrations between the two.

**The migration rules**, enforced here or pinned by tests:

* **Ordered** — by format version, then id; a chain stops at the first one that
  cannot finish, because later migrations may assume earlier ones ran.
* **Idempotent** — ``needed`` is re-asked after ``apply``; a migration that is
  still needed after running is reported, never retried in a loop.
* **Creation- or edit-only, confined to the vault root** — every path a
  migration reports writing is checked against the root (symlinks included) and
  the run aborts on an escape. No migration ever deletes a note.
* **Undecidable → reported, never guessed** — a migration that cannot decide
  raises :class:`MigrationRefused`; the reason goes to a human as a finding.

The written result is ONE commit, ``migrate(<ids>): …``, staging only the paths
the run wrote — a doctor run never sweeps up someone else's half-finished edit.

The vault's format lives in its identity file (``.claudron-vault``,
``claudron: N``); a vault without one is format 0. After a chain completes the
runner records :data:`VAULT_FORMAT` there — the bump is part of the same commit.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from .knowledge import index_divergence
from .locking import vault_write_lock
from .schema import Finding, validate_path
from .structure import StructureError, check_structure, fix_structure, is_fixable
from .vault import (IDENTITY_FILE, VAULT_FORMAT, Vault, _ensure_gitignore,
                    identity_text, is_within_root, missing_gitignore_rules)

__all__ = ["VAULT_FORMAT", "Migration", "MigrationRefused", "MIGRATIONS",
           "diagnose", "fix", "pending_migrations", "vault_format"]

#: Git verdicts (docs/CLI_CONTRACT.md, `sync --check`) that need no attention:
#: a clone that is merely ahead or behind is the ordinary between-syncs state.
_GIT_FINE = frozenset({"clean", "ahead", "behind"})


class MigrationRefused(Exception):
    """A migration met a state it must not decide for a human. The message is
    the reason, reported verbatim."""


@dataclass(frozen=True)
class Migration:
    """One step that brings a vault from ``version - 1`` to ``version``.

    ``needed(vault)`` must be cheap and read-only. ``apply(vault)`` returns the
    paths it wrote (absolute or vault-relative); it must be idempotent, may
    create or edit, and must never delete.
    """

    id: str
    version: int
    title: str
    needed: Callable[[Vault], bool]
    apply: Callable[[Vault], list[Path]]


# ── the registry ──────────────────────────────────────────────────────


def _m001_needed(vault: Vault) -> bool:
    return not (vault.root / IDENTITY_FILE).is_file()


def _m001_apply(vault: Vault) -> list[Path]:
    """Create the identity file (#183, F6) — format 1; the runner records the
    engine's format after the chain."""
    path = vault.root / IDENTITY_FILE
    if path.exists():                       # idempotent, and never overwrites
        return []
    path.write_text(identity_text(vault.root.name, vault.shared.name, fmt=1))
    return [path]


def _m002_needed(vault: Vault) -> bool:
    return bool(missing_gitignore_rules(vault.root))


def _m002_apply(vault: Vault) -> list[Path]:
    """Append the F9 ignore rules (#182) that are missing — existing lines are
    never touched. A file that is ALREADY tracked stays tracked (ignore rules do
    not untrack): those are reported by the D008 check for a human to decide."""
    changed = _ensure_gitignore(vault.root, added_by="`claudron doctor --fix` (m002)")
    return [vault.root / ".gitignore"] if changed else []


#: The registry, in application order. A vault-shape change adds its entry here
#: and bumps VAULT_FORMAT in the same PR (docs/CLAUDE.md).
MIGRATIONS: tuple[Migration, ...] = (
    Migration("m001", 1, "create the .claudron-vault identity file (#183)",
              _m001_needed, _m001_apply),
    Migration("m002", 2, "add the F9 .gitignore rules: runtime, telemetry, *.bak (#182)",
              _m002_needed, _m002_apply),
)


def _read_identity(vault: Vault) -> dict | None:
    """The identity file's mapping; ``None`` when absent; ``{}`` when present
    but unreadable (reported by D007, never guessed at)."""
    path = vault.root / IDENTITY_FILE
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def vault_format(vault: Vault) -> int:
    """The format a vault records: ``claudron:`` in its identity file, or 0
    when it has none (or it cannot be read as an int)."""
    ident = _read_identity(vault)
    fmt = (ident or {}).get("claudron")
    return fmt if isinstance(fmt, int) and not isinstance(fmt, bool) else 0


def _record_format(vault: Vault, fmt: int) -> Path | None:
    """Rewrite ``claudron: N`` in place — an edit of one line, every other line
    (comments, name, hub, anything a human added) kept byte-for-byte."""
    path = vault.root / IDENTITY_FILE
    if not path.is_file() or vault_format(vault) >= fmt:
        return None
    text = path.read_text()
    new, n = re.subn(r"(?m)^claudron:[ \t]*\S*[ \t]*$", f"claudron: {fmt}", text, count=1)
    if n == 0:
        new = text + ("" if text.endswith("\n") else "\n") + f"claudron: {fmt}\n"
    path.write_text(new)
    return path


def pending_migrations(vault: Vault,
                       migrations: tuple[Migration, ...] | None = None) -> list[Migration]:
    """Registry entries newer than the vault's format that still need to run."""
    registry = MIGRATIONS if migrations is None else migrations
    have = vault_format(vault)
    ordered = sorted(registry, key=lambda m: (m.version, m.id))
    return [m for m in ordered if m.version > have and m.needed(vault)]


@dataclass
class DoctorReport:
    """What the doctor found (and, after ``fix``, what it did)."""

    findings: list[Finding] = field(default_factory=list)
    vault_format: int = 0
    engine_format: int = VAULT_FORMAT
    pending: list[Migration] = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    index: dict = field(default_factory=dict)
    git: dict | None = None
    # --fix only
    fixed: bool = False
    applied: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    commit: dict | None = None

    @property
    def fixable(self) -> list[str]:
        """Migration ids and finding codes `doctor --fix` would act on."""
        out = [m.id for m in self.pending]
        out += sorted({f.code for f in self.findings if is_fixable(f)})
        return out

    def to_dict(self) -> dict:
        data = {
            "vault_format": self.vault_format,
            "engine_format": self.engine_format,
            "pending": [{"id": m.id, "version": m.version, "title": m.title}
                        for m in self.pending],
            "fixable": self.fixable,
            "schema": self.schema,
            "index": self.index,
            "git": self.git,
            "fixed": self.fixed,
        }
        if self.fixed:
            data.update(applied=self.applied, repairs=self.repairs, commit=self.commit)
        return data


def _finding(code: str, severity: str, message: str, path: str = ".") -> Finding:
    return Finding(code=code, severity=severity, path=path, field=None,
                   line=None, message=message)


def _git_health(vault: Vault) -> dict | None:
    """`sync --check`'s verdict, or ``None`` for a vault that is not a git
    repository (a plain-directory vault is legal, so that is not a finding)."""
    from .sync import SyncError, check

    try:
        return check(vault).to_dict()
    except SyncError:
        return None


def diagnose(vault: Vault, *,
             migrations: tuple[Migration, ...] | None = None) -> DoctorReport:
    """Read-only diagnosis against this engine's rules. Never writes."""
    report = DoctorReport(vault_format=vault_format(vault))
    ident = _read_identity(vault)
    if ident == {} or (ident and "claudron" in ident and report.vault_format == 0):
        report.findings.append(_finding(
            "D007", "error",
            f"{IDENTITY_FILE} is present but unreadable (want YAML with an integer "
            "`claudron:`) — fix it by hand; doctor never guesses", IDENTITY_FILE))
    elif report.vault_format > report.engine_format:
        report.findings.append(_finding(
            "D007", "warning",
            f"vault format {report.vault_format} is newer than this engine's "
            f"{report.engine_format} — upgrade claudron", IDENTITY_FILE))
    report.pending = pending_migrations(vault, migrations)
    for m in report.pending:
        report.findings.append(_finding(
            "D001", "error",
            f"migration {m.id} pending (format {m.version}): {m.title} "
            "— run: claudron doctor --fix"))
    if not report.pending and ident and 0 < report.vault_format < report.engine_format:
        report.findings.append(_finding(
            "D001", "error",
            f"vault records format {report.vault_format}, engine is at "
            f"{report.engine_format}, and nothing needs migrating — run: "
            "claudron doctor --fix to record it", IDENTITY_FILE))

    report.findings += check_structure(vault)

    notes = validate_path(vault.root, strict=False, vault_root=vault.root)
    errors = sum(f.severity == "error" for f in notes)
    warnings = sum(f.severity == "warning" for f in notes)
    report.schema = {"errors": errors, "warnings": warnings}
    if errors or warnings:
        # A summary, not the list: `validate` is the door for the detail, and
        # repeating every note finding here would make doctor a second linter.
        report.findings.append(_finding(
            "D002", "error" if errors else "warning",
            f"notes carry {errors} schema error(s), {warnings} warning(s) "
            "— details: claudron validate"))

    report.index = index_divergence(vault)
    if report.index.get("corrupt") or report.index.get("missing") or report.index.get("ghost"):
        what = ("unreadable" if report.index.get("corrupt") else
                f"{report.index.get('missing', 0)} missing, "
                f"{report.index.get('ghost', 0)} ghost")
        report.findings.append(_finding(
            "D003", "warning",
            f"index drifted from the notes ({what}) — rebuild: claudron index"))

    report.git = _git_health(vault)
    if report.git is not None:
        tracked = _tracked_but_ignored(vault)
        if tracked:
            shown = ", ".join(tracked[:5]) + (f" (+{len(tracked) - 5} more)"
                                               if len(tracked) > 5 else "")
            report.findings.append(_finding(
                "D008", "warning",
                f"{len(tracked)} tracked file(s) match the ignore rules, so they keep "
                f"being committed: {shown} — a human decides: "
                "`git rm --cached <path>` stops tracking without deleting the file"))
    if report.git is not None and report.git.get("state") not in _GIT_FINE:
        state = report.git.get("state")
        detail = report.git.get("detail") or ""
        report.findings.append(_finding(
            "D004", "warning",
            f"git health: {state}" + (f" — {detail}" if detail else "")
            + " (see: claudron sync --check)"))
    return report


def _tracked_but_ignored(vault: Vault) -> list[str]:
    """Files git tracks that the ignore rules now match (read-only query).
    Ignore rules never untrack a file, so after m002 these are exactly the
    paths the safety net will go on committing."""
    try:
        out = subprocess.run(
            ["git", "-C", str(vault.root), "ls-files", "-ci", "--exclude-standard", "-z"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return sorted(p for p in out.stdout.split("\0") if p)


def _rel(vault: Vault, p: Path) -> Path:
    p = Path(p)
    return p if not p.is_absolute() else p.relative_to(vault.root)


def fix(vault: Vault, *,
        migrations: tuple[Migration, ...] | None = None) -> DoctorReport:
    """Apply structure repairs and pending migrations; commit what was written
    as one ``migrate(<ids>): …`` commit; return a FRESH diagnosis of the result.

    Raises :class:`StructureError` when a repair or a migration would write
    outside the vault root — a security boundary, so a hard stop.
    """
    written: list[Path] = []
    ids: list[str] = []
    repairs: list[str] = []
    applied: list[str] = []
    refusals: list[Finding] = []

    with vault_write_lock(vault):
        structure = [f for f in check_structure(vault) if is_fixable(f)]
        if structure:
            actions = fix_structure(vault, structure)
            repairs += actions
            created = [Path(f.path) for f, a in zip(structure, actions)
                       if a.startswith("created ")]
            if created:
                written += created
                ids += sorted({f.code for f in structure})

        for m in pending_migrations(vault, migrations):
            try:
                paths = [Path(p) for p in m.apply(vault)]
            except MigrationRefused as exc:
                refusals.append(_finding(
                    "D005", "error", f"migration {m.id} needs a human: {exc}"))
                break
            for p in paths:
                target = p if p.is_absolute() else vault.root / p
                if not is_within_root(target, vault.root):
                    raise StructureError(
                        f"migration {m.id} wrote outside the vault: {target}")
            written += paths
            ids.append(m.id)
            applied.append(m.id)
            repairs.append(f"applied {m.id}: {m.title}")
            if m.needed(vault):
                refusals.append(_finding(
                    "D006", "error",
                    f"migration {m.id} ran but is still needed — not idempotent; "
                    "stopping the chain"))
                break

        chain_done = not refusals
        if chain_done and (vault.root / IDENTITY_FILE).is_file():
            bumped = _record_format(vault, VAULT_FORMAT)
            if bumped is not None:
                written.append(bumped)
                repairs.append(f"recorded vault format {VAULT_FORMAT} in {IDENTITY_FILE}")
                if not ids:
                    ids.append(f"format{VAULT_FORMAT}")

        commit = _commit(vault, written, ids, repairs) if written else None

    report = diagnose(vault, migrations=migrations)
    report.findings = refusals + report.findings
    report.fixed = True
    report.applied = applied
    report.repairs = repairs
    report.commit = commit
    return report


def _commit(vault: Vault, written: list[Path], ids: list[str],
            lines: list[str]) -> dict:
    """One commit for the whole run, staging only what the run wrote. A vault
    that is not a git repository is a plain success with nothing to commit."""
    from .sync import (DEFAULT_GIT_TIMEOUT, SyncError, _git_dir,
                       _interrupted_state, commit_paths)

    message = f"migrate({','.join(ids)}): claudron doctor --fix"
    try:
        git_dir = _git_dir(vault.root, DEFAULT_GIT_TIMEOUT)
        if git_dir is None:
            return {"committed": False, "message": message, "error": None}
        interrupted = _interrupted_state(vault.root, git_dir, DEFAULT_GIT_TIMEOUT)
        if interrupted:
            return {"committed": False, "message": message,
                    "error": f"not committed: {interrupted}"}
        rel = [_rel(vault, p) for p in written]
        outcome = commit_paths(vault.root, rel, message + "\n\n" + "\n".join(lines))
    except SyncError as exc:
        return {"committed": False, "message": message, "error": str(exc)}
    return {"committed": outcome.ok, "message": message,
            "error": None if outcome.ok else f"git {outcome.step} failed: {outcome.error}"}
