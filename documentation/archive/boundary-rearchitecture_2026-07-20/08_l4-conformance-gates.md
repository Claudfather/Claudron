---
title: "L4 — Conformance gates: rename-map drift, boundary invariants in CI"
type: plan
status: draft
owner: chris
tags: [plan, claudlobby, ci, conformance]
created: 2026-07-20
updated: 2026-07-20
---

# L4 — Conformance gates (Claudlobby)

## Summary

Makes the two hand-maintained conformance surfaces machine-checked (R3), and turns the boundary's
"never" clauses into CI invariants so drift is caught where it lands rather than in the next
visioning pass. Small PR, wave 3.

## Evidence

- `claudlobby/known_values.py:90–155` — a hand-maintained map of clauDNA skill renames (the
  `/claudna:` namespace tracked by copy, no gate).
- The pin that makes a gate cheap: `pyproject.toml` `[vault]` = `claudron @ git+…@v0.2.0`;
  plugin default `claudna@Claudfather` (`config.py:424–438`) — both sibling versions are pinned or
  default-known, so a CI job can fetch exactly what the fleet composes.
- Direct-access status quo (the invariant to freeze): no Claudlobby code reads/writes vault note
  bodies — access is bridge-file resolution (`paths.py:104–130`), CLI wedge
  (`dispatch-task.sh:124`), env emit (`composer.py:611`). L3 adds the lookup-based lessons
  renderer (pointers only).

## Implementation Plan

### Dependencies
L1 (corrected validator posture). The whole phase is **pulled forward to wave 2** — its gates
should exist before waves 2–3 create the most new conformance surface, and nothing in it waits on
L3 anymore (F4 locked out the renderer this phase once had to gate).

### Blocks
Nothing downstream — this phase is the program's regression armor; it exists so waves 2–3 drift
gets caught where it lands.

### Steps

1. **Rename-map drift gate (F8 lean a, semantics as locked):** a CI job that resolves the clauDNA
   ref (`bot.claudna_version` when the fleet pins one; marketplace-latest otherwise), lists
   `skills/*/` dirs, then parses `known_values.py`'s map **live values** (current verb forms like
   `/claudna:audit security` — strip the namespace and arguments to the skill-dir token) and fails
   when a live value references a skill dir that no longer exists. **Promise: stale-live-values
   only** — the map's keys are dead names by design, and a *new* clauDNA rename with no map entry
   is undetectable by construction (F8(b)'s manifest is the named upgrade if one ships unnoticed).
   Offline-safe: skip-with-notice when the clone fails (local-first — CI convenience, not a
   required hosted dependency).
2. **Boundary invariants** (a `tests/test_boundary_invariants.py`):
   - **(a) hook-snippet parity** (the L2 rendered copy's drift gate): the composer's emitted hook
     entries match `claudron.hooks.settings_snippet()` from the `[vault]`-pinned engine — a test
     importing claudron for comparison is exempt from the module invariant below; skip-with-notice
     when the extra isn't installed;
   - no *runtime module* outside `paths.py` imports `claudron.*` (tests exempt; L1's validator
     check resolves through the `paths.py` helper and satisfies this);
   - no code path opens files under a resolved vault's note tiers (`_shared/`, `projects/`,
     `<fleet>/shared/`) — grep/AST-level assertion over `claudlobby/` and `lib/`;
   - `validator.py` contains no `claudron` MCP assertions (guards L1's fix against regression);
   - composed bot env for vault-wired bots names only `CLAUDRON_VAULT_PATH` (no deprecated alias);
   - no composed settings file contains `Bash(claudron *)` (guards L2's narrow-grant rule).
3. **Docstring truth:** `claudron_compat.py` docstring matches its real consumers (L1 wired the
   doctor check; assert the reference).

## Test Plan

The phase *is* tests; each invariant gets a deliberate-violation fixture proving it fires, then the
fixture is removed.

## Verification Checklist

- [ ] CI fails on a synthetic stale rename-map entry; passes on head.
- [ ] CI fails on a synthetic direct note-tier read; passes on head.
- [ ] Gates skip gracefully offline (message, not failure).
- [ ] Repo suite green.

## What NOT To Do

- No gate may require network to *pass* locally (local-first; skip-with-notice offline).
- Do not gate clauDNA's internals beyond the consumed surface (skill dir names) — R6 in reverse.

## Context

Area: Claudlobby CI/tests · Effort: S · Risk: low · Priority: medium — wave 3.
