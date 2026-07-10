---
title: Claudron Roadmap — v0.2 → v0.6 (the SD card)
type: plan
status: active
owner: chris
tags: [roadmap, epic, claudron, ecosystem]
created: 2026-07-07
updated: 2026-07-07
---

# Claudron Roadmap — v0.2 → v0.6

Six epics that take Claudron from a working-but-standalone CLI to the knowledge
hub of the Claudfather ecosystem: the "SD card" powering local Claude Code
sessions, the fleet memory Claudlobby is already wired for, the engine under
clauDNA's knowledge-lifecycle skills, and the scenario source Claudosseum's
grounding loop expects.

This overview carries the portfolio shape, the decisions already made, and the
evidence they rest on. Each epic has its own plan doc (`01-` through `06-`).

## Where Claudron stands (2026-07-07)

Claudron v0.1.0 is a real, tested package: `init`, `status`, `lookup`
(two-tier heuristic search over a JSON frontmatter index), `index`, `plug` /
`unplug` / `config` / `migrate` (Claudlobby bridge), `fleet add/list`. Single
dependency (PyYAML). What the mission promises but the code stubs out:

- `promote.py` — empty (lifecycle/curation)
- `resolve_wikilinks()` — returns `{}` (graph)
- No MCP server, no schema enforcement, no packs, no session hooks
- Open issues: #10 (semantic search), #11 (cross-fleet reads), #12 (auto-categorization)

Last substantive commit: 2026-05-19. The siblings ship daily. This roadmap is
how Claudron catches up — not by matching their pace, but by shipping the
specific plugs their already-built sockets are waiting for.

## The sockets are already built

Recon across the ecosystem (2026-07-06/07) found Claudron-shaped holes, not
greenfield:

One honesty note the ironclad panel added (08-ironclad-cycle1.md): all four
repos share one author, so these sockets are **prior self-commitments, not
independent demand** — real code seams, but inert today (the `.claudron`
bridge file exists only as a parser; no sibling user is blocked on Claudron).
They de-risk integration; they do not validate it. The falsifiable probes are
the first fleet bot writing through E3 and the first external pack subscriber.

| Sibling | Socket already built | Claudron plug (epic) |
|---|---|---|
| Claudlobby | `.claudron` bridge parser; `pip install claudlobby[vault]` pulls Claudron from git (currently **unpinned** — pin-to-tag issue files at E3 kickoff); vault path takes precedence over `local/<fleet>/` as fleet-overlay home, with fallback (`paths.py:355-405`); per-bot `claudron_vault_path` → `CLAUDRON_VAULT_PATH` env (`composer.py:448-459`); validator cross-checks vault-path ↔ `claudron` MCP config both ways (`validator.py:243-254`); mission sprint #4: "Add Claudron MCP server config to bot bootstrap"; **open issues #251 (this exact work) and #266 (ecosystem wiring)** — E3 dedups against them, not fresh filings | E3 (MCP server + `library/mcp/claudron.json` fragment) |
| clauDNA | Knowledge-lifecycle skills shipped: `/remember → /learn → /reflect → /index → /publish --to disk` over `shared/{knowledge,planning,decisions,runbooks}` via `SHARED_DOCS_PATH` (substrate itself unprovisioned — no init path creates it); publish/index enforce a six-type schema incl. audit/review; the "when Claudron's MCP server lands and a `/claudron-write` skill (or equivalent) ships" upgrade path is real but lives in an **archived** design doc; open issues #110/#112 (capture/persist) and #106/#107 (lessons/notes boundary awaiting Claudron) are E3's dedup targets; `/remember` is INDEX.md line-scanning with a 5-doc cap | E1 (shared schema SSOT), E3 (MCP + skills handoff), E4 (search engine under `/remember`) |
| Claudosseum | Zero Claudron *code*, but its mission already fixes the vocabulary — "public Claudron packs" (public arena) + "local vault" (private arena) in four places — so E6 codifies that sketch rather than inventing a contract. Hard constraints in code: scenarios are `{description, projectContext, userPrompt, difficulty}` with a strict difficulty union (`scenarios.ts:9-14`, DB CHECK) + `scenarioIndex` ordering; the clean-start sanitizer runs only inside LLM generation, so an import path must address it explicitly (E6) | E6 (scenario export + pack contract) |
| claudlobby protocols | `shared-documentation.md` protocol: pre-work INDEX scan (5-doc cap), one-file-per-topic, frontmatter required, 90-day TTL, promotion tiers `memory/ → shared/ → library/`; `frontmatter-schema.md` (types plan/decision/knowledge/runbook/audit/review, `expires`, `source_url`); INDEX.md convention ratified but zero adoption ("no `/index` producer here" gap) | E1 (schema unification), E5 (promotion mechanics) |

