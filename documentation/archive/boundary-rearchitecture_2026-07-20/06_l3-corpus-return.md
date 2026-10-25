---
title: "L3 — Return the corpus: lessons → vault, compose-from-vault, door-stamped template"
type: plan
status: draft
owner: chris
tags: [plan, claudlobby, knowledge, vault, migration]
created: 2026-07-20
updated: 2026-07-20
---

# L3 — Return the corpus (Claudlobby)

## Summary

`library/lessons/` — 26 files (25 notes + README) — is corpus-class content living in the runtime
repo (§10.5.5), **but mixed-class by the placement test itself**: some entries are Q1 behavior
(e.g. `messaging-channel-discipline.md` steers what a bot does), not Q2 reference, and a behavior
rule rendered as a vault pointer is inert. So this phase runs **triage first** (the D2 ledger
method), migrates the *referential* subset to the vault through the typed write door, re-homes
behavior-class lessons to `protocols/`/guardrail slots (which keep rendering in-context), teaches
delivery to the session-time loop — **no compose-from-vault renderer (F4 locked: option d)**:
always-relevant referential lessons promote into the vault's `CONVENTIONS.md` (the always-injected,
budget-checked layer), the rest surface through L2's recall — and updates the two prose surfaces
that still stamp the pre-vault world: the bot template's §Shared Documentation (now points at the
door) and the mission's "does not define skills" sentence (reworded per §10.1). The renderer
re-opens only against post-wave-2 evidence of lessons not surfacing.

## Evidence

- The corpus: `library/lessons/` — 25 notes, README: *"'We learned this the hard way' notes …
  incidents, retro findings, failure modes."* Mission: *"Claudlobby does not store the long-lived
  knowledge corpus. Claudron does."* (PROJECT_MISSION.md:36).
- Composition renders library slots into bot CLAUDE.md: `templates/claude.md.j2:181–202`
  (`render_section` for Resources/…/Lessons/…); `loader.py` loads library files.
- The template still stamps the legacy convention: `claude.md.j2:105–120` §Shared Documentation
  (`planning/active/ … decisions/ … knowledge/<repo>/` under `{{ shared_docs_path }}`) — the
  raw-tree shape, not the vault door.
- The false sentence: PROJECT_MISSION.md:35 *"Claudlobby does not define skills. clauDNA does."*
  vs 44 `SKILL.md` files under `library/skills/` (fleet-ops commands — staying, per §10.1).
- The write door for migration: `claudron capture --stdin --json` (typed envelope, dedup routes —
  `docs/CLI_CONTRACT.md` §capture); adoption tooling: `claudron init --adopt`, `migrate`.

## Implementation Plan

### Dependencies
C1 (contract docs the migration cites); a vault present for the target fleet (the operator's —
migration is run by the operator, not CI).

### Blocks
Retiring the last parallel knowledge home; L4's "no direct corpus" gate becomes assertable.

### Steps

1. **Lessons triage ledger first** (the D2 method, applied here): one row per `library/lessons/`
   note — class verdict (Q1 behavior / Q2 referential) with the coupling question answered in one
   line. Behavior-class lessons (imperative bot-steering: channel discipline, workflow rules)
   **re-home to `protocols/` or guardrail slots** and keep rendering in-context — a pointer cannot
   steer behavior. Referential lessons (incident residue, environment facts learned the hard way)
   migrate. The ledger is the PR-reviewable artifact; no move happens before it merges. The
   remaining categories (`resources/`, `integrations/`, `principles/`) get inventory-only rows in
   the same ledger (flag world-truth candidates; no bulk move in this PR).
