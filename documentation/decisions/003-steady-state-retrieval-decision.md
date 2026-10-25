---
title: "Steady-state retrieval — how agents comb the vault at scale"
type: decision
status: draft
owner: chris
tags: [decision, retrieval, e4, e5, indexer, embeddings, graph, claudron]
created: 2026-07-19
updated: 2026-07-19
---

# Steady-state retrieval — how agents comb the vault at scale

**Status: draft** — records the routes and the recommended sequence; the actual
engine choice is **evidence-gated** (re-run the eval seed at real scale), so this
ratifies the *framework and default*, not a final build order.

## The question

At steady state — when the vault holds a lot of accumulated learnings — how do
fleet agents efficiently comb it for the right context on a task, without a slow
scan or a wrong answer? The proximate trigger was weighing a `claudron context`
command (relevance + wikilink expansion) for agent routing; the evaluation
showed that command is only the *orchestration* layer and the real question is
the retrieval *engine* under it.

## Evidence — this is live now, not hypothetical

Measured on the real vault (`chrisrogers37/crogs-claudron-vault`, 2026-07-19):

- **~85 indexed docs** (≈139 markdown files total), largest fleet
  `crog-eng-team` = 61 — **approaching the F3 retrieval knee (~100–200 notes)**
  where the flat JSON index + O(vault) full-text scan stops being viable as
  primary retrieval.
- **0% promoted — 132 notes all `unrated`.** The curation layer (E5) is entirely
  unexercised: there are **no canonical hubs**, so graph-navigation routing has
  no map yet.

So the vault is right at the edge where retrieval efficiency becomes real, with
the cheapest route (curation) untouched.

## The four routes

`claudron context` (the orchestration layer) inherits its efficiency from
whichever engine sits underneath:

- **A — SQLite/FTS5 (E4 scale half, deferred).** Indexed BM25 + an edges table.
  Fast at thousands of notes (not an O(vault) scan), stdlib-only. The roadmap's
  own scale answer, gated on the D6/F2 trigger (~1k notes / paraphrase-miss).
  Makes `lookup`/`context` fast. The **floor**.
- **B — Embeddings / vector (deferred further).** Semantic combing — "auth
  tokens" finds "OAuth credential rotation" with no shared words. The
  "comb-by-concept" instinct. Real infra (local model, RRF fusion). The **escape
  valve**, per D6.
- **C — Graph navigation + canonical hubs (substrate BUILT).** The mission's bet
  (*"graph traversal over vector similarity"*): an agent reads a canonical hub,
  follows curated `[[wikilinks]]` to leaves, never scans the whole vault. Routing
  intelligence lives in the **curated structure** (E5 promotion builds the hubs;
  the wikilink graph is the map) + the agent's navigation. Cheapest, most
  **token-efficient** for agents (read a small high-signal path, not 20 full-text
  hits). Substrate shipped (`related`, `links`, maturity ranking); the **hubs do
  not exist yet** (0% promoted).
- **D — `context` orchestration.** Thin, engine-agnostic — rides A/B/C. The
  interface, not the answer.

## Decision (default; evidence may reorder)

1. **Cheapest high-leverage move first: curation (E5), not a new engine.** The
   vault is 0% curated — promoting the load-bearing notes to `canonical` builds
   the hubs Route C needs. This is the mission thesis (structure routes, not a
   vector index) and it is token-efficient for agents. It needs no new code —
   `claudron promote` shipped (E5 PR1).
2. **When the vault crosses the F3 knee, build FTS5 (Route A).** At ~85 notes and
   climbing, this trigger is near. FTS5 is the fast floor under both `lookup` and
   Route C. Measured, stdlib, no new deps.
3. **Embeddings (Route B) only if the eval proves it.** Re-run the eval seed
   (`claudron/tests/eval/`) **against the real vault** (not the 9-note reference
   fixture): if the paraphrase-miss rate crosses the F2 threshold, the vector
   tier earns its place; otherwise skip it (graph-over-vectors holds).
4. **`context` (Route D) is the last mile** — build it once there is a real
   engine and real scale to route over; it wraps A + C cleanly and is the natural
   shape of a future MCP `context` tool.

## The gate — what actually decides the engine

The route is not chosen from an empty vault (that is the SQLite-before-the-trigger
trap). It is chosen by **re-measuring at real scale**: run the eval seed against
`crogs-claudron-vault` and read *what breaks* —

- retrieval too **slow** (O(vault) scan) → build **FTS5 (A)**;
- **concept/paraphrase** misses → consider **embeddings (B)**;
- **graph too sparse to navigate** (few links, no hubs) → the gap is **curation
  (C)**, not a new engine.

The current 0%-promoted state predicts the gap is **C** today. That is the first
thing to fix, and it is free.

## Boundary note (why this doc lives here)

This is a **Claudron project design decision** (how the software retrieves), so
it lives in the repo's `documentation/`, versioned with the code and
PR-reviewed — per the ecosystem plane doctrine (repo-coupled records with the
repo; the vault holds cross-project referential knowledge). It is *not* a
`_shared/` vault decision. Related: `04-indexer.md` (E4/FTS5 + the `[vector]`
tier design), `05-lifecycle.md` (E5 curation), `2026-07-18-adopt-vs-build-spike.md`.
