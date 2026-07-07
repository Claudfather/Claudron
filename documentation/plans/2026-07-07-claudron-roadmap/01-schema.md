---
title: "E1 — Note Schema v1 + authoring tooling"
type: plan
status: active
owner: chris
tags: [epic, schema, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E1 — Note Schema v1 + authoring tooling

**Release:** 0.2.0 (with E2) · **Depends on:** nothing · **Blocks:** everything else

## Goal

One ratified note schema that Claudron enforces and the siblings point to as
source of truth — plus the tooling that makes writing a valid note easier than
writing an invalid one. The mission calls the schema "the highest-leverage
decision — blocks everything else." E2's capture path, E3's MCP `write` tool,
E5's promotion rules, and E6's pack format all enforce or extend it.

## Why now — the drift is live

Three schemas describe the same notes today:

1. **Claudron CLAUDE.md** — requires `title, type, status, owner, tags, created, updated`
2. **claudlobby `library/resources/frontmatter-schema.md`** — the same six
   types with **type-dependent status enums** (knowledge→`current|stale|
   superseded`, decision→`draft|ratified|superseded`, …), `owner`/`created`
   required, `updated` optional, plus `expires`, `source_url`, `source_type`,
   `slug`, `last_verified`, `supersedes`
3. **clauDNA `skills/_shared/output-guide.md`** — self-declares "the canonical
   house-style spec"; same six types (audit/review route to
   `shared/planning/active/`), fields incl. `repos`/`links`, **no `updated`**

The drift is in *fields and status values*, not type enums. Every bot-written
note deepens it. Unify now, while the corpus is small.

