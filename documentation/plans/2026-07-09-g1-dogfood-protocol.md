---
title: "Gate G1 — lightweight dogfood note"
type: plan
status: active
owner: chris
tags: [gate, g1, dogfood, e3, claudlobby, claudna, claudron]
created: 2026-07-09
updated: 2026-07-18
---

# Gate G1 — lightweight dogfood note

> **2026-07-18 — de-ceremonied.** The original version of this doc was a
> two-week runbook with four pre-registered signals, thresholds, and tracking
> tables. That was over-built for a solo operator dogfooding their own hub
> (operator steer: *"we do not need to be so rigid… it can be a bit more
> handwavey than that"*). The rigid protocol is retired; what a gate still needs
> is below. The decision context — E3–E6 are evidence-gated options, the gate
> emits a `G1-verdict.md`, the adopt-vs-build spike is a separate artifact,
> multi-writer stays parked — lives in `2026-07-07-claudron-roadmap/00-overview.md`
> §Gate G1.

## What the gate actually is now

**Validate by real use.** Run the vault on your machines and the Pi fleet via
the **CLI wedge** (E2's `recall`/`capture`/`sync` + the vault-structure contract;
**not** MCP — that's E3, which this gate decides). Over a stretch of ordinary
use, just notice whether it's working:

- recall surfaces useful context across machines and fleets,
- capture accumulates signal rather than noise,
- resync holds (conflicts quarantine and recover, not lose data),
- the hooks fire on their own rather than needing a manual nudge.

No pre-registered thresholds, no clock, no tracking tables. If it's clearly
working, that's a pass. **As of 2026-07-18 the wedge is largely validated in
practice** — the structure contract shipped (P1/P2), clauDNA reconciled its
hooks + terminology (#45; `/reflect`→`/capture`), and the fleet consumes the
vault via the interim query-before wedge (Claudlobby #528).

**Keep writes effectively single-writer** during the dogfood — the parked
multi-writer claim stays parked until E3's write-lock exists. Concurrent-write
collisions, if they surface, are E3 design input, not G1 bugs.

## The two things a gate still owes

1. **A short written verdict** — a dated `G1-verdict.md` in the roadmap dir, a
   few honest sentences (go / adjust / pivot), cross-posted to EPIC #14, before
   E3/E4's first implementation PR. A PIVOT is a recorded strategy change, never
   silently absorbed into "shipped anyway".
2. **The adopt-vs-build spike** — the one real gate artifact (a decision, not
   ceremony): a light eval of **Basic Memory** (ships MCP + hybrid search over
   the same markdown substrate) and **Graphify**, as its own writeup that merges
   before any E3/E4 build PR. Expected answer is consume-not-adopt, but it could
   collapse a chunk of E3/E4 — worth the look.

## Fleet-scoped recall (P3) rides the same dogfood

The vault-structure contract's **P3** (`derive_fleet()` + fleet-aware `recall`)
builds **only if** the dogfood shows fleet-blind recall actually hurts — bots
getting cross-fleet noise in briefs, or a fleet's own canon out-ranked. Same
run, one observation: if you notice that during real use, P3 is warranted; if
you don't, skip it (F6). Its build/skip note can live in the same `G1-verdict.md`.

See also `2026-07-09-claudna-claudron-reconciliation.md` for the clauDNA hook/
index seam (the SessionStart/PreCompact overlap #45 addressed).
