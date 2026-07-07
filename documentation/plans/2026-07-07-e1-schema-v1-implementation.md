---
title: "E1 implementation plan — Note Schema v1 + authoring tooling"
type: plan
status: active
owner: chris
tags: [e1, schema, implementation, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E1 implementation plan — Note Schema v1 + authoring tooling

**Implements:** [EPIC #14](https://github.com/Claudfather/Claudron/issues/14)
child [#15](https://github.com/Claudfather/Claudron/issues/15), per
[`documentation/plans/2026-07-07-claudron-roadmap/01-schema.md`](2026-07-07-claudron-roadmap/01-schema.md).
This doc makes the design decisions the epic plan deferred; where it decides,
it cites the constraint that forced the choice. Effort M · 4 PRs + sibling PRs.

## The schema, decided

### Note types and per-type fields

Six types. Universal required: `title` (string), `type` (enum), `status`
(per-type enum below), `created` (ISO date). Universal recommended: `updated`,
`tags` (list), `owner` (**required when written by an agent** — the write
paths enforce this; humans may omit). Universal optional: `aliases`,
`maturity`, `confidence`, `expires`, `source_url`, `source_type`, `slug`,
`last_verified`, `supersedes`, `superseded_by`, `schema_version`,
`promoted_by`, `promoted_at`, `links`, `repos`.

| type | `status` enum (activity axis) | Type-specific notes |
|---|---|---|
| `knowledge` | `current \| stale \| superseded \| archived` | claudlobby's exact knowledge enum, adopted verbatim; `active` accepted ≈ `current` |
| `decision` | `draft \| ratified \| superseded \| archived` | `draft` here is claudlobby's pre-ratification state (activity, not trust) — the one place `draft` is a *native* status value |
| `runbook` | `current \| stale \| superseded \| archived` | mirrors knowledge |
| `plan` | `draft \| active \| completed \| superseded \| archived` | claudlobby's plan enum + terminal values |
| `audit` | `draft \| completed \| archived` | claudlobby/clauDNA audit shape |
| `review` | `draft \| completed \| archived` | same |

**Equivalence mapping (normative, used by `validate` in lenient mode and by
the sibling-alignment docs):** `current ≈ active` (knowledge/runbook),
`stale` ⇒ valid + auto-enters the E5 review queue, `ratified` ⇒ terminal-lock
for decisions (treated like `completed` for staleness), legacy `status: draft`
on non-decision/plan/audit/review types ⇒ warn + suggest `maturity: draft`.

**Terminal statuses:** extend the existing `TERMINAL_STATUSES` frozenset
(`vault.py:27`) to `{completed, superseded, archived, ratified}` — one
constant, reused everywhere (closed #8's rule; do not reintroduce literals).

### The trust axis

`maturity: draft | verified | canonical` — optional; **write paths stamp
`draft` on agent-written notes**; absent means "unrated" (human notes are not
presumed trustworthy or untrustworthy — ranking treats absent as neutral,
between draft and verified). Cycle-2 C2-7 rule restated as implementation:
`validate --strict` (the tier applied to `new`- and engine-written notes)
**errors** on `status: draft` for `knowledge`/`runbook` types — draftness of
trust lives on `maturity` only.

### Wikilink grammar (normative for E4's resolver)

`[[Target]]` and `[[Target|label]]`. Resolution order: exact `title`
(case-insensitive) → exact alias (ci) → slug (ci, where slug = kebab-cased
filename stem). Ambiguity (two notes share a title across tiers) resolves to
the higher-priority tier (project > fleet > shared > pack) and `validate`
warns on the collision. Unresolved links are **valid** — they mark wanted
notes. Escapes: literal `[[` inside code fences/inline code is ignored.

### Directory taxonomy + the #4 reversal, implemented

`SHARED_SUBDIRS` becomes `("knowledge", "decisions", "runbooks", "planning")`
with **nested scaffolding** `planning/{active,completed}` created by `init`
and `fleet add` from one shared constant (`SCAFFOLD_TREE`), killing the
hardcoded triples in `cli.py:102-104` and `cli.py:309-316`. Tier labels:
`shared/planning` (status/index reports don't split active/completed — the
`status` frontmatter field carries that). Issue #4 gets the closing comment
recording the deliberate reversal (vault-level planning docs are now
searchable, matching claudlobby/clauDNA behavior).

### Referential-only boundary (M13), implemented

SCHEMA.md carries the boundary section (procedural → clauDNA). `validate`
heuristic (warning, never error): a note is *skill-shaped* if its frontmatter
contains any of `allowed-tools`, `argument-hint`, `user-invocable`, or its
body's first heading matches `^#+\s*(usage|invocation)` AND `type` ∈
{knowledge, runbook}. Deliberately narrow — runbooks legitimately contain
imperative steps; only SKILL.md-artifact markers trigger.

### CONVENTIONS.md

`init` scaffolds `_shared/CONVENTIONS.md` from a template: vault-specific
conventions + standing facts, ≤120 tokens of body (the F6 always-loaded
budget). `validate` enforces the budget (error at >160 tokens — 33% grace).
E2's recall injects it unconditionally.

## CLI contract (ships as `docs/CLI_CONTRACT.md`, PR1)

- Exit codes: `0` ok · `1` findings (validate errors, review items) · `2`
  usage error · `3` environment error (no vault, git missing)
- Global flags: `--vault`, `--json`; scoping flags `--project`/`--fleet`
  where meaningful
- `--json` envelope: `{"ok": bool, "command": str, "data": {...},
  "warnings": [...], "errors": [...]}` — one shape, every command
- stdout = payload only; all diagnostics to stderr (recall's stdout is
  injected session context — this rule is load-bearing)
- Command groups for `--help`: vault (init/status/validate/index) · notes
  (new/lookup) · session (recall/capture/sync/hooks — E2) · fleet
  (add/list/plug/unplug/config/migrate) · curation (promote/review — E5) ·
  packs (E6)

## `claudron validate` design

Two tiers (cycle-1 M2):

- **Lenient (default, whole-vault):** pre-existing files produce *warnings*
  for: missing `updated`, unknown-but-nonempty status (outside the union),
  legacy `status: draft` (mapping suggestion), skill-shaped heuristic,
  duplicate titles/alias collisions, CONVENTIONS over-budget. *Errors* only
  for: unparseable YAML, missing `title`/`type`/`created`, unknown `type`.
- **Strict (`--strict`; applied automatically by `new` and by E2/E3 write
  paths):** everything above is an error, plus `owner` required (agent
  writes), `maturity`-not-`status` draftness, ISO date validation.

Error catalog with stable codes (`E001 missing-required-field`,
`E002 unknown-type`, `E003 bad-status-for-type`, `W101 missing-updated`,
`W102 legacy-status-value`, `W103 skill-shaped`, `W104 duplicate-title`,
`W105 conventions-over-budget`, …) — codes are API, documented in SCHEMA.md,
stable across releases.

Implementation home: new module `claudron/schema.py` — pure functions
`validate_note(fm, body, *, strict) -> list[Finding]` and
`validate_vault(vault) -> Report`. `cli.py` wraps; E2's `engine.py` imports
`validate_note` (this is the shared-engine seam named in cycle-1).

## `claudron new` design

`claudron new <type> "<title>" [--project X|--fleet Y] [--tags a,b] [--edit]`
→ slugged filename in the right tier dir, frontmatter populated (`created`/
`updated` today, `schema_version` stamped, `status` = type default:
`current` for knowledge/runbook, `draft` for decision/plan/audit/review),
body seeded with an H1. Output passes `validate --strict` by construction
(the acceptance test literally pipes one into the other).

## Reference vault (`examples/reference-vault/`)

One exemplary note per type + one per interesting edge: an aliased note, a
wikilink pair (incl. one unresolved link), a superseded/superseded_by pair,
a legacy-status claudlobby-style note (validates lenient-clean with W102),
a skill-shaped bad example (fixtures/known-bad/), CONVENTIONS.md at budget.
Doubles as pytest fixture — `conftest.py` gains `reference_vault` copying it
to `tmp_path`; existing synthetic fixtures migrate incrementally (only tests
touched by E1 move now; wholesale migration is not this epic).

## Phased PRs (red-first per cycle-1)

| PR | Contents | Red-first gate |
|---|---|---|
| 1 | `SCHEMA.md` + `docs/CLI_CONTRACT.md` + reference vault + known-bad fixtures + `SCAFFOLD_TREE`/`SHARED_SUBDIRS` change + CONVENTIONS template + #4 closing comment | known-bad fixtures committed with expected error codes *before* validator exists |
| 2 | `claudron/schema.py` + `claudron validate` (both tiers, `--json`, exit codes) | PR1's fixtures are the failing tests |
| 3 | `claudron new` + conftest `reference_vault` fixture + migrate touched tests | `new → validate --strict` round-trip test written first |
| 4 | Sibling PRs: claudlobby `frontmatter-schema.md` SSOT pointer + mapping table; clauDNA `output-guide.md` reconciliation (their schema table points at SCHEMA.md, keeps their body-skeleton contract — we own frontmatter, they own body structure); both PRs link #15 | n/a (docs) |

## Acceptance criteria (from #15, made mechanical)

- `claudron validate examples/reference-vault` → exit 0, zero warnings except
  the deliberate W102 note
- Every file in `fixtures/known-bad/` produces exactly its documented code
- `claudron new knowledge "X" && claudron validate --strict <file>` → exit 0
- A real claudlobby fleet doc (`status: current`, no `updated`) → lenient
  warnings only, never errors
- Both sibling PRs merged; #4 commented; #15 closed by PR4

## Non-goals

Lifecycle *semantics* (E5 — fields reserved only) · index/search changes
(E4) · recall/capture (E2 — but `schema.py`'s API is designed for
`engine.py` to import) · any sibling behavior change (docs-only there).

## Risks

- **Union drift** — a sibling adds a status value post-v1 → the mapping
  table lives in SCHEMA.md with a changelog; sibling PRs add "changes here
  must PR Claudron first" pointers (SSOT discipline).
- **Heuristic false-positives** (W103 on legitimate runbooks) → warning-only,
  narrow markers, fixture-tested against the reference runbook.
- **Scope creep into E2** — `schema.py` stays pure-function; no I/O beyond
  reading the note; anything session-shaped is E2's.

## Context

area: schema/CLI · effort: M · risk: medium (SSOT freeze) · priority: highest
(blocks everything) · release: 0.2.0 with E2
