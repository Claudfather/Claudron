---
title: "C1 — Own the door: address contract, write guarantees, INTEGRATION.md"
type: plan
status: completed
owner: chris
tags: [plan, claudron, contracts, cli]
created: 2026-07-20
updated: 2026-07-21
---

# C1 — Own the door (Claudron)

> **Shipped** in [#79](https://github.com/Claudfather/Claudron/pull/79), merged
> 2026-07-21 and released as **v0.3.0**. All twelve steps landed; both
> approval-gated amendments (step 9 VAULT-STRUCTURE §Consumption(b), step 10
> decision-C trigger 1) were ratified on merge, and the F3 grep sweep is
> recorded in the PR body. Claudron #30 and #46 closed with it.
>
> **Follow-on the merge makes urgent:** the hard cut is live, and clauDNA still
> orders `CLAUDRON_VAULT` first in its ladder — `skills/_shared/claudron-engine.md`
> additionally states "the CLI resolves the vault from `CLAUDRON_VAULT`", which
> is now false. That is [D1](03-d1-claudna-conformance.md), and it is the
> two-vaults hazard pointing the other way until it lands.

## Summary

Claudron's CLI is already the fleet's vendor-neutral door; this phase makes Claudron *own* it:
the vault-address contract gets one table with one canonical name, the write path gets its honest
cross-host guarantee ladder, and the any-agent front door (`docs/INTEGRATION.md`) that decision C
cites — but which does not exist — is written. Closes contract-register gaps #3, #4, #6 (docs half)
from the boundary spec §10.4.

## Evidence

- Resolution order lives only in code + one contract line: `claudron/cli.py:75–84`
  (`--vault` → `CLAUDRON_VAULT_PATH` → `CLAUDRON_VAULT` → walk-up); `docs/CLI_CONTRACT.md` §Flags
  states the order but names no canonical var, no deprecation, no bridge-file format.
- `claudron/cli.py:271` prints `export CLAUDRON_VAULT={root}` — the engine's own quickstart teaches
  the deprecated spelling.
- Bridge-file format exists only as an implementation: `claudron/cli.py:145–149`
  (`_write_claudron_config`, `vault=<path>`); consumed by Claudlobby `paths.py:42–58`.
- The guarantee ladder is documented only in module docstrings: `claudron/locking.py:1–27` (flock
  per host, NFS caveat), `claudron/sync.py:1–19` (single-writer-per-machine assumption, quarantine).
- `docs/` contains only `CLI_CONTRACT.md` — no INTEGRATION.md (decision-C doc line 67 cites it as
  the vendor-neutral mitigation; ironclad rescope record §E flagged the gap).
- `VAULT-STRUCTURE.md:160–173` §Consumption(b) still frames `CLAUDRON_VAULT_PATH` with an MCP
  aside; the rescope record's fix list includes "update VAULT-STRUCTURE.md §Consumption(b) to stop
  implying an MCP consumer."
- The recall brief renders notes with no pointer to the CLI: `claudron/session.py:152–191`
  (`render_brief`).

## Implementation Plan

### Dependencies
The wave-1 entry gate (spec §10 placements + forks F1/F3/F5/F7 locked). First code phase of wave 1.

### Blocks
C2 (extends the same contract doc), D1, L1 (both conform to the names this phase fixes), L3 and D2
(cite the contract docs and the adopt/migrate path).

### Steps

1. **`docs/CLI_CONTRACT.md` — add §Environment.** One normative table, **rows in precedence
   order**: `--vault` flag (wins) → `CLAUDRON_VAULT_PATH` (canonical env; emitted by Claudlobby's
   composer) → walk-up. `CLAUDRON_VAULT` is **removed** (F3 locked: hard cut) — a migration line
   in the table records it, and the breaking change gets its CHANGELOG entry. §Flags **defers to
   this table** (point, don't restate — R3 applied at home; the doc-parity test covers the one
   normative statement). State consumer obligations: emit/read the canonical name only;
   `SHARED_DOCS_PATH` is a clauDNA fallback-mode variable, never consulted when an engine is
   present, and out of deprecation scope.
2. **`docs/CLI_CONTRACT.md` — add §Bridge file.** Format `vault=<path>` + `#` comments; written by
   `claudron plug` at a consumer root; read by consumers to point a checkout at a vault; a
   *resolution artifact, not vault structure* (mirror VAULT-STRUCTURE's aside). Answer #46 here
   explicitly: the bridge file remains a consumer-side pointer read by the consumer; the engine
   does not adopt it as an implicit resolution default (declined — keeps the resolution ladder
   one-directional); close or update #46 with this decision.
3. **`docs/CLI_CONTRACT.md` — add §Write guarantees.** The ladder verbatim: per-host serialized
   (flock; Windows/NFS caveats), cross-host eventually consistent with conflict quarantine
   (rebase; markers left for the human), multi-writer exclusion out of scope by constraint
   (no daemon). Name the honest conflict surface (same-slug creates, `--update` appends,
   `CONVENTIONS.md`) and the mitigation (dedup routes pre-write; quarantine excludes from recall).
4. **Alias hard cut (F3 locked).** Delete the `CLAUDRON_VAULT` read from `_detect_vault`
   (`cli.py:81–83`). **Softener on the failure path:** in `_resolve_vault`'s exit-3 message, when
   `CLAUDRON_VAULT` is set in the environment, append one stderr line: `note: CLAUDRON_VAULT is no
   longer read (removed in <version>) — set CLAUDRON_VAULT_PATH`. **Pre-merge gate:** the grep
   sweep for `CLAUDRON_VAULT` (word-boundary, excluding `_PATH`) across all three repos and the
   dogfood vault, results recorded in the PR body. stdout discipline unchanged (payload only).
5. **Fix the init text.** `claudron/cli.py:271` → `export CLAUDRON_VAULT_PATH={root}`.
6. **Engine version surface (the capability probe consumers guard on).** `status --json`'s `data`
   gains `engine_version` (from `__version__`), and CLI_CONTRACT §`--json` documents it plus the
   stable `status` field set consumers (L1's doctor, D1's guard) may rely on. This is the probe
   the program's cross-repo guards depend on — today the only detection ladder lives in clauDNA's
   private doc, the inverted-ownership pattern this program fixes.
7. **`docs/INTEGRATION.md` (new, per F5 lean).** Sections: what the engine is (one paragraph);
   **get the CLI** (supported install channels — git clone/tag pip install — and minimum version);
   **step 0: detect the engine** (probe via `status --json` → `engine_version`; the three no-engine
   states, each with what a consumer may assume: CLI absent = ENOENT/127 at the shell; CLI present
   + no vault = exit 3; vault resolved = exit 0); **hello-world** (one copy-paste sequence: `init`
   a scratch vault → `capture --stdin` → `recall`); resolve a vault (§Environment pointer);
   query-before (`recall`/`lookup --json`, envelope, abstention); write-after (`capture --stdin`,
   branch on `written`, dedup actions); session-loop pointer (C2's protocol section once it lands);
   conformance checklist — **self-contained testable sentences** (register R-numbers as
   parenthetical cross-refs at most). Explicitly vendor-neutral. The doc is under CLI_CONTRACT's
   change discipline (breaking changes → CHANGELOG) and has a canonical GitHub URL for cross-repo
   citation (L1's validator warning uses it).
8. **Recall-brief hint.** In `claudron/session.py:render_brief`, append one budget-counted line when
   notes rendered: `query more: claudron lookup <terms> · capture: claudron capture --stdin`. This
   is the in-context discovery channel named in §10.5.2.
9. **`VAULT-STRUCTURE.md` §Consumption(b) amendment** (approval-gated — quote the diff in the PR):
   drop the MCP aside from the runtime-resolution paragraph; point at CLI_CONTRACT §Environment;
   keep the decision-C cross-reference as the door-policy pointer.
10. **Amend the decision-C doc** (`documentation/plans/2026-07-18-decision-c-mcp-demand-gated.md`):
    trigger 1 re-scoped to adversarial-grade per-verb enforcement (cooperative-grade splits are now
    expressible via #644 grants); the monitor becomes the named L1 doctor/validator check, not a
    human habit; dated amendment note citing boundary spec §10.5.2.
11. **Deprecate the Claudlobby tree-walk** (`cli.py:104–113`, the second R5 violation): `plug` /
    `config` / `migrate` prefer an explicit `--claudlobby <path>` (already accepted) or a bridge
    file at the target; when the tree-shape walk is what resolved the root, emit a one-line stderr
    deprecation pointing at `--claudlobby`. Removal rides the F3 schedule.
12. **README.** Add an "Integrating any agent" pointer to `docs/INTEGRATION.md` under Position in
    the ecosystem. Cite and close Claudron #30 (its claim is stale post-#62; the §Environment table
    is the resolution).

## Test Plan

Write the resolution/warning tests first (red), then touch `cli.py` (green) — this phase's code
changes are behavioral.

- Extend the parametrized channel-discipline test: the removed-var hint and the tree-walk
  deprecation go to stderr, never stdout.
- New resolution tests: both vars set + disagreeing ⇒ `CLAUDRON_VAULT_PATH` wins (alias never
  read); `CLAUDRON_VAULT`-only + no walk-up vault ⇒ exit 3 with the removed-var hint on stderr;
  neither ⇒ walk-up unchanged.
- `status --json` carries `engine_version`; envelope shape unchanged otherwise.
- Brief test: hint line present when notes exist, absent when brief is empty, counted against
  `BRIEF_TOKEN_BUDGET`.
- Doc-parity: a test asserting `cli.py` resolution order matches the §Environment table order and
  the removal target matches the constant (mirror the SCHEMA.md doc-parity pattern).

## Verification Checklist

- [ ] `claudron init` output contains `CLAUDRON_VAULT_PATH` and not `export CLAUDRON_VAULT=`.
- [ ] `CLAUDRON_VAULT=x CLAUDRON_VAULT_PATH=y claudron status` resolves `y`; `CLAUDRON_VAULT=x
      claudron status` outside any vault exits 3 with the removed-var hint.
- [ ] The pre-merge grep-sweep results are recorded in the PR body.
- [ ] `claudron status --json` reports `engine_version` matching `claudron.__version__`.
- [ ] `docs/INTEGRATION.md` exists; its hello-world sequence runs copy-paste clean on a scratch
      vault; its conformance checklist items are self-contained testable sentences.
- [ ] `VAULT-STRUCTURE.md` §Consumption(b) no longer implies MCP is required to consume the vault
      (the decision-C policy pointer stays); PR description quotes the diff and names the approval
      gate.
- [ ] The decision-C doc carries the dated trigger-1 amendment.
- [ ] `claudron plug` via tree-walk-only resolution emits the deprecation line; with `--claudlobby`
      it does not.
- [ ] Claudron #30 closed with the §Environment table linked; #46 closed-or-updated with the
      §Bridge decision.
- [ ] `pytest` green; channel-discipline suite green.

## What NOT To Do

- No new CLI *commands* (no `doctor`, no `context`) — F5 lean adds one field to an existing
  envelope, nothing else.
- No warn-phase machinery for `CLAUDRON_VAULT` — F3 locked the hard cut; the only trace is the
  failure-path hint. The tree-walk, by contrast, is deprecate-only here (its removal is a later
  release).
- Do not touch `SHARED_DOCS_PATH` handling — that's clauDNA's side (D1).

## Context

Area: Claudron docs + CLI · Effort: M · Risk: low (additive; one approval-gated doc amendment) ·
Priority: high — wave 1; unblocks D1/L1/C2.
