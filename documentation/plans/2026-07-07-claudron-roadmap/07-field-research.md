---
title: "Field research — the 2026 'AI brain' wave, verified do/don'ts"
type: knowledge
status: active
owner: chris
tags: [research, memory, retrieval, curation, claudron]
created: 2026-07-07
updated: 2026-07-07
source_url: deep-research run wf_b14dde92-334 (22 sources, 109 claims extracted, 25 verified 3-vote adversarial)
---

# Field research — the 2026 "AI brain" wave

Deep-research run (2026-07-07): 5 search angles, 22 sources fetched, 109 claims
extracted, top 25 adversarially verified (3 independent refutation votes each).
Result: 12 confirmed, 2 refuted, 11 unverified (verifier infrastructure
failures — see Coverage gaps). Epic docs cite findings as **F1–F8**.

Anchor systems, all shipped within the research window: **Karpathy's llm-wiki
gist** (2026-04-04), **obsidian-second-brain** (~3.0k stars, created
2026-03-24), **Basic Memory** (3.4k stars, AGPL, v0.22.1 2026-06-13).

## Confirmed findings

**F1 — Markdown + git + derived rebuildable index is the converged substrate**
(high confidence, 3× unanimous). Karpathy: "The wiki is just a git repo of
markdown files." Basic Memory: "Just files plus a local SQLite index… the
source of truth is always your files." obsidian-second-brain: plain markdown,
embedding index is a gitignored regenerable cache, and the plain-file substrate
is what let one vault serve six different agent CLIs. Critiques (penfieldlabs,
The New Stack) note git/markdown lacks ACID/RBAC for simultaneous multi-agent
writes — which argues **for** a single write chokepoint, not against the
substrate. Pack federation is *consistent with* this evidence but not
demonstrated by it.

**F2 — Lexical retrieval must be BM25-grade; hybrid is the expected upgrade
path, not a rejected alternative** (high confidence, 2× unanimous). Decisive
measurement lineage (obsidian-second-brain, ~1,150-note vault, self-measured):
naive keyword scored **5.7% recall@10 → 80% after BM25-style fixes**
(stopwords, log-saturated TF, length normalization). Optional local-embedding
fusion took it **80% → 91%**, and paraphrased queries **17% → ~46%**. Basic
Memory made hybrid FTS+vector the *default* (local FastEmbed model, no API
key) with graceful keyword-only fallback. Keyword-only carries a measured
paraphrase blind spot (17% recall@10).

