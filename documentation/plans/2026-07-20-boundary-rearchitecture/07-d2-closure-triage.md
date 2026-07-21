---
title: "D2 — Closure triage: reference payloads inside clauDNA skills"
type: plan
status: draft
owner: chris
tags: [plan, claudna, knowledge, triage]
created: 2026-07-20
updated: 2026-07-20
---

# D2 — Closure triage (clauDNA)

## Summary

Applies the Q-closure rule (boundary spec §10.3/§10.5.5) to the inventoried reference payloads
inside clauDNA skills — **shrunk to S** on review: the spec's §10.5.5 inventory is adopted as the
ledger (its default verdicts are *closure — stays* for every payload class), the durable
deliverables are the authoring-guide rule and the drift gates, and **move work is gated on the
promotion signal actually firing for a named payload** — not scheduled unconditionally. The
observation channel for that signal, named honestly: manual session evidence (a payload consulted
outside its skill's execution, seen in transcripts/handoffs) and capture-dedup hits (an agent
tries to capture content a skill already embeds). Imperfect by design; the default posture is
closure-stays, so a missed signal costs nothing. This ledger method is the template L3 step 1
reuses for lessons.

## Evidence

Verified inventory (v0.17.0 line):

- `skills/audit/access-path/scan-categories.md` (205 lines) — "Correct Layer Guidance": which
  cross-cutting concerns belong at which layer. Genuinely consultable architecture knowledge, also
  the lens's rubric.
- `skills/audit/security/scan-categories.md` (121 lines) — scanner/tool catalog per category.
- `skills/dbt/SKILL.md` — "Quick Commands" vendor cheat-sheet; infra verb depth files
  (`vercel/logs.md` 187, `modal/deploy.md` 168, `modal/logs.md` 145, `vercel/deploy.md` 155,
  `railway/deploy.md` 123) — vendor-CLI flag reference interleaved with procedure.
- `skills/ironclad/lenses/*.md` (6 files, 127–270 lines) — mostly method; embedded checklists.
- The sanctioned-copy precedent: `skills/_shared/output-guide.md` §3 renders Claudron SCHEMA.md
  enums under a CI drift gate with an `x-*` escape hatch (v0.16.0 #199) — the R3 pattern this
  phase reuses.

## Implementation Plan

### Dependencies
C1 (INTEGRATION.md + contract docs to cite as the move target's front door). Independent of C2/L*.

### Blocks
None (hygiene; shrinks the referential surface a marketplace update can silently change).

### Steps

1. **Adopt the ledger** (`documentation/planning/` per house style): the boundary spec §10.5.5
   inventory becomes the ledger verbatim, one row per payload with the default verdict recorded —
   audit scan-categories: **closure** (version with the lens method); vendor-CLI references in
   infra verb files: **closure** (operands of the procedure; the vendor surface is versioned by
   the vendor, not an ecosystem SSOT); ironclad lenses: **closure**; init-project templates:
   **closure** (stamped artifacts version with the skill). Each row names its promotion signal.
   No unconditional move step exists.
2. **Signal-gated moves (deferred by default):** when a row's signal fires (session evidence or a
   capture-dedup hit naming that payload), capture the payload to the vault (typed, deduped),
   replace in-skill content with a pointer line — one payload per small PR.
3. **Gates for renders:** any payload kept as a rendered copy of an external SSOT gets the
   output-guide-§3-style CI drift gate (audit: none currently beyond output-guide §3 itself —
   assert that in the ledger).
4. **SKILL_CONTRACT note:** one paragraph in the authoring guide codifying Q-closure for future
   skills ("reference that tracks the world belongs in the vault; reference that tracks your
   method belongs in your skill").

## Test Plan

- clauDNA CI (skill-contract checks) green; every future replaced payload's pointer resolves
  (lint: no dangling paths).
- For any moved note: `claudron validate --strict` green; recall surfaces it by its tags.
- Drift gates fire on a deliberate fixture mismatch (one-off local check).

## Verification Checklist

- [ ] The ledger exists with a verdict + one-line rationale + named promotion signal per
      inventoried payload.
- [ ] Any signal-fired move: the payload exists as a vault note, its skill carries a pointer, and
      the skill's smoke invocation (named per row in the ledger, with expected output) matches its
      pre-move fixture — plus skill-contract CI green.
- [ ] The authoring guide states the Q-closure rule.

## What NOT To Do

- No bulk moves without the ledger — the default posture is *closure stays*; moving rubric content
  breaks skills for a purity win the boundary does not ask for.
- Do not fork content into both homes without a drift gate (R3).
- Do not touch `_shared/claudron-engine.md` / `output-guide.md` — already conformant.

## Context

Area: clauDNA skills · Effort: S (shrunk from M on review — the ledger adopts the spec inventory;
moves are signal-gated) · Risk: low (default posture is no-move) · Priority: medium — wave 3;
the named first cut if the solo-maintainer stall materializes.
