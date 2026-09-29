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

The registry ships EMPTY with the framework (#190 part A). The first entries —
the ``.claudron-vault`` identity file and the F9 ignore patterns — land with the
changes that require them (#183, #182), and with them the storage for the
vault's own format number; until then every vault reads as format 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .knowledge import index_divergence
from .locking import vault_write_lock
from .schema import Finding, validate_path
from .structure import StructureError, check_structure, fix_structure, is_fixable
from .vault import Vault, is_within_root

#: The vault format this engine writes. A vault whose recorded format is lower
#: has migrations pending. Bumped only by the PR that registers the migration
#: bringing vaults to the new number.
VAULT_FORMAT = 0

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


#: The registry, in application order. EMPTY until #183/#182 (see module doc).
MIGRATIONS: tuple[Migration, ...] = ()


def vault_format(vault: Vault) -> int:
    """The format version a vault records. No vault records one yet — the
    identity file that will carry it is #183's — so every vault is format 0."""
    return 0


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
    report.pending = pending_migrations(vault, migrations)
    for m in report.pending:
        report.findings.append(_finding(
            "D001", "error",
            f"migration {m.id} pending (format {m.version}): {m.title} "
            "— run: claudron doctor --fix"))

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
    if report.git is not None and report.git.get("state") not in _GIT_FINE:
        state = report.git.get("state")
        detail = report.git.get("detail") or ""
        report.findings.append(_finding(
            "D004", "warning",
            f"git health: {state}" + (f" — {detail}" if detail else "")
            + " (see: claudron sync --check)"))
    return report


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
