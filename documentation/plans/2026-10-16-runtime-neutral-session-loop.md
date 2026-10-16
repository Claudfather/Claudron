---
title: Runtime-neutral session-loop owner adapter
type: plan
status: active
owner: Claudron maintainers
created: 2026-10-16
---

# Runtime-neutral session-loop owner adapter

## Summary

Deliver the engine-owned Codex lifecycle snippet and its installer/diagnosis, and correct capture-prompt delivery for both supported agent CLIs. Capture instructions move from a PreCompact block reason to SessionStart(source=compact) stdout once per session, while the registered pre-compact identity remains as the structural ownership claim for released consumers.

## Evidence

- At baseline `bb4b72f`, `claudron/hooks.py:149-196` emits the capture instruction as a PreCompact block reason; `:276-314` renders only Claude settings and defaults to its user settings file.
- `claudron/doctor.py:376-465` compares installed entries with that same snippet and resolves their vault addresses without executing them.
- `docs/CLI_CONTRACT.md:220-404` owns roles, structural claiming, snippets and the 2-second pull / 10-second push budgets. The boundary register row 12 remains planned before this phase.
- The 2026-10-16 continuation in [the epic run log](https://github.com/Claudfather/Claudlobby/blob/main/documentation/plans/2026-10-04-runtime-neutral-observability-run-log.md) records actual Codex 0.162.0-alpha.17.2 stdin: SessionStart source startup/resume/compact, PreCompact manual and SessionEnd other. Common session_id fields already match the engine adapter. Hook SessionEnd's measured default is one second, so the Codex snippet must explicitly allow the engine push budget.
- Independent C3 review found no material findings: on native Claude Code 2.1.301 an actual auto-triggered PreCompact was followed by a same-turn main request after 10.544 ms without the instruction or further human input. The configured block branch was inspected and hashed; stdout was not separately captured. Successful manual compaction delivered SessionStart(compact) stdout to the next main request. Synthetic usage counters, fixed localhost responses, one CLI version and manual-only successful compact delivery limit the conclusion; no real-model uptake is inferred. Codex startup/compact stdout uptake was measured separately. This activates the ratified conditional correction in Claudron#179 / Claudlobby#2145 P4.

## Implementation Plan

### Dependencies

Measured C1/C3 and their independent procedure review. No telemetry floor-host week is a prerequisite. A released owner surface must precede consumer adaptation and fleet composition (R4/R6).

### Blocks

The Codex consumer hook manifest, the execution companion's Codex session-loop composition, and consumer capture-prompt adaptation to the corrected owner contract.

### Steps

1. Keep `hook pre-compact` installed and fail-open but noninjecting. After a successful SessionStart brief, append one neutral capture instruction only for source compact. Use an atomically created private temporary marker keyed by vault, agent CLI and validated session ID; no consumer detection, note writes or vault migration.
2. Extend `hooks.py`'s existing renderer, settings reader and merge with explicit `agent_cli` selection (claude default). The Codex snippet keeps the same three event/verb identities, selects `--agent-cli codex` before the `hook <event>` suffix and sets an explicit SessionEnd timeout above the engine's 10-second push budget. Install into CODEX_HOME/hooks.json, falling back to ~/.codex/hooks.json, only with --write; preserve unrelated settings and refuse malformed files.
3. Add `--agent-cli {claude,codex}` to hook dispatch, hooks install and doctor. Preserve Claude defaults and doctor D009/D010 machine/settings meaning; pass the selected renderer through diagnosis and fix re-diagnosis. Do not discover or execute other front ends' settings.
4. Change the owner contract, integration guide, README/instruction indexes, CHANGELOG, role/parity assertions and boundary-register row 12 in the same commit. Give Codex its own level-two normative section/fence and capability `codex-session-loop`, with an explicit gate sentence. Name a release ordering window for consumers; retain `hook pre-compact` structural deferral compatibility.
5. Verify separately prepared baseline/after exports, affected negative/positive cells, consumer compatibility and an actual CLI subprocess protocol canary against a private temporary vault. Have independent Codex simplify/review/verify assess the final artifact before any push/release coordinated by the root workstream.

## Test Plan

Run the complete current main suite in a history-free export/private HOME/TMPDIR, then the complete changed suite in another export using the same interpreter/dependencies; retain counts, names and exit codes. New tests cover startup/resume/clear vs compact delivery, repeat/concurrent compact, host/vault namespacing, malformed stdin/SID and fail-open marker failures; legacy PreCompact no stdout; both normative snippet parity blocks; Codex install/idempotent replacement/preservation/refusal; default CODEX_HOME targeting and per-front-end doctor drift/address remedies. A subprocess canary drives rendered commands with real CLI parsing and real temp-vault readback, without a provider or native fleet activation. Existing native C3 evidence proves the host delivery path; this canary proves the changed owner adapter, not semantic model compliance or fleet acceptance.

## Verification Checklist

- [x] Baseline and after suite counts, failing names and exit codes retained separately.
- [x] One capture prompt only on first compact SessionStart per valid session/agent/vault; no PreCompact block stdout.
- [x] Existing Claude command identities and structural consumer deferral remain compatible.
- [x] Codex renderer/install/merge/doctor agree and match their own normative fence.
- [x] Capability, release ordering, contract, CHANGELOG and boundary register describe the actual shipped source.
- [x] Private actual CLI canary passes; no real user settings, provider requests or production runtime touched.
- [ ] Independent simplify/review/verify converged on the exact source tree before root coordinates publication.

### Recorded verification

Independent history-free exports under Python 3.12.13 with identical dependencies returned **856 passed, exit 0** before and **887 passed, exit 0** after; no failing/error names in either. The new failing-first cells were retained separately, followed by **146 affected tests passed, exit 0**. The existing Claude snippet parity stayed unchanged. Five actual-native Codex lifecycle fixtures retain exact sanitized bytes and raw-input/transform hashes; no unobserved hook is invented.

Ten actual changed Claudron CLI subprocess arms exercised both selectors' rendered startup, PreCompact, compact, repeated compact and end commands against a private local-git-only vault. All exited 0 with empty stderr, instructions appeared exactly once per selector, private marker modes were 0600, both actual settings installs were idempotent, doctor selected each intended target, and the vault's tracked HEAD was unchanged. There were no provider requests. This is owner-command/protocol evidence; the native agent CLI was not invoked by this changed-owner canary, so native trust, semantic model compliance, production activation and elapsed fleet gates are not claimed. Independent source review remains the unchecked gate above.

## What NOT To Do

No consumer-name sniffing, note/schema/vault-shape changes, additional dependency, real provider inference, global settings modification, production activation, timed-gate waiver, fleet execution adapter, summarizer change, or inference that one controlled host sample proves universal automatic-compaction behavior. Do not remove the legacy ownership identity before consumers migrate.

## Context

Area: owned lifecycle protocol. Effort: M. Risk: prompt-delivery compatibility and settings correctness, bounded by preserved command identities, dual parity and independent review. Priority: critical path for Claudfather/Claudlobby#2145 P4. The operator delegated source review and eligible integration; live host/channel and timed acceptance remain separate.
