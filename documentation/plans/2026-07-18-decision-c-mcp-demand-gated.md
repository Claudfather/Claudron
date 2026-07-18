---
title: "Decision C — the MCP server is demand-gated"
type: decision
status: ratified
owner: chris
tags: [decision, mcp, e3, claudlobby, claudna, claudron]
created: 2026-07-18
updated: 2026-07-18
---

# Decision C — the MCP server (E3) is demand-gated, not the next epic

**Decision (2026-07-18):** Claudron's MCP server (E3, `03-mcp-server.md`) is
**parked as a demand-gated option**, not the fleet-consumption mechanism. The
fleet consumes the hub through the **CLI door** — clauDNA's `/claudron`,
`/capture`, `/recall` skills wrapping the `claudron` CLI (clauDNA #197), over
`claudron>=0.2`, on every bot. Weighed via `/weigh-development-paths`
(2026-07-18) and hardened by the re-ironclad (`2026-07-18-ironclad-rescope-record.md`,
Juncture E); this doc is the dated record the drift previously lacked.

## Why

- The role E3 was to fill (bots query-before / write-after) is **filled in
  practice** by the CLI skill door — shipped, working, vendor-neutral at the
  `--json` contract layer (hardened in PR-H: `documentation/plans/…` / the
  CLI_CONTRACT typed write envelope). "The CLI is the contract floor; MCP would
  be the same engine with equivalent semantics" (clauDNA's own framing).
- This is decision **D3** (MCP optional, `claudron[mcp]`, never a daemon)
  playing out — not a reversal. The substrate was always markdown+git+CLI.

## The falsifiable trigger (what un-parks E3)

Build the MCP server **only when one of these is concretely true** — not "someday":

1. **Per-tool permission gating is needed.** A specific fleet bot must be granted
   `recall` (read) while denied `capture` (write) *at the permission layer* —
   filed as a fleet-policy issue. **Grounded capability gap:** Claudlobby's grant
   model is per-tool for MCP (`mcp__<server>__<tool>`, `composer.py:252-294`);
   **CLI-backed integrations get no per-tool grants** (a skill wrapping the CLI
   is one blanket `Bash(claudron *)` grant — it cannot split read from write).
   So if the fleet wants per-verb Claudron access, only MCP can express it.
2. **A non-clauDNA MCP consumer appears** — a fleet member (Cursor/Codex/other)
   that speaks MCP but not clauDNA's skills and needs in-context tool discovery.

## Monitor

Claudlobby's **#644 permissions/grants epic is live** (P4 in flight) — it is the
machinery trigger (1) would fire through. **Owner (Chris) checks #644's grant
granularity at each Claudron work session:** the moment a bot's fleet.yaml needs
read/write-differentiated Claudron access, trigger (1) has fired and E3 re-enters
the critical path. Until then, C holds.

## Accepted reversal cost

Reversing C (build E3 after all) is bounded but real, paid later: re-derive E3's
spec (kept ready in `03-mcp-server.md`), un-park Claudlobby's
`library/mcp/claudron.json` fragment, revive the collapsed consumption children
(#511/#512/#513), and cut fleet bots from the CLI door onto `mcp__claudron__*`.
This deferral costs one paragraph now to preserve the option; it does **not**
foreclose E3.

## Honest residual (what C gives up)

True **in-context tool discovery for arbitrary agents** is the one thing only
MCP delivers — a CLI can't announce itself in-context the way MCP tools do. C
accepts that gap as the price of demand-gating, mitigated by giving Claudron its
own vendor-neutral door (the hardened `--json` CLI contract + any-agent
integration doc, PR-H) so consumption does not depend on clauDNA being present.

## Cross-repo consequence (filed, not done here)

Parking the MCP fragment strands two things in Claudlobby to clean up:
`validator.py:243-254` asserts vault-present ⟹ `claudron` MCP config present
(now permanently false — relax/invert it), and `CLAUDRON_VAULT_PATH` is now a
CLI pointer, not an MCP one (reconcile its doc). Filed as Claudlobby cleanup.

## Related

`03-mcp-server.md` (the parked E3 spec + banner) · `00-overview.md` §2026-07-18
re-scope · `2026-07-09-claudna-claudron-reconciliation.md` · VAULT-STRUCTURE.md
§Consumption(b).
