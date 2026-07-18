---
title: "Gate G1 — verdict (provisional)"
type: decision
status: draft
owner: chris
tags: [gate, g1, dogfood, verdict, claudron]
created: 2026-07-18
updated: 2026-07-18
---

# Gate G1 — verdict

**Status: PROVISIONAL (draft) — engineering criteria met; the human↔fleet usage
signal is pending Chris's dogfood.** This is deliberately not a final PASS: per
the re-ironclad (Juncture D), a verdict written without real signals is
confirmation bias, and the quantitative signals below require live use only Chris
can produce. It records what *is* validated, defines the three retained signals,
and states the **one falsifiable PIVOT condition** — so the gate can fail, not
only pass. Fill the signal values from the dogfood, then flip `status: ratified`
with PASS or PIVOT.

## Validated in practice (engineering, not dogfood)

The wedge is validated by **adoption at the build level**, independent of usage
metrics:

- The SD-card loop works live and hook-driven (E2: capture on A → sync → B's
  SessionStart brief; proven at 0.2.0).
- The **vault-structure contract** shipped (P1/P2) — the fleet has a documented,
  `validate`-checked shape to conform to.
- **clauDNA reconciled** its hooks + terminology (#45; `/reflect`→`/capture`) and
  consumes the vault via the CLI door (#197) — the fleet-consumption path is live.
- **Concurrent-write safety landed** (PR-H) — the fleet can write without
  dropping index entries; `claudron status` now instruments index-vs-vault
  divergence, so silent index failures surface.

## The three retained signals (fill from the dogfood — Chris)

Lightweight per the operator's steer; no tracking tables. Read these from real
use on Chris's machines + the Pi fleet over a stretch of ordinary use:

| Signal | How | Value |
|---|---|---|
| **S1 — cross-boundary recall** | ≥1 concrete instance where a note captured on one machine/bot surfaced in another's brief/recall and was useful (a tally, not a metric) | _pending_ |
| **S2 — accumulation quality** | a one-time keep/junk skim of captured notes: roughly what fraction you'd want recalled again | _pending_ |
| **S3 — index health** | `claudron status` divergence stays ~0 through the run (missing/ghost); resync conflicts recover without note loss | _pending_ |

## The falsifiable PIVOT condition (decide before reading the data)

**PIVOT if any of:** S1 is **zero** (no cross-boundary recall ever fired — the
SD-card thesis unproven in use), **or** the S2 skim shows the vault is mostly
noise (capture accumulates junk, not signal), **or** S3 shows unrecoverable
index/resync loss. Absent all three, **PASS**. A PIVOT is a recorded strategy
change (fleet-first replan), never silently absorbed into "shipped anyway."

## What this verdict gates

On PASS: the next build proceeds — the **graph slice** (`resolve_wikilinks` +
`links`/`related`, scale-free) then **E5-lite** (maturity + `promote`); SQLite/FTS5
stays deferred behind the measured D6/F2 trigger (adopt-vs-build spike:
`2026-07-18-adopt-vs-build-spike.md`, verdict BUILD). MCP/E3 stays demand-gated
(`2026-07-18-decision-c-mcp-demand-gated.md`). On PIVOT: re-anchor per
`00-overview.md` §Gate G1.
