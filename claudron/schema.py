"""Note schema: vocabularies, parsing, and validation.

The executable half of SCHEMA.md (repo root) — the ratified SSOT. The
STATUS_VOCAB and CATALOG constants here are bound to SCHEMA.md's
`doc-parity` tables by tests/test_schema.py::TestDocParity; change them
together.

This is the package's base module: it imports nothing from claudron so
vault.py / knowledge.py / cli.py can all build on it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

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

# Structural files that are never notes (skipped by walks AND validation).
# CLAUDE.md is a Claude Code dir-guidance file (e.g. projects/CLAUDE.md) — never
# a note. CONVENTIONS.md is deliberately not here: walks skip it (vault._SKIP_NAMES
# adds it) but validation budget-checks it.
NON_NOTE_FILES = frozenset({"INDEX.md", "README.md", "CLAUDE.md"})

# Where each type files inside a shared tier (SCHEMA.md §taxonomy; matches
# clauDNA publish's disk routing — audit/review share planning/active).
TYPE_DIRS = {
    "knowledge": "knowledge",
    "decision": "decisions",
    "runbook": "runbooks",
    "plan": "planning/active",
    "audit": "planning/active",
    "review": "planning/active",
}


def slugify(title: str) -> str:
    """Kebab-case filename stem per SCHEMA.md's slug convention."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"

# Two sets, deliberately not one (SCHEMA.md: "Terminal ≠ hidden"): a
# ratified decision is exempt from staleness but must stay searchable.
# Derived from the per-type terminal tuples (doc-parity-bound), so adding a
# terminal status to a type cannot silently miss the staleness set.
STALENESS_DONE = frozenset(s for v in STATUS_VOCAB.values() for s in v["terminal"])
LOOKUP_EXCLUDED = STALENESS_DONE - {"ratified"}

# Statuses whose notes no longer attract write-time dedup: their topic moved
# on and a fresh note is the successor. Deliberately the LOOKUP set, not
# STALENESS_DONE — a *ratified* decision is authoritative and searchable, so
# a same-title capture must suggest updating it, never silently twin it.
DEDUP_EXEMPT = LOOKUP_EXCLUDED

# The trust axis (SCHEMA.md §The two axes; D11). Agent write paths stamp the
# first rung; E5's promote walks the rest.
MATURITY_VALUES = ("draft", "verified", "canonical")

# `source_type`'s vocabulary (SCHEMA.md §Frontmatter fields, optional). Held
# here so the CLI door can refuse a value the schema doesn't define — on both
# spellings, the flag and the --stdin key; a parity test reads the doc row
# rather than trusting this copy. Not a validation code: the 0.x error catalog
# is closed, so `validate` still treats an out-of-vocabulary value already on
# disk as preserved-and-ignored, exactly like any unknown field.
SOURCE_TYPES = ("url", "file", "inline")


def ladder_index(maturity: str) -> int:
    """Position on the trust ladder: draft(0) < verified(1) < canonical(2);
    unrated is below all (-1). The single home of the maturity ordinal — E5's
    promote reads it for direction (higher = a promotion), and lookup's sort
    negates it (``-ladder_index`` puts canonical first, unrated last)."""
    return MATURITY_VALUES.index(maturity) if maturity in MATURITY_VALUES else -1


