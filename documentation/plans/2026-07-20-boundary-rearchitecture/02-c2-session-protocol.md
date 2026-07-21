---
title: "C2 — Session-loop protocol: four roles, a declared claim, and --source-url"
type: plan
status: draft
owner: chris
tags: [plan, claudron, session, hooks, protocol]
created: 2026-07-20
updated: 2026-07-20
---

# C2 — Session-loop protocol (Claudron)

> **Status: in flight.** Scope amended once, before implementation: **Claudron
> #81 (C1 residue) rides this phase** as step 5 — it reopens the same contract
> doc and the same test class, so it has no cheaper home. Two findings from the
> codebase-comparison pass are recorded inline: step 3's SCHEMA.md change is a
> **no-op** (the rows already exist), and the Verification Checklist's
> `--source-type article` example was **wrong** against the ratified vocabulary
> and is corrected below. Neither is a fork amendment; F1 and F7 stand as locked.

## Summary

Turns the session loop from two repos' implementation lore into contract text with one owner per
role (§10.5.1): continuity brief (clauDNA) · recall brief (Claudron) · capture prompt (Claudron
defines; exactly one holder per session) · sync (Claudron). Replaces the `hooks.py` clauDNA
plugin-sniff with a **declared claim** (F1 lean: env override + the existing glob specified as the
interim fallback), and adds `capture --source-url` (F7 lean) so consumers stop folding provenance
into body-line position.

## Evidence

- The sniff: `claudron/hooks.py:62–69` (`_claudna_installed` globs `~/.claude/plugins` for a dir
  named `claudna`); consumed at `hooks.py:121` (PreCompact returns silently when found). An R5
  violation — the engine infers a consumer from its install tree.
- The protocol today is scattered: `claudron/hooks.py:1–16` (module docstring), clauDNA CHANGELOG
  0.17.0 "hook stacking" note, `2026-07-09-claudna-claudron-reconciliation.md` §3. No normative
  text anywhere.
- Role split already half-practiced: clauDNA registers no SessionEnd hook (its `hooks.json` wires 5
  events, none SessionEnd; CHANGELOG: "SessionEnd is Claudron's `sync --push`").
- Ordering invariant already load-bearing: `hooks.py:72–95` (`session_start_brief` — pull precedes
  recall, re-detect after pull).
- Provenance coupling: clauDNA `skills/capture/SKILL.md:51` folds `Source: <url>` into the trailing
  body line *because* `claudron capture` has no source flag and `session.py:_summary` reads the
  first body line.

## Implementation Plan

### Dependencies
C1 (the contract doc this section extends).

### Blocks
L2 (composer sets the claim env this phase defines), D1's provenance step.

### Steps

1. **`docs/CLI_CONTRACT.md` — add §Session-loop protocol** (decided: a section of CLI_CONTRACT, not
   a sibling doc — one normative home; INTEGRATION.md points at it). Contents:
   - The four roles and owners (table from §10.5.1), and that briefs *co-inject by design*.
   - Ordering: sync-pull precedes recall; recall injection is budgeted (`BRIEF_TOKEN_BUDGET`,
     which also covers the C1 hint line and any composed lesson pointers) and abstains below the
     floor; push happens at session end, bounded. **Combined-budget rule, stated explicitly:**
     per-brief caps only, by design — the continuity brief is the front-end's to budget; the
     engine's brief never exceeds its own cap; no cross-brief budget exists (named so context
     creep at SessionStart has an owner per brief rather than none).
   - **Single-prompt rule:** exactly one R-capture-prompt holder per session.
   - **Claim mechanism (F1 locked: structural consumer-defers).** The engine **always prompts**
     where its PreCompact hook is installed — front-end-neutral text ("distill this session's
     durable findings through your capture door — your capture skill if you have one, else
     `claudron capture --stdin` — then retry the compaction"); the engine never sniffs consumers.
     **Conformance rule for front-ends that ship their own prompt:** defer when the engine's
     PreCompact entry is registered — detected by the normative `hook pre-compact` command suffix
     (the same identity `merge_settings` keys on) in the standard settings files. **Transitional
     shim:** the existing plugin-dir glob (`hooks.py:62–69`) stays only until the front-end's
     defer ships, then is deleted — and the **release ordering is mandatory**: the engine's
     shim-removal release precedes or accompanies the front-end's defer release (defer-first
     while the shim lives ⇒ both yield, nobody prompts; the reverse ordering's worst case is a
     bounded double-prompt window, accepted).
   - **The hook-settings snippet shape, normative** (the surface L2 composes against): the three
     events, the command form `<executable> hook <event>` (runtime dispatch; `hooks install` is the
     installer verb), the identity rule consumers must preserve (`hook <event>` suffix — what
     `merge_settings` keys on), and the absolute-executable-path requirement. A consumer emitting
     these entries is a rendered copy and MUST carry a drift gate (R3; L4 implements it).
   - Fail-open contract (hooks never break a session) and the per-event timeout budgets.
