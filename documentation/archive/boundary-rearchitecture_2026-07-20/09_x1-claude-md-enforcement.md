---
title: "X1 — CLAUDE.md seam enforcement across the three repos"
type: plan
status: draft
owner: chris
tags: [plan, claude-md, enforcement, claudron, claudna, claudlobby]
created: 2026-07-20
updated: 2026-07-20
---

# X1 — CLAUDE.md seam enforcement (all three repos)

## Summary

Deliverable (c) of the boundary program: the boundary becomes self-enforcing at the points where
placement decisions happen. Before this pass: 3 root files, 0 internal-seam files. Target:
refreshed roots carrying the two-register rule, plus one small CLAUDE.md at each seam where a
contributor or agent chooses where something lives. Every seam file answers three questions: what
belongs here, what must never land here, and the one-line placement test — pointing at the boundary
spec §10.3 rather than restating it. **The texts exist — authored by the visioning pass
(2026-07-20)**: Claudron's root refresh + `claudron/CLAUDE.md` + `docs/CLAUDE.md` live in the
Claudron working tree on this plan's branch; clauDNA's root edit + 2 seam files are committed on
its `docs/boundary-claude-md-seams` branch (`49f13cf`); Claudlobby's root edit + 3 seam files on
its `docs/boundary-claude-md-seams` branch (`f158ae1`). This phase is their landing (one PR per
repo) plus the mission-hygiene rider below.

## Evidence

- Current surface (spec §4.6): root CLAUDE.md ×3; zero internal-seam files in any repo
  (clauDNA's `project-template/CLAUDE.md` and Claudlobby's `templates/claude.md.j2` are consumer
  scaffolding, not seam guidance; clauDNA root CLAUDE.md carries no boundary sentence at all).
- The in-vault precedent already shipped: Claudron scaffolds `projects/CLAUDE.md` into vaults
  (commit `820bb7e`; `SCHEMA.md` §Non-note files exempts CLAUDE.md from note walks) — the pattern
  is proven at the vault seam; this phase applies it to the *repo* seams.

## Implementation Plan

### Dependencies
None (content is ratified by the boundary spec §10; landing can precede or follow any other phase).

### Blocks
Success criterion §9.4 — "a new contributor or agent can place any new file by reading the nearest
CLAUDE.md."

### Steps

1. **Claudron root CLAUDE.md refresh:** add the two-register paragraph (content vs contract; the
   engine owns its consumption contracts; R5 — never know a consumer by name) + pointers to
   SCHEMA/VAULT-STRUCTURE/CLI_CONTRACT as the owned contracts. Keep the existing structure/test
   conventions text. **Mission-hygiene rider (same PR):** refresh Claudron
   `PROJECT_MISSION.md`'s stale implementation letter — line 5 asserts present-tense MCP
   consumption + a SQLite mirror and line 54 lists "MCP server v0.1" as sprint focus, all
   superseded by decision C and D-decisions; either amend the letter (consumption = the CLI door,
   MCP demand-gated; index = derived `.claudron/index.json`) or stamp a dated supersession note
   pointing at the decision docs. Contributors read missions first; the phantom door must not
   re-import itself from the top. (Claudlobby's equivalent rider rides L3 step 6.)
2. **Claudron seam files (2):**
   - `claudron/CLAUDE.md` — engine vs CLI vs hooks: engine modules never print (CLI owns
     stdout/stderr per CLI_CONTRACT); hooks fail open and never gain consumer names; every write
     goes through `engine.py`; contract changes touch docs + parity tests together.
   - `docs/CLAUDE.md` — these files are owned contract text (R1–R7 summary); consumers PR here;
     breaking changes need CHANGELOG entries + version-window notes.
3. **clauDNA root CLAUDE.md refresh:** add the boundary paragraph the root currently lacks
   (procedural-by-coupling, not by format; referential payloads follow Q-closure; the engine is
   consumed through the door, never reimplemented) + the fallback-freeze rule.
4. **clauDNA seam files (2):**
   - `skills/CLAUDE.md` — what a skill may contain (method, rubrics-as-closure); what it must not
     (world-truth reference → vault; engine internals → point at claudron-engine.md); the
     Q-closure one-liner; capture's boundary check as the enforcement backstop.
   - `skills/_shared/CLAUDE.md` — shared orchestration material only; rendered copies of sibling
     SSOTs require a drift gate (the §3 precedent); no new SSOT text here — SSOTs live with their
     owner.
5. **Claudlobby root CLAUDE.md refresh:** composition-and-policy identity; the reworded skills
   sentence (fleet-ops commands are runtime content); the corpus rule (durable knowledge lives in
   the vault; compose from it); R6 (never assert a sibling's unshipped surface — cite the L1 fix).
6. **Claudlobby seam files (3):**
   - `library/CLAUDE.md` — composed sources of truth; per-category one-liners; the corpus rule
     (lessons frozen → vault; world-truth additions go through the door); skills here = fleet
     operations only.
   - `lib/CLAUDE.md` — lifecycle scripts; consume siblings only through their contracts (the
     dispatch-wedge shape: pointers, never note bodies; env names from CLI_CONTRACT §Environment);
     no vault file access.
   - `claudlobby/CLAUDE.md` — compositor code; fleet.yaml is owned here and parsed nowhere else;
     `paths.py` is the only claudron import; validator asserts only shipped sibling surfaces.
7. **Cross-check the stamped templates** (clauDNA `project-template/CLAUDE.md` +
   `init-project/references/CLAUDE_MD_TEMPLATE.md`; Claudlobby `templates/claude.md.j2`): no
   stamped text contradicts a seam file (the L3 door-stamp handles the one found instance).

## Test Plan

- Repo-local: docs-only PRs; existing suites stay green.
- clauDNA CI directory checks (the repo gates structure) pass with the new non-skill files at
  `skills/CLAUDE.md` and `skills/_shared/CLAUDE.md` (verify the skill-discovery glob ignores
  non-SKILL.md files — evidence: `_shared/` already ships 13 non-skill files harmlessly, and
  `scripts/validate-skills.py` ran green with both seam files present on the landing branch).
- Grep audit per repo: every seam file's "never" clauses name at least one enforcing mechanism
  (test, gate, or contract line) — guidance that cites enforcement, not aspiration.

## Verification Checklist

- [ ] 3 refreshed roots + 7 seam files exist with the three-question shape.
- [ ] Each seam file fits in ~40 lines and points at (never restates) §10.3.
- [ ] `git grep -l "placement test"` finds every seam file (uniform hook for future audits).
- [ ] All three repos' suites/CI green on the docs PRs.

## What NOT To Do

- No seam file restates the full register or the placement algorithm — pointer + the local
  one-liner only (a fork of the spec at nine locations is the R3 anti-pattern in miniature).
- Do not stamp seam files into consumer projects/bots — these govern the *repos*; the templates
  govern consumers and already exist.
- Do not add CLAUDE.md to directories with no placement decisions (tests/, voices/) — noise.

## Context

Area: all three repos, docs · Effort: M (spread thin) · Risk: none (docs) · Priority: high —
wave 1; cheap and makes every later phase's PR review self-explaining.
