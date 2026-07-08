"""Note schema: vocabularies, parsing, and validation.

The executable half of SCHEMA.md (repo root) — the ratified SSOT. The
STATUS_VOCAB and CATALOG constants here are bound to SCHEMA.md's
`doc-parity` tables by tests/test_schema.py::TestDocParity; change them
together.

This is the package's base module: it imports nothing from claudron so
vault.py / knowledge.py / cli.py can all build on it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

SCHEMA_VERSION = 1


class _SchemaLoader(yaml.SafeLoader):
    """SafeLoader whose timestamp constructor never raises.

    PyYAML implicitly resolves date-shaped scalars and its constructor
    raises a bare ValueError on near-dates like 2026-13-45 — which would
    crash parsing. SCHEMA.md's contract is that near-dates surface as
    E005/W107 findings, so construction failures fall back to the raw
    string and date validation catches them downstream.
    """


def _lenient_timestamp(loader, node):
    try:
        return yaml.SafeLoader.construct_yaml_timestamp(loader, node)
    except (ValueError, OverflowError):
        return loader.construct_scalar(node)


_SchemaLoader.add_constructor("tag:yaml.org,2002:timestamp", _lenient_timestamp)

TYPES = ("knowledge", "decision", "runbook", "plan", "audit", "review")

# Per-type status vocabulary (SCHEMA.md §Status vocabulary).
# canonical: what writers emit. terminal: activity-done values (drives
# staleness; NOT lookup exclusion — see the two sets below). legacy:
# accepted aliases -> the suggestion validate offers (W102).
STATUS_VOCAB: dict[str, dict] = {
    "knowledge": {
        "canonical": ("current", "stale", "superseded", "archived"),
        "terminal": ("superseded", "archived"),
        "legacy": {"active": "current", "draft": "use maturity: draft"},
        "default": "current",
    },
    "decision": {
        "canonical": ("draft", "ratified", "superseded", "archived"),
        "terminal": ("ratified", "superseded", "archived"),
        "legacy": {},
        "default": "draft",
    },
    "runbook": {
        "canonical": ("current", "stale", "superseded", "archived"),
        "terminal": ("superseded", "archived"),
        "legacy": {"active": "current", "draft": "use maturity: draft"},
        "default": "current",
    },
    "plan": {
        "canonical": ("draft", "active", "completed", "superseded", "archived"),
        "terminal": ("completed", "superseded", "archived"),
        "legacy": {},
        "default": "draft",
    },
    "audit": {
        "canonical": ("draft", "completed", "archived"),
        "terminal": ("completed", "archived"),
        "legacy": {},
        "default": "draft",
    },
    "review": {
        "canonical": ("draft", "completed", "archived"),
        "terminal": ("completed", "archived"),
        "legacy": {},
        "default": "draft",
    },
}

MATURITY_VALUES = ("draft", "verified", "canonical")

# Two sets, deliberately not one (SCHEMA.md: "Terminal ≠ hidden"): a
# ratified decision is exempt from staleness but must stay searchable.
STALENESS_DONE = frozenset({"completed", "superseded", "archived", "ratified"})
LOOKUP_EXCLUDED = frozenset({"completed", "superseded", "archived"})

REQUIRED_ALWAYS = ("title", "type", "created")
DATE_FIELDS = ("created", "updated", "expires", "last_verified")

# CONVENTIONS.md body budget (whitespace-token proxy; SCHEMA.md §taxonomy).
CONVENTIONS_BUDGET = 120
CONVENTIONS_BUDGET_HARD = 160

# Frontmatter keys that mark a note as skill-shaped (W103) — SKILL.md
# artifacts, not referential markers. Deliberately narrow: imperative
# bodies alone never trigger (runbooks are supposed to contain those).
_SKILL_MARKER_KEYS = frozenset({"allowed-tools", "argument-hint", "user-invocable"})
_SKILL_HEADING_RE = re.compile(r"^#+\s*(usage|invocation)\b", re.IGNORECASE | re.MULTILINE)

# Closed catalog for the 0.x line (SCHEMA.md §Error catalog). Tier values:
# "error" / "warning" / None (n/a) / "→ Wnnn"|"→ Ennn" (emitted as that
# code in the other tier). Conditions live in SCHEMA.md; parity is checked
# on codes + tier behavior, not prose.
CATALOG: dict[str, dict[str, str | None]] = {
    "E001": {"lenient": "error", "strict": "error"},
    "E002": {"lenient": "error", "strict": "error"},
    "E003": {"lenient": "→ W106", "strict": "error"},
    "E004": {"lenient": "error", "strict": "error"},
    "E005": {"lenient": "→ W107", "strict": "error"},
    "E006": {"lenient": "→ W102", "strict": "error"},
    "E007": {"lenient": None, "strict": "error"},
    "W101": {"lenient": "warning", "strict": "error"},
    "W102": {"lenient": "warning", "strict": "error"},
    "W103": {"lenient": "warning", "strict": "warning"},
    "W104": {"lenient": "warning", "strict": "warning"},
    "W105": {"lenient": "warning", "strict": "warning"},
    "W106": {"lenient": "warning", "strict": None},
    "W107": {"lenient": "warning", "strict": None},
}


@dataclass
class Finding:
    """One validation finding — the stable machine carrier of the catalog.

    Serialized verbatim into the --json envelope's errors/warnings arrays
    (docs/CLI_CONTRACT.md); fields are API, additions only.
    """

    code: str
    severity: str  # "error" | "warning"
    path: str
    field: str | None
    line: int | None
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── parsing ───────────────────────────────────────────────────────────


def parse_note(text: str) -> tuple[dict | None, str, str | None]:
    """Split a note into (frontmatter, body, parse_error).

    Unlike vault-walk parsing (which tolerates anything), validation must
    distinguish "no frontmatter" (fm={}) from "broken frontmatter"
    (fm=None, parse_error set) — E004 is unemittable otherwise.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text, None
    lines = text.splitlines(keepends=True)
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            end = i
            break
    if end is None:
        return None, text, "frontmatter fence opened but never closed"
    try:
        fm = yaml.load("".join(lines[1:end]), Loader=_SchemaLoader)
    except yaml.YAMLError as exc:
        return None, text, f"YAML parse error: {exc}"
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        return None, text, "frontmatter is not a YAML mapping"
    body = "".join(lines[end + 1 :]).lstrip("\n")
    return fm, body, None