def _as_str_list(value) -> list[str]:
    """Coerce a frontmatter scalar-or-list to a list of strings — the one
    home of the `tags:` / `aliases:` shape tolerance. A YAML scalar (`tags:
    foo`, or a stray non-string like `tags: 5`) is one value: without the
    coercion a consumer iterating the field walks a string's characters
    (scoring saw `tags: foo` as ['f','o','o']) or crashes on a non-iterable.
    Falsy → []."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def claimed_names(mapping: dict) -> list[str]:
    """Lowercased title + aliases a note claims — the name set wikilink
    resolution and dedup both key on. One home (used by write-time dedup
    and validate's W104 collision check)."""
    names = [mapping.get("title")] + list(mapping.get("aliases") or [])
    return [str(n).lower() for n in names if n]


def content_fingerprint(body: str) -> str:
    """A title-independent hash of a note's CONTENT, so byte-identical
    bodies collide for dedup even under a different (or mangled) title.

    Drops a leading H1 (``compose_note`` prepends ``# <title>``) and
    normalizes trailing whitespace, so the fingerprint keys on the content
    a human wrote — not the title heading or incidental spacing. Returns
    ``""`` for empty/whitespace-only content: too thin to dedup on (stub
    notes share an empty body), so callers skip content-matching then.
    """
    lines = body.strip().splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    normalized = "\n".join(line.rstrip() for line in lines).strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def set_frontmatter_field(text: str, field: str, value: str) -> str:
    """Line-level frontmatter upsert: replace *field*'s line if present,
    else insert after ``created:``, else before the closing fence. Never
    re-serializes YAML — the note's own formatting is preserved. The single
    write-side fm-surgery primitive (adopt-backfill and addendum both use
    it)."""
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    replace_at = insert_at = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            if insert_at is None:
                insert_at = i
            break
        key = line.split(":", 1)[0].strip()
        if key == field:
            replace_at = i
            break
        if key == "created":
            insert_at = i + 1
    if replace_at is not None:
        lines[replace_at] = f"{field}: {value}\n"
    elif insert_at is not None:
        lines.insert(insert_at, f"{field}: {value}\n")
    else:
        return text
    return "".join(lines)

REQUIRED_ALWAYS = ("title", "type", "created")
DATE_FIELDS = ("created", "updated", "expires", "last_verified")

# CONVENTIONS.md body budget (whitespace-token proxy; SCHEMA.md §taxonomy).
CONVENTIONS_BUDGET = 120
CONVENTIONS_BUDGET_HARD = 160

# The shipped default for the always-loaded layer — lives beside the budget
# it must satisfy (guarded by test). `init` writes it; the reference vault
# carries a filled-in twin (adds the standing-facts example bullet) — keep
# the shared bullets in sync when editing either.
CONVENTIONS_TEMPLATE = """\
# Vault conventions

- One file per topic; update or supersede, never duplicate.
- Wikilink related notes at write time: `[[Title]]`.
- Agent captures enter as `maturity: draft`; humans promote.
- Stale? Set `superseded_by` and `status: superseded` — never delete.
"""


# Dropped into projects/ at scaffold time; Claude Code reads it up the directory
# tree, so it governs every projects/<repo>/ beneath it. The vault-vs-repo-plane
# boundary is normative in VAULT-STRUCTURE.md §projects/<repo>/.
PROJECTS_CLAUDE_TEMPLATE = """\
# projects/<repo>/ — the operator's outside view of a repo

Each `projects/<repo>/` holds what the vault (operator + fleet) knows about a
codebase that does **not** belong in that repo's own `documentation/`.

- **Belongs here:** operational gotchas, cross-repo workflow, how the repo fits
  the wider operation, durable residue promoted from audits/reviews.
- **Not here:** the repo's own architecture, ADRs, specs, design decisions —
  those live in `<repo>/documentation/`, versioned with the code.

Two tests before filing a note:

- Still true if this repo didn't exist? → `_shared/` instead.
- The repo speaking about itself? → the repo's own `documentation/` instead.

Standard note taxonomy + frontmatter apply (`knowledge/`, `decisions/`, … —
see `SCHEMA.md`).
"""


_MARKER_OPEN_RE = re.compile(r"^<{7}(?: |$)", re.MULTILINE)
_MARKER_CLOSE_RE = re.compile(r"^>{7}(?: |$)", re.MULTILINE)


def has_conflict_markers(text: str) -> bool:
    """True when *text* carries unresolved git conflict markers.

    Line-anchored AND both fence sides required — prose *about* markers
    (a backticked `<<<<<<< HEAD` mid-line, or a lone mention) does not
    trip it. Marker-bearing notes are quarantined: excluded from index,
    lookup, and recall until a human resolves them (E2 sync contract).
    """
    return bool(_MARKER_OPEN_RE.search(text) and _MARKER_CLOSE_RE.search(text))


def count_tokens(text: str) -> int:
    """The whitespace-token proxy every budget uses (W105's conventions
    budget here; the session brief budget in session.py). One home, so the
    proxies can't diverge."""
    return len(text.split())

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


def split_fence(text: str) -> tuple[str | None, str, bool]:
    """Split raw text at the ``---`` frontmatter fences.

    Returns (raw_yaml_or_None, body, fence_opened). The single home of the
    fence protocol — both the lenient walk parser (vault.parse_frontmatter)
    and the error-reporting validation parser (parse_note) build on it.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, text, False
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            raw = "".join(lines[1:i])
            body = "".join(lines[i + 1 :]).lstrip("\n")
            return raw, body, True
    return None, text, True  # fence opened, never closed


def parse_note(text: str) -> tuple[dict | None, str, str | None]:
    """Split a note into (frontmatter, body, parse_error).

    Unlike vault-walk parsing (which tolerates anything), validation must
    distinguish "no frontmatter" (fm={}) from "broken frontmatter"
    (fm=None, parse_error set) — E004 is unemittable otherwise.
    """
    raw, body, opened = split_fence(text)
    if raw is None:
        if opened:
            return None, text, "frontmatter fence opened but never closed"
        return {}, text, None
    try:
        fm = yaml.load(raw, Loader=_SchemaLoader)
    except yaml.YAMLError as exc:
        return None, text, f"YAML parse error: {exc}"
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        return None, text, "frontmatter is not a YAML mapping"
    return fm, body, None


# ── per-note validation ───────────────────────────────────────────────


def _resolve_code(code: str, strict: bool) -> tuple[str, str] | None:
    """Resolve a catalog code for the active validation tier (strict/lenient).

    Returns (emitted_code, severity) or None when the code is n/a in this
    tier. A "→ X" deferral emits code X with X's severity — deferrals only
    ever target a terminal code (one hop), so a single re-lookup suffices.
    """
    key = "strict" if strict else "lenient"
    behavior = CATALOG[code][key]
    if behavior and behavior.startswith("→ "):
        code = behavior[2:]
        behavior = CATALOG[code][key]
    return (code, behavior) if behavior else None


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

    # One frontmatter scan up front (fields → line numbers); emit() then
    # does O(1) lookups instead of re-splitting the note per finding.
    line_of: dict[str, int] = {}
    if raw:
        for i, line in enumerate(raw.splitlines()[:200], start=1):
            if line.rstrip() == "---" and i > 1:
                break
            key = line.split(":", 1)[0].strip()
            if ":" in line and key and key not in line_of:
                line_of[key] = i

    def emit(code: str, message: str, field: str | None = None) -> None:
        resolved = _resolve_code(code, strict)
        if resolved is None:
            return
        emitted, severity = resolved
        findings.append(
            Finding(
                code=emitted,
                severity=severity,
                path=path,
                field=field,
                line=line_of.get(field) if field else None,
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
    count = count_tokens(body)
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
        for name in claimed_names(fm):
            claims.setdefault(name, []).append(path)
    return [
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
        for name, paths in sorted(
            (n, p) for n, p in claims.items() if len(p) > 1
        )
    ]


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

    def one(p: Path) -> tuple[list[Finding], dict | None]:
        """Per-file dispatch: conventions budget vs note validation."""
        text = p.read_text()
        if has_conflict_markers(text):
            # Name the actual condition — a frontmatter conflict would
            # otherwise misdiagnose as generic E004 and a body-only
            # conflict would validate CLEAN while being quarantined from
            # search everywhere else.
            return [
                Finding(
                    code="E004",
                    severity="error",
                    path=rel(p),
                    field=None,
                    line=None,
                    message=(
                        "unresolved git conflict markers — the note is "
                        "quarantined from search until resolved"
                    ),
                )
            ], None
        if is_conventions(p):
            fm, body, _ = parse_note(text)
            return check_conventions(body if fm is not None else text, path=rel(p)), None
        fm, body, err = parse_note(text)
        return (
            validate_note(
                fm, body, strict=strict, path=rel(p), raw=text, parse_error=err
            ),
            fm,
        )

    if target.is_file():
        return one(target)[0]

    findings: list[Finding] = []
    parsed: list[tuple[str, dict]] = []
    for md in sorted(target.rglob("*.md")):
        if md.name in NON_NOTE_FILES:
            continue
        file_findings, fm = one(md)
        findings.extend(file_findings)
        if fm:
            parsed.append((rel(md), fm))
    findings.extend(check_collisions(parsed))
    return findings
