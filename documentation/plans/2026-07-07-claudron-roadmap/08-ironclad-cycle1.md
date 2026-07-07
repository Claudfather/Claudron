---
title: "Ironclad review — Claudron roadmap, cycle 1"
type: review
status: completed
owner: chris
tags: [ironclad, review, roadmap, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# Ironclad review: Claudron Roadmap v0.2→v0.6

**Cycle:** 1 · **Target:** plan (portfolio: overview + 6 epics + research appendix)
· **Lenses:** 9/9 completed (first-principles, adversarial-review, cost-benefit,
precedent-check, plan-health-audit, align-to-mission, ceo-review,
engineering-review, devex-review; design-review and extension-check N/A — no UI,
no diff). Precedent-check ran three sub-recons (Claudron history, Claudlobby,
clauDNA) plus a Claudosseum recon. Sibling `file:line` citations spot-checked
6/6 accurate.

Every finding below was folded into the plan docs in this cycle (resolution
noted inline). Convergence after fold: **zero open blockers, D1–D11 locked.**

## Blocker (resolved by fold)

- **B1 — No evidence gate between the wedge and the build-out** *(adversarial
  [critical]; independently found by ceo-review and first-principles)*. E3–E6
  were committed as scheduled deliverables while each one's core justification
  is explicitly unvalidated, and single-maintainer dogfood structurally cannot
  exercise any of them; base rate: solo maintainer, 4 commits, ~7-week
  dormancy. → **Fold:** 00-overview gains a "Gate G1" section after E2 with
  named thresholds per epic, E3–E6 demoted from scheduled to evidence-gated;
  minimum-success floor stated (0.2.0+0.3.0 = roadmap succeeded); effort sizing
  added (plan-health).

## Majors (all resolved by fold)

- **M1 — The write "chokepoint" doesn't serialize writers** *(engineering,
  adversarial, first-principles)*. Per-session stdio subprocesses mean N bots =
  N independent dedup→write→commit paths: dedup TOCTOU, `git index.lock`
  races, and F8 dogfood metrics that only see within-process events; the
  personal wedge is single-writer so it can't validate the bet either. →
  **Fold:** E3 specifies a vault-level advisory lock (`flock` on
  `.claudron/write.lock`) around the dedup+write+commit critical section +
  commit retry; the chokepoint claim is re-scoped (validation is per-writer;
  malformed-never-lands holds, global dedup needs the lock); an append-only
  `.claudron/events.jsonl` gives the F8 metrics a substrate in 0.3.0; fleet
  validation moved to a named fleet milestone behind G1.
- **M2 — "Superset" schema was not a superset** *(engineering, precedent,
  adversarial; + first-principles' two-axes question)*. E1 dropped
  `current|stale|ratified` (real values in claudlobby/clauDNA docs), required
  `updated` where claudlobby has it optional, required `confidence` on the
  weakest evidence in the record, and fused trust + activity into one `status`
  enum. → **Fold:** E1 splits the axes — `status` stays the activity axis as a
  genuine type-aware union incl. sibling values with a documented mapping;
  trust becomes a separate optional `maturity: draft|verified|canonical` field
  (E5 promotes on `maturity`); `updated` and `confidence` demoted to
  recommended; lenient adoption mode specified (pre-existing files warn, newly
  authored/MCP-written notes hard-error).
- **M3 — `planning/` in SHARED_SUBDIRS reverses closed issue #4 unacknowledged**
  *(precedent; + engineering's scaffolding-mismatch observation)*. → **Fold:**
  E1 cites #4, makes the reversal an explicit decision (vault-level planning
  becomes searchable), and owns the follow-through: nested
  `planning/{active,completed}` scaffolding reconciled across `init`/`fleet
  add` literals, tier labeling defined.
- **M4 — "Closes #11" claimed the opposite of what #11 asks** *(precedent)*.
  #11 demands direct cross-fleet reads, no copying; E5 ships promotion. →
  **Fold:** E5 reworded to "rejects #11's direct-read approach in favor of
  auditable promotion; #11 to be closed as superseded-by-design," overview
  table updated.
- **M5 — Promotion-ladder top rung mis-mapped** *(precedent)*. claudlobby's
  tier 3 is `library/` (cross-deployment via PR) — the analogue of E6 packs,
  not vault `_shared/`; "ratified" descriptor belongs to the INDEX.md ADR. →
  **Fold:** E5 ladder table corrected (`_shared/` = middle-rung analogue;
  packs = top rung), descriptor fixed.
- **M6 — E6's "Claudosseum blank slate" was half-true** *(precedent recon)*.
  Claudosseum's mission already fixes pack(public)/local-vault(private)
  vocabulary in four places. → **Fold:** E6 reframed to "codify the contract
  their mission sketches," adopts their vocabulary, follows their two-hop
  issue → `feat/claudron-grounding-spec` → contract-doc workflow.
- **M7 — Sanitizer misread + category collision** *(precedent, adversarial)*.
  `sanitizeProjectContext` runs only inside `generateScenarios` — an import
  path bypasses it entirely; its regexes would gut handoff/resume-category
  scenarios; mirroring the regexes invites drift-corruption. → **Fold:** E6
  contract must specify the sanitizer's status at the import boundary;
  Claudron exports provably-clean content by construction (no regex
  mirroring) + a CI fixture pinned to a snapshot of the patterns;
  `scenarioIndex` + JSONL/schema-version added, mirroring
  `telemetry-contract.md`.
- **M8 — Cross-repo adoption treated as afterthought; unpinned git dependency**
  *(adversarial; recon dedup findings)*. → **Fold:** sibling PRs become
  first-class epic deliverables with acceptance criteria; E3 dedups against
  Claudlobby #251/#266 and clauDNA #110/#112/#106/#107 instead of filing
  fresh; Claudlobby's `[vault]` extra to be pinned to a released tag (issue at
  E3 kickoff).
