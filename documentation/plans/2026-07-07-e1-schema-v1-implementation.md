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

Each table row separates **canonical values** (what writers should emit) from
**accepted legacy aliases** (validated with a W102-class warning + mapping
suggestion) — so an agent reading SCHEMA.md never mistakes an alias for
first-class vocabulary (devex fold):

| type | canonical `status` values | accepted legacy aliases | Notes |
|---|---|---|---|
| `knowledge` | `current \| stale \| superseded \| archived` | `active → current`, `draft → maturity: draft` | claudlobby's knowledge enum (`current\|stale\|superseded`) **plus `archived`** — a deliberate superset addition across all six types, not verbatim adoption (engineering correction); the mapping table records it |
| `decision` | `draft \| ratified \| superseded \| archived` | — | `draft` here is claudlobby's pre-ratification state (activity, not trust) — the one place `draft` is a *native* status value |
| `runbook` | `current \| stale \| superseded \| archived` | `active → current`, `draft → maturity: draft` | mirrors knowledge |
| `plan` | `draft \| active \| completed \| superseded \| archived` | — | claudlobby's plan enum + terminal values |
| `audit` | `draft \| completed \| archived` | — | claudlobby/clauDNA audit shape |
| `review` | `draft \| completed \| archived` | — | same |

**Equivalence mapping (normative, used by `validate` in lenient mode and by
the sibling-alignment docs):** `current ≈ active` (knowledge/runbook),
`stale` ⇒ valid + auto-enters the E5 review queue, `ratified` ⇒ terminal-lock
for decisions (treated like `completed` for staleness), legacy `status: draft`
on non-decision/plan/audit/review types ⇒ warn + suggest `maturity: draft`.

**Terminal statuses — two constants, because the two consumers diverge**
(engineering blocker: `TERMINAL_STATUSES` feeds both `_is_stale`
(`vault.py:234`) and `_is_excluded` (`knowledge.py:309`); adding `ratified`
to one shared constant makes ratified decisions *exempt from staleness* —
correct — and *silently hidden from default lookup* — a bug; a ratified
decision is the most authoritative note in the vault):

- `STALENESS_DONE = {completed, superseded, archived, ratified}` — used only
  by `_is_stale`
- `LOOKUP_EXCLUDED = {completed, superseded, archived}` — used only by
  `_is_excluded`; **`ratified` never enters it**
- Both live in `schema.py` as the single source (closed #8's no-literals rule
  still holds — it's one *home*, two *sets*); a red test pins ratified
  visibility: a `status: ratified` decision MUST appear in default `lookup`
  results

Related engine-default note: `knowledge.py` hardcodes `"active"` as the
absent-status fallback in four places (`:41,112,137,309`). E1 does **not**
rewrite those (E4 replaces that module wholesale); `validate` treats absent
`status` as the type default (lenient: no finding; strict: E001), and W102
fires only on *explicit* legacy values — so the engine fallback and the
schema never fight.

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
— the **walk** constant — while scaffolding moves to a new `SCAFFOLD_TREE`
(nested `planning/{active,completed}`). Engineering corrections folded:
`SHARED_SUBDIRS` is dual-use today — `init()` iterates it to *create* dirs
(`vault.py:136`) — so `init` must switch to `SCAFFOLD_TREE` or it creates a
flat `planning/`; `test_fleet.py:22-23` already asserts the nested shape on
the fleet side, so vault `init` is the only laggard; and `cli.py:102-104`
are `print()` *display* lines (not scaffolding) — they get updated for
accuracy, but the load-bearing literal is the `vault.py:136` iteration plus
the fleet-add tree at `cli.py:309-316`. Tier labels:
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

- Exit codes: `0` ok **(warnings do not change the exit code — warnings → 0,
  errors → 1; CI that wants to gate on warnings runs `validate --strict`)** ·
  `1` findings (validate errors, review items) · `2` usage error · `3`
  environment error (no vault, git missing). **Breaking change, called out:**
  no-vault currently exits 2 (`cli.py:36`); it moves to 3 at 0.2.0 —
  CHANGELOG entry required.
- Global flags: `--vault`, `--json`; scoping flags `--project`/`--fleet`
  where meaningful. Argparse mechanics: `--json` and `--vault` live on a
  **shared parent parser** attached to every subcommand (not the top parser
  alone) so `claudron status --json` keeps parsing — the flag-placement
  footgun devex flagged.
- `--json` envelope: `{"ok": bool, "command": str, "data": {...},
  "warnings": [Finding...], "errors": [Finding...]}`. **Each element of
  `errors`/`warnings` IS a serialized `Finding`** (struct below) — the
  top-level arrays are the authoritative finding lists; `data` carries the
  per-command payload (for `validate`: summary counts + per-note breakdown;
  for `new`: `{path}` of the created note — `new` honors `--json` like
  everything else).
- **Envelope migration is in-scope for E1 (PR2):** `status`, `lookup`, and
  `config` currently emit three different ad-hoc `--json` shapes
  (`cli.py:113-114`, `:159-174`, `:270-277`) — 0.2.0 is the first public
  release and therefore the cheapest moment there will ever be to unify
  them. Breaking change, CHANGELOG'd with before/after examples.
- stdout = payload only; all diagnostics to stderr (recall's stdout is
  injected session context — this rule is load-bearing). **Made true, not
  just documented:** PR2 retrofits the existing offenders (`status` human
  report, `lookup`'s "no results", `index` progress lines → stderr where
  they are diagnostics) and adds a **channel-discipline test** parametrized
  over the command table so regressions fail CI.
- `validate [PATH]` trichotomy, stated: no arg → detected vault; directory →
  that subtree; file → that single note.
- One preview line for humans: "run `validate --strict` to see what the
  engine/bot write paths will accept" (the two-tier model gives one note two
  verdicts; say so where users look).