2. **Migration script** (`lib/` or a `claudlobby lessons-migrate` command — implementer's call):
   for each *referential-verdict* note, map frontmatter → `claudron capture --type knowledge
   --stdin --json` (tags carry `lesson` + original tags; `--fleet <name>` when fleet-scoped,
   default `_shared/`), branch on `data.action` per the contract (`created` proceed; `suggest_*`
   list for the human — never `--force`). Dry-run mode prints the mapping. Idempotent by dedup.
3. **CONVENTIONS promotions (F4 locked — replaces the renderer):** the ledger marks the few
   always-relevant referential lessons (timezone-class environment facts, standing operational
   rules that are reference-not-behavior) for promotion into the vault's `_shared/CONVENTIONS.md`,
   within its token budget (`SCHEMA.md` caps it; validation budget-checks it). Everything else
   referential reaches bots through L2's recall, relevance-ranked at session time. The composed
   `lessons` slot renders nothing when the ledger empties the library (vault-wired fleets); the
   frozen library rendering remains for non-vault fleets. No compose-time CLI use exists in this
   phase or anywhere in the program.
4. **Freeze `library/lessons/`:** README banner (frozen; new lessons go through `/claudna:capture`;
   behavior-class content goes to protocols/guardrails), scaffolding for lessons (if any) disabled;
   existing files retained for the fallback path until a removal release.
5. **Template door-stamp:** `claude.md.j2:105–120` — when the bot is vault-wired, §Shared
   Documentation instead names the door: recall/capture verbs, `CLAUDRON_VAULT_PATH`, "navigate for
   config, query for knowledge" (quote VAULT-STRUCTURE §Consumption). Raw-tree text remains the
   non-vault branch.
6. **Mission sentences:** reword PROJECT_MISSION.md:36 to *"Claudlobby does not define
   engineering-workflow skills — clauDNA does; Claudlobby's `library/skills/` are fleet-operations
   commands, coupled to the runtime."* (corpus sentence is :37). Root CLAUDE.md line 34 stays (it
   already describes them as fleet commands). **Mission-hygiene rider:** annotate Claudlobby
   sprint-focus #4 ("Add Claudron MCP server config to bot bootstrap") as superseded by decision C
   with a dated pointer — the mission must stop steering readers toward the phantom door.

## Test Plan

- Ledger completeness: every `library/lessons/*.md` has a verdict row before any move merges.
- Migration dry-run against a fixture vault: one mapping per referential-verdict note, all
  strict-valid.
- Live run on a scratch vault: `claudron validate --strict` green; re-run ⇒ all `suggest_update`
  (idempotence).
- Rendering test: behavior-class lessons render in-context in *both* modes (via their new
  protocol/guardrail homes); a vault-wired fleet whose ledger emptied the library composes no
  lessons slot; a non-vault fleet's library rendering is byte-identical; template snapshot tests
  updated.
- CONVENTIONS budget: after promotions, `claudron validate` passes the CONVENTIONS budget check.
- `claudlobby validate` green on the example fleet in both modes.

## Verification Checklist

- [ ] The triage ledger exists with a class verdict per lessons note (+ inventory rows for the
      other categories).
- [ ] Every referential-verdict lesson exists as a schema-valid vault note (dedup-routed,
      human-reviewed list for any `suggest_*`); every behavior-verdict lesson has a
      protocol/guardrail home and still renders in-context.
- [ ] A vault-wired bot's composed CLAUDE.md §Shared Documentation names the recall/capture door;
      always-relevant promotions appear in the vault's CONVENTIONS.md within budget.
- [ ] A non-vault fleet composes byte-identically to before this PR (snapshot).
- [ ] `library/lessons/README.md` carries the freeze banner.
- [ ] PROJECT_MISSION.md carries the reworded skills sentence and the sprint-focus-#4 supersession
      note.

## What NOT To Do

- Do not migrate a behavior-class lesson to the vault — a pointer cannot steer behavior; the
  ledger's verdict gates every move.
- Do not delete `library/lessons/` files in this PR (fallback + provenance; removal is a later,
  scheduled release).
- Do not move `resources/`/`integrations/`/`principles/` — inventory rows only; composition config
  is runtime content and stays.
- Do not build the compose-from-vault renderer — F4 locked it out; it re-opens only against
  post-wave-2 evidence. No compose-time `claudron` CLI use, period.
- Do not touch `library/skills/` — they stay (§10.1).

## Context

Area: Claudlobby library/templates/mission · Effort: M (shrunk from L — F4 locked out the
renderer) · Risk: low-medium (content migration; mitigated by ledger-first, dry-run, dedup
routing, snapshot parity) · Priority: medium — wave 3.
