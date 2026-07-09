---
title: "P3 — Fleet-scoped consumption (conditional, dogfood-gated)"
type: plan
status: draft
owner: chris
tags: [plan, vault, consumption, recall, claudron]
created: 2026-07-09
updated: 2026-07-09
---

# P3 — Fleet-scoped consumption (conditional)

## Summary

Resolve the two consumption findings from the audit, with two different
verdicts. **Tier-A cross-fleet pooling is intended** for a single-tenant vault
(the operator's accepted "one hub") — it gets *documented*, not fixed.
**Fleet-blind `recall` is the real gap** — the automated brief never scopes to a
fleet. This phase **specs** the fix (`derive_fleet()` + a fleet-aware `recall`)
but **builds it only if a pilot-fleet dogfood shows the blindness actually
degrades recall** (Fork F6). It may never ship — and that is a success state,
not a gap.

## Evidence (current state)

- **Tier A indexes every fleet unconditionally** — `build_index` walks
  `_shared` plus *all* `<fleet>/shared/` (`knowledge.py:196-203`), so a plain
  `lookup` pools cross-fleet. Tie-break is `project > fleet > shared`
  (`knowledge.py:430-437`).
- **`lookup --fleet` does not isolate** — the `fleet` arg only augments the
  Tier-B fallback scan (`knowledge.py:459-461`); it never filters Tier A. So
  `--fleet` widens, it doesn't scope.
- **`recall` is fleet-blind** — `session.recall` has no `fleet` parameter
  (`session.py:78-149`) and `cmd_recall` never passes one (`cli.py:511-513`).
  There is a `derive_project()` (`session.py:39-46`) but **no `derive_fleet()`**
  anywhere. The SessionStart brief (`hooks.py:72-95`) is therefore project +
  vault-shared only — it cannot narrow to the fleet a bot serves.

## Implementation Plan

### Dependencies

- **P1** — the consumption contract (query-don't-hardcode; pooling-is-intended)
  is documented there; this phase is its conditional code half.

### Blocks

- Nothing hard. If built, it sharpens the fleet dogfood's recall relevance.

### Gate (build-or-not)

Build **only if**, over ≥2 weeks of a pilot-fleet dogfood, fleet-blind `recall`
measurably hurts — bots receive cross-fleet noise in briefs, or miss their own
fleet's canon because it ranked below another fleet's. Mirror the roadmap's G1
pulse discipline: record a one-line verdict (build / skip) with the evidence.
Absent that evidence, **skip** — pooling is the accepted behavior.

### Steps (only if the gate passes)

1. **`derive_fleet()`** (`session.py`) — analogous to `derive_project()` but
   **not a pure mirror**: it needs the **vault root** to bound the upward walk
   (find the root-level ancestor under the vault carrying a `fleet.yaml`).
   Returns `None` outside a fleet (at vault root, or inside `projects/`).
2. **Thread `fleet` into `recall`/`session_start_brief` — and into the index
   path.** `recall` takes no `fleet` today and its hot path is `tier_b=False`,
   so a `fleet` argument never filters Tier A (`knowledge.py`); real scoping
   means adding a fleet filter to the Tier-A query, not just passing an arg.
   When a fleet is derived, scope the brief to that fleet's `shared/` +
   `_shared/`, ranked by the existing `tier_priority`. No fleet derived →
   today's behavior, unchanged. (This is why the effort is S→M, not a trivial S.)
3. **Preserve pooling as the default for explicit queries.** `lookup` stays
   cross-fleet; add an **opt-in** `lookup --fleet-only <f>` for a user who wants
   isolation. Isolation is opt-in; pooling is the default (single-tenant
   contract).

## Test Plan (only if built)

- `derive_fleet()` returns the fleet for a bot cwd inside `<fleet>/…`, `None`
  at vault root / inside `projects/`.
- `recall` with a derived fleet surfaces that fleet's `shared/` + `_shared/`,
  ranked by `tier_priority`; a sibling fleet's note does **not** appear in the
  brief.
- Cross-fleet reach is preserved: an explicit `lookup` still finds sibling-fleet
  notes (pooling intact); `--fleet-only` filters them.

## Verification Checklist

- [ ] **Gate recorded** — a dated build/skip verdict with dogfood evidence
      (this box is checkable even when the answer is "skip").
- [ ] (if built) `recall` in a fleet context excludes sibling-fleet notes from
      the brief while `lookup` still reaches them.
- [ ] (if built) no-fleet context is a **byte-identical** brief on a no-fleet
      fixture (diff the recall output before/after — not a subjective "no
      regression").

## What NOT To Do

- Do **not** remove Tier-A pooling — it is the desired single-tenant behavior,
  not a bug.
- Do **not** build a cross-tenant query surface — portfolio non-goal; E5's
  promotion is the sanctioned cross-scope mechanism.
- Do **not** gold-plate isolation before the dogfood asks. Default to **skip**.

## Context

Area: `claudron/` `session.py`/`knowledge.py` · Effort: **S–M** (S for
`derive_fleet` + recall-scoping; M if the Tier-A index filter is needed) · Risk:
low (additive; default path unchanged) · Priority: **low / conditional** —
dogfood-gated; the honest default is not to build it.