- Command groups for `--help`: vault (init/status/validate/index) · notes
  (new/lookup) · session (recall/capture/sync/hooks — E2) · fleet
  (fleet add/fleet list) · **integration (plug/unplug/config/migrate)** —
  renamed from the draft's "fleet" grouping because `fleet` is a real
  subcommand namespace and "fleet → plug" in help would teach users a
  command that doesn't exist · curation (promote/review — E5) · packs (E6)

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

**Error catalog — closed for the 0.x line** (devex blocker fold: an
open-ended catalog cannot be API). Every condition the design enumerates has
a code; additions are minor-version events recorded in SCHEMA.md's changelog:

| Code | Condition | Tier |
|---|---|---|
| `E001` | missing required field (`title`/`type`/`created`) | both |
| `E002` | unknown `type` | both |
| `E003` | status not in type's canonical-or-alias set | strict (lenient ⇒ W106) |
| `E004` | unparseable YAML frontmatter | both |
| `E005` | malformed date (non-ISO `created`/`updated`/`expires`) | strict (lenient ⇒ W107) |
| `E006` | trust-draftness on `status` for knowledge/runbook (`maturity` owns it) | strict |
| `E007` | missing `owner` on agent-written note | strict |
| `W101` | missing `updated` | lenient |
| `W102` | accepted legacy status value (mapping suggested) | lenient |
| `W103` | skill-shaped note (referential-boundary heuristic) | both |
| `W104` | duplicate title / alias collision across tiers | both |
| `W105` | CONVENTIONS.md over token budget | both |
| `W106` | status outside union (lenient form of E003) | lenient |
| `W107` | malformed date (lenient form of E005) | lenient |

**`Finding` is a stable struct — the machine carrier of the catalog** (devex
blocker): `{code: str, severity: "error"|"warning", path: str, field:
str|null, line: int|null, message: str}`. Each element of the `--json`
envelope's `errors`/`warnings` arrays is exactly a serialized `Finding`; one
known-bad fixture asserts the **full JSON element**, not just the code.

**Doc-parity test** (devex major: the epic exists to end doc-vs-code drift
and must not re-create it internally): a PR2 test parses SCHEMA.md's
equivalence-mapping table and error-catalog table and asserts equality with
`schema.py`'s constants — SCHEMA.md and the enforcing code cannot silently
diverge.

Implementation home: new module `claudron/schema.py` — pure functions
`validate_note(fm, body, *, strict) -> list[Finding]` and
`validate_vault(vault) -> Report`. `cli.py` wraps; E2's `engine.py` imports
`validate_note` (this is the shared-engine seam named in cycle-1).

**Parser seam** (engineering major: `parse_frontmatter` swallows `YAMLError`
into `({}, text)` (`vault.py:265-268`), making "unparseable YAML"
indistinguishable from "no frontmatter" — E004 would be unemittable):
`schema.py` gets `parse_note(text) -> (fm, body, parse_error|None)`, a thin
wrapper that catches and *reports* `YAMLError` instead of swallowing it.
`vault.py`'s lenient `parse_frontmatter` keeps its behavior for
non-validating paths (status walks, indexing) — validation is the only
consumer that must distinguish the two cases.

**Date semantics** (engineering: YAML pre-parses valid ISO dates into `date`
objects, so a string-only ISO check is a partial no-op with a crash edge on
values like `2026-13-45`): E005/W107 accept `date`/`datetime` objects as
already-valid; strings must parse `date.fromisoformat`; everything else —
including YAML's ints or malformed near-dates — is the finding, inside a
`try` so no input crashes the validator.

## `claudron new` design

`claudron new <type> "<title>" [--project X|--fleet Y] [--tags a,b]
[--owner NAME] [--edit] [--force]`
→ slugged filename in the right tier dir, frontmatter populated (`created`/
`updated` today, `schema_version` stamped, `status` = type default:
`current` for knowledge/runbook, `draft` for decision/plan/audit/review,
**`owner` derived: `--owner` flag → `git config user.name` → `$USER`** —
devex major: without owner population, `new` fails its own strict round-trip
acceptance test), body seeded with an H1. Output passes `validate --strict`
by construction (the acceptance test literally pipes one into the other and
asserts `owner` present).

Edge behaviors, specified (devex): slug collision → **error** naming the
existing note, `--force` overwrites (never silent data loss);
`--project`/`--fleet` are an argparse mutually-exclusive group; `--edit`
with `$EDITOR` unset → note written, clear stderr error about the editor;
`--json` → envelope with `data: {path}`.

