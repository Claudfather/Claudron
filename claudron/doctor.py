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

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from .hooks import (SNIPPET_EVENTS, default_settings_path, parse_hook_command, read_settings,
                    settings_snippet)
from .knowledge import index_divergence
from .locking import vault_write_lock
from .schema import Finding, validate_path
from .structure import StructureError, check_structure, fix_structure, is_fixable
from .vault import (IDENTITY_FILE, VAULT_FORMAT, Vault, _ensure_gitignore, detect,
                    identity_text, is_within_root, missing_gitignore_rules)

__all__ = ["CODES", "VAULT_FORMAT", "Migration", "MigrationRefused", "MIGRATIONS",
           "diagnose", "fix", "pending_migrations", "vault_format"]

#: Every D code doctor emits, with the severities each may carry. The contract's
#: doctor table (docs/CLI_CONTRACT.md, doc-parity DOCTOR_CODES) is pinned to it,
#: and `_finding` refuses anything it does not list (#204).
CODES: dict[str, frozenset[str]] = {
    "D001": frozenset({"error"}),
    "D002": frozenset({"error", "warning"}),
    "D003": frozenset({"warning"}),
    "D004": frozenset({"warning"}),
    "D005": frozenset({"error"}),
    "D006": frozenset({"error"}),
    "D007": frozenset({"error", "warning"}),
    "D008": frozenset({"warning"}),
    "D009": frozenset({"warning"}),
    "D010": frozenset({"error", "warning"}),
}

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
    hooks: list[dict] = field(default_factory=list)
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
            "hooks": self.hooks,
            "fixed": self.fixed,
        }
        if self.fixed:
            data.update(applied=self.applied, repairs=self.repairs, commit=self.commit)
        return data


def _finding(code: str, severity: str, message: str, path: str = ".") -> Finding:
    if severity not in CODES.get(code, ()):
        raise ValueError(f"doctor code {code} with severity {severity!r} is not "
                         "registered in CODES (and the contract's doctor table)")
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
             migrations: tuple[Migration, ...] | None = None,
             settings: list[Path] | None = None) -> DoctorReport:
    """Read-only diagnosis against this engine's rules. Never writes.

    *settings* names the Claude Code settings files whose hooks to check
    (D009, D010); None means the file `hooks install --write` writes."""
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

    report.hooks, found = _check_hooks(vault, settings)
    report.findings += found
    return report


def _check_hooks(vault: Vault, settings: list[Path] | None) -> tuple[list[dict], list[Finding]]:
    """The per-host checks (#204, #190's last two rows), read-only.

    D009: each settings file's claudron entries against the current snippet
    shape. D010: whether each entry reaches a vault from where it runs, its
    address resolved by `detect()`, as the hook resolves it. The files are the
    ones declared (`--settings`), or by default the one `hooks install --write`
    writes; doctor never goes looking for others, and never executes anything
    it reads in them."""
    files = ([(Path(p), True) for p in settings] if settings
             else [(default_settings_path(), False)])
    root = str(vault.root.resolve())
    checked: list[dict] = []
    found: list[Finding] = []
    for path, declared in files:
        record = {"path": str(path), "declared": declared, "state": "ok", "entries": []}
        checked.append(record)
        where = str(path)
        if not path.exists():
            record["state"] = "absent"
            if declared:
                found.append(_finding(
                    "D009", "warning",
                    f"settings file {path} not found — nothing to check: pass the file the "
                    "hooks live in, or install them there with claudron --vault "
                    f"{shlex.quote(root)} hooks install --write --settings {shlex.quote(where)}",
                    where))
            continue
        # The installer's own reader (#205): what doctor calls unparseable is
        # exactly what `hooks install --write` refuses, so the remedy is true.
        data, why = read_settings(path)
        if data is None:
            record["state"] = "unreadable"
            found.append(_finding(
                "D009", "warning",
                f"cannot parse {path} ({why}) — its hooks were not checked, and "
                "`hooks install` refuses the file too: repair the file (or re-render it, "
                "if a composer manages it)", where))
            continue
        hint = ("re-install: claudron --vault " + shlex.quote(root) + " hooks install --write"
                + (f" --settings {shlex.quote(where)}, or re-render the file if a composer "
                   "manages it" if declared else ""))
        hooks = data.get("hooks") or {}
        per_event = {}
        for event, cmd in SNIPPET_EVENTS.items():
            groups = hooks.get(event) if isinstance(hooks.get(event), list) else []
            per_event[event] = [
                (g, h) for g in groups if isinstance(g, dict)
                for h in (g.get("hooks") if isinstance(g.get("hooks"), list) else [])
                if isinstance(h, dict)
                and parse_hook_command(str(h.get("command", "")), cmd) is not None]
        if not any(per_event.values()):
            record["state"] = "not-installed"
            if not declared:
                # No claudron entry on any event: this host never ran `hooks
                # install`, like a host with no file, and the re-install remedy
                # would put the loop into the operator's own sessions (#205).
                continue
        for event, cmd in SNIPPET_EVENTS.items():
            ours = per_event[event]
            if not ours:
                found.append(_finding("D009", "warning",
                                      f"{event} has no claudron hook entry, so the loop "
                                      f"skips that step — {hint}", where))
                continue
            if len(ours) > 1:
                found.append(_finding("D009", "warning",
                                      f"{event} has {len(ours)} claudron hook entries, so the "
                                      f"step runs {len(ours)} times — {hint}", where))
            for group, hook in ours:
                command = str(hook["command"])
                parsed = parse_hook_command(command, cmd)
                entry = {"event": event, "command": command, "vault": parsed.vault,
                         "resolves_to": None}
                record["entries"].append(entry)
                if parsed.vault is None:
                    found.append(_finding(
                        "D009", "warning",
                        f"{event}'s claudron hook names no vault (no --vault: installed before "
                        "#183), so it finds one only through CLAUDRON_VAULT_PATH or walk-up "
                        f"from where the session starts — {hint}", where))
                else:
                    expected = settings_snippet(parsed.prefix, parsed.vault)["hooks"][event][0]
                    if group != expected:
                        found.append(_finding(
                            "D009", "warning",
                            f"{event}'s claudron hook differs from the current snippet "
                            f"({_drift(group, hook, expected)}) — {hint}", where))
                found += _resolution(event, command, parsed.vault, root, hint, where, entry)
    return checked, found


