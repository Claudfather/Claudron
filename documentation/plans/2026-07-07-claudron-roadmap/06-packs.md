---
title: "E6 — Packs + Claudosseum grounding: federation by git"
type: plan
status: active
owner: chris
tags: [epic, packs, federation, claudosseum, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E6 — Packs + Claudosseum grounding: federation by git

**Release:** 0.6.0 · **Depends on:** E1 (pack.yaml v0), benefits from E5 (curation gates exports) · **Parallel with:** E3, E4 · **Gated by:** G1; PR4 additionally by the demand trigger

## Goal

Federation without a service: a pack is a public git repo containing a curated
subset of a vault. Other deployments subscribe by cloning. This is the
mission's "opt-in federation through git," the umbrella README's "public packs"
loop, and the input Claudosseum's grounding loop was designed around. This
epic also completes the promotion ladder E5 corrected: bot `memory/` → fleet
`shared/` → vault `_shared/` → **pack** (the analogue of claudlobby's
`library/` top rung — cross-deployment via git).

On the contract's provenance, stated precisely (panel M6): Claudosseum has
zero Claudron *code*, but its mission already fixes the relationship and
vocabulary in four places — "public Claudron packs" for the public arena, a
"local vault" for the private arena. E6 therefore **codifies the contract
their mission sketches**, in their vocabulary, through their established
workflow (two-hop issue → `feat/claudron-grounding-spec` →
`documentation/planning/claudron-grounding-contract.md`) — it does not invent
one on a blank slate.

## Deliverables

1. **`pack.yaml` v1** (extends E1's reserved v0):
   `name, version, description, license, homepage, include` (glob list),
   `exclude`, `min_maturity` (default `verified`, on the D11 trust axis —
   packs export curated knowledge, not raw drafts), `scrub` (owner/provenance
   fields to strip), `provenance` (source vault id, exported_at, claudron
   version)
2. **`claudron pack publish <pack.yaml> --to <dir>`** — exports matching notes
   into a properly-structured pack repo: `_shared/`-rooted layout, pack.yaml,
   generated README with note inventory. Links pointing outside the pack get
   an **exclusion downgrade** — plain text + a "referenced but not included"
   appendix (not "rewriting": resolution is title-based and path-independent,
   so included links need no changes at all)
3. **Scenario export for Claudosseum:** `claudron scenarios export
   [--pack <name>|--tier <tier>] --out scenarios.jsonl` — maps eligible notes
   (types `knowledge`/`runbook`/`decision` with sufficient body) to
   Claudosseum's battle shape: `{description, projectContext, userPrompt,
   difficulty}` with the strict `easy|medium|hard` union (a DB CHECK on their
   side) **plus `scenarioIndex` ordering**, JSONL with a `schema_version`
   header record — structurally mirroring their existing
   `telemetry-contract.md` (JSONL batch + schema-version) precedent.
   **Clean-start, handled at the contract level (panel M7):** their
   `sanitizeProjectContext` runs only inside LLM generation — an import path
   would bypass it entirely, so "their sanitizer catches it" is not a
   backstop. Claudron exports provably-clean content by construction
   (eligibility filter excludes notes referencing session/handoff artifacts in
   `projectContext` terms) and does **not** mirror their regexes (silent
   drift-corruption risk); a CI fixture pinned to a snapshot of their patterns
   detects upstream drift instead. The contract must state explicitly whether
   imported scenarios are subject to or exempt from the sanitizer, and flag
   the handoff/resume scenario category (their real skill categories) as the
   known collision case
4. **Contract doc PR to Claudosseum** via their two-hop workflow:
   `documentation/planning/claudron-grounding-contract.md` on their side.
   **Their scenario importer does not exist and is filed explicitly as a
   Claudosseum-side dependency** — the fixture-validated export is our
   deliverable; a battle generated from it is theirs
5. **`claudron pack add <git-url>` / `pack sync` / `pack list` / `pack rm`** —
   subscribe read-only: clone/pull into `_packs/<name>/`, indexed (E4) as tier
   `pack:<name>` with lowest default rank priority; never written to; `sync`
   is explicit (no background fetch). **Gated behind a named demand trigger
   (panel M9): builds only after the first concrete external subscriber
   exists.** Interim consumption path, documented: clone the pack repo and
   read it — it's markdown
6. **Discovery, deliberately informal (umbrella open question, answered
   minimally):** document the `claudron-pack` GitHub topic convention; no
   registry
7. **First real pack shipped:** `claudfather-patterns` exported from the
   maintainer vault — proof, example, the org's first public knowledge
   artifact, and **the demand probe itself**

## Tier & trust semantics

- Subscribed packs rank below local tiers by default (local knowledge wins
  conflicts); per-pack rank boost is a config knob
- Pack notes keep their `status` but are display-labeled `pack:<name>` — a
  subscriber's `canonical` is *their* canon, not yours; promotion into your
  own `_shared/` is an explicit copy with provenance (E5 mechanics)
- `validate` runs on pack add and warns on schema drift (packs from older
  claudron versions load with warnings, not failures)

## Phased PRs

Panel-corrected PR order (M9 — probe fires before subscribe-side is built;
sunk-cost direction fixed: the exporter's genuinely new internals are
exclusion-downgrade + appendix generation; `min_maturity`-style subset
selection is trivial and E5's provenance stamps precede this epic, not
follow it):

| PR | Scope |
|---|---|
| 1 | pack.yaml v1 (self-designating as the mission's `pack.yaml` approval artifact, mirroring E3's pattern) + `pack publish` (layout, exclusion downgrade, README gen) |
| 2 | `scenarios export` + Claudosseum contract doc PR (their two-hop workflow) + pattern-snapshot CI fixture |
| 3 | `claudfather-patterns` first pack + `claudron-pack` topic docs — **the demand probe** |
| 4 | `pack add/sync/list/rm` + pack tier indexing + trust semantics — **builds only on the named demand trigger (first external subscriber)** |

## Acceptance criteria

- PR1–3: `claudfather-patterns` public on GitHub with the topic set; org
  README updated to link it; a pack containing an external wikilink publishes
  cleanly with the documented appendix behavior
- Exported scenarios validate against Claudosseum's `GeneratedScenario` type
  incl. the difficulty union and `scenarioIndex` (fixture test against a
  pinned snapshot of their interface + sanitizer patterns)
- PR4 (if triggered): round-trip — vault A publishes → vault B subscribes →
  B's `lookup` surfaces pack notes with correct tier labeling and rank; B
  never mutates pack content
- Pre-committed fallback if the probe returns zero subscribers: publish-side
  + scenario export survive on in-family value; PR4 and discovery polish are
  the first cut — recorded here so sunk-cost drift has nothing to grip

## Non-goals

- Central registry, search, or discovery service (topic convention only)
- Pack dependency graphs / packs-of-packs (a pack is flat)
- Write-back or upstream contributions via packs (contribution = PR to the
  pack's source repo, out of band)
- Instance-to-instance federation queries (mission: "v2 or never")

## Risks

- **Demand is unproven (F1 caveat / open question #4).** No verified source
  demonstrates multi-party curated-subset sharing — the field has proven
  single-vault git sync only. Mitigation: sequenced last, subscribe-side
  gated behind the probe (PR order above), scope deliberately thin (git +
  globs, no registry). If nobody subscribes, the sunk cost is the publish
  exporter and the scenario export — both of which stand on in-family value
  (Claudosseum grounding, the org's public knowledge artifact) without any
  subscriber.
- **Publishing leaks something private** → `min_maturity: verified` default +
  scrub list + generated inventory README makes the export reviewable before
  push; publish never pushes (it writes a local dir; the human pushes).
  License clarity at pack boundaries is part of the format from day one
  (`license` is required in pack.yaml — the field's AGPL-vs-MIT contrast shows
  it matters).
- **Pack drift breaks subscribers** → schema_version in pack.yaml,
  warn-don't-fail loading, `pack sync` shows a note-level diff summary.
- **Scenario export produces low-quality battles** → eligibility filter
  (min body length, type allowlist, `min_maturity`) + Claudosseum's own
  sanitizer as the second gate; start with maintainer-curated exports.

## Field evidence

See [07-field-research.md](07-field-research.md). This is the epic the
research is honest about rather than encouraging: git-based federation is
*consistent with* F1 (git collaboration primitives endorsed; cross-tool
single-vault sync proven) but **no verified source demonstrates
cross-deployment pack sharing, and demand is an explicit open question**. The
design responds by keeping the mechanism minimal (a pack is just a git repo),
sequencing this epic last in the DAG, and treating the first published pack as
a falsifiable probe. The Claudosseum scenario-export half of the epic is
independent of federation demand — its consumer is in-family and its contract
was confirmed greenfield by direct recon of the Claudosseum codebase.
