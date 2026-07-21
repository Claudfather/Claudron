---
title: "Ironclad review — boundary re-architecture, cycle 1"
type: review
status: completed
owner: chris
tags: [review, ironclad, boundaries, claudron, claudna, claudlobby]
created: 2026-07-20
updated: 2026-07-20
---

# Ironclad review: Boundary re-architecture — implementing §10

**Cycle:** 1 · **Target:** plan (epic + 9 phase docs) · **Lenses:** 8/8 completed
(first-principles, adversarial-review, cost-benefit, precedent-check, plan-health-audit,
align-to-mission, engineering-review, devex-review; extension-check n/a — plan-only target,
its codebase-verification half was carried by engineering-review, which validated ~40 Evidence
file:line claims across the three repos and found only cosmetic drift).

**Disposition: all findings below were folded into the plan docs in this same cycle**
(the reforge edits are in the plan directory's history).

**Convergence (updated 2026-07-20, post-ratification): CONVERGED** — zero open Blockers after
fold, and all eight forks locked by chris in the same-day ratification pass: F1 → structural
consumer-defers, chosen via `/weigh-development-paths` over the folded env-var lean (the sniff
actually dies; a release-ordering rule prevents the defer-first silent-no-prompt state); F2 →
per-bot standard hooks; F3 → **hard cut** of `CLAUDRON_VAULT` in C1 (diverging from the
warn-then-remove lean; failure-path hint + pre-merge grep sweep as the safety); F4 → migrate
without the renderer (L3 shrinks L→M; compose-time CLI use eliminated program-wide); F5 → doc
only; F6 → minimal stable subset; F7 → `source_url`+`source_type` at one schema gate; F8 → CI
drift gate, stale-live-values scope. The wave-1 entry gate is satisfied; the program is ready for
implementation.

## Blockers (1 — resolved by fold)

- **[critical · adversarial] The `Bash(claudron *)` wildcard grant defeated human-gated curation.**
  L2's original step 4 granted every vault-wired bot the full verb surface — including `promote`,
  `plug`, `unplug`, `config`, `migrate` — contradicting spec §8 ("agents capture as draft; humans
  promote"). Its rationale was also wrong: settings hooks are harness-executed and need no grant.
  → Folded: narrow allowlist (lookup/recall/capture/status) as the composed default; wildcard
  banned program-wide (overview What-NOT + an L4 invariant); fresh-box asserts promote is denied.

## Risks (majors — all folded)

1. **[4 lenses] The composed hook snippet was a rendered copy with no contract text and no drift
   gate** — the program's own R3 anti-pattern. → C2's protocol section now carries the snippet
   shape as normative text; L4 gains the parity gate against the pinned engine's
   `settings_snippet()`; L2 cites both.
2. **[3 lenses] Loop liveness was unobservable in steady state** — fail-open everywhere, hooks.log
   unread, only compose-time checks; plus fleet-scale SessionEnd contention could silently drop
   pushes under the 10s budget. → L1's doctor gains loop-execution evidence rows; L2 gains an
   N-bot (≥8) contention test, an injected-brief fresh-box assertion, and the
   unpushed-work-travels-next-cycle statement; new high-severity risk row in the overview.
3. **[3 lenses] The glob fallback's removal promise was unmeetable on workstations** (the claim env
   is composer-set on fleets only; clauDNA ships no settings writes). → Re-labeled the permanent
   zero-config mechanism for non-fleet hosts; F1 rewritten; no removal schedule exists.
4. **[devex] No engine version/capability probe existed** though D1's guard, L1's floor check, and
   the mixed-version-fleet mitigation all depend on one — the only detection ladder lived in a
   consumer's private doc (inverted ownership at the seam the program leans on hardest). → C1 adds
   `engine_version` to `status --json` + the stable field set; INTEGRATION.md gains step 0; D1's
   guard is probe-based (floor-vs-probe question decided: probe).
5. **[devex + first-principles] Claim-mechanism failure modes were silent** (typo'd value ⇒ nobody
   prompts; truth table only in tests). → The decision table is contract text; `claudron` is a
   reserved value; `status --json` exposes the effective holder; Claudlobby doctor checks
   claim-owner-composed ⇒ owner-plugin-present; C2's matrix is now six cells.
6. **[adversarial] L1's doctor would have reported deliberately-unshipped surfaces as "unmet"**
   (the parked MCP fragment; a nonexistent `claudron review` verb) — the phantom-MCP pattern
   reborn through the check that replaces it. → COMPAT_FLOOR amended in the same PR: parked ≠
   unmet; review row dropped/re-keyed; session-loop row added.
7. **[engineering] Two phase contradictions:** L1's validator `detect()` import vs L4's
   paths.py-only invariant (→ routed through a `paths.py` helper; invariant scoped to runtime
   modules, tests exempt); L3's compose-time CLI shell-out vs L2's prohibition (→ the overview now
   states the reconciled rule: compose-time CLI use only with a defined CLI-less degradation +
   loud warning, never for settings emission; L3's degradation cell defined).
8. **[adversarial] L3's bulk migration mis-classed behavior lessons as reference** — a behavior
   rule rendered as a vault pointer is inert (e.g. `messaging-channel-discipline.md`), and the
   "parity-checked" claim overstated. → L3 restructured triage-first (the D2 ledger method);
   behavior-class lessons re-home to protocols/guardrails and keep rendering in-context; the
   renderer test is honest about differing shapes; F4 rewritten with option (d) re-weighed at
   ratification.
9. **[precedent] The issue-tracker layer was undedupped:** provenance is tracked open work
   (Claudron #44, #55/EPIC #54) — F7 re-proposed a narrower version risking double schema churn
   (→ F7 now cites both; lean = #44's field set at one gate, extras deferred to #54 explicitly);
   Claudlobby #511/#512/#513 still carry stale MCP scope — #654's promised re-scope never executed
   (→ program gate 2: execute the re-scope; L1 dedups into #511, L2 into #512; #513/#251
   closed-or-re-scoped); #560–564 are in flight on the same surfaces (→ reconciliation named in
   L1's dependencies); #30/#43/#46 wired into C1/F2/C1 respectively.
10. **[first-principles] Wave 1 merged approval-gated SSOT amendments while §10 was draft and all
    forks open** — with every phase hard-coding its lean. → Program gate 1: §10 ratification +
    F1–F8 locked is the wave-1 entry condition; this review cycle is the ratification venue.

## Gaps (minors — all folded)

Combined-brief budget rule stated (per-brief caps by design, named owner per brief) · doc topology
decided (protocol = CLI_CONTRACT section; INTEGRATION.md points) · §Environment is the one
normative table, precedence-ordered, §Flags defers · three no-engine states distinguished
(ENOENT/127 vs exit 3 vs success) · removal target single-sourced + time-bomb test · F3 scoped to
`CLAUDRON_VAULT` only (`SHARED_DOCS_PATH` out of scope) · conformance checklist items
self-contained (R-numbers parenthetical) · INTEGRATION.md under CLI_CONTRACT change discipline +
canonical URL (used by L1's warning) · install section + hello-world added (F5 rewritten) ·
`[vault]`-pin vs host-CLI conflation fixed in L1/L4 (probe reads the host; pin governs the import;
L4's gate resolves the clauDNA ref from `bot.claudna_version`) · the second R5 violation (the
Claudlobby tree-walk, `cli.py:104–113`) was unscheduled — now C1 step 11 · D1's env-equivalence
test restated honestly (grep-gate + manual eval; the ladder is prompt text) · C1's checklist no
longer contradicts its own step 8 · D2's untestable "spot-run" criterion replaced with
fixture-matched smoke invocations · F5/F7 gained their missing Context fields · C1's §Blocks
synced with the sequencing table; D2's row parenthetical corrected · risk rows carry impact
levels · X1's authored texts referenced concretely (working tree + the two landing branches) ·
mission-hygiene riders added (Claudron mission letter in X1; Claudlobby sprint-focus #4 in L3) ·
post-wave-2 mission-metric checkpoint added (program gate 3) · cosmetic fixes (mission :36/:37;
26 lessons files; 13 `_shared/` files; `hook <event>` vs `hooks install` spelling clarified).

## Questions (answered in the fold)

D2's promotion-signal channel named (manual session evidence + capture-dedup hits; imperfect,
default is closure-stays) · L4's rename-map semantics specified (live values → skill-dir tokens;
stale-live-values only; F8(b) is the upgrade) · #644 P4 sequencing named in L2's dependencies ·
fork-ratification timing fixed (program gate 1) · L2's grant question resolved inside the Blocker
fix (hooks are harness-executed).

## Scope shifts from the fold

D2: M → S (ledger adopts the spec inventory; moves signal-gated; the named first cut under stall).
L4's two drift gates: pulled forward to wave 2. L3: triage-ledger-first restructure (its step 6
inventory folded into the same ledger). Program gates 1–3 added to the overview.

## What did NOT survive

- "Build MCP now" — no lens argued for it; adversarial-review's counter-plan (wiring-first, skip
  C2) was considered and rejected for re-creating the documented drift pattern, with its speed
  benefit noted as already captured by wave 1.
- Repo consolidation as the root-cause fix — first-principles checked and cleared it: the seams
  are runtime seams (plugin ↔ CLI ↔ composed env), not repo seams; the contract register targets
  the right layer.
- F3(b) hard-cut — kept as a live option in the fork (all known consumers are in-house), not
  adopted; the warn-phase lean stands with the time-bomb test making it honest.

## Net

The §10 boundary itself survived first-principles challenge intact — the contract-register idea
was independently reconstructed by the from-scratch comparison, and adversarial-review's
murphyjitsu concluded failure would be surprising *after* the Blocker and majors were fixed. All
are fixed in this fold. The plan's remaining distance to convergence is exactly the eight fork
ratifications (chris), which the wave-1 entry gate now makes explicit.

---
*Reviewed by /ironclad — cycle 1 · 8 lenses · findings folded via reforge same-cycle*