## Reference vault (`examples/reference-vault/`)

One exemplary note per type + one per interesting edge: an aliased note, a
wikilink pair (incl. one unresolved link), a superseded/superseded_by pair,
CONVENTIONS.md at budget. **The exemplar vault is strict-clean — zero
warnings** (devex: it's what humans and agents copy; an exemplar carrying a
deliberate legacy pattern teaches the legacy pattern). Migration material
lives separately: `fixtures/legacy/` holds the claudlobby-style
legacy-status note (asserts lenient-clean + exactly W101/W102),
`fixtures/known-bad/` holds the error corpus incl. the skill-shaped example.
Doubles as pytest fixture — `conftest.py` gains `reference_vault` copying it
to `tmp_path`; existing synthetic fixtures migrate incrementally (only tests
touched by E1 move now; wholesale migration is not this epic).

**Adopt path gets its remedy** (devex: W101 without a fix path is a wall of
warnings for consumer 1): `claudron init --adopt` backfills missing
`updated` from file mtime — the exact backfill the epic doc promised — so
adopting an existing claudlobby `shared/` tree converges to lenient-clean in
one command. `validate` itself never mutates.

**README (PR3):** Quick-start golden path becomes init → new → validate;
CLI table gains the `new` and `validate` rows (devex: the epic's headline
commands must appear in the entry doc it ships with).

## Phased PRs (red-first per cycle-1)

| PR | Contents | Red-first gate |
|---|---|---|
| 1 | `SCHEMA.md` (incl. closed catalog + mapping tables) + `docs/CLI_CONTRACT.md` + reference vault (strict-clean) + `fixtures/{known-bad,legacy}/` + `SCAFFOLD_TREE`/`SHARED_SUBDIRS` change (incl. `init` switch) + CONVENTIONS template + #4 closing comment | known-bad fixtures committed with expected codes *and full JSON `Finding` elements* before the validator exists; **ratified-visibility red test** (a `status: ratified` decision must appear in default lookup) |
| 2 | `claudron/schema.py` (constants, `parse_note`, `validate_note`, the two status sets) + `claudron validate` (both tiers, envelope, exit codes) + **envelope migration of `status`/`lookup`/`config`** + **channel-discipline test + stdout/stderr retrofit** + doc-parity test + **updates to the green tests the contract breaks** (`test_cli.py:36,53,67`, `test_plug.py:94` — exit 2→3 and envelope assertions change in the same PR as the behavior, red-first) | PR1's fixtures are the failing tests |
| 3 | `claudron new` (owner derivation, collision/mutex/$EDITOR edges) + `init --adopt` mtime backfill + conftest `reference_vault` fixture + migrate touched tests + README golden-path update | `new → validate --strict` round-trip test (asserting `owner`) written first |
| 4 | Sibling PRs: claudlobby `frontmatter-schema.md` SSOT pointer + mapping table (recording the `archived` superset addition); clauDNA `output-guide.md` reconciliation (their schema table points at SCHEMA.md, keeps their body-skeleton contract — we own frontmatter, they own body structure); both PRs link #15 | n/a (docs) |

## Acceptance criteria (from #15, made mechanical)

- `claudron validate examples/reference-vault` → exit 0, **zero warnings**
  (exemplar is strict-clean; legacy material lives in `fixtures/legacy/`)
- Every file in `fixtures/known-bad/` produces exactly its documented code
  *and* the asserted full JSON `Finding` element
- `fixtures/legacy/` claudlobby-style doc → lenient warnings only
  (W101/W102), never errors
- `claudron new knowledge "X" && claudron validate --strict <file>` → exit 0,
  `owner` populated
- A `status: ratified` decision appears in default `lookup` results
  (the TERMINAL_STATUSES-split red test)
- `status`/`lookup`/`config`/`validate`/`new` all emit the one envelope
  shape under `--json`; channel-discipline test green across the command
  table
- SCHEMA.md ↔ `schema.py` doc-parity test green
- Both sibling PRs merged; #4 commented; #15 closed by PR4

## Panel record (focused ironclad, 2026-07-07)

Two lenses (engineering-review, devex-review), both `major`+ severity, both
folded above in the same PR: **engineering blocker** — the
`TERMINAL_STATUSES`+`ratified` one-constant instruction would have silently
hidden ratified decisions from lookup (→ two-set split + red test);
**devex blocker** — codes-as-API had no machine carrier (→ `Finding` struct
as the envelope element + fixture assertion). Majors: envelope unification
scoped in (three legacy `--json` shapes), stdout/stderr made-true with a
guard test, `new` owner derivation (was failing its own acceptance test),
doc-parity test (SSOT epic must not drift internally), `parse_note` seam
(E004 was unemittable), green-test collisions scheduled with the behavior
change, "verbatim adoption" corrected to superset-with-`archived`,
`SCAFFOLD_TREE`/`init` dual-use fixed. Deliberately declined: rewriting
`knowledge.py`'s hardcoded `"active"` fallbacks (E4 replaces that module;
noted in Terminal statuses section).

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
