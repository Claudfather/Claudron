"""Vault directory-structure lens for ``claudron validate``.

The structure sibling of :mod:`claudron.schema`'s frontmatter lens: schema.py
lints note *content*, this lints the vault's *shape* against VAULT-STRUCTURE.md
(P1 of the vault-structure contract). :func:`check_structure` is pure and
read-only; :func:`fix_structure` is the opt-in, creation-only, contained repair
path behind ``validate --fix`` — it never moves or deletes, and never escapes
the vault root.

Findings reuse :class:`claudron.schema.Finding` verbatim (same ``--json``
envelope, same ``error``/``warning`` severity model). Fixability is a property
of the *code* (:data:`_FIXABLE_CODES`), not a per-finding field — so the shared
Finding stays unforked and every frontmatter finding's JSON shape is untouched.
"""

from __future__ import annotations

from pathlib import Path

from .schema import Finding
from .vault import SKIP_DIRS, Vault, _dir_named

# Infra names inside SKIP_DIRS that a human never collides with and must never
# surface in a user-facing message. The user-facing reserved set is the
# *subset* left after excluding them — derived from SKIP_DIRS, never re-listed
# (a second hardcoded list would drift the moment SKIP_DIRS gains a member).
_INFRA_SKIP = frozenset({".git", ".github", ".claudron", "__pycache__"})
USER_RESERVED = SKIP_DIRS - _INFRA_SKIP  # {_shared, shared, projects, _packs}

# Codes that are an error regardless of tier (S2 — a reserved-name collision is
# always malformed). Every other structure code is a warning by default and an
# error under --strict, exactly like a frontmatter warning, so cmd_validate's
# `1 if errors else 0` gates structure findings with no special case. The rule
# is small enough to state directly: a schema.CATALOG-shaped table here would be
# a second severity SSOT bound to nothing (VAULT-STRUCTURE.md has no S-code
# table and no parity test to pin it) — drift waiting to happen.
_ALWAYS_ERROR = frozenset({"S2"})

# Codes ``--fix`` can repair (creation-only). S1 alone: create a fleet's
# missing shared/. S2/S3/S4 describe things --fix must never touch (a reserved
# collision, an unknown dir, a two-hub data hazard) — reported, never mutated.
_FIXABLE_CODES = frozenset({"S1"})


class StructureError(Exception):
    """Raised when ``--fix`` refuses an unsafe repair (escape/symlink)."""


def is_fixable(finding: Finding) -> bool:
    """True if ``validate --fix`` can repair this finding (creation-only)."""
    return finding.code in _FIXABLE_CODES


def _severity(code: str, strict: bool) -> str:
    return "error" if strict or code in _ALWAYS_ERROR else "warning"


def check_structure(vault: Vault, *, strict: bool = False) -> list[Finding]:
    """Audit *vault*'s directory shape against VAULT-STRUCTURE.md.

    Pure and read-only — returns ``[]`` for a conforming vault. Codes:

    - **S1** (warning, fixable) — a fleet dir lacks its ``shared/`` tier.
    - **S2** (error) — a reserved-name top-level dir carries a ``fleet.yaml``.
    - **S3** (warning) — an unrecognized top-level dir (the ``other:`` hatch).
    - **S4** (warning) — both ``_shared/`` and ``shared/`` exist (data hazard).

    Not checked here: the "no vault marker" case (a :class:`Vault` cannot exist
    without one — validate errors upstream), and the SCHEMA↔VAULT-STRUCTURE
    cross-link drift guard (a Claudron *repo* test — those docs never live
    inside a vault, so a per-vault lens would false-positive on every vault).
    """
    findings: list[Finding] = []
    root = vault.root

    def emit(code: str, path: Path, message: str) -> None:
        findings.append(
            Finding(
                code=code,
                severity=_severity(code, strict),
                path=str(path),
                field=None,
                line=None,
                message=message,
            )
        )

    # A child reaching the membership test below is already past the dot-dir
    # skip and the USER_RESERVED continue, so the only non-fleet name that can
    # still be "recognized" is a non-dot infra dir (__pycache__). _INFRA_SKIP
    # names it without re-adding the reserved names that already continued out.
    known = set(vault.fleets) | _INFRA_SKIP
    # Single root walk carries S2 (reserved dir + fleet.yaml) and S3 (unknown
    # dir). S2 raw-walks the root deliberately: vault.fleets pre-filters
    # reserved names out (vault._scan_vault), so this is the audit-time
    # backstop for the vector `fleet add` already guards at write time.
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in USER_RESERVED:
            if (child / "fleet.yaml").is_file():
                emit(
                    "S2",
                    child,
                    f"reserved directory '{child.name}/' contains a fleet.yaml — "
                    "a fleet cannot live under a reserved name; rename it or move "
                    "it to its own top-level directory",
                )
            continue
        if child.name in known:  # a discovered fleet, or a non-dot infra skip-dir
            continue
        emit(
            "S3",
            child,
            f"unrecognized top-level directory '{child.name}/' — not a fleet "
            "(no fleet.yaml) and not a reserved tier; left as-is",
        )

    # S1 — a fleet (has fleet.yaml) with no shared/ knowledge tier.
    for name, fleet_dir in sorted(vault.fleets.items()):
        if not (fleet_dir / "shared").is_dir():
            emit(
                "S1",
                fleet_dir / "shared",
                f"fleet '{name}' has no shared/ directory — its knowledge tier "
                "is missing",
            )

    # S4 — both markers present. _scan_vault prefers _shared/ and the index
    # skips shared/ as a SKIP_DIR, so the non-preferred tree is silently
    # dropped: a data-loss hazard nothing else catches.
    if _dir_named(root, "_shared") and _dir_named(root, "shared"):
        emit(
            "S4",
            root / "shared",
            "both _shared/ and shared/ exist at the vault root — only _shared/ "
            "is read; the shared/ tree is silently ignored. Merge it into "
            "_shared/ and remove it",
        )

    return findings


def _rejects_escape(target: Path, root: Path) -> None:
    """Raise :class:`StructureError` unless *target* is safely inside *root*.

    *root* must already be ``resolve()``d (the sole caller does so once). Two
    independent guards: (1) the fully symlink-resolved *target* must stay
    within *root* (catches a symlink pointing *out*); (2) no existing component
    from *target* up to *root* may itself be a symlink (catches a symlinked
    component even if it happens to resolve inside).
    """
    if not target.resolve().is_relative_to(root):
        raise StructureError(f"refusing to create outside the vault: {target}")
    probe = target
    while probe != root and probe.parent != probe:
        if probe.is_symlink():
            raise StructureError(f"refusing to follow a symlink at: {probe}")
        probe = probe.parent


def fix_structure(vault: Vault, findings: list[Finding]) -> list[str]:
    """Apply creation-only, contained repairs; return one line per action.

    Repairs only fixable findings (S1 → create ``<fleet>/shared/``). Every
    target is contained by :func:`_rejects_escape` (inside root, no symlinked
    component), created with ``exist_ok=True`` so a re-run is a no-op. NEVER
    moves or deletes — a non-fixable finding is left for the operator.
    """
    root = vault.root.resolve()
    actions: list[str] = []
    for finding in findings:
        if not is_fixable(finding):
            continue
        target = Path(finding.path)
        _rejects_escape(target, root)
        target.mkdir(parents=True, exist_ok=True)
        actions.append(f"created {target.resolve().relative_to(root)}/")
    return actions
