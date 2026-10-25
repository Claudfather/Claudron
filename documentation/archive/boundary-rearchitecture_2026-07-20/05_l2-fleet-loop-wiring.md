---
title: "L2 — Wire the fleet loop: engine hooks per vault-wired bot"
type: plan
status: draft
owner: chris
tags: [plan, claudlobby, session, hooks, fleet]
created: 2026-07-20
updated: 2026-07-21
---

# L2 — Wire the fleet loop (Claudlobby)

## Summary

The largest payoff of the program (§10.5.1's verification finding): fleet bots currently run **no
Claudron session loop** — no pull-before-recall, no SessionEnd push; vault sync on a fleet host is
unowned. This phase makes the loop a composition concern: `claudron_vault_path` set ⇒ the composer
installs the engine's hooks into the bot's settings, per the C2 protocol. Declarative, per-bot,
fail-open — F2 as locked: per-bot standard hooks, no new machinery.

> **Corrected 2026-07-21 (title + this summary).** Both previously said the composer also "sets the
> claim env (`CLAUDRON_CAPTURE_OWNER=claudna`)" — residue from F1's pre-ratification env-claim
> lean. **F1 locked the *structural* mechanism instead: there is no claim env, and L2 composes
> nothing for it.** The engine always prompts where its PreCompact hook is installed; clauDNA's
> hook defers when it finds that hook registered. Step 3 and the Verification Checklist were
> already correct; the title and summary were not. Flagged by the C2 session on hand-off.

## Evidence

- No composer path installs Claudron hooks: `composer.py::_compose_hooks` composes only
  fleet.yaml/system hooks (default `bot-vitals.sh`); no `lib/` script runs `claudron hooks install`.
- The engine's hooks are settings-mergeable by design: `claudron/hooks.py:184–236`
  (`settings_snippet`, `merge_settings` — idempotent, self-replacing per event, foreign entries
  untouched) and fail-open (`run_hook`, `hooks.py:161–172`) with bounded budgets
  (`SESSION_START_PULL_TIMEOUT=2.0`, `SESSION_END_PUSH_TIMEOUT=10.0`).
- Shared-host concurrency is already handled at the engine: `locking.py` flock per host;
  `sync.py:90–165` bounded git ops under the write lock.
- The recall wedge exists but is opt-in and manager-scoped: `lib/dispatch-task.sh:98–125`
  (`CLAUDRON_QUERY_BEFORE=1`), pointers only.
- The session-boundary verbs the loop composes with: `start-bot.sh:296–322` (`/claudna:session
  resume --auto`), `pre-stop-handoff.sh:46` (`/claudna:session handoff --auto`, weekly-restart
  path).

## Implementation Plan

### Dependencies
C2 (the protocol section — including the **normative snippet shape** this phase composes against);
C1 (address contract the bots resolve by). #644 P4's remaining work
is named here: confirm sequencing with the grant-surface changes before this PR opens (the epic is
live on the surface step 4 writes to). L2's scope dedups into re-scoped #512 (the protocol-cutover
sibling: its dispatch-preflight/write-after overlays are the prompt-layer complement of this
hook-layer loop).

### Blocks
The fleet actually accumulating vault knowledge at session boundaries — the mission loop
("query Claudron before tasks and write findings after").

### Steps

1. **fleet.yaml surface:** per-bot / defaults key `claudron_session_loop: true|false` (default
   `true` when `claudron_vault_path` is set, `false` otherwise) — declarative wiring per the
   repo's own rule.
2. **Composer — settings:** when enabled, merge the engine's hook entries into the bot's composed
   `settings.local.json` per the **C2 contract's snippet shape** (three events; command form
   `<executable> hook <event>`; absolute executable path — resolve at compose time and record the
   resolution; a bare-`claudron` fallback is permitted only with a compose warning, since PATH may
   not survive hook context and the loop would be wired-but-dead). Do not shell out to `claudron`
   at compose time — emit the entries inline. This is a **rendered copy of an owner surface**: the
   L4 snippet-parity gate (compare against the pinned engine's `settings_snippet()` in a test —
   tests are exempt from the import invariant) is this step's drift protection and lands with or
   immediately after this phase.
