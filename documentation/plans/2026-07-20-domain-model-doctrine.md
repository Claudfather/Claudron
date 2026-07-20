---
title: "Claudron domain model — note taxonomy, tiers, and promotion doctrine"
type: decision
status: draft
owner: chris
tags: [decision, schema, domains, taxonomy, promotion, tiers, claudron]
created: 2026-07-20
updated: 2026-07-20
---

# Claudron domain model — note taxonomy, tiers, and promotion doctrine

**Status: draft** — consolidates a fresh-eyes design pass on Claudron's
"domains." The conceptual model is settled; pieces already normative have
graduated into `SCHEMA.md` / `VAULT-STRUCTURE.md` (marked inline). One design
call remains, scoped to a follow-up build (the `_shared/` folder refactor).

**Scope — Claudron alone.** This doc defines Claudron's *internal* knowledge
model: what note types exist, what belongs in each, and how they are tiered and
promoted **within the vault**. It deliberately stays out of the cross-repo frame —
*how* content reaches the vault (the write door, clauDNA conformance), the
Claudron/clauDNA/Claudlobby boundary, and CLAUDE.md seam enforcement across repos
are the **boundary program's** concern (`2026-07-20-claudfather-boundary-separation.md`
+ `2026-07-20-boundary-rearchitecture/`). Where the two touch, this doc defers.

## The question

What are Claudron's *domains* (note types), what belongs in each, and how does
knowledge get routed into and promoted through them? Trigger: the dogfood vault
(`crogs-claudron-vault`) validated at **320 strict / 177 lenient errors**, which
first looked like schema drift between Claudron and clauDNA. Fresh-eyes
investigation reframed the whole question.

## Finding: the vault holds three artifact classes, not one

The "drift" was a category error. A vault commingles three things:

1. **Curated notes** — files carrying the schema's types and frontmatter: what
   Claudron indexes, validates, and ranks. The only class Claudron *manages*.
2. **Raw agent memory** — per-session `feedback`/`project`/`reference` files in
   `*-memories/` trees (Claude Code auto-memory format: `name`/`description`/
   `originSessionId`, `**Why/How to apply**` bodies). Never meant to be notes.
3. **Imported ballast** — corpora carried for provenance/harvest (e.g. the
   Artemis `*-memories/` import), not the ecosystem's own knowledge.

The 320 errors were Claudron validating (2) and (3) as if they were (1). The fix
is not schema convergence — it is *recognizing the classes*.

→ **Ratified (build pending):** a reserved **`_unindexed/`** tier for class (3) —
a top-level dir the walker skips wholesale (validate/index/search); git still
tracks it. Harvesting is a separate, deliberate op that reads the raw tree.

## The 6 types hold

Fresh-eyes, the ratified six — `knowledge, decision, runbook, plan, audit,
review` — are correct and MECE for *referential* knowledge. Every apparent gap
from clauDNA's wider vocabulary dissolves:

| apparent gap | resolution |
|---|---|
| feedback / reference / project (content) | class (2) memory, or `knowledge` — not a type |
| synthesis | `decision` (a governing choice) or `review` (an adjudicated assessment) — not a distinct type |
| findings | `audit` (assessment) or `knowledge` (a learning) |
| pointer | a `[[wikilink]]`/alias — structural, not a type |
| project (scope) | the `projects/<repo>/` *tier* — location, not type |

Adding a type trips the schema approval gate; nothing here earns it. Procedural /
executable content stays clauDNA's (the referential-only boundary, `SCHEMA.md`).

**Resolved — spec folds into plan.** data-hive-mind splits `specs/` (a durable
target) from planning, but a spec is a `plan` sub-shape (a folder), not a 7th
type — splitting it trips the schema approval gate. This doc is the
demonstration (see §Boundary note): a durable *governing* design is a `decision`
(ratified→superseded), a durable *implementation* target is plan-family — "spec"
splits across those two and is not a coherent third type.

## Two layers: type (schema) vs folder (sub-domain)

The lever that reconciles "6 disciplined types" with the richer real categories a
mature wiki grows (data-hive-mind runs concepts / architecture / conventions /
entities / playbooks / incidents):

- **`type:`** = the schema domain. The ratified 6. Coarse, approval-gated — what
  `claudron validate` enforces.
- **`_shared/` folder** = the sub-domain. As fine as useful, added freely, zero
  schema cost. Carries the human distinction.

data-hive-mind proves the split: fine folders, `type:` stamped on only a few. The
finer categories are *organization*, not new domains.