2. **`claudron/hooks.py`:** rewrite the PreCompact prompt to the front-end-neutral text; keep the
   glob only as the documented transitional shim (comment cites the contract section and the
   removal condition — the front-end's defer release — instead of narrating clauDNA). No env
   consultation, no holder field: F1's structural mechanism needs neither.
3. **`capture --source-url <url> --source-type <type>` (F7 as locked — cites #44, #54/#55):**
   plumb through `cli.py` → `engine.compose_note`; writes optional frontmatter `source_url` +
   `source_type` (#44's field set; the spelling claudlobby's legacy `frontmatter-schema.md`
   already used); `SCHEMA.md` gains the optional-field rows in **one** approval-gated change
   (quote the diff in the PR). Close #44 on land; comment on #55/#54 deferring `last_verified` +
   typed anchors to that epic explicitly.
   - **Finding (2026-07-21): the schema change is a no-op — `SCHEMA.md` needs no diff.** Both rows
     have existed since schema v1 (§Frontmatter fields, optional; shipped in `bb84ee3`, ratified
     with 0.2.0), `source_type` already typed `url | file | inline`. F7's approval gate has nothing
     to gate. The phase carries the *plumbing* only, and the PR states this rather than
     manufacturing a change to satisfy the step's wording.
   - **Consequence for the vocabulary.** Because the enum is already ratified, the write door
     enforces it (`--source-type` takes SCHEMA.md's three values; anything else is exit 2) and
     `schema.SOURCE_TYPES` is pinned to the doc row by a parity test. Widening the vocabulary
     *would* be an approval-gated schema change, and is out of scope here.
   - **Scope of #44's closure: carry-through only.** #44's trailing clause — `find_duplicate`
     keying on `source_url` — is #55 step 4 and is **not** built here. The closing comment says so,
     so the residue stays tracked rather than silently dropped.
4. **`docs/INTEGRATION.md`:** link the protocol section; add the "one capture prompt" conformance
   line for front-ends that ship their own prompt.
5. **Inherited C1 residue — Claudron #81** (folded in 2026-07-21; ratifier: chris). Three items,
   all living in files this phase already opens:
   - **The §Environment doc-parity test pinned less than the contract claimed.** Nothing asserted
     that `--vault` beats `CLAUDRON_VAULT_PATH`, while `CLI_CONTRACT.md` claimed a test "pins it to
     the resolver." Resolution: **add the test** (#81's stated preference) rather than soften the
     claim — `TestEnvironmentDocParity::test_flag_beats_env`, two real resolvable vaults with the
     env *and* walk-up rungs both pointing at the loser. The self-disclosed `_RecordingEnv`
     bulk-read caveat is left alone: it is honestly documented in place, and is not what #81 asked
     for.
   - **A test pinned an unrelated pre-existing bug.** `test_oversized_conventions_still_overflow`
     asserted a `BRIEF_TOKEN_BUDGET` overflow as current behavior. #81 offered drop-or-xfail;
     **neither was taken.** Step 1 must state the combined-budget rule, and *"the engine's brief
     never exceeds its own cap"* is false in exactly this case — writing it unqualified would put a
     false promise into the contract. So the contract states the limit honestly (the cap holds
     *given a `CONVENTIONS.md` within its own budget*; the always-loaded layer is injected
     unconditionally and `validate` owns its budget), and the test is renamed to
     `test_oversized_conventions_is_the_stated_exception` — it now gates that sentence instead of
     recording an unowned surprise. **The behavior is unchanged; only its ownership is.**
   - **`.gitignore`'s `AGENTS.md` rule.** Reviewed and **kept** — confirmed intentional, no diff.
     The file is a stale local fork of `CLAUDE.md`, never tracked on any branch.
   - Also under this step: the phase-state row in `00-overview.md`'s status ledger, per the
     ledger's own rule ("update it in the PR that changes a phase's state").

## Test Plan

Write the hook tests first (red), then touch `hooks.py` (green).

- **Transitional-state matrix** (plugin dir present / absent): absent ⇒ engine prompts once with
  the neutral text (marker honored); present ⇒ engine yields (shim behavior, unchanged until the
  front-end's defer ships). A skip-marked test documents the end state (shim deleted ⇒ engine
  prompts in both cells) so the removal release flips it on rather than writing it then.
- Prompt-text test: the block reason contains no front-end name (grep: no `claudna` in the
  emitted prompt).
- `capture --source-url/--source-type` round-trip: frontmatter carries both; `validate --strict`
  passes; `--json` envelope unchanged.
- Doc-parity: role table matches `HOOK_EVENTS`; the snippet shape in the contract matches
  `settings_snippet()` output (the engine-side half of the L4 parity gate).

## Verification Checklist

- [x] One normative session-protocol section exists in CLI_CONTRACT naming the four roles, the
      consumer-defer rule + grep identity, the release-ordering rule, the snippet shape, and the
      combined-budget rule.
- [x] The engine's PreCompact prompt names no front-end (note: `hook <event>` is the runtime
      dispatch verb; `hooks install` is the installer — both spellings are per the contract).
- [x] `claudron capture --type knowledge --title t --stdin --source-url https://x --source-type
      url` writes both frontmatter fields and strict-validates. (**Corrected 2026-07-21:** this
      line read `--source-type article`, which is outside SCHEMA.md's ratified `url | file |
      inline` vocabulary. The SSOT wins over an illustrative example in a phase doc — the example
      was wrong, not the schema, and the write door now rejects out-of-vocabulary values.)
- [x] `hooks.py` contains no clauDNA-narrating docstring; the glob is commented as the
      transitional shim with its removal condition.
- [ ] Claudron #44 closed; deferral comment on #55/#54 posted. *(on land)*
- [x] **#81 (step 5):** `--vault`-beats-env test exists; the budget test gates a contract sentence
      rather than an unowned gap; the `.gitignore` rule is confirmed-and-kept.
      *(#81 closes on land.)*
- [x] **No release cut.** No version bump, no CHANGELOG release heading — the entry lands under
      *Unreleased*. A phase cuts a release only when a step says so, and none here does.
- [x] `pytest` green — 415 passed, 1 skipped (the skip is F1's end-state test, by design).

### Spec review — two false sentences caught and fixed (2026-07-21)

An adversarial spec review of the branch found **two contract sentences this phase wrote that the
code did not keep**. Both are recorded because the failure mode is the one this program exists to
prevent, and both were in the deliverable that matters most:

1. **The `source_type` vocabulary held only on the human path.** `choices` sat on argparse, so the
   flag was guarded and the `--stdin` key was not — while `CLI_CONTRACT.md` §capture and
   `schema.py`'s own comment both claimed *the write door* enforces it, and the contract sends
   every programmatic writer through `--stdin`. Exactly inverted: the spelling a consumer will
   actually use was the unguarded one. **Fixed at the door** (`cmd_capture`, exit 2 — the same
   answer it already gives the payload's other bad-argument shapes), with a test on the stdin path
   that asserts nothing lands on disk.
2. **"Enforcement of the conventions budget is `validate`'s job" was false.** W105 is a *warning in
   both tiers*, so `validate --strict` reports an over-budget `CONVENTIONS.md` and still exits 0 —
   a CI gate reading that sentence would go green over the very case the limit describes. **Fixed
   by saying so**: the budget is reported, not enforced, and nothing hard-enforces it. (Promoting
   W105 to a strict error would be an approval-gated SCHEMA change and is out of scope.)

Also from the review: `capture` joined the `--json` envelope-shape gate (a Test Plan bullet with no
gate behind it), the identity-rule parity test stopped being presence-only and now runs the
documented suffix through `_is_claudron_hook`, and `INTEGRATION.md`'s defer obligation gained the
transitional-ordering caveat it was restating without.

## What NOT To Do

- Do not delete the glob shim in this phase — its removal release must precede or accompany the
  front-end's defer release (F1's ordering rule), and that defer is D1-side work.
- Do not add `CLAUDRON_CAPTURE_OWNER` or any claim env — F1 locked the structural mechanism.
- Do not touch clauDNA's hooks or scripts — D1/L2 are the consumer sides.
- No new hook events; no MCP tools; no `last_verified`/typed-anchor fields (deferred to #54).

## Context

Area: Claudron hooks + engine + contract · Effort: M · Risk: medium (behavioral seam; mitigated by
the four-combination test matrix) · Priority: high — wave 2 opener; unblocks L2.