- **M9 — E6 subscribe-side ships before its demand probe can fire**
  *(cost-benefit, ceo, first-principles)*. → **Fold:** E6 PRs reordered
  (publish → scenarios → first pack = the probe), subscribe machinery gated
  behind a named demand trigger; scenario export explicitly severable from
  federation.
- **M10 — Build-vs-adopt never evaluated** *(adversarial)*. Basic Memory ships
  most of E3+E4 over the same substrate. → **Fold:** G1 gains a time-boxed
  adopt-vs-build spike as an entry task for E3/E4 (AGPL + dependency-policy
  trade-offs named).
- **M11 — Sync placement + hook robustness unspecified** *(devex ×2)*. →
  **Fold:** E2 specifies pull-at-SessionStart with ~2s timeout + offline
  fail-open, push at SessionEnd; hook contract: fail open, inject nothing on
  error, log to `.claudron/hooks.log`, health surfaced in `status`; absolute
  executable path embedded by `hooks install`; stdout=payload /
  stderr=diagnostics CLI-wide.
- **M12 — Portfolio mechanics: no effort sizing, no consolidated risk table,
  template divergence** *(plan-health ×3)*. → **Fold:** effort column (S–XL)
  added to the portfolio table + per-epic Context lines; consolidated `##
  Risks` table added to 00-overview; the `[plan]` children are
  separately-authored issue bodies (docs are in-repo companions), so the
  publish-contract concern is moot — noted in 00.

## Selected minors folded

E4 "closes #10" softened (semantic core deferred; #10's keyword ask largely
already shipped); E5 link-rewrite machinery **cut** (title-resolution is
path-independent — post-move edges assertion only; E6 wording fixed to
exclusion-downgrade); `hooks install --write` re-labeled net-new (clauDNA
principle, not mechanism); PreCompact stacking with clauDNA's
`precompact-reflect.sh` documented (and cited as the hook template); Tier A/B
vocabulary retired in E4; FTS5-less fallback re-framed as degraded (persistent
surfacing, not one warning); shared engine gets a named module home
(`engine.py`, E2 PR2) and E3's header gains "Depends on: E1, E2"; E2 documents
single-writer-per-machine; paraphrase eval seeded in E2 PR4 (metric timing
fixed in overview); E5 PR1 advertised as pull-forward (curation verbs can ship
≤0.3.0); mission-doc amendment rider added to the umbrella issue; adoption
metric stance stated + cheap public proof front-loaded (0.2.0 demo artifact,
0.4.0 eval numbers); pack.yaml v1 self-designates as the mission's approval
artifact; CLI contract one-pager added to E1; `init --personal` quickstart
added to E2; MCP error-payload schemas added to E3's approval table; `lookup
--explain` added to E4; `plug`/`migrate` coexistence documented in E3; E6
sunk-cost claim direction fixed; "battle generated" success metric re-scoped
to fixture-validated export (importer is a Claudosseum-side dependency);
overview corrections (precedence-with-fallback wording, bidirectional
validator cross-check, clauDNA six types, archived-doc caveat on the
`/claudron-write` quote, sockets labeled as same-author design commitments).

## Deferred (recorded, not folded)

- Per-epic ironclad deep-dives at epic kickoff (user-chosen depth for this
  cycle was one portfolio panel).
- Re-verification of the four multi-agent-governance papers (arXiv 2606.24535,
  2606.00007, 2604.27283, 2605.05242) at E3/E5 kickoff.
- E5 heuristic-precision gates (contradiction candidates, `--suggest`) — measure
  during dogfood before committing PR4 scope.
- Claudosseum-side scenario importer — their roadmap, filed as a dependency.

---
*Reviewed by /ironclad — cycle 1 · 2026-07-07 · converged after fold*
