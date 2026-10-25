---
title: "L1 — Validate the real door: validator inversion, compat floor, dispatch tail"
type: plan
status: draft
owner: chris
tags: [plan, claudlobby, validator, claudron]
created: 2026-07-20
updated: 2026-07-20
---

# L1 — Validate the real door (Claudlobby)

## Summary

Resolves the §6 triggering example. The runtime stops warning about the absence of a door the
engine deliberately never shipped (an R6 violation) and starts validating the door that exists:
vault-wired ⇒ `claudron` CLI reachable + compat floor met. The `dispatch-task.sh` workaround built
on a fixed bug is removed with its false comment, and the decision-C amendment (trigger 1 re-scoped
after #644, boundary spec §10.5.2) is recorded where the monitor lives.

## Evidence

- The phantom warning: `claudlobby/validator.py:403–414` — `claudron_vault_path` set + no `claudron`
  MCP entry ⇒ *"the vault path won't be used without the Claudron MCP server"*; inverse warning at
  410–413. `library/mcp/claudron.json` does not exist (`library/mcp/` holds ten other fragments).
- The compat floor exists but is unwired: `claudlobby/claudron_compat.py` (COMPAT_FLOOR: bridge API
  0.2.0, CLI wedge 0.2.0, MCP fragment 0.3.0, review sweep 0.5.0); its docstring claims
  "`claudlobby doctor`'s claudron check reads this table" — `doctor.py` contains no claudron/vault
  check; the table's only consumer is its own test.
- The stale tail: `lib/dispatch-task.sh:103` comment *"the claudron CLI does not read
  CLAUDRON_VAULT_PATH itself"* — false since Claudron #62 (`cli.py:75–84` reads it); line 124 passes
  `--vault "$CLAUDRON_VAULT_PATH"` explicitly.
- Grant facts for the decision-C note: `composer.py:252–294` (`_resolve_integration_grants` —
  "CLI-backed (no tool_grants) — nothing"), `validator.py:69–79` (grant grammar: exact MCP tool or
  trailing `*`; `Bash(<cmd> ...)` patterns), `composer.py:1307–1454` (allow/deny union, deny wins).

## Implementation Plan

### Dependencies
C1 (the contract §Environment this validates against, and INTEGRATION.md's canonical URL to cite).
Program gate 2: the #511/#512/#513 re-scope (#654's promised follow-through) executes with or
before this phase — L1's doctor work **dedups into re-scoped #511** (its item 2d is this same
check), and the in-flight #560–564 branch is reconciled before this PR opens. #513 and #251
(mooted by decision C) are closed-or-re-scoped in the same pass.

### Blocks
L4 (gates build on the corrected validator posture).

### Steps

1. **Invert `validator.py:403–414`:** delete both MCP cross-check warnings. New check, same site:
   `claudron_vault_path` set ⇒ warn only when the *CLI door* is unhealthy — `claudron` not on PATH
   (compose-time best-effort: `shutil.which`), or the path fails vault detection **via a
   `paths.py` helper** (the sanctioned `[vault]` import seam — `_resolve_vault_fleet` is the
   precedent; the validator itself never imports `claudron.*`, keeping L4's invariant satisfiable).
   Warning text names the door and the canonical INTEGRATION.md URL: *"vault path set but the
   claudron CLI is not on PATH — bots reach the vault through the CLI (see <INTEGRATION.md URL>)"*.
2. **Amend COMPAT_FLOOR in the same PR, then wire it:** demand-gated rows (the MCP fragment) get a
   `parked` status rendered as *parked (decision C)* — never "unmet"; the `review sweep` row is
   dropped or re-keyed to the verb's actual epic (no `claudron review` verb exists at head); a new
   row records the session-loop surface (engine hooks installed per bot, engine ≥ the C2
   release). Then implement the `check_claudron` doctor section the docstring already promises:
   CLI presence, `claudron status --json` health (incl. `engine_version` from C1's probe — the
   host CLI is installed out of band; the `[vault]` pin governs only the imported API), floor rows
   met/unmet/parked, and **loop-execution evidence** per vault-wired bot (most recent
   `.claudron/hooks.log` degradation lines; last push timestamp) so a wired-but-dead loop is
   visible in steady state. Correct the docstring if the shape lands differently.
3. **`lib/dispatch-task.sh`:** replace line 124's `--vault "$CLAUDRON_VAULT_PATH"` with plain env
   reliance (`claudron lookup --json …` — the CLI reads the var); rewrite the 98–110 comment block
   to cite CLI_CONTRACT §Environment. Keep the `2>/dev/null || return 0` fail-open net **and** a
   one-line version-skew note (the host CLI can lag the repo pin) — drop only the false
   "does not read CLAUDRON_VAULT_PATH" sentence and the 0.1.x exit-code prose.
4. **Record the decision-C amendment where the monitor lives:** a short note in
   `documentation/integrations/claudron-integration.md` (the bump-policy home named by the
   pyproject pin comment): trigger 1 is re-scoped to adversarial-grade per-verb enforcement —
   #644's `tool_grants` + `tools.deny` already express cooperative-grade `Bash(claudron lookup *)`
   / `Bash(claudron capture *)` splits; cite boundary spec §10.5.2. (The decision doc itself is
   amended in C1 step 10; this is the Claudlobby-side pointer.)
5. **fleet.yaml.example:** correct the `claudron_vault_path` comment ("Claudron vault scope for this
   bot" reads as sub-vault scoping; the value is a vault *pointer* — detection walks up; one vault
   per tenant). Reference the query-before block that already documents `CLAUDRON_QUERY_BEFORE`.

## Test Plan

- Validator unit tests: vault-path set + CLI absent ⇒ new warning; vault-path set + CLI present ⇒
  no warning; MCP-fragment absence produces **no** vault-related warning in any combination.
- Doctor test: with a fixture vault + stub `claudron` on PATH, `check_claudron` reports floor rows
  with the MCP row rendered `parked`, never `unmet`; loop-evidence rows render for a bot with a
  fixture hooks.log.
- Import-seam test: the validator module imports no `claudron.*` (the detect call resolves through
  the `paths.py` helper) — the same assertion L4 later generalizes.
- `validate-bot-change.sh` (the repo's own gate) passes on a vault-wired example bot with no
  `claudron` MCP entry.

## Verification Checklist

- [ ] `claudlobby validate` on a vault-wired fleet with no MCP fragment emits zero MCP-related
      vault warnings.
- [ ] `claudlobby doctor` shows a claudron section with COMPAT_FLOOR rows; no row for a
      deliberately-unshipped surface reads "unmet".
- [ ] `grep -n "does not read CLAUDRON_VAULT_PATH" lib/` returns nothing.
- [ ] `dispatch-task.sh` invokes `claudron` without `--vault`.
- [ ] #511 re-scoped and this phase's doctor scope recorded there; #513/#251 closed-or-re-scoped;
      #560–564 reconciliation noted in the PR body.
- [ ] Repo test suite green.

## What NOT To Do

- Do not add `library/mcp/claudron.json` — the fragment stays unbuilt per decision C.
- Do not make the CLI check a hard validation *error* — bots can be composed before the host has
  the CLI; warn is the contract-honest level.
- Do not touch grants/permissions machinery here (that's #644's own epic; L4 only *gates*).

## Context

Area: Claudlobby validator/doctor/lib · Effort: M · Risk: low (deletes a false invariant; adds a
true one) · Priority: high — wave 1; resolves the §6 trigger.
