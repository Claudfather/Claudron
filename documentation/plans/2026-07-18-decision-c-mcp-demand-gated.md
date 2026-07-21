---
title: "Decision C — the MCP server is demand-gated"
type: decision
status: ratified
owner: chris
tags: [decision, mcp, e3, claudlobby, claudna, claudron]
created: 2026-07-18
updated: 2026-07-20
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

1. **Adversarial-grade per-verb enforcement is needed.** A fleet policy that
   must be **non-circumventable at the permission layer** — a bot granted
   `recall` (read) and denied `capture` (write) where the denial has to hold
   against an agent actively trying to spell around it. See the 2026-07-20
   amendment below: the *cooperative-grade* form of this trigger has been
   answered by #644 and no longer un-parks E3.
2. **A non-clauDNA MCP consumer appears** — a fleet member (Cursor/Codex/other)
   that speaks MCP but not clauDNA's skills and needs in-context tool discovery.

## Monitor

**The monitor is a machine check, not a human habit** (amended 2026-07-20).
Claudlobby's doctor validates the door that actually exists — `claudron`
resolvable, a vault detected, and the `claudron_compat` floor met — and its
validator no longer asserts an MCP config the engine deliberately never shipped.
Trigger (1) fires when a fleet policy is filed that those checks cannot express;
trigger (2) fires when such a consumer is named. Claudron's side of the probe is
`status --json` → `engine_version` (docs/CLI_CONTRACT.md §Capability probe); the
Claudlobby side lands in boundary phase L1. Until one of the triggers fires,
C holds.

## Amendment — 2026-07-20: trigger 1 re-scoped, monitor named

Recorded by boundary phase C1
(`2026-07-20-boundary-rearchitecture/01-c1-own-the-door.md`); grounds in the
boundary spec §10.5.2
(`2026-07-20-claudfather-boundary-separation.md`).

**The gate is affirmed; the framing is revised.** Verification found that
trigger 1's original grounds no longer hold as stated. Claudlobby's #644 grant
machinery *can* now express per-verb CLI gating —
`Bash(claudron lookup *)` allow beside `Bash(claudron capture *)` deny, with
deny winning (`composer.py:1307–1454`; grammar `validator.py:69–79`). The
premise that "a skill wrapping the CLI is one blanket `Bash(claudron *)` grant"
is therefore obsolete: **for a cooperative fleet, #644 already answers the
read/write split, and that half of trigger 1 is retired.**

What survives is the adversarial-grade form only. Grant patterns are
*pattern*-grade, not structural — an agent can spell an invocation many ways —
so a policy that must hold against circumvention still exceeds what the grant
layer promises. Trigger 1 is narrowed to exactly that case above.

Two related corrections from the same pass, for the record:

- **§6's pain was a validator bug, not a missing transport.** Claudlobby's
  `validator.py` warned vault-path ⟹ MCP config — asserting a sibling's
  unshipped surface (register rule R6). That warning is deleted and inverted to
  check the CLI door; it was a recurring reason MCP kept being re-proposed, and
  it was never evidence of demand.
- **The honest residual named in "what C gives up" is now mitigated on both
  halves.** The vendor-neutral door has its front door: `docs/INTEGRATION.md`
  exists (it was cited here as a mitigation before it was written). And for any
  host running the engine's hooks, the recall brief carries a one-line pointer
  at `claudron lookup` / `claudron capture` — in-context discovery for the
  hosts the engine actually reaches. True self-announcement for arbitrary
  MCP-speaking agents remains gated behind trigger 2.

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