def field_line(text: str, field: str) -> int | None:
    """1-indexed line of a top-level frontmatter field, for Finding.line."""
    for i, line in enumerate(text.splitlines()[:200], start=1):
        if line.rstrip("\r\n") == "---" and i > 1:
            return None
        if re.match(rf"^{re.escape(field)}\s*:", line):
            return i
    return None


# ── per-note validation ───────────────────────────────────────────────


def _tier(code: str, strict: bool) -> tuple[str, str] | None:
    """Resolve a catalog code for the active tier.

    Returns (emitted_code, severity) or None when the code is n/a in this
    tier. A "→ X" deferral emits code X with X's severity in that tier.
    """
    behavior = CATALOG[code]["strict" if strict else "lenient"]
    if behavior is None:
        return None
    if behavior.startswith("→ "):
        target = behavior[2:]
        return _tier(target, strict)
    return code, behavior


def _check_date(value) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def validate_note(
    fm: dict | None,
    body: str,
    *,
    strict: bool,
    path: str = "",
    raw: str = "",
    parse_error: str | None = None,
) -> list[Finding]:
    """Validate one note against SCHEMA.md. Pure function, never mutates.

    The shared-engine seam: CLI validate, E2 capture, and E3 MCP write all
    call this. `raw` (original text) enables line numbers; optional.
    """
    findings: list[Finding] = []

    def emit(code: str, message: str, field: str | None = None) -> None:
        resolved = _tier(code, strict)
        if resolved is None:
            return
        emitted, severity = resolved
        findings.append(
            Finding(
                code=emitted,
                severity=severity,
                path=path,
                field=field,
                line=field_line(raw, field) if (raw and field) else None,
                message=message,
            )
        )

    if parse_error is not None or fm is None:
        emit("E004", f"unparseable YAML frontmatter: {parse_error or 'unknown error'}")
        return findings

    for req in REQUIRED_ALWAYS:
        if not fm.get(req):
            emit("E001", f"missing required field '{req}'", field=req)
    if strict and not fm.get("status"):
        emit("E001", "missing required field 'status'", field="status")

    note_type = fm.get("type")
    if note_type and note_type not in TYPES:
        emit(
            "E002",
            f"unknown type '{note_type}' (valid: {', '.join(TYPES)})",
            field="type",
        )
        note_type = None  # type-dependent checks can't run

    status = fm.get("status")
    if note_type and status:
        vocab = STATUS_VOCAB[note_type]
        if status in vocab["legacy"]:
            suggestion = vocab["legacy"][status]
            if status == "draft":
                # Trust-draftness on the wrong axis (E006 strict / W102 lenient)
                emit(
                    "E006",
                    f"status 'draft' on type '{note_type}' puts trust-draftness "
                    f"on the activity axis — {suggestion}",
                    field="status",
                )
            else:
                emit(
                    "W102",
                    f"legacy status '{status}' on type '{note_type}' — "
                    f"canonical value is '{suggestion}'",
                    field="status",
                )
        elif status not in vocab["canonical"]:
            legacy_clause = (
                f"; accepted legacy: {', '.join(vocab['legacy'])}"
                if vocab["legacy"]
                else ""
            )
            emit(
                "E003",
                f"status '{status}' is not valid for type '{note_type}' "
                f"(canonical: {', '.join(vocab['canonical'])}{legacy_clause})",
                field="status",
            )

    for field in DATE_FIELDS:
        value = fm.get(field)
        if value is not None and not _check_date(value):
            emit(
                "E005",
                f"malformed date in '{field}': {value!r} (expected ISO YYYY-MM-DD)",
                field=field,
            )

    if not fm.get("updated"):
        emit("W101", "missing 'updated' (init --adopt backfills from mtime)", field="updated")

    if strict and not fm.get("owner"):
        emit("E007", "missing 'owner' (required on the authoring/engine tier)", field="owner")

    if note_type in ("knowledge", "runbook"):
        marker = _SKILL_MARKER_KEYS.intersection(fm)
        heading = _SKILL_HEADING_RE.search(body or "")
        if marker or heading:
            why = (
                f"frontmatter key(s) {', '.join(sorted(marker))}"
                if marker
                else f"body heading {heading.group(0)!r}"
            )
            emit(
                "W103",
                f"skill-shaped note ({why}) — procedural content belongs in "
                "clauDNA, not the vault (SCHEMA.md §Note types)",
            )

    return findings


