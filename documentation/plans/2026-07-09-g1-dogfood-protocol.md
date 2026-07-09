---
title: "Gate G1 — dogfood protocol & tracking checklist"
type: plan
status: active
owner: chris
tags: [gate, g1, dogfood, e3, claudlobby, claudna, claudron]
created: 2026-07-09
updated: 2026-07-09
---

# Gate G1 — dogfood protocol & tracking checklist

**This is the operational runbook for Gate G1.** The *decision* — that E3–E6
are evidence-gated options, that the gate emits a dated `G1-verdict.md`, that
the adopt-vs-build spike is a separate gate artifact, that multi-writer stays
parked — lives in `2026-07-07-claudron-roadmap/00-overview.md` §Gate G1 and is
unchanged. This doc adds *how the dogfood is run and read*, per the 2026-07-09
scope refinement.

## What changed on 2026-07-09 (and why)

The ratified G1 measured a **personal-first** dogfood, with the fleet as the
*failure* branch ("pulse fails → re-anchor on the fleet"). But the wedge thesis
is "shared knowledge for a human **and** their bot fleet, tied together" — so a
personal-only dogfood tests half of it. The refinement: **exercise the fleet
during G1's positive dogfood**, so the human↔fleet signal is observable when we
render the verdict. This does **not** reverse D1 (local-first) — the personal
loop is still primary and first; the fleet is added to make the shared-knowledge
half of the thesis testable.

Three guardrails keep this a *gate*, not a smuggled E3 build:

1. **CLI + git, not MCP.** The vault is plain git+markdown, and E2 already ships
   the surface the fleet needs: `claudron recall` / `capture` as shell-outs,
   `claudron sync` for resync. E3's own doc frames itself as "upgrading E2's
   shell-outs" — so the fleet-on-vault loop runs *today*, and where the
   shell-outs hurt becomes E3's design input. **Building the MCP server to pass
   G1 would have the gate build half of what it exists to decide.**
2. **Writes serialized.** `00-overview.md` §Gate G1 parks multi-writer claims
   "until a real fleet milestone exists (see E3)." Concurrent bot writes are
   exactly the races E3's write-lock is designed for and which are **not built
   yet**. So during G1, writes go through **one serialized path** (a single
   "librarian" writer, or low-frequency captures) — keeping the parked claim
   parked. Do **not** fix concurrency inside G1; if collisions happen anyway,
   **log them as E3 evidence** rather than patching them here.
3. **Signals pre-registered.** See below — fix the four thresholds *before* the
   clock starts and do not move them mid-flight.

## The four signals (pre-register before the clock starts)

"Decide the four signals" means: commit in writing to these four as *the*
criteria the verdict reads, each with a concrete threshold, **before** any data
exists. Deciding what counts as success *after* looking at the data is how a
PIVOT gets quietly written up as a PASS. Pre-registration is what makes the
verdict mechanical.

| # | Signal | PASS threshold | How measured |
|---|---|---|---|
| **S1** | **Cross-boundary recall works** | ≥3 *unprompted* instances over the 2 weeks where a note captured on one machine/agent (A) surfaced in another's (B) SessionStart brief or `recall` and was relevant — at least one in each direction (laptop↔fleet). | Tally in the log below: timestamp, note, A→B direction, useful? |
| **S2** | **Accumulation is signal, not noise** | notes/week > 0 and trending up **and** at a day-14 skim ≥~70% of captured notes are ones you'd want recalled again (not junk/dupes). High volume of noise = PIVOT signal, not PASS. | `claudron status` counts over time + a day-14 keep/junk skim |
| **S3** | **Resync holds** | ≤~1 conflict-quarantine event/week, and **every** one recovered without losing a note (bounded, documented action — not a data-loss scare). | `claudron status` quarantine count + a note per event (cause, recovery) |
| **S4** | **Hooks fired automatically** | The majority of captures originated from the PreCompact/SessionEnd path *without* you invoking them; SessionStart briefs appeared unprompted on both laptop and Pi. If you had to run `capture` by hand to get anything, the loop isn't real. | Spot-check capture provenance (hook vs manual) + confirm briefs appear at session start on both |

**Verdict logic.** All four clear → **PASS**. The *pattern* selects the next
epic (consistent with the overview's "E4 if the vault is growing toward the F3
knee, E3 otherwise"): a strong S1 (cross-boundary value) argues **E3 first**; a
strong-S2-fast-growth-but-weak-S1 argues **E4 first**. Any structural failure
(S2 mostly noise, S3 data-loss, S4 nothing fired automatically) → **PIVOT**,
recorded in `G1-verdict.md` with what changed, cross-posted to EPIC #14. A weak
*personal* pulse but strong *fleet* signal is not a plain fail — it re-anchors
toward E3-led, which the overview already anticipates.

## Setup (once, before the clock starts)

- [ ] **Vault as a private git repo.** `claudron init ~/vault --personal` (done
      on the primary machine already if the dogfood clock started), then create
      a **private** GitHub repo and `claudron --vault ~/vault sync` / push. This
      is the resyncable SD card.
- [ ] **Second personal machine** clones the vault; confirm `recall` reads it
      and `sync` round-trips.
- [ ] **Pi fleet wiring (CLI, per bot):** each bot `git clone`s the vault; set
      `CLAUDRON_VAULT_PATH` per bot (Claudlobby already emits this,
      `composer.py:448`); bots `claudron recall` at session start and
      `claudron capture` findings via shell-out; a scheduled/where-appropriate
      `claudron sync` resyncs.
- [ ] **clauDNA reconciliation** (see `2026-07-09-claudna-claudron-reconciliation.md`):
      point clauDNA's `SHARED_DOCS_PATH` at the vault; decide single hook
      ownership so SessionStart/PreCompact don't double-fire; confirm
      learn/reflect land schema-valid notes (lenient tier).
- [ ] **Pre-register S1–S4 thresholds** (copy the table, lock the numbers, date
      it). This is "decide the four signals."
- [ ] **Serialized-writer decision** recorded (who/what may write during G1).

## Two-week tracking checklist

Keep this running; it *is* the evidence attached to the verdict.

- [ ] **Week 1 mid** — `claudron status` snapshot (note counts per tier,
      quarantine count); first S1 instances logged?
- [ ] **Week 1 end** — status snapshot; S3 events (if any) noted with recovery;
      spot-check S4 (did hooks fire unprompted?).
- [ ] **Week 2 mid** — status snapshot; S1 tally check (on track for ≥3?).
- [ ] **Day 14** — final status snapshot; **S2 keep/junk skim**; assemble S1–S4
      against thresholds.
- [ ] **Write `G1-verdict.md`** (dated, in the roadmap dir) — PASS or PIVOT,
      pulse numbers + S1–S4 results attached; cross-post to **EPIC #14**.
- [ ] **Adopt-vs-build spike** merged as its own PR *before* any E3/E4 impl PR
      (separate artifact — not part of this dogfood; tracked here only as a gate
      dependency).

### S1 cross-boundary log

| date | note | A → B | useful? |
|---|---|---|---|
| | | | |

### Status snapshots

| date | notes total | per-tier | quarantined | S3 events |
|---|---|---|---|---|
| | | | | |