**F3 — A flat INDEX.md stops working as the agent's primary retrieval at
~100–200 pages** (high confidence). Karpathy: index-first-then-drill "works
surprisingly well at moderate scale (~100 sources)… as the wiki grows you want
proper search." agentmemory's author from production: "don't rely on it as the
LLM's primary search mechanism past ~100 pages." Keep the index as a
human-readable catalog; keyword-class search is load-bearing above the knee.
(Directly applicable to clauDNA's `/remember` INDEX.md-scanning pattern.)

**F4 — Partition write authority explicitly by layer** (high confidence).
Karpathy's three layers: immutable human sources ("the LLM reads but never
modifies"), an agent-owned derived layer, and an always-loaded schema/
conventions doc governing structure. obsidian-second-brain enforces
conventions with a **write-time validator hook** and keeps one residual human
gate ("never deletes or modifies destructively without explicit confirmation").

**F5 — Curation is maintenance-by-review; supersession beats decay** (high
confidence). Karpathy's "lint" pass: contradictions, stale claims superseded
by newer sources, orphan pages, missing cross-references. No verified system
ships TTL/expiry-based *deletion*; the one decay experiment drew direct
pushback ("the right primitive is explicit supersession, not decay").
obsidian-second-brain automates the full loop — post-compaction capture agent
plus four cron librarians (nightly reconcile/synthesize/heal-orphans, weekly
review, health audit) with automatic contradiction resolution — **but offers
no longitudinal anti-rot evidence**, and destructive ops still require human
confirmation. Human-gated vs fully-automated promotion is an open bet; the
conservative side is the gate.

**F6 — AI-first note conventions with per-claim provenance** (medium
confidence, single source). Notes written for future-agent consumption:
machine-readable structure, per-claim recency markers ("as of 2026-04,
source.com"), mandatory wikilinks, verbatim source URLs, confidence levels
(`stated|high|medium|speculation`), plus a ~120-token always-loaded
critical-facts file — enforced by the write-time validator.

**F7 — Encode the graph in the markdown; serve traversal from the derived
index** (high confidence). Basic Memory's shipped architecture: each file an
entity, typed wikilinks as relations, traversal served from the rebuildable
SQLite index — exactly the markdown-source-of-truth + SQLite-edges split.
Contrast class: sibling MCP memory servers put the graph in the database,
making graph-in-markdown the distinctive, deliberate choice.

**F8 — The MCP write-chokepoint is motivated but unvalidated** (low
confidence, synthesized). Basic Memory is an existence proof (a local MCP
server over the identical substrate); the ACID/RBAC critiques point at exactly
the gap a serialized write chokepoint fills. But no verified source
demonstrates a chokepoint working or failing in production multi-agent use —
the four papers speaking to it directly all failed verification (below).

## Refuted — do not cite

- Basic Memory "explicitly rejects transcripts/RAG/vector-DBs" DON'T list (0–3)
- agentmemory's 95.2% LongMemEval hybrid-retrieval benchmark (0–3)

## Coverage gaps (unverified ≠ false — re-verify before citing)

All verification of **multi-agent shared-write governance** failed on
infrastructure errors (session limits), so research sub-question 4 is
*unanswered, not settled*. Papers awaiting re-verification: arXiv 2606.24535
(leakage/stale-propagation/provenance-collapse taxonomy; measured 0.439
cross-fleet leak rate in one production system; dedup-before-contradiction
ordering hazard at a write chokepoint), arXiv 2606.00007 (gated
proposed→active lifecycle as formal analogue of draft→verified→canonical;
commit-reveal voting worth +8.2–8.6pp precision), arXiv 2604.27283 (blind
top-k memory injection harming coding agents: 17.5% false-positive injection
vs 0% for abstention-aware retrieval), arXiv 2605.05242 (grep-agent beating
embeddings at 100K docs; direct-interaction scale ceiling). Also unanswered:
pack-federation demand (sub-question 6) and the mem0/Letta/Zep contrast layer.

## Caveats

Recency/survivorship bias: all anchors <4 months old; "worked" = shipped and
adopted, not longitudinally validated. Headline recall numbers are
single-author, self-measured, one vault. Attested scale envelope ~100–1,200
notes; Claudron's low-thousands top end sits at its edge.

## What this changes in the roadmap

| Claudron bet | Verdict | Action |
|---|---|---|
| Markdown+git substrate | **Supported (F1)** | none |
| FTS5-over-embeddings default | **Supported as floor (F2, F3)** — hybrid is the expected ceiling | E4 designs the hybrid upgrade path (RRF fusion, local model, kill switch) with named triggers; eval set gains paraphrase cases |
| Wikilink graph via derived index | **Supported (F7)** | none |
| Hook-based capture at compaction | **Supported (F5)**; PostCompact-payload variant noted | E2 supports both PreCompact/SessionEnd; recall gains an abstention threshold (2604.27283 caution, unverified) |
| Promotion lifecycle | **Supported (F5)** with amendment | E5: expiry becomes a review trigger, never deletion; `superseded_by` link is the terminal primitive; contradiction candidates join the review queue |
| MCP write-chokepoint | **Silent/indirect (F8)** | Keep (motivated by F1's ACID/RBAC gap); add dogfood validation metrics; re-verify the four papers when limits reset |
| Schema (new from F4/F6) | — | E1 adds `superseded_by` + `confidence` enum + per-claim provenance conventions + always-loaded `CONVENTIONS.md` |

## Addendum (2026-07-07): Graphify — the data point the sweep missed

**What it is** (verified via GitHub API + repo README): `Graphify-Labs/graphify`
— **79.4k stars / 7.8k forks, created 2026-04-03, MIT, YC S26**, v0.9.9
released 2026-07-07. Turns any folder (code via deterministic tree-sitter
across 36 languages; docs/PDFs/media via *optional* LLM passes; wiki links
become edges) into a queryable knowledge graph: portable `graph.json` + HTML
viz + report, consumed via `/graphify` slash command, an MCP server
(`query_graph`/`get_node`/`shortest_path`), and always-on hook guidance.
Edges are provenance-tagged `EXTRACTED` vs `INFERRED`; Leiden community
detection summarizes subsystems. Self-reported benchmarks (not independently
verified): LOCOMO recall@10 0.497 vs mem0 0.048; LongMemEval-S 76% QA,
with a published BENCHMARKS.md + judge-validation methodology.

**Why the original sweep missed it:** all five search angles were
memory-shaped ("AI brains," markdown memory, curation, memory-layer
products). Graphify is filed by the ecosystem under code-understanding /
GraphRAG (its topics: `graphrag`, `tree-sitter`, `knowledge-graph`) — it
**maps existing corpora; it does not accumulate memory**. A map, not a
brain. Structurally out-of-frame for the research question, but too big and
too adjacent to leave out of the appendix.

**What it changes for Claudron:**

- **F7 gains a third contrast architecture.** Graph-in-markdown (Basic
  Memory ≈ Claudron) · graph-in-database (memento-class MCP servers) · now
  **derived portable graph artifact** (Graphify's rebuildable `graph.json`
  compiled *from* content). Claudron's bet is unchanged — our content *is*
  the graph, the index is derived — but the derived-artifact pattern at 79k
  stars validates "rebuildable, disposable index" as the field consensus.
- **Convergent evidence for E2/E5's shape, from the space's biggest tool:**
  Graphify's bolt-on memory layer (`save-result` → `memory/`, `reflect` →
  `LESSONS.md` with provenance, a learning overlay tagging nodes
  `preferred|tentative|contested`, recency-weighted) independently converges
  on capture → reflect → trust-tagged curation — Claudron's loop and
  maturity axis, arrived at from the opposite direction.
- **The moat statement sharpens** (ironclad ceo-lens): the *map* layer is
  now commoditized — a three-month-old tool owns "understand this repo
  cheaply." The open ground is exactly Claudron's lane: **accumulated,
  governed, portable fleet memory** (cross-session, cross-machine,
  multi-writer, curated, federated). Complement, not competitor: the same
  bot can run Graphify to understand a repo and Claudron to remember what
  the fleet learned about it. Claudron should not drift toward codebase
  mapping — that race is over.
- **Mission principle validated, not contradicted:** Graphify's split —
  deterministic extraction where possible (tree-sitter), LLM strictly
  optional and off the default path — is the same posture as "no LLM at
  index time; authors write the wikilinks."
- **Concrete borrowables:** `EXTRACTED`/`INFERRED` edge provenance (E4's
  edges are all author-written = EXTRACTED by construction; tag inferred
  relations if a `[vector]` tier ever adds them); their MCP tool-surface
  naming as prior art for E3; their published-benchmark discipline as the
  model for publishing E4's eval numbers; joins Basic Memory on the **G1
  adopt-vs-build spike list** (expected frame: consume-not-adopt — wikilink
  edges are trivially derivable and node semantics differ — but the spike
  decides).