# ── vault-scope checks ────────────────────────────────────────────────


def check_conventions(body: str, *, path: str = "") -> list[Finding]:
    """W105: CONVENTIONS.md body budget (whitespace-token proxy)."""
    count = len(body.split())
    if count > CONVENTIONS_BUDGET_HARD:
        return [
            Finding(
                code="W105",
                severity="warning",
                path=path,
                field=None,
                line=None,
                message=(
                    f"CONVENTIONS.md body is ~{count} tokens — budget is "
                    f"{CONVENTIONS_BUDGET} (hard ceiling {CONVENTIONS_BUDGET_HARD}); "
                    "it is injected into every session brief"
                ),
            )
        ]
    return []


def check_collisions(notes: list[tuple[str, dict]]) -> list[Finding]:
    """W104: duplicate titles / alias collisions across a note set.

    *notes* is [(path, frontmatter)]. One finding per colliding name,
    listing every claimant.
    """
    claims: dict[str, list[str]] = {}
    for path, fm in notes:
        names = [fm.get("title")] + list(fm.get("aliases") or [])
        for name in names:
            if name:
                claims.setdefault(str(name).lower(), []).append(path)
    findings = []
    for name, paths in sorted(claims.items()):
        if len(paths) > 1:
            findings.append(
                Finding(
                    code="W104",
                    severity="warning",
                    path=paths[0],
                    field="title",
                    line=None,
                    message=(
                        f"'{name}' is claimed by {len(paths)} notes "
                        f"({', '.join(sorted(paths))}) — wikilink resolution is ambiguous"
                    ),
                )
            )
    return findings


def validate_path(target: Path, *, strict: bool, vault_root: Path | None = None) -> list[Finding]:
    """Validate a file or directory tree (docs/CLI_CONTRACT.md trichotomy).

    Cross-note checks (W104) and the CONVENTIONS budget run for directory
    scope; a single file gets per-note checks only (plus W105 when the file
    itself is a shared-root CONVENTIONS.md).
    """
    base = vault_root or (target if target.is_dir() else target.parent)

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(base))
        except ValueError:
            return str(p)

    def is_conventions(p: Path) -> bool:
        return p.name == "CONVENTIONS.md" and p.parent.name in ("_shared", "shared")

    findings: list[Finding] = []
    if target.is_file():
        text = target.read_text()
        if is_conventions(target):
            fm, body, _ = parse_note(text)
            return check_conventions(body if fm is not None else text, path=rel(target))
        fm, body, err = parse_note(text)
        return validate_note(
            fm, body, strict=strict, path=rel(target), raw=text, parse_error=err
        )

    parsed: list[tuple[str, dict]] = []
    for md in sorted(target.rglob("*.md")):
        if md.name in ("INDEX.md", "README.md"):
            continue
        text = md.read_text()
        if is_conventions(md):
            fm, body, _ = parse_note(text)
            findings.extend(
                check_conventions(body if fm is not None else text, path=rel(md))
            )
            continue
        fm, body, err = parse_note(text)
        findings.extend(
            validate_note(fm, body, strict=strict, path=rel(md), raw=text, parse_error=err)
        )
        if fm:
            parsed.append((rel(md), fm))
    findings.extend(check_collisions(parsed))
    return findings
