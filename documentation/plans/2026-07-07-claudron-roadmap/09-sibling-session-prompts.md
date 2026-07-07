---
title: "Sibling-session prompts — Claudlobby & clauDNA companion epics"
type: runbook
status: active
owner: chris
tags: [handoff, claudlobby, claudna, forge, ironclad, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# Sibling-session prompts

Paste each prompt into a fresh Fable session in the named repo. Each leads a
forge → ironclad planning session that produces that repo's companion epic to
the Claudron roadmap (Claudfather/Claudron PR #13, EPIC #14). Planning only —
no implementation in these sessions.

---

## Prompt A — run in `/Users/chris/Projects/Claudlobby`

```
Plan the "Claudlobby consumes Claudron" companion epic. This is a planning
session: the deliverable is committed plan docs + filed GitHub issues, no
implementation.

CONTEXT — what already happened on Claudron's side (2026-07-07):
Claudron's six-epic roadmap shipped as Claudfather/Claudron PR #13 (EPIC #14,
children #15–#20): E1 schema SSOT + E2 personal session loop (0.2.0) → Gate
G1 (evidence gate) → E3 MCP server + Claudlobby socket (0.3.0) ∥ E4
SQLite/FTS5+graph indexer (0.4.0) → E5 curation lifecycle (0.5.0) ∥ E6 packs
+ Claudosseum grounding (0.6.0). Read these docs FIRST (branch
plan/claudron-roadmap-v0.2-v0.6 until #13 merges, then main), under
documentation/plans/2026-07-07-claudron-roadmap/:
- 00-overview.md — decisions D1–D11, Gate G1, the sockets table, risk table
- 03-mcp-server.md — the contract this epic consumes: five tools
  (claudron_lookup/read/write/related/status), stdio subprocess, vault
  resolution --vault → CLAUDRON_VAULT_PATH → CLAUDRON_VAULT → walk-up,
  vault-level write lock (flock on .claudron/write.lock), write returns
  {action: created|updated|suggest_update|suggest_supersede, path, reason},
  .claudron/events.jsonl instrumentation
- 01-schema.md — SCHEMA.md as tri-repo SSOT; two axes (status = activity,
  type-aware union incl. current/stale/ratified with mappings; maturity =
  draft|verified|canonical trust axis); referential-only boundary
- 05-lifecycle.md — corrected promotion ladder (memory/ → <fleet>/shared/ →
  vault _shared/ → packs) and the librarian review-queue contract

YOUR MISSION: produce Claudlobby's receiving-side epic, in this repo's house
style, deduped into the existing backlog — NOT fresh filings where issues
exist. Claudron authors the fragment + schema-pointer PRs; this epic plans
everything Claudlobby-side around receiving them.

RECON FIRST (repo ships daily — verify these anchors before planning on them):
- paths.py:355-405 vault precedence-with-fallback; .claudron bridge parser :42-58
- composer.py:448-459 per-bot CLAUDRON_VAULT_PATH emission (done — sprint #6)
- validator.py:243-254 bidirectional vault-path ↔ claudron-MCP cross-check
- library/mcp/ fragment contract (README + github.json exemplar; no
  claudron.json exists yet)
- library/protocols/dispatch.md:119-128 INDEX.md-scanning preflight;
  library/protocols/shared-documentation.md (5-doc cap, ladder :47-49)
- documentation/decisions/index-md-convention.md:12 — ratified, ZERO adoption
  (no INDEX.md exists anywhere, no /index producer ships here)
- pyproject.toml:20 — [vault] extra pulls claudron from git UNPINNED
- Open issues #251 (this exact work: "Claudron MCP in default bot template +
  query-before/write-after"), #266 (ecosystem citizen wiring umbrella)
- Merge adjacency: the goal-aware-fleet / feat/projects-tier work touches
  validator.py/composer.py/config.py — coordinate, don't collide

SCOPE TO PLAN (decide, size, sequence — push back where you disagree):
1. Receive + land Claudron's PRs: claudron.json fragment (into #251) and the
   frontmatter-schema.md SSOT pointer with status mappings
2. Fragment graduation: opt-in → fleet default / system tier. This IS
   approval-gated (PROJECT_MISSION.md:66 "new MCP servers in the default bot
   template") and is mission sprint #4 — the epic is the approval artifact
3. Protocol rewrites: dispatch.md preflight switches from INDEX.md scanning
   to claudron_lookup query-before; shared-documentation.md post-work write
   switches to claudron_write; promotion-ladder text aligned to the corrected
   rungs; decide the INDEX.md convention's disposition (retire vs scope to
   claudron-less fleets) given its admitted zero adoption
4. Compositor/validator/doctor work: vault provisioning at generate time,
   per-bot vs fleet-level CLAUDRON_VAULT_PATH defaults, doctor checks for
   vault reachability + claudron version, any composer knobs the fragment
   needs
5. Pin [vault] extra to a released Claudron tag; define the version-bump
   policy against Claudron's release train (0.2.0…0.6.0)
6. Librarian bot: a standing fleet job draining `claudron review --json`
   weekly — Claudron E5's acceptance criterion names this; plan the bot/cron
   definition here
7. Optional: fleet observability reading .claudron/events.jsonl (dedup/lock
   metrics) — decide in-scope or defer

SEQUENCING CONSTRAINTS: schema alignment can land alongside Claudron 0.2.0;
everything MCP-consuming is blocked on Claudron 0.3.0 (E3) and sits behind
Claudron's Gate G1. Stage the epic so nothing here dangles if G1 re-orders
E3/E4.

BOUNDARIES (from both missions): Claudlobby does not store the knowledge
corpus — Claudron does. The vault is tenant-owned; runtime/ and .env never
enter it. Schema SSOT is Claudron's SCHEMA.md — file deltas as feedback, not
local forks. Contract gaps you discover → comment on Claudfather/Claudron#17
(E3), do not redesign the contract unilaterally.

PROCESS: recon → /forge a plan doc under documentation/plans/2026-07-07-* (or
this repo's current convention) → /ironclad panel over it → fold findings →
file the EPIC + [plan] child issues (house style, planning label), linking
Claudfather/Claudron#14 and #17, folding into #251/#266 rather than
duplicating them. Definition of done: plan docs committed via PR, issues
filed, #251 updated with the plan link.
```

---

## Prompt B — run in `/Users/chris/Projects/clauDNA`

```
Plan the "clauDNA ⇄ Claudron integration" companion epic. This is a planning
session: the deliverable is committed plan docs + filed GitHub issues, no
implementation.

CONTEXT — what already happened on Claudron's side (2026-07-07):
Claudron's six-epic roadmap shipped as Claudfather/Claudron PR #13 (EPIC #14,
children #15–#20): E1 schema SSOT + E2 personal session loop (0.2.0) → Gate
G1 → E3 MCP server + sibling handoffs (0.3.0) ∥ E4 indexer ∥ E6 packs, E5
lifecycle. Read these docs FIRST (branch plan/claudron-roadmap-v0.2-v0.6
until #13 merges, then main), under
documentation/plans/2026-07-07-claudron-roadmap/:
- 00-overview.md — D1–D11, Gate G1, the clauDNA socket row (your open issues
  are named there), risk table
- 03-mcp-server.md — the tool surface your skills will call:
  claudron_lookup/read/write/related/status; write returns {action, path,
  reason} and routes near-duplicates to update/supersede suggestions
- 01-schema.md — SCHEMA.md as SSOT: two axes (status activity union incl.
  your ratified/current values with mappings; maturity draft|verified|
  canonical), referential-only boundary (type enum excludes skill BY DESIGN;
  validate warns on skill-shaped notes), your output-guide.md named as the
  reconciliation target
- 02-session-loop.md — recall/capture hooks; PreCompact stacking with your
  precompact-reflect.sh is explicitly planned to defer/combine

YOUR MISSION: produce clauDNA's integration epic in the house style you
invented (#165: EPIC + [plan] P-children, planning label), deduped into the
existing backlog — several open issues already stake out this ground.

RECON FIRST (verify anchors; repo ships daily):
- skills/remember/SKILL.md:26 (SHARED_DOCS_PATH or CLAUDE.md section
  resolution), :51/:98 (hard 5-doc cap, INDEX.md-scan-only) — the exact
  ceiling Claudron's engine replaces (field evidence F3: INDEX scanning dies
  at ~100–200 pages)
- skills/_shared/output-guide.md:5 (self-declared "canonical house-style
  spec") and :19 (the KNOWN, deferred split: per-project documentation/ vs
  the shared/ vault — "reconciling the two is its own change")
- skills/init-project/ — provisions NEITHER SHARED_DOCS_PATH nor a "Shared
  Documentation" CLAUDE.md section (the consumer at remember:26 has no
  producer anywhere)
- documentation/archive/2026-05-15-session-handoff-resume-redesign-design.md
  :199-205 — the deferred "/claudron-write (or equivalent)" bridge, listed
  there as out-of-scope-until-Claudron-ships; that condition fires at
  Claudron 0.3.0
- plugin-hooks/precompact-reflect.sh — your PreCompact block-and-instruct
  hook; Claudron's capture hook will stack on the same event
- Open issues to dedup INTO (not duplicate): #110 (post-lifecycle knowledge
  capture hook — "without it, Claudron retrieval has nothing to retrieve"),
  #112 (CLAUDE.md persist phase), #106/#107 (lessons/notes boundary — both
  say "don't deprecate before Claudron's skill ships"), #50 (closed
  knowledge loop), #36 (index --fleet), #104 (SessionStart auto-resume)

SCOPE TO PLAN (decide, size, sequence — push back where you disagree):
1. /claudron-write — the new skill wrapping claudron_write (drafts by
   default on the maturity axis; respects the routes-never-rejects dedup
   contract). Resolves the #106/#107 wait condition
2. /remember prefers the Claudron engine when a vault is detected (CLI or
   MCP — decide which door), with clean fallback to today's INDEX.md scan
   when claudron isn't installed. Same treatment for /learn (source_url
   dedup goes through the engine)
3. /reflect's vault-write half: whether reflect gains a capture step or
   defers to Claudron's PreCompact hook — resolve the same-event stacking
   (double-prompt is the failure mode; a combined prompt is the likely fix)
4. /init-project provisions the vault seam: SHARED_DOCS_PATH + "Shared
   Documentation" CLAUDE.md section + optionally `claudron init --adopt`
   guidance — closes the producer-less-consumer gap
5. The doc-planes reconciliation (output-guide.md:19): per-project
   documentation/ vs shared/ vault — THE design question of this session.
   Decide the target end-state (publish disk adapter routing, /index scope,
   documentation-standard.md updates) with Claudron's SCHEMA.md as the
   schema SSOT (Claudron's E1 PR lands the pointer; this epic owns the
   behavioral reconciliation)
6. Boundary enforcement both directions: skills never write procedural
   content into the vault (SCHEMA.md excludes type skill; validate warns on
   skill-shaped notes) — and reference content stops accumulating in skill
   prose. State where /notes and /lessons land per #106/#107
7. Telemetry: whether skill-events.jsonl should note Claudron engine usage
   (optional, local-only per your rules)

CONSTRAINTS (your own): marketplace-plugin-only; clauDNA ships ZERO MCP
servers (Claudron ships the server; your skills only call its tools);
SKILL_CONTRACT is CI-enforced; --auto skills emit §10.C structured results
and never AskUserQuestion; adding skills requires approval — the epic is the
approval artifact.

SEQUENCING: item 4 and parts of 5 are filesystem-convention work that can
proceed against Claudron 0.2.0 (schema only); items 1–3 are blocked on
Claudron 0.3.0 (E3) and sit behind Claudron's Gate G1. Contract gaps you
find → comment on Claudfather/Claudron#17, don't fork the contract.

PROCESS: recon → /forge the plan → /ironclad panel → fold → file EPIC +
[plan] children (#165 style), folding into #110/#112/#106/#107 with comments
rather than duplicating. Definition of done: plan docs committed via PR,
EPIC + children filed, the four dedup-target issues cross-linked.
```
