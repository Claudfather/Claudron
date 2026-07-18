---
title: "E3 — MCP server v0.1 + the Claudlobby socket"
type: plan
status: deferred
owner: chris
tags: [epic, mcp, claudlobby, claudna, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E3 — MCP server v0.1 + the Claudlobby socket

> **⛔ DEMAND-GATED — parked 2026-07-18 (decision C).** The fleet already
> consumes the hub through clauDNA's **CLI-skill door** (`/claudron`
> lookup/status, `/capture`, `/recall` over the `claudron` CLI — shipped in
> clauDNA #197; *"the CLI is the contract floor; MCP tools, if configured, are
> the same engine with equivalent semantics"*). So this MCP server is **no
> longer the next epic** — it is an optional upgrade built **only on a named
> trigger:** per-tool permission gating (Claudlobby #644) or a non-clauDNA MCP
> consumer. Until a trigger fires, the vault is fully fleet-consumable without
> it. Everything below is the design, kept ready. Release "0.3.0" below is the
> *original* ordinal placement, now void — see `00-overview.md` §2026-07-18
> re-scope.

**Release:** 0.3.0 by default order (ordinal — see overview DAG legend) ·
**Depends on:** E1, E2 (imports E2's `engine.py`; the overview DAG legend is
the authoritative dependency statement) · **Parallel with:** E4, E6 ·
**Gated by:** G1 (defined in `00-overview.md` §Gate G1), incl. the
adopt-vs-build spike (PR 0)

## Goal

Expose the vault as typed tools any agent can discover in-context — the
difference between a hivemind and a suggestion. One stdio server serves both
consumers: the maintainer's local sessions (upgrading E2's shell-outs) and
Claudlobby fleet bots (closing the socket the compositor already built).

Posture (D3): stdio subprocess spawned per session — like an LSP server, not a
daemon. Ships as `pip install 'claudron[mcp]'`; the only new dependency (the
`mcp` SDK) stays out of core.

## Why now — the socket is documented and warning

- Claudlobby emits `CLAUDRON_VAULT_PATH` per bot (`composer.py:448-459`) and
  its schema docs say: *"The Claudron MCP server reads this to scope queries"*
  (`fleet-yaml-schema.md:441`)
- Its validator already cross-checks a `claudron` MCP server that doesn't
  exist (`validator.py:243-252`)
- Its mission sprint #4: "Add Claudron MCP server config to bot bootstrap and
  document the query-before / write-after pattern"
- clauDNA's documented upgrade path: "when Claudron's MCP server lands and a
  `/claudron-write` skill ships"

## Deliverables

1. **`claudron mcp serve`** (also a `claudron-mcp` console script for
   `.mcp.json` command fields) — stdio transport, vault resolved from
   `--vault` → `CLAUDRON_VAULT_PATH` → `CLAUDRON_VAULT` → walk-up, in that
   order.
2. **Five tools, v0.1 surface** (mission gate: MCP tool-surface changes
   require approval — this list is the approval):
   | Tool | Contract |
   |---|---|
   | `claudron_lookup` | query, optional project/fleet scope, limit → ranked results (title, path, tier, score, snippet) |
   | `claudron_read` | path or exact title → frontmatter + body |
   | `claudron_write` | type, title, body, tags, project? → validate (E1) + dedup (E2 `engine.py`) + write; returns `{action: created\|updated\|suggest_update\|suggest_supersede, path, reason}`. **Scoped honestly (panel M1):** *malformed never lands* is a pure per-note check and holds for any N; *duplicates never land* requires cross-process serialization — see the lock spec below. Dedup **routes, never hard-rejects**: a near-duplicate becomes an update/supersede suggestion returned to the caller (a silent-drop gate would also drop the contradicting updates curation exists to catch — unverified 2606.24535 caution, adopted because rejection-by-default is riskier anyway) |

   **Vault write-lock spec** (cycle-2 consensus #1 — the three
   under-specifications, answered):
   - **Mechanism:** `flock` on `.claudron/write.lock` around the
     dedup→write→commit critical section, held by **every vault mutator** —
     MCP `write`, CLI `capture`, `sync`'s git operations, E5's
     `promote`/`promote --to-tier` (cycle-2 must-fix #8). Kernel-held, so a
     crashed process releases it automatically — no stale-lock cleanup path
     exists to get wrong (this is why flock over lockfiles)
   - **Contention:** bounded wait (default 5s) with backoff; on timeout the
     caller gets a structured `{action: retry_later, reason: lock_contention}`
     — never a hang, never a silent drop. Contention events land in
     `events.jsonl`
   - **Readers are lockless by design, protected by atomic writes:** every
     note write is write-temp-then-`rename()` (atomic on POSIX), so a
     concurrent reader sees the old note or the new note, never a torn one.
     Readers may see last-durable state during a write burst — acceptable for
     a read-mostly, git-versioned corpus
   - **Scope stated plainly:** the lock serializes **one filesystem**. The
     cross-machine topology (D4's clones) is serialized at the git layer —
     `sync`'s pull-rebase-push plus one-writer-per-note convention — and
     simultaneous multi-machine fleet writes to the same logical vault are
     **out of scope for v0.1** (named fleet-milestone work, with the
     multi-writer validation it depends on)
   | `claudron_related` | title/path → wikilink neighbors, in/out. v0: on-demand `[[link]]` parse of the target note; E4 upgrades to the edges table transparently |
   | `claudron_status` | vault health summary (wraps `status --json`) |
3. **Shared engine, three doors:** `recall`/`capture` (CLI) and
   `lookup`/`write` (MCP) import the same `engine.py` (named module home,
   landed in E2 PR2) — one validate/dedup/rank implementation, tested once as
   plain functions (no transport in tests). Error payloads are part of the
   v0.1 approval surface, not an afterthought: `read` not-found returns
   nearest-title candidates; validation failures return the same field-level
   errors `capture` emits.
4. **Instrumentation (the F8 substrate):** an append-only, gitignored
   `.claudron/events.jsonl` written by the write path (dedup hits, routed
   updates, malformed attempts, lock contention) and summarized by
   `claudron status`. Without it the chokepoint ships un-instrumented — E4's
   SQLite is a parallel epic, so 0.3.0 needs its own substrate. These are the
   first publishable field data on the F8 gap.
5. **Claudlobby fragment PR — into open issue #251** (umbrella #266):
   `library/mcp/claudron.json` matching the documented fragment contract
   (top-level `claudron` key — what `validator.py:244` keys on —
   `command`/`args`/`env` with `${CLAUDRON_VAULT_PATH}`, `_env_contract`
   metadata, `_permissions_contract` listing the five `mcp__claudron__*`
   tools), plus the query-before/write-after pattern doc against its dispatch
   protocol. Nuance the panel verified: the mission gate covers adding to the
   *default bot template*; shipping the opt-in fragment itself is not gated.
   The pattern doc should note Claudron's `lookup` **replaces** the
   INDEX.md-scanning preflight — claudlobby's own ADR admits that convention
   has zero adoption (no INDEX.md exists, no producer ships there). Existing
   `plug`/`unplug`/`config`/`migrate` **coexist**: `plug` registers the vault
   path claudlobby's compositor resolves; the fragment is the query path;
   `migrate` stays a one-time import. Rider: pin claudlobby's `[vault]` extra
   to a released Claudron tag (unpinned git HEAD today).
6. **clauDNA handoff issues (filed as comments/dedups into their open
   backlog, not fresh — clauDNA owns its skills):** `/remember` and `/learn`
   prefer the Claudron engine when a vault is detected (→ #110/#112 territory);
   new `/claudron-write` skill wrapping `claudron_write` (the archived design
   doc's deferred bridge — #106/#107 explicitly wait on it); `/init-project`
   gains vault provisioning (`SHARED_DOCS_PATH` + "Shared Documentation"
   CLAUDE.md section — the gap recon confirmed total). Skills conform to
   clauDNA's CI-enforced SKILL_CONTRACT.

## Phased PRs

| PR | Scope |
|---|---|
| 0 | **Adopt-vs-build spike writeup — gate artifact, merges before PR 1 opens** (cycle-2 consensus #2: bundled with build code it cannot gate the build). Shared with E4 |
| 1 | server skeleton + `lookup`/`read`/`status` (read-only first) |
| 2 | `write` (vault lock per spec + events.jsonl) + `related` — imports E2 `engine.py`, proven by the shared test suite |
| 3 | Claudlobby `claudron.json` fragment + pattern doc → #251 (cross-repo) + `[vault]` pin rider |
| 4 | clauDNA handoff comments/issues + `.mcp.json` recipes for personal setup |

## Acceptance criteria

- A Claudlobby fleet bot with the fragment queries before a task and writes a
  finding after, with no CLAUDE.md convention text — tools discovered
  in-context; claudlobby validator warnings resolve; #251 closes
- `claudron_write` rejects the same inputs `capture` rejects (shared
  `engine.py` — proven by shared test suite, not parallel implementations)
- **Concurrency test:** two writer processes racing the same near-duplicate
  title produce one note + one routed suggestion (lock proven), and a
  simulated `index.lock` collision retries clean
- `claudron status` reports write/dedup/malformed counters from events.jsonl
- Personal sessions: `.mcp.json` snippet in README; `claudron_lookup` used
  in-session where E2's hook brief is insufficient
- Server cold-start under ~1s on a 1k-note vault (index reuse, no rebuild)

## Non-goals

- HTTP/SSE transports, auth, multi-tenant serving — stdio only, local only
- Semantic/vector tools (E4+ decides; surface reserves nothing)
- Fleet write-policy (who may write which tier) — E5's provenance groundwork;
  v0.1 trusts the tenant boundary (a vault is one tenant)
- **Multi-writer validation claims.** The lock makes concurrent writes *safe*;
  proving the chokepoint's value under real fleet load is a named follow-up
  milestone (first fleet with ≥2 writing bots), because personal dogfood is
  single-writer and structurally cannot exercise it (panel M1). Until then
  F8 stays "motivated but unvalidated" and the docs say so

## Risks

- **Tool-surface churn after siblings integrate** → v0.1 surface is small and
  named conservatively; additions are cheap, renames are not; changes gated by
  mission approval rule.
- **`mcp` SDK version drift** → pin lower bound in the extra, CI against
  latest, no SDK types leak into core modules.
- **Two consumers, conflicting scoping needs** → scoping is explicit tool
  input (project/fleet), not server state; the env var only picks the vault.

## Field evidence

See [07-field-research.md](07-field-research.md). **F8: this epic carries the
one bet the verified record neither validates nor contradicts.** Indirect
support is real — Basic Memory ships as a local MCP server over the identical
files+SQLite substrate (existence proof), and the published critiques of the
Karpathy pattern name exactly the gap this closes: git/markdown has no
ACID/RBAC story for simultaneous multi-agent writes (F1). But no verified
source shows a write chokepoint working or failing under production
multi-agent load. Consequences for this epic: (a) the bet ships with its own
validation — dogfood metrics (write rejections routed to update, dedup hits,
malformed-write attempts) reported by `claudron status` so the chokepoint
proves or indicts itself; (b) the four unverified papers on multi-writer
governance get re-verified and folded in at epic kickoff; (c) design choices
that the unverified literature warns about (dedup ordering) are taken in the
conservative direction now rather than retrofitted.