def _drift(group: dict, hook: dict, expected: dict) -> str:
    """What differs between an installed hook group and the snippet's."""
    parts: list[str] = []
    want_hook = expected["hooks"][0]
    for have, want, what in ((group, expected, "the group"), (hook, want_hook, "the entry")):
        for key in sorted(set(have) | set(want)):
            if key == "hooks" or (key == "command" and have is hook):
                continue
            if key not in have:
                parts.append(f"{what} has no {key}")
            elif key not in want:
                parts.append(f"{what} has an extra key, {key}")
            elif have[key] != want[key]:
                parts.append(f"{key} is {have[key]!r} where the snippet has {want[key]!r}")
    if hook.get("command") != want_hook["command"]:
        parts.append("the command is not in the snippet's form")
    others = len(group.get("hooks") or []) - 1
    if others > 0:
        # merge_settings replaces every group that holds a claudron entry, so
        # the re-install this finding names deletes them (vera, #205).
        parts.append(f"the group also holds {others} other command(s): re-installing "
                     "replaces the whole group and drops them, so move them to a group of "
                     "their own first")
    return "; ".join(parts) or "the entries are in another order"


def _resolution(event: str, command: str, address: str | None, root: str, hint: str,
                where: str, entry: dict) -> list[Finding]:
    """D010 for one entry: does it reach a vault from where it runs?"""
    out: list[Finding] = []
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    exe = words[0] if words else ""
    if os.path.isabs(exe):
        if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
            out.append(_finding(
                "D010", "error",
                f"{event}'s claudron hook runs {exe}, which does not exist or is not "
                f"executable, so the hook fails before claudron starts — {hint}", where))
    else:
        out.append(_finding(
            "D010", "warning",
            f"{event}'s claudron hook runs a bare `{exe}`, which resolves only if the PATH "
            f"hooks run with carries it (the snippet records an absolute path) — {hint}",
            where))
    if address is None:
        return out
    if not os.path.isabs(address):
        out.append(_finding(
            "D010", "warning",
            f"{event}'s claudron hook records the address {address!r}, which is not "
            "absolute: the engine never expands `~`, and a relative path resolves against "
            f"wherever the session starts — {hint}", where))
        return out
    bound = detect(Path(address))
    if bound is None:
        out.append(_finding(
            "D010", "error",
            f"{event}'s claudron hook addresses {address}, which is not a vault (moved, or "
            f"deleted), so the hook fails open, silently — {hint}", where))
        return out
    bound_root = str(bound.root.resolve())
    entry["resolves_to"] = bound_root
    if bound_root != str(Path(address).resolve()) and bound_root == root:
        out.append(_finding(
            "D010", "warning",
            f"{event}'s claudron hook addresses {address}, inside this vault, not its root: "
            "walk-up from it binds this vault, so the hook works while that path stays "
            f"inside it — {hint}", where))
    elif bound_root != str(Path(address).resolve()):
        out.append(_finding(
            "D010", "error",
            f"{event}'s claudron hook addresses {address}, but walk-up from it binds "
            f"{bound_root}, so the hook syncs that vault instead — {hint}", where))
    elif bound_root != root:
        out.append(_finding(
            "D010", "warning",
            f"{event}'s claudron hook syncs {bound_root}, not this vault ({root}); to give "
            "this vault hooks of its own, install them into another settings file: "
            f"claudron --vault {shlex.quote(root)} hooks install --write --settings <file>",
            where))
    return out


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
        migrations: tuple[Migration, ...] | None = None,
        settings: list[Path] | None = None) -> DoctorReport:
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

    report = diagnose(vault, migrations=migrations, settings=settings)
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