Three frontmatter schemas drift today: Claudron's CLAUDE.md, claudlobby's
`library/resources/frontmatter-schema.md`, clauDNA's publish types. E1 makes
Claudron the single source of truth.

## Decisions locked (2026-07-07 planning session)

| # | Decision | Choice | Why |
|---|---|---|---|
| D1 | First adoption wedge | **Local Claude Code sessions** (Chris's daily driver), Claudlobby second | Dogfood accumulates knowledge and design feedback daily; fleet rides the same MCP server one epic later |
| D2 | Storage substrate | **Plain markdown in a git repo — unchanged, forever** | The vault IS the Karpathy-style brain; MCP/CLI/hooks are doors into it, not replacements. "If Claudron disappears, the data still works" |
| D3 | MCP posture | **Optional extra** (`claudron[mcp]`), stdio subprocess, never a daemon/service | Local-first; core stays PyYAML-only; hooks shell the CLI and need no MCP at all |
| D4 | Vault topology (personal) | **One personal vault** (single private git repo, `_shared/` + `projects/<repo>/`) | The literal SD card: clone anywhere, every session plugs in. Work knowledge (employer systems) stays out |
| D5 | Roadmap shape | **SD-card ladder → DAG**: E1→E2 sequential, then E3/E4/E6 parallel, E5 after E4 | Fastest personal value; explicit DAG lets the fleet parallelize the rest |
| D6 | Retrieval bet | **SQLite FTS5 (BM25) + wikilink graph as default; embeddings deferred** to an optional extra | stdlib-only, zero deps, index can't rot silently; mission principle "graph traversal over vector similarity". Field-evidence amendment (F2/F3): BM25-grade ranking is the floor, hybrid fusion is the designed upgrade path with named triggers (paraphrase misses in the dogfood eval, or vault >~1k notes) |
| D7 | Deliverable format | Plan docs committed in-repo + umbrella EPIC issue + six `[plan]` children (clauDNA #165 house style). The children are separately-authored issue bodies linking these docs — the docs are companions, not the issue bodies | Survives model access windows; issues drive fleet execution |
| D8 | Planning rigor | Docs informed by web research on the 2026 "AI brain" wave; hardened by an ironclad panel (cycle 1: 08-ironclad-cycle1.md) before filing | Stress-test the bets against field evidence, not just internal coherence |
| D9 | Continuation gate | **Gate G1 after E2** (see below): E3–E6 are evidence-gated options, not scheduled commitments | Three panel lenses independently converged: an unproven wedge that can't reshape the plan is a preamble; base rate (solo maintainer, 7-week dormancy) predicts a stalled tail without a gate |
| D10 | Minimum-success floor | **0.2.0 + 0.3.0 shipped = this roadmap succeeded.** E4–E6 are compounding upside, not obligations | Makes a partial climb read as a ladder climbed partway, not a broken promise; the release train already makes each rung independently valuable |
| D11 | Trust vs activity axes | `status` (activity: type-aware union incl. sibling values) and `maturity` (trust: `draft→verified→canonical`) are **two fields, not one enum** | Panel caught the fused axes before the 0.2.0 schema freeze; a note can be `canonical` and `superseded` simultaneously — E4 ranks on both, E5 promotes on `maturity` |

## The portfolio

```
E1 Schema v1 + note tooling        ─┐ the ladder:
E2 Session loop v0 (hooks+CLI+git) ─┘ sequential, you feel it immediately
        │
   ═══ GATE G1 (evidence gate — see below) ═══
        │
   then evidence-gated (DAG):
        ├─ E3 MCP server v0.1 + Claudlobby socket
        ├─ E4 Indexer v2 (SQLite FTS5 + wikilink graph)
        │      └─ E5 Lifecycle & curation (PR1 may pull forward to ≤0.3.0)
        └─ E6 Packs + Claudosseum grounding
```

DAG legend — **this legend is the authoritative dependency statement;
per-epic header lines are summaries of it** (cycle-2 finding #4). The
parallel branch forks after the **0.2.0 release**: E3 depends on E1 + E2
(imports E2's `engine.py`), E4 on E1 (+ E2's dogfood queries for its eval
set), E6 on E1. E5 PR1 needs only E1; E5 PR2–4 need E4. Critical path:
E1→E2 (personal value); E1→E4→E5 (engine depth). **Release numbers are
ordinal, not bound to epics** (cycle-2 finding #5): the portfolio table shows
the default order, but if G1 swaps E3/E4, version numbers follow ship order —
whichever gated epic ships first takes 0.3.0.

| Epic | Release | Effort | One-line goal |
|---|---|---|---|
| [E1 — Schema v1 + authoring tooling](01-schema.md) | 0.2.0 | M | The contract: unified frontmatter schema, `validate`, `new`, reference vault, CLI contract |
| [E2 — Session loop v0: the SD card](02-session-loop.md) | 0.2.0 | M | `recall` / `capture` / `sync` + hook pack + quickstart; machine A's finding reaches machine B's next session |
| [E3 — MCP server v0.1 + Claudlobby socket](03-mcp-server.md) | 0.3.0 | M | Five tools (lookup/read/write/related/status) + vault write-lock; `claudron.json` fragment PR; clauDNA skills handoff |
| [E4 — Indexer v2: SQLite + graph + real search](04-indexer.md) | 0.4.0 | L | FTS5 BM25 + edges table + incremental reindex; implements `resolve_wikilinks`; addresses #10's scale/incremental half |
| [E5 — Lifecycle & curation](05-lifecycle.md) | 0.5.0 | M | draft→verified→canonical on `maturity`, `promote`, `review` queue, librarian workflow; supersedes #11, partially closes #12 |
| [E6 — Packs + Claudosseum grounding](06-packs.md) | 0.6.0 | M (S if subscribe-side stays gated) | pack.yaml v1, publish + scenario export; subscribe machinery behind a demand trigger |

**Gate G1 — the continuation gate (D9).** Sits between the 0.2.0 release and
everything after it. E3–E6 are *options the evidence exercises*, not
commitments. Entry criteria, measured over ≥2 weeks of E2 dogfood:

- **Dogfood scope (2026-07-09 refinement):** the ≥2-week dogfood runs the vault
  on Chris's local machines **and** the Pi fleet, wired **CLI + git, not MCP**
  (E2's shipped surface; the MCP server is E3, which this gate decides), with
  **writes serialized** so the parked multi-writer claim (below) stays parked.
  Success is read from **four pre-registered signals** — cross-boundary recall,
  accumulation quality, resync robustness, hooks-fired-automatically — each
  threshold fixed *before* the clock starts. Runbook + tracking checklist:
  [`2026-07-09-g1-dogfood-protocol.md`](../2026-07-09-g1-dogfood-protocol.md).
  This does not reverse D1 (local-first); it makes the human↔fleet half of the
  wedge observable rather than only the personal half
- **Pulse:** notes/week > 0 and trending up; recall briefs referenced in-session
- **Continue personal-first** (E4 next if the vault is growing fast toward the
  F3 knee, E3 next otherwise) when pulse passes
- **Pulse fails → re-anchor on the fleet:** E3 leads against Claudlobby's
  sprint #4 / issue #251, and E4's eval set derives from fleet queries instead
  of personal ones — the wedge failure reshapes the plan rather than being
  ignored
- **The gate emits a written verdict** (cycle-2 must-fix #1): a dated
  `G1-verdict.md` in this directory recording **PASS** (wedge validated —
  pulse numbers attached) or **PIVOT** (wedge failed; fleet-first replan,
  with what changed), cross-posted to EPIC #14. The two branches are
  deliberately distinguishable: a PIVOT is a recorded strategy change, never
  silently absorbed into "shipped anyway"
- **Adopt-vs-build spike (M10):** lands as **its own gate artifact — a spike
  writeup PR that merges before any E3/E4 implementation PR opens** (cycle-2
  consensus #2: a spike bundled with build code cannot gate the build).
  Candidates: Basic Memory (AGPL, ships MCP+hybrid over the same substrate)
  and Graphify (79k-star MIT graph engine; see 07's addendum — expected
  answer is consume-not-adopt since wikilink edges are trivially derivable
  and node semantics differ, but the spike decides). Claudron-specific glue
  (schema SSOT, recall/capture semantics, CONVENTIONS layer, packs, scenario
  export) is ours either way
- **Multi-writer claims stay parked** until a real fleet milestone exists
  (see E3): single-writer dogfood cannot validate them

**Release train:** each epic ends in a tagged release with CHANGELOG discipline.
0.2.0 ships via a **GitHub release** (wheel + sdist attached) and flips the org
README's Claudron status from "Design" to "Active". **PyPI is deferred** (pivot
2026-07-09): the four repos are co-installed *products* with split distribution
channels — Claudron + Claudlobby → PyPI, clauDNA → Claude Code plugin
marketplace — so shipping one PyPI leg before the session loop is validated (and
before its sibling leg exists) is premature. Coordinated PyPI/marketplace
distribution becomes a **G1-gated decision**, ideally Claudron + Claudlobby
published together under one install story. E1+E2 ship together as 0.2.0 — the
schema alone isn't a usable release; the SD card is. **Floor (D10): 0.2.0 + the first post-gate release
shipped *with the G1 verdict recorded* = success; E4–E6 are upside.** The
verdict requirement keeps the floor honest — "wedge validated" and "wedge
failed, pivoted, shipped anyway" are different outcomes and the record says
which one happened (cycle-2 must-fix #1). Two acceptance gates are
wall-clock (E2's two-week dogfood, E5's
two-week librarian drain) — they, not engineering effort, set the minimum
cadence for those releases, and that's a conscious buy. Cheap public proof is
front-loaded: an SD-card demo recording ships with 0.2.0, the E4 eval numbers
(before/after recall@10) publish in the README at 0.4.0.

## Field evidence (2026 "AI brain" wave)

Full verified report: [07-field-research.md](07-field-research.md) (22 sources,
25 claims through 3-vote adversarial verification; findings cited as F1–F8).
The wave converged on Claudron's shape — plain markdown + git as source of
truth with a derived rebuildable SQLite index (F1), BM25-grade lexical
retrieval as the zero-setup floor (F2), graph encoded in the markdown and
traversed via the derived index (F7), capture hooked to the compaction event
and review-based librarian curation (F5).

**Five of six Claudron bets are supported; the MCP write-chokepoint is
motivated but unvalidated (F8) — the multi-agent-governance literature failed
verification on infrastructure errors and needs a re-check.** Two pressure
points changed this roadmap:

1. **A flat index stops being viable as primary retrieval at ~100–200 pages
   (F3)** — so E4's FTS5 tier is load-bearing at target scale (and clauDNA's
   INDEX.md-scanning `/remember` inherits the same ceiling; the E3 handoff is
   the fix).
2. **Both mature markdown-first systems added local-embedding hybrid fusion
   (F2: recall@10 80→91%, paraphrased 17→46%)** — hybrid is the expected
   upgrade path, not a rejected alternative. D6 stands (FTS5 default), but E4
   now *designs* the hybrid tier (RRF fusion, local model, silent lexical
   fallback, kill switch) and names its triggers instead of hand-waving
   "later."

Also folded in: supersession-over-decay curation (F5 → E5), per-claim
provenance conventions and an always-loaded conventions file (F4/F6 → E1/E2),
and an abstention threshold on recall injection (→ E2).

## Success metrics (from PROJECT_MISSION.md, made concrete)

- **Dogfood pulse (E2, feeds G1):** notes/week written to the personal vault;
  recall injections referenced in-session; a **saved-me tally** (one-flag mark
  on a recall hit that materially helped — impact, not just activity)
- **Retrieval quality (E4):** paraphrase-miss rate on the eval set (the F2
  hybrid trigger; a minimal query/expected-hit seed list ships in E2 PR4 so
  trigger data accumulates before E4's full harness lands)
- **Query volume (E3/E4):** `lookup`/MCP calls per bot task in a Claudlobby fleet
- **Lifecycle progression (E5):** % of drafts reaching verified/canonical
  `maturity`; staleness queue drained weekly
- **Federation traction (E6):** first public pack published (the demand probe);
  scenario export validates against Claudosseum's `GeneratedScenario` fixture.
  "≥1 external subscriber" and "battle generated from an export" are stretch
  outcomes — the latter depends on a Claudosseum-side importer that does not
  exist yet (filed as their dependency, not our metric)
- **Engine health (E4):** lookup latency flat as the vault passes 1k notes
- **Adoption beyond the maintainer** (mission metric #1): deliberately a
  post-v0.6 outcome under D1 — tracked, not gated. The 0.2.0 demo artifact and
  0.4.0 eval numbers are its leading indicators
- **Chokepoint validation (E3, F8):** write rejections routed to update, dedup
  hits, malformed-write attempts — from `.claudron/events.jsonl`, surfaced by
  `claudron status`, publishable as the first field data on the F8 gap

## Risks (portfolio-level)

| Risk | Impact | Mitigation |
|---|---|---|
| Stalled tail after 0.2.0 (base rate: solo maintainer, 7-week dormancy) | README flips "Active," then E4–E6 slide; roadmap reads as broken promise | Gate G1 + floor D10; every rung independently valuable; effort sizing keeps the DAG schedulable |
| F8 write-chokepoint unvalidated (the moat bet) | E3's headline guarantee overstated under fleet load | Vault write-lock specified before code; claims scoped to per-writer in v0.1; fleet milestone named; events.jsonl instruments it; four governance papers re-verified at E3 kickoff |
| E1 schema freezes wrong (post-0.2.0 changes approval-gated) | Three repos inherit a bad contract | Superset made genuine (type-aware status union + mapping); required set kept minimal (`updated`/`confidence` recommended); SCHEMA.md "open questions" is a first-class expected-to-change section |
| Sibling adoption is outside our control (approval gates, their backlogs) | The hub thesis stalls at the seams | Sibling PRs are first-class deliverables with acceptance criteria; dedup into their open issues (#251/#266, #110/#112/#106/#107); unpinned `[vault]` dep pinned to release tags |
| Pack-federation demand unproven | E6 subscribe-side is sunk cost | Sequenced last; PRs reordered publish→scenarios→probe; subscribe machinery behind a named demand trigger |
| Retrieval quality regressions during E4 cutover | Dogfood trust lost mid-roadmap | Parity PR before ranking PR; checked-in eval set as a red gate; FTS5-less fallback surfaced persistently as degraded mode |

## Non-goals (carried forward, restated)

No hosted vault storage. No central pack registry. No graph database. No
LLM-driven extraction at indexing time. No human-facing browse UI (Obsidian
et al. already work). No real-time multi-writer collaboration. No cross-tenant
queries. Federation is packs-only, opt-in, via git.

## Sibling-repo work this roadmap triggers (filed at epic kickoff, not now)

Sibling adoption is the thesis's hard part, so each item below is a
first-class epic deliverable with its own acceptance criterion — not a
docs-PR afterthought. Where the sibling already tracks the work, we comment
into and dedup against their issue rather than filing fresh.

- Claudlobby: `library/mcp/claudron.json` fragment (matching its documented
  fragment contract: top-level `claudron` key, `_env_contract` mapping
  `${CLAUDRON_VAULT_PATH}`, `_permissions_contract` listing the five tools) +
  query-before/write-after protocol doc → **into open #251**, umbrella #266;
  the mission gate covers adding it to the *default template*, not shipping
  the opt-in fragment. Plus: pin the `[vault]` extra to a released Claudron
  tag (currently unpinned git HEAD)
- clauDNA: `/remember`/`/learn` prefer Claudron engine when available;
  `/claudron-write` skill; `/init-project` provisions `SHARED_DOCS_PATH` →
  dedup against **#110/#112** (capture/persist) and **#106/#107**
  (lessons/notes boundary); skills conform to its CI-enforced SKILL_CONTRACT;
  reconcile SCHEMA.md SSOT with `output-guide.md` (self-declared canonical)
- Claudosseum: scenario-grounding contract doc via their established two-hop
  issue → `feat/claudron-grounding-spec` → `documentation/planning/
  claudron-grounding-contract.md` workflow (E6); their scenario **importer**
  filed explicitly as a Claudosseum-side dependency
- Umbrella (Claudfather/.github + Claudron PROJECT_MISSION.md): amend the
  mission docs as a rider on the EPIC issue — D1's personal wedge, E2's
  session loop, E4's watcher deferral, and the G1 gate all deviate from the
  current sprint-focus text and should be governed by an amended mission, not
  by this plan alone
