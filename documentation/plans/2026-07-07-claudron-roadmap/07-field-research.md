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