**Why Claudron as SSOT** (vs anointing claudlobby's already-thorough doc):
Claudron is the only sibling where the schema is *executable* — `validate`,
`capture`, and E3's `write` enforce it in code, while claudlobby's is a
reference doc and clauDNA's is skill prose. SSOT follows the enforcement
point. The sibling-alignment PRs (below) must explicitly reconcile clauDNA's
`output-guide.md` — which is wired into its publish/index validation — not
just point at SCHEMA.md.

## Deliverables

1. **`SCHEMA.md` at repo root** — the ratified spec:
   - **Note types:** `knowledge | decision | runbook | plan | audit | review`
     (superset of all three current sets), with per-type required/optional
     frontmatter tables
   - **Universal required fields:** `title, type, status, created` — a
     deliberately *minimal* required set (panel finding M2: the least-reversible
     artifact ships before multi-bot writes can stress it, so requiring less is
     the reversible direction). `updated` is **recommended** (backfilled from
     mtime on adopt, hard-required only for newly authored notes); `owner`
     required for bot-written notes (provenance), optional for human notes;
     `tags` recommended
   - **Two axes, two fields (D11):** `status` is the **activity axis** — a
     genuine type-aware union of all sibling values (`active | completed |
     superseded | archived | current | stale | ratified | draft`, per-type
     tables with a documented equivalence mapping, e.g. `current≈active`,
     `ratified` decision ≈ locked) so migrated claudlobby/clauDNA docs pass
     without edits. `maturity` is the **trust axis** — `draft | verified |
     canonical`, optional, defaulting to `draft` for bot-written notes; E5
     promotes on `maturity`, never on `status`. A note can be `canonical` and
     `superseded` at once; E4 ranks on both axes
   - **Lifecycle fields (reserved for E5):** `promoted_by`/`promoted_at`
     reserved; **`superseded_by: <wikilink>`** as the terminal pointer — field
     evidence (F5) is unambiguous that explicit supersession, not
     decay/deletion, is the freshness primitive
   - **Trust fields:** `confidence: stated | high | medium | speculation`
     (adopted from the AI-first convention, F6) — **recommended** (SHOULD) in
     v1, promoted to required for bot writes once E3's write path makes
     enforcement free and real bot traffic has stress-tested the field set
   - **Retrieval fields:** `aliases` (already indexed), `expires` (a review
     trigger, never a deletion trigger — E5), `source_url`, plus carried
     sibling fields `source_type`, `slug`, `last_verified`, `supersedes` (a
     genuine superset must not silently narrow the installed contract)
   - **Body conventions for bot-written notes (F6):** per-claim recency
     markers ("as of 2026-07, <source>") and verbatim source URLs — documented
     as SHOULD in v1, linted as warnings by `validate`, candidates for MUST
     once E3's write chokepoint makes enforcement free
   - **Wikilink conventions:** `[[Title]]` and `[[Title|label]]` resolve by
     exact title → alias → slug, case-insensitive; links are written by the
     note author at write time (never inferred post-hoc); unresolved links are
     valid (they mark wanted-but-unwritten notes, mirroring the memory-system
     convention)
   - **Directory taxonomy:** `_shared/{knowledge,decisions,runbooks,planning/{active,completed}}`
     — **adds `planning/` to Claudron's `SHARED_SUBDIRS`**, which **knowingly
     reverses closed issue #4's "What NOT To Do"** ("don't extend
     KNOWLEDGE_TIERS with planning/ — the vault-wide scanners would start
     walking them"). The reversal is deliberate: claudlobby's composer and
     clauDNA's publish adapter both create/target `shared/planning/` as a real
     content tier, so vault-level planning docs *should* be searchable; #4 gets
     a closing comment recording the reversal. Follow-through the panel
     demanded: the nested `planning/{active,completed}` shape must be
     reconciled with the flat `SHARED_SUBDIRS` iteration (scaffolding in
     `init()` and the hardcoded triples in `cmd_init`/`cmd_fleet_add`
     printouts update together — the drift #4 actually feared), and `status`
     tier labels for `planning/active` vs `planning/completed` are defined in
     SCHEMA.md. Reuse `TERMINAL_STATUSES` (`vault.py:27`, from closed #8) as
     the single terminal-status source — do not reintroduce a literal
   - **`pack.yaml` v0:** name, version, description, license — reserved and
     minimal; E6 extends it
   - **Schema versioning:** `schema_version` in the index; SCHEMA.md carries a
     changelog section; post-0.2.0 changes require approval per the mission
2. **`claudron validate`** — vault linter with a **two-tier leniency contract**
   (panel M2): pre-existing/adopted files degrade to warnings (unknown-but-
   nonempty status, missing `updated`), while newly authored (`new`) and
   MCP-written notes get hard errors (missing required fields, unknown type,
   bad enum, malformed dates). Vault-level warnings: duplicate titles,
   colliding aliases, unresolved wikilinks once E4 lands. `--json` for bots,
   exit-code contract for CI. Validates but never mutates.
3. **CLI contract one-pager** (ships beside SCHEMA.md, before the surface
   grows from ~8 to ~17 commands): exit-code table (0 ok / 1 findings / 2
   usage / 3 environment), common flags (`--json`, `--vault`, `--project`),
   one `--json` envelope shape, **stdout = payload, stderr = diagnostics**
   (load-bearing for E2: recall's stdout is literally the injected session
   context), and the grouped command taxonomy (vault / session / knowledge /
   fleet / pack) for `--help`.
4. **`claudron new <type> <title>`** — scaffolds a schema-valid note: right
   tier directory (`--project <name>`, `--fleet <name>`, default `_shared`),
   slug filename, populated frontmatter, `--edit` opens `$EDITOR`.
5. **Reference vault at `examples/reference-vault/`** — one exemplary note per
   type with realistic wikilinks; doubles as the pytest fixture (replaces
   ad-hoc synthetic vaults in conftest) and as living documentation.
6. **`_shared/CONVENTIONS.md` template** — scaffolded by `init`, patterned on
   the always-loaded schema-doc layer (F4) and the ~120-token critical-facts
   file (F6): vault-specific conventions, naming, and standing facts every
   agent should hold. E2's recall brief injects it unconditionally; it is the
   one file with a hard token budget enforced by `validate`.
7. **Sibling alignment PRs (docs-only):** claudlobby `frontmatter-schema.md`
   and clauDNA's `output-guide.md` (self-declared canonical — the PR must
   reconcile, not just link) point to Claudron's SCHEMA.md as SSOT, carrying
   the status-value equivalence mapping. No behavior changes on their side in
   this epic.

## Phased PRs

| PR | Scope |
|---|---|
| 1 | SCHEMA.md spec (status/maturity split, mappings, CLI contract) + `planning/` added to SHARED_SUBDIRS incl. scaffolding-literal reconciliation + reference vault + CONVENTIONS.md template. **Known-bad fixtures land first (red), the spec makes them pass (green)** |
| 2 | `claudron validate` two-tier leniency (fixtures from PR1 are the red gate) |
| 3 | `claudron new` + conftest migration to reference-vault fixture |
| 4 | Sibling docs-alignment PRs (claudlobby schema doc, clauDNA output-guide reconciliation) + closing comment on #4 recording the reversal |

## Acceptance criteria

- `claudron validate examples/reference-vault` exits 0; the known-bad corpus
  produces the documented error codes
- `claudron new knowledge "X"` output passes `validate` untouched
- **A real migrated claudlobby fleet doc with `status: current` and no
  `updated` field validates with warnings, not errors** — the criterion the
  panel proved the draft schema failed; the type-aware union + leniency
  contract exist precisely to pass it
- claudlobby + clauDNA docs merged pointing at SCHEMA.md, incl. the
  output-guide reconciliation

## Non-goals

- Enforcing lifecycle transitions (E5 owns semantics; E1 only reserves fields)
- Any index/search changes (E4)
- Renaming or migrating existing sibling directory conventions

## Risks

- **Schema bikeshed stalls the ladder.** Mitigation: v1 is deliberately a
  superset of the three existing schemas — adoption is additive, no field is
  removed; disagreements get parked in SCHEMA.md's "open questions" section.
- **Sibling docs drift back.** Mitigation: SSOT pointer plus `validate` in
  Claudron CI; E3's write tool makes conformance automatic for bots.

## Field evidence

See [07-field-research.md](07-field-research.md). This epic absorbs: **F4**
(write authority partitioned by layer; conventions in an always-loaded schema
doc; write-time validation — `validate` is the same pattern
obsidian-second-brain enforces with its validator hook), **F6** (per-claim
provenance: recency markers, verbatim source URLs, `confidence` enum,
critical-facts file — medium confidence, single-source, adopted because it is
cheap and directly serves E5's auditability), and **F5**'s supersession
primitive (`superseded_by`). F1 validates the substrate the schema describes.