→ **Graduated to SSOT:** the non-note concept (`SCHEMA.md` §Non-note files) and
the `projects/<repo>/` boundary (`VAULT-STRUCTURE.md`, PR #72).

## What earns a `_shared/` home: durability × coupling

`_shared/` is for knowledge that is **durable AND cross-cutting**. Membership is
decided by durability × coupling — not by "is it an assessment":

- **Repo-coupled + point-in-time** (audits, reviews) → the **repo plane**
  (`repo/documentation/` or `projects/<repo>/`), *not* `_shared/`. They are
  *feedstock*: their generalizable **residue** promotes into `_shared/conventions/`
  when a finding recurs. The raw artifact never moves.
- **Durable operational wisdom** (incidents/postmortems — a recovery runbook + a
  lesson that generalizes) → earns a `_shared/` home.

This is why **incidents stay and audits don't**: postmortems produce durable
residue; audits produce fix-lists that are done once the fixes land. So `/audit`
and `/review-work` route **low** (repo plane); only distilled residue reaches the
top. **`_shared/` is earned, not authored.**

## The second axis: reach, and promotion as climb + distill

Beyond `maturity` (trust: draft→verified→canonical), the vault has a **reach**
axis — already partly ratified in `VAULT-STRUCTURE.md` ("Knowledge rises"):

    bot/user → project/repo → fleet → system → _shared

| axis | values | motion | question |
|---|---|---|---|
| maturity (trust) | draft / verified / canonical | in place | how much do we trust it? |
| reach (scope) | bot → … → `_shared` | climbs + distills | how widely does it apply? |

Promotion up the reach ladder raises reach, raises trust, and **generalizes the
content** (a code review → a project tidbit; three audit findings → one
convention). This extends `claudron promote` (today maturity-in-place only) into
**tiered promotion + a distillation transform** — the "shared brain" machinery,
and the meatiest build ahead.

- **The "system" tier** is being defined in a Claudlobby branch (bot folders
  tiered by system); Claudron adapts later. [parked — external]

## Routing enforcement — deferred to the boundary program

*How* content gets routed into these domains at the write door — binding
authoring operations to the right `(type, folder, tier)`, and conforming the
clauDNA write path — is a **cross-repo** concern owned by the boundary program
(`2026-07-20-boundary-rearchitecture/` D1 clauDNA-conformance, D2 closure-triage).
This doc defines only the Claudron-side **target** that enforcement routes into:
the types, the sub-domain folders, and the tier/promotion rules below. Claudron's
own contribution to enforcement is `validate` (strict at the write path) — the
domains are what it validates against.

## Boundary note — why this doc is a `decision`, and why it lives here

Applying the doctrine to itself (dogfood):

**Type — `decision`, not `plan` or `spec`.** Its purpose is a durable *governing
model* whose lifecycle is `draft→ratified→superseded` — exactly `decision`'s —
and it records architectural choices with rationale. A `plan`'s
`draft→active→completed` is the wrong shape (a doctrine does not "complete"), and
`spec` is not a type (it folds into plan, above). The forward *work* it implies
is tracked as tasks/PRs — which is why the ledger below stays thin: a ratified
decision holds the model, not the work status (the same "status lives elsewhere"
rule specs follow).

**Placement — the Claudron repo, not the vault.** This is a Claudron project
design decision (how the engine classifies knowledge), so it lives in the repo's
`documentation/plans/` (Claudron's design-doc home — decisions and plans alike
sit there), versioned with the code it governs and PR-reviewed — the same plane
placement as `2026-07-19-steady-state-retrieval-decision.md`. It is **not**
`_shared/` vault knowledge: it is the repo speaking about its own schema, not
cross-project referential knowledge the fleet consumes. The fleet consumes the
ratified *conclusions* via `SCHEMA.md` / `VAULT-STRUCTURE.md` — not a vault copy
of this deliberation.

**Relation to the boundary program.** This doc and the concurrent boundary
program (`2026-07-20-claudfather-boundary-separation.md` + its
`boundary-rearchitecture/` phases) sit at different altitudes and nest: the
program draws the **cross-repo** boundary (Claudron=referential vs
clauDNA=procedural vs Claudlobby=runtime) and owns cross-repo placements; this doc
draws Claudron's **internal** knowledge model *inside* the referential system. On
the seams they share — clauDNA routing (program D1/D2), the CLAUDE.md seam
(program X1), corpus movement (program L3) — this doc **defers** to the program as
the placement SSOT.

## Consequences

Normative conclusions graduate into the SSOTs; the rest is follow-up work,
tracked as tasks/PRs (a ratified decision holds the model, not the work status):

- **In SSOT now:** the 6 types; non-note files (`SCHEMA.md`); the
  `projects/<repo>/` boundary + `projects/CLAUDE.md` scaffold
  (`VAULT-STRUCTURE.md`, PR #72).
- **Follow-up builds (Claudron tasks/PRs):** the `_unindexed/` tier; the
  `_shared/` folder refactor (finer sub-domains); tiered promotion + distillation
  (extending `claudron promote`).
- **Owned by the boundary program (not this doc):** clauDNA routing enforcement
  (D1/D2), the CLAUDE.md seam (X1), corpus movement (L3).
- **Parked (external):** the "system" tier (Claudlobby branch).