3. **Single prompt on fleets — nothing to compose (F1 locked):** the structural mechanism needs no
   env. With the claudna plugin installed (the fleet default), its defer check finds the engine's
   composed `hook pre-compact` entry and yields the prompt to the engine's neutral text — which
   routes the agent to `/claudna:capture` anyway; bots without the plugin get the engine prompt
   directly. During the transition (fleet's plugin older than D1's defer release), the engine's
   shim yields to the plugin exactly as today — every transitional state is single-prompt on
   fleets. One validator note: no check needed; the F1 ordering rule is engine/clauDNA release
   discipline, not fleet config.
4. **Grants — narrow allowlist only (hooks need none):** settings-configured hooks are
   harness-executed and do not pass through permission evaluation — the loop itself requires no
   grant. Grants matter for *model-initiated* calls (the query-before wedge, `/claudna:capture`
   shelling the CLI): compose the narrow set `Bash(claudron lookup *)`, `Bash(claudron recall *)`,
   `Bash(claudron capture *)`, `Bash(claudron status *)` on vault-wired bots. **Never emit
   `Bash(claudron *)`** — the wildcard grants `promote`/`plug`/`unplug`/`config`/`migrate` and
   defeats human-gated curation (spec §8). Fresh-box asserts both directions: zero prompts on the
   allowed verbs, and a vault-wired bot **cannot** run `claudron promote`.
5. **Validator:** `claudron_session_loop: true` + no `claudron_vault_path` ⇒ error;
   loop enabled + CLI absent ⇒ the L1 warning covers it; claim-holder check per step 3.
6. **Docs:** fleet.yaml.example block; `documentation/integrations/claudron-integration.md` gains
   the loop section (what fires when, citing the C2 protocol as owner).

## Test Plan

- Composer unit tests: enabled ⇒ settings contain the three hook entries; disabled ⇒
  none; idempotent re-compose (self-replacing identity per event, no duplicates); wildcard
  grant never emitted (assert the literal `Bash(claudron *)` absent from every composed
  settings.local.json).
- Snippet-parity: composed entries match the pinned engine's `settings_snippet()` (the L4 gate,
  runnable here as a plain test).
- Fresh-box gate (`freshbox-boot-gate.sh`): a vault-wired bot boots clean with zero permission
  prompts on the allowed verbs, **an injected recall brief observed in the transcript** (not just
  registered hook entries), and `claudron promote` denied.
- **N-bot contention test (≥8 bots, one host, one fixture vault):** concurrent SessionEnd pushes
  serialize on the flock; count pushes that complete vs time out under the 10s budget; assert no
  hook exits nonzero and every timed-out push's commit lands on the *next* cycle (sync commits
  before pull — unpushed work travels next session). State in the loop docs whether the 10s
  budget includes flock wait (it does — the budget bounds the whole `sync` call), and note the
  weekly-restart stagger as the operational mitigation.
- Doctor: loop-execution evidence rows (L1's check) populate for the test bots.

## Verification Checklist

- [ ] A composed vault-wired bot's `settings.local.json` carries SessionStart/PreCompact/SessionEnd
      claudron hook entries (and no claim env — F1 is structural).
- [ ] The same bot with `claudron_session_loop: false` carries none of them.
- [ ] No composed file anywhere contains `Bash(claudron *)`.
- [ ] Fresh-box boot gate green, including the injected-brief and promote-denied assertions.
- [ ] N-bot contention test green with the push-loss accounting recorded in the PR body.
- [ ] On a live test bot: SessionStart injects a recall brief; PreCompact prompts exactly once
      (clauDNA's prompt, not the engine's); SessionEnd pushes within its budget.
- [ ] Repo test suite green.

## What NOT To Do

- Do not build a host-level sync daemon/timer in this phase — F2 lean is (a); the timer variant is
  the recorded fallback (tracked: Claudron #43) if the contention test or the post-wave-2
  checkpoint shows push loss.
- Do not install hooks via `claudron hooks install` subprocess at compose time (composition must
  work on CLI-less hosts).
- Do not emit `Bash(claudron *)` anywhere — narrow verb allowlist only (curation is human-gated).
- Do not enable the loop for bots without a vault path — the engine's hooks fail open but the noise
  is avoidable.

## Context

Area: Claudlobby composer/validator/lib · Effort: L · Risk: medium (touches every vault-wired bot's
settings; mitigated by fail-open hooks, fresh-box gate, per-bot off-switch) · Priority: high —
wave 2; the mission loop's missing half.
