# Claudron Note Schema — v1

**Status: ratified with 0.2.0 · SSOT for the Claudfather ecosystem.**
claudlobby's `library/resources/frontmatter-schema.md` and clauDNA's
`skills/_shared/output-guide.md` point here for frontmatter; changes to this
document after 0.2.0 require approval (PROJECT_MISSION.md, "Requires
approval"). Sibling schema changes must PR Claudron first.

A **note** is a markdown file with YAML frontmatter in a Claudron vault.
This document is normative for: note types, frontmatter fields, status and
maturity vocabularies, wikilink resolution, the per-tier note-filing layout
(the vault's directory *shape* and tenancy are `VAULT-STRUCTURE.md`'s),
validation error codes, and the `pack.yaml` v0 reservation. The tables in
§Status vocabulary and §Error catalog are **machine-checked** against
`claudron/schema.py` by a doc-parity test — edits here and there move
together.

## The two axes

Claudron separates *what state a note's content is in* from *how much you
should trust it* (roadmap decision D11):

- **`status`** — the **activity axis**. Per-type vocabulary below. Describes
  the note's lifecycle as a document: is it current, superseded, done?
- **`maturity`** — the **trust axis**. `draft | verified | canonical`,
  uniform across types, optional. Describes curation: bot-written notes
  enter as `draft`; humans promote (`claudron promote`, E5). Absent means
  *unrated* — ranking treats it as neutral, between `draft` and `verified`.

A note can be `maturity: canonical` and `status: superseded` at the same
time: it was the trusted answer, and something newer replaced it. Search
ranks on both axes and follows `superseded_by` to the successor.

The axes never share live vocabulary in newly authored notes: **trust-
draftness is always `maturity: draft`, never `status: draft`** — except for
the four types where `draft` is a *native activity state* (decision, plan,
audit, review: a drafted decision is genuinely pre-ratification activity).
For `knowledge` and `runbook` types, `status: draft` is accepted only as a
legacy alias (W102) and rejected by strict validation (E006).

## Note types

Six types. Procedural content — skills, slash commands, agent-executable
how-tos — is **out of scope by design**: it belongs in clauDNA
(PROJECT_MISSION.md:25, "the schema makes the distinction enforceable").
There is deliberately no `skill` type, and `validate` warns (W103) on
skill-shaped notes. A runbook is referential operational knowledge (*what we
know about operating X*); a skill is an executable procedure (*how an agent
does X*). When in doubt: if an agent is meant to *execute* it, it's clauDNA's.

| type | Purpose |
|---|---|
| `knowledge` | Findings, learnings, gotchas, domain facts |
| `decision` | Architecture/process decisions (ADR-style) |
| `runbook` | Operational reference: how a system behaves, recovery facts |
| `plan` | Work plans, roadmaps, specs |
| `audit` | Point-in-time assessment outputs |
| `review` | Review outputs (code, plan, design) |

### Non-note files

Not every `.md` file in a vault is a note. **Structural files carry no
frontmatter and are skipped by every note walk — index, search, *and*
validation:** `README.md`, `INDEX.md` (navigation), and `CLAUDE.md` (Claude Code
directory guidance, e.g. `projects/CLAUDE.md`). They are never indexed, ranked,
or error-flagged as broken notes. `CONVENTIONS.md` is a near-cousin — skipped by
index/search but *budget-checked* by validation, because it is the always-injected
layer. The skip set is `schema.NON_NOTE_FILES` (plus `CONVENTIONS.md`), closed for
the 0.x line.

## Frontmatter fields

**Universal — required:** `title` (string), `type` (enum above), `status`
(per-type vocabulary below; absent is tolerated in lenient validation and
treated as the type default), `created` (ISO date `YYYY-MM-DD`).

**Universal — required for agent-written notes:** `owner` (the writing
bot/agent identity; provenance). Human authors may omit it. The write paths
(`claudron new`, `capture`) always populate it.

**Universal — recommended:** `updated` (ISO date; `init --adopt` backfills
from file mtime), `tags` (list of strings).

**Optional:**

| Field | Type | Meaning |
|---|---|---|
| `aliases` | list | Alternate titles for search and wikilink resolution |
| `maturity` | `draft \| verified \| canonical` | Trust axis (see above) |
| `confidence` | `stated \| high \| medium \| speculation` | Author's confidence in the content (recommended for agent writes; may become required once the write chokepoint enforces it for free) |
| `expires` | ISO date | Review trigger — **never** a deletion trigger. Past-`expires` notes enter the review queue (E5) |
| `source_url` | string | Provenance / dedup key for ingested content |
| `source_type` | `url \| file \| inline` | How the content arrived |
| `slug` | string | Explicit slug override; defaults to the kebab-case filename stem |
| `last_verified` | ISO date | Last human/agent verification of the content |
| `supersedes` | wikilink | This note replaces that one |
| `superseded_by` | wikilink | The successor; terminal pointer — set it instead of deleting |
| `schema_version` | int | Stamped by write paths at creation (`1`); survives index rebuilds |
| `promoted_by` / `promoted_at` | string / ISO date | Reserved for E5 promotion provenance |
| `links` / `repos` | list | clauDNA house-style carry-overs; indexed, not interpreted |

Unknown fields are preserved and ignored (forward compatibility); `validate`
does not flag them.

## Status vocabulary (per type)

Canonical values are what writers emit. Accepted legacy aliases exist so the
installed base (claudlobby fleets, clauDNA publish output) validates without
edits — they warn (W102) with the mapping suggestion, and write paths never
emit them.

<!-- doc-parity: STATUS_TABLE -->
| type | canonical | terminal | accepted legacy → mapping |
|---|---|---|---|
| knowledge | `current`, `stale`, `superseded`, `archived` | `superseded`, `archived` | `active` → `current`; `draft` → use `maturity: draft` |
| decision | `draft`, `ratified`, `superseded`, `archived` | `ratified`, `superseded`, `archived` | — |
| runbook | `current`, `stale`, `superseded`, `archived` | `superseded`, `archived` | `active` → `current`; `draft` → use `maturity: draft` |
| plan | `draft`, `active`, `completed`, `superseded`, `archived` | `completed`, `superseded`, `archived` | — |
| audit | `draft`, `completed`, `archived` | `completed`, `archived` | — |
| review | `draft`, `completed`, `archived` | `completed`, `archived` | — |

Notes on the vocabulary:

- The knowledge/runbook enums are claudlobby's (`current|stale|superseded`)
  **plus `archived`** — a deliberate superset addition across all types, not
  verbatim adoption.
- `stale` is valid, first-class, and auto-enters the E5 review queue.
- **Terminal ≠ hidden.** Terminal statuses are excluded from default search
  *except `ratified`*: a ratified decision is exempt from staleness checks
  but must always remain searchable — it is the most authoritative note in
  the vault. (Implementation: two constants, `STALENESS_DONE` includes
  `ratified`, `LOOKUP_EXCLUDED` does not.)
- Type default when `status` is absent: `current` for knowledge/runbook,
  `draft` for decision/plan/audit/review.

## Wikilinks

`[[Target]]` or `[[Target|display label]]`. Written by authors at write time
— never inferred by machinery (PROJECT_MISSION.md non-goal: no LLM at index
time).

**Resolution order** (case-insensitive at every step):
1. exact `title` match
2. exact `aliases` entry
3. slug (explicit `slug` field, else kebab-case filename stem)

Ambiguity — two notes resolve for the same target — goes to the
higher-priority tier (`project > fleet > shared > pack`); `validate` warns
(W104) on cross-tier title/alias collisions.

**Unresolved links are valid.** They mark wanted-but-unwritten notes and are
reported by `claudron links`, never errored. Literal `[[` inside code
fences or inline code is not a wikilink.

## Vault directory taxonomy

`VAULT-STRUCTURE.md` is the SSOT for the vault's directory *shape* and tenancy;
this section draws only the note-filing view — where each note *type* lives
within that shape.

```
<vault>/
  _shared/                  # cross-cutting tier ("shared/" also accepted)
    CONVENTIONS.md          # always-loaded conventions + standing facts (≤120 tokens)
    knowledge/
    decisions/
    runbooks/
    planning/
      active/
      completed/
  projects/<repo>/          # per-repo tier
  <fleet>/                  # fleet overlay (marked by fleet.yaml)
    shared/{knowledge,decisions,runbooks,planning/{active,completed}}
  _packs/<name>/            # subscribed packs (E6)
  .claudron/                # derived index
```

`planning/` is walked as one tier (`shared/planning`); the `status` field —
not the subdirectory — is the machine-readable activity state. The
`active`/`completed` split is a human-facing filing convention (adopted from
claudlobby/clauDNA). Vault-level planning became a walked content tier in E1,
deliberately reversing issue #4.

**CONVENTIONS.md** is special: injected unconditionally into session briefs
(E2), so its body is budgeted at **≤120 tokens** (W105 above 160 — 33%
grace). Everything else earns injection through relevance.

**Tenancy, scope, consumption, and promotion** are specified in
`VAULT-STRUCTURE.md`, this section's directory sibling.

## Validation

`claudron validate [PATH]` — no arg: detected vault; directory: that
subtree; file: that note. Never mutates. Two tiers:

- **Lenient** (default): the adoption posture. Pre-existing content warns;
  only structural breakage errors (E001/E002/E004).
- **Strict** (`--strict`; automatic for `claudron new` output and all
  engine/MCP writes): the authoring contract. Everything below marked
  *strict* errors.

Findings are stable structs — the machine carrier of this catalog:

```json
{"code": "E003", "severity": "error", "path": "…", "field": "status",
 "line": 4, "message": "…"}
```

`--json` output is the standard envelope with `errors`/`warnings` arrays of
exactly these objects. Warnings do not affect the exit code (warnings → 0,
errors → 1).

### Error catalog — closed for the 0.x line

Additions are minor-version events recorded in this file's changelog.

<!-- doc-parity: ERROR_CATALOG -->
| Code | Condition | Lenient | Strict |
|---|---|---|---|
| E001 | missing required field (`title`/`type`/`created`; `status`/`owner` strict-only) | error (title/type/created) | error |
| E002 | unknown `type` | error | error |
| E003 | status outside the type's canonical+legacy set | → W106 | error |
| E004 | unparseable YAML frontmatter | error | error |
| E005 | malformed date (`created`/`updated`/`expires`/`last_verified`) | → W107 | error |
| E006 | trust-draftness on `status` for knowledge/runbook | → W102 | error |
| E007 | missing `owner` on agent-written note | n/a | error |
| W101 | missing `updated` | warning | error |
| W102 | accepted legacy status value (mapping suggested) | warning | error |
| W103 | skill-shaped note (referential boundary) | warning | warning |
| W104 | duplicate title / alias collision across tiers | warning | warning |
| W105 | CONVENTIONS.md over token budget | warning | warning |
| W106 | status outside vocabulary (lenient form of E003) | warning | n/a |
| W107 | malformed date (lenient form of E005) | warning | n/a |

Date semantics: YAML already parses valid ISO dates into date objects —
those pass. Strings must satisfy `date.fromisoformat`. Anything else
(including YAML ints and near-dates like `2026-13-45`) is E005/W107; no
input crashes the validator.

The skill-shape heuristic (W103) is deliberately narrow: frontmatter
containing `allowed-tools`, `argument-hint`, or `user-invocable`, or a first
body heading of `Usage`/`Invocation`, on a `knowledge`/`runbook` note.
Imperative steps alone never trigger it — runbooks are supposed to contain
those.

## pack.yaml v0 (reserved)

Packs (E6) are curated vault subsets published as git repos. v0 reserves the
file and four fields; E6 extends to v1 (that extension is the mission's
approval gate for `pack.yaml`):

```yaml
name: claudfather-patterns
version: 0.1.0
description: Curated patterns from the Claudfather fleet
license: MIT
```

## Versioning

`schema_version: 1`. This schema follows the additive rule: v1.x changes may
add types, fields, codes, or legacy aliases; they may not remove or re-type
any of them. Non-additive changes bump the major version and require the
mission approval gate plus a migration note here.

### Changelog

- **v1 (2026-07-07, ships with 0.2.0):** initial ratified schema. Unifies
  Claudron CLAUDE.md, claudlobby `frontmatter-schema.md`, and clauDNA
  `output-guide.md` vocabularies; introduces the `status`/`maturity` axis
  split (D11), the closed error catalog, wikilink resolution rules, the
  `planning/` tier (reverses #4), and the referential-only boundary (M13).

### Open questions (expected to change; not defects)

- Does `confidence` graduate to required-for-agents once E3's chokepoint
  makes enforcement free? (Field evidence F6 is single-source; deliberately
  SHOULD for now.)
- Do per-claim provenance conventions (recency markers, verbatim source
  URLs in bodies) graduate from SHOULD to linted MUST? (Same trigger.)
- Does `maturity` gain a `contested` value if fleet-scale curation surfaces
  genuine disputes? (Graphify's learning overlay suggests it might; wait for
  evidence.)
