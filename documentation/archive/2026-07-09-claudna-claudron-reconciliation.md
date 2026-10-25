---
title: "clauDNA ↔ Claudron — hook & index reconciliation"
type: plan
status: active
owner: chris
tags: [claudna, claudron, e3, integration, hooks, index]
created: 2026-07-09
updated: 2026-07-09
---

# clauDNA ↔ Claudron — hook & index reconciliation

**Purpose.** Wiring clauDNA to accumulate fleet knowledge into the Claudron
vault is **not** "add hooks to clauDNA." clauDNA already runs a full,
overlapping knowledge loop; the work is *reconciling two systems that already
exist* so they compose instead of stepping on each other. This is the
load-bearing seam **E3** (MCP server + Claudlobby socket) formalizes, and the
thing the G1 fleet dogfood (`2026-07-09-g1-dogfood-protocol.md`) will force.
Doubles as the clauDNA **#207** follow-through and de-risks E3's PR 0.

> Observed 2026-07-09 in `~/Projects/clauDNA`. Verify file/hook/skill names
> against the current tree before implementing — clauDNA moves fast.

## The overlap

Both repos run a session-lifecycle knowledge loop over the **same tier names**:

| Concern | clauDNA | Claudron |
|---|---|---|
| SessionStart | `plugin-hooks/hooks.json` → `session-start.sh` (fleet brief — the "plugged into the hivemind" banner) | `session_start_brief`: git pull → re-detect vault → recall brief |
| PreCompact | `precompact-reflect.sh` (reflect/capture) | capture prompt |
| SessionEnd | — | push (`claudron sync`) |
| Capture verbs | skills `learn` / `reflect` (write), `remember` (consume), `index` (builds `INDEX.md`) | `claudron capture` → validate + dedup + write |
| Index | per-tier human-readable **`INDEX.md`** | machine **`.claudron/index.json`** |
| Docs root | `SHARED_DOCS_PATH` env, else CLAUDE.md "Shared Documentation" section | vault marker `_shared/` (detection also accepts `shared/`), else `--vault` / `CLAUDRON_VAULT_PATH` / walk-up |
| Tiers | `shared/{knowledge,planning,decisions,runbooks}` | `_shared/{knowledge,decisions,runbooks,planning/{active,completed}}` |

Claudron's `merge_settings` identity is **self-replacing** (event +
is-claudron-hook), so installing Claudron's hooks **coexists** with clauDNA's
rather than replacing them. Net on a machine running both plugins: **two
SessionStart briefs, two PreCompact captures, two indexes** over the same tiers.

## The boundary that resolves direction

Ratified ecosystem boundary: **procedural = clauDNA, referential = Claudron**.
So the *verbs* (remember/learn/reflect) are clauDNA's; the *knowledge they emit*
is referential and belongs in the Claudron vault; the *transport, machine index,
and recall ranking* are Claudron's. Direction is settled — only the mechanics
need decisions.

## Proposed reconciliation

1. **Shared root = the vault.** Point clauDNA's `SHARED_DOCS_PATH` at the
   Claudron vault's shared tier. One tree, not two. (Resolve the `shared/` vs
   `_shared/` marker: pick one physical dir; Claudron detection already accepts
   both, so aligning on clauDNA's `shared/` or symlinking is the low-friction
   option — decide in E3 PR 0.)
2. **Capture verbs write through, not around.** clauDNA `learn`/`reflect` become
   the fleet's human-facing capture verbs, but the *write* lands schema-valid
   Claudron notes. Pre-E3: they can write raw markdown that Claudron's **lenient
   tier** adopts (drift accumulates → curation is E5). Post-E3: they route
   through the `/claudron-write` skill clauDNA's docs already anticipate →
   validate (E1) + dedup (E2 `engine.py`) + the single write-lock.
3. **One owner per hook event.** Don't double-fire. Options to decide:
   - *SessionStart:* one brief. Either clauDNA's fleet brief calls
     `claudron recall` inline, or Claudron's brief is the one installed on
     vault-bearing machines and clauDNA's is scoped off there.
   - *PreCompact:* one capture path (clauDNA `reflect` **or** Claudron capture,
     not both writing the same finding twice).
   - *SessionEnd:* Claudron owns push (`claudron sync`) — clauDNA has no
     equivalent, so no conflict.
4. **Two indexes, two jobs — keep both, sync their triggers.** `INDEX.md` is the
   human-readable tier index (clauDNA `index` verb); `.claudron/index.json` is
   the machine retrieval index (Claudron, maintained on the write path). They're
   not redundant; ensure a capture updates *both* (or E4's SQLite mirror
   subsumes `index.json` and `INDEX.md` is regenerated from it).

## Open decisions (settle in E3 PR 0)

- **Marker:** align on `shared/` vs `_shared/` (symlink, config, or Claudron
  emits clauDNA-compatible layout).
- **Brief ownership** on vault-bearing machines (merge vs. scope-off).
- **Pre-E3 write fidelity:** accept lenient-tier raw-markdown drift during G1,
  or ship a minimal `/claudron-write` earlier.
- **`INDEX.md` ↔ `index.json`** maintenance: dual-write now, or defer to E4's
  SQLite mirror as the single source with `INDEX.md` generated.

## Relationship to E3

E3's deliverables (MCP `claudron_lookup/read/write`, the Claudlobby socket, the
cross-process write-lock) are the *formalization* of this reconciliation. Doing
the CLI-level version during G1 surfaces which of the open decisions actually
bite, so E3 is specced against felt pain rather than guesses.
