---
title: "D1 — clauDNA conformance: env ladder, session.md surface, provenance"
type: plan
status: draft
owner: chris
tags: [plan, claudna, conformance, contracts]
created: 2026-07-20
updated: 2026-07-20
---

# D1 — clauDNA conformance (clauDNA)

## Summary

Brings the ergonomics layer into conformance with the contracts C1/C2 named: the env ladder stops
being inverted relative to the engine, the `session.md` handoff artifact becomes a declared stable
surface (F6 lean — Claudlobby consumes it today with no promise behind it), and provenance moves to
`--source-url` behind a floor guard. Small PR; no behavior change for users on current fleets.

## Evidence

- Inverted ladder (the §10.8.1 fracture): clauDNA resolves `CLAUDRON_VAULT` →
  `CLAUDRON_VAULT_PATH` → `SHARED_DOCS_PATH` (stated identically in
  `skills/_shared/documentation-standard.md:142`, `skills/index/SKILL.md:17`, `SETUP_GUIDE.md:554`);
  the engine resolves `CLAUDRON_VAULT_PATH` first (`cli.py:75–84`). Both set + disagreeing ⇒ the
  skill layer and the engine resolve different vaults.
- `session.md` consumption without a contract: Claudlobby `start-bot.sh:296–322` age-gates resume on
  it; `lib-common.sh:1098` documents parsing its `last_updated:` field — clauDNA nowhere declares
  the artifact stable.
- Provenance workaround: `skills/capture/SKILL.md:51` — trailing `Source: <url>` body line, keyed to
  the engine's `_summary()` reading the *first* body line.
- Floor mechanism exists: `skills/claudron/SKILL.md:6–8` (`requires: cli: claudron>=0.2`);
  `skills/_shared/claudron-engine.md` §1 detection ladder.

## Implementation Plan

### Dependencies
C1 (the §Environment table this conforms to). The provenance step additionally needs C2 shipped in
an engine release; it is floor-guarded and may trail in the same PR (guard) or a follow-up.

### Blocks
Nothing hard; L2 benefits (fleet bots resolve identically at both layers).

### Steps

1. **Re-order the ladder** to `CLAUDRON_VAULT_PATH` → `SHARED_DOCS_PATH` (fallback mode only —
   never consulted when the detection ladder found an engine), **dropping `CLAUDRON_VAULT`
   entirely** (F3 locked the engine-side hard cut; a consumer reading a var the engine ignores
   would re-create the two-vaults hazard in reverse) in all three stating locations
   (`documentation-standard.md:142`, `index/SKILL.md:17`, `SETUP_GUIDE.md:554`) and any
   code-adjacent echo found by `grep -rn "CLAUDRON_VAULT" skills/ SETUP_GUIDE.md`.
2. **Point, don't restate:** each of those locations cites Claudron `docs/CLI_CONTRACT.md`
   §Environment as the owner (R3), keeping only clauDNA-specific behavior (the mismatch notice,
   fallback-mode semantics) locally.
3. **Declare `session.md` stable (F6 lean):** in the `session` skill's docs, a "Stable surface"
   block: the file exists at `<cwd>/.claude/session.md` after handoff; `last_updated:` ISO
   timestamp is guaranteed; everything else is informal. Add the corresponding line to the
   CHANGELOG ("consumers may rely on…").
4. **Capture-prompt defer (F1 locked — the consumer half):** `precompact-reflect.sh` gains the
   defer check: when the engine's PreCompact entry is registered — grep the standard settings
   files (the `pretooluse-permissions.sh` read pattern) for a hook command ending `hook
   pre-compact` (the C2 contract's normative identity) — exit without prompting; the engine's
   neutral prompt covers the session, and this hook's rich `/claudna:capture` flow is still what
   the agent routes to. **Sequencing (mandatory, from F1):** this defer ships only at-or-after the
   engine release that removes its transitional glob shim — defer-first while the shim lives means
   both sides yield and nobody prompts. Gate it in the hook: activate the defer only when the
   probed `engine_version` ≥ the shim-removal release, or (simpler, maintainer-controlled) release
   this after the engine's removal release per the ordering rule — implementer's call, stated in
   the CHANGELOG either way.
5. **Provenance (F7, capability-probe-guarded — decided, not floor-guarded):** in
   `capture`/`publish`, probe the engine via `status --json` → `engine_version` (C1's version
   surface; version floors mis-read git-installed engines between tags — the ecosystem's actual
   distribution mode). Probe satisfied ⇒ pass `--source-url`/`--source-type` and drop the
   trailing-line fold; otherwise keep the fold. The fold's rationale comment updates to name the
   guard. claudron-engine.md §1's detection ladder gains the probe as its version step.
6. **CHANGELOG + version bump** per house rules.

## Test Plan

- Doc grep-gate (the executable check): no remaining `CLAUDRON_VAULT → CLAUDRON_VAULT_PATH`
  ordering strings anywhere in skills/ or SETUP_GUIDE. (The ladder is prompt text an LLM executes,
  so "both layers resolve the same vault" is not automatable — verify it as a manual/eval check
  against the retrieval fixture with both vars set and disagreeing, and record the observation in
  the PR body per house rules.)
- Manual: handoff → `session.md` carries `last_updated:`; resume path unaffected.

## Verification Checklist

- [ ] All three stating locations list `CLAUDRON_VAULT_PATH` first and cite the engine contract.
- [ ] `session` skill docs contain the Stable-surface block naming existence + `last_updated:`.
- [ ] With a `>=0.3` engine, a captured note carries `source_url:` frontmatter and no trailing
      `Source:` body line; with `0.2`, behavior is unchanged.
- [ ] Plugin version bumped; CHANGELOG entries present.

## What NOT To Do

- Do not touch the raw-tree fallback paths or INDEX.md scan — frozen (claudron-engine.md §4).
- Do not remove `SHARED_DOCS_PATH` — it is the fallback mode's variable; it only loses standing on
  the engine path.
- No new skills, no verb renames.

## Context

Area: clauDNA skills/docs · Effort: S · Risk: low · Priority: high — wave 1 (ladder), with one
floor-guarded trailing step.
