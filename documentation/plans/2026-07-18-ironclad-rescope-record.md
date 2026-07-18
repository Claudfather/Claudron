---
title: "Ironclad record — re-scope stress test (decision C · E4 timing · lightened gate)"
type: plan
status: active
owner: chris
tags: [ironclad, review, rescope, e4, gate, claudron]
created: 2026-07-18
updated: 2026-07-18
---

# Ironclad record — the 2026-07-18 re-scope

A scoped adversarial panel (4 lenses: architecture / sequencing / governance /
ecosystem) attacked the three re-scope deltas — **decision C** (MCP demoted),
**E4 timing** (SQLite premature?), **the lightened Gate G1**. 24 findings raised.

**Process note (honest):** the panel's automated adjudication phase failed
mid-run (session limit) — every verify agent errored, so the raw workflow
reported "0 survived," which is a false zero, not a real dismissal. Adjudication
was then done by hand **with the source code open** — the load-bearing claims are
code-verified below, not taken on the attackers' word. That verification
*raised* confidence: most concrete claims checked out.

## Verdict per delta

- **Decision C (MCP demand-gated): STANDS in direction, under-built in record.**
  Right call — but it has no dated decision artifact, forfeits the "any agent
  discovers in-context" vision without saying so, and rests on one **unverified**
  assumption (that #644 doesn't already need per-tool grants). Fixable, not wrong.
- **Lightened Gate G1: STANDS in spirit, cut one notch too far.** "Notice if it
  works" is right for a solo hub — but it dropped the *verdict artifact*, left
  **PIVOT unreachable** (no falsifiable failure condition), and is structurally
  blind to the one failure class the architecture actually introduces.
- **E4 as next build: RECONSIDER.** This is the panel's sharpest, most
  constructive result — E4 is not one gated unit, and the urgent piece it carried
  isn't the SQLite scale work. See Theme C. This directly answers the
  SQLite-vs-markdown question.

## The five must-fix themes (24 findings deduplicated)

### A — The write-lock is orphaned while the fleet writes live · **MUST-FIX**
Code-verified: `knowledge.py:164` writes the index with a bare `write_text` (no
atomic temp+rename, no lock); note writes (`engine.py:274,321`) likewise; **zero
locking primitives in the package.** The `flock` write-lock existed *only* in
E3's `claudron_write` spec — decision C parked E3 and E4 is deferred, so the lock
has **no home**, yet clauDNA's `/capture` → `claudron capture` is the *live* fleet
write path and the G1 dogfood runs "on the Pi fleet." Two Pi bots capturing to one
vault → last-writer-wins drops an index entry (note on disk, invisible to lookup
*and* to dedup → silently re-created as a twin). "Multi-writer parked" is
contradicted by a live multi-writer door.
**Fix (pick one):** (a) land a stdlib `fcntl.flock` + atomic `os.replace` in
`capture`/`sync` now — ~15 lines, no E3/E4 dependency; **or** (b) explicitly
declare single-writer-per-vault-checkout in VAULT-STRUCTURE.md's consumption
contract and have Claudlobby serialize bot captures. Either way, stop leaving it
implicit. **This, not SQLite, is the urgent thing E4 was carrying.**

### B — "The CLI is the contract floor" has real cracks · **MUST-FIX cluster**
For C's premise (CLI floor, MCP optional-over-it) to hold, the floor must be
solid. Four code-verified gaps:
1. **`CLAUDRON_VAULT_PATH` is not read.** `cli.py:67` reads only
   `CLAUDRON_VAULT`; the contract (`CLI_CONTRACT.md:59`) and Claudlobby
   (`composer.py:611` emits it per bot) both use `CLAUDRON_VAULT_PATH`.
   Claudlobby's `dispatch-task.sh:103` *already documents the mismatch* and works
   around it with explicit `--vault` — but a bot hook running bare `claudron
   recall` from a CWD outside the vault breaks. **One-line fix**, clearly correct.
2. **Dedup `suggest_*` looks like success to a naive wrapper.** `_emit_write_result`
   (`cli.py:498-507`) returns exit 0 and `ok=true` when nothing was written; only
   `data.action` disambiguates. A skill keying on exit/`ok` silently drops the
   finding — breaking the "capture accumulates signal" invariant.
3. **`--body` interpolation is unsafe for LLM text.** A safe `--stdin` JSON door
   exists, but a skill building `--body "<model text>"` breaks on quotes/newlines
   and executes `$(...)`/backticks in its own shell. Routine input, real hazard.
4. **Typed write semantics degrade to text.** E3's `{action, reason, path}` +
   field-level errors flatten over the CLI; consumers hardening on CLI text make a
   later MCP layer a *breaking re-contract*, not the additive upgrade D3 promised.
**Fix:** harden the `--json` envelope into the durable typed contract in
CLI_CONTRACT.md (action enum incl. the not-written signal, reason, field errors);
document that programmatic writers MUST use `--stdin`; fix the env var; coordinate
clauDNA's skills to branch on `action` and pipe via stdin.

### C — E4 is the wrong-shaped and wrong-timed next build · **RECONSIDER** (answers the SQLite question)
Code-verified: `resolve_wikilinks` is still a `return {}` stub
(`__init__.py:25`); no `tests/eval` seed exists; the reference vault is ~9 notes.
Three compounding points:
- **E4 splits cleanly.** The **graph half** (`resolve_wikilinks` + `links
  --broken/--orphans` + `related()`) is **scale-independent** — it helps at 50
  notes as much as 5000, it's the mission's stated core retrieval principle, and
  E5 + a future E3 both depend on it. Its logic needs only the existing index; the
  SQLite `edges` table is a *persistence optimization*, not a prerequisite. The
  **SQLite/FTS5 half** is the scale bet.
- **The scale trigger was never measured.** D6/F2 gate the SQLite/FTS5 tier on
  "~1k notes or a paraphrase-miss threshold." The vault is ~2 orders of magnitude
  below the note trigger, and the eval harness that measures the *other* trigger
  ships *inside* E4 PR2 — so E4 was greenlit against a trigger nobody checked,
  using an *adopt-vs-build* (HOW) spike as cover for a *whether-now* (WHEN)
  decision it never tested.
- **E4's blended ranking leans on a maturity axis only E5 populates** — until E5
  ships `promote`, every note is `draft` and the maturity boost ranks nothing.
**Fix:** don't open the SQLite PR1 yet. **Pull the graph slice forward** (over the
existing index) as scale-free value; **defer SQLite/FTS5** behind the measured
trigger; build the cheap ~20-query eval seed *now* (no SQLite needed) and read
today's miss-rate. If the small vault's real pain is quality/rot (likely), **E5
PR1 (maturity + promote)** may deserve the slot over E4.

### D — The gate lost its instruments and its verdict · **MUST-FIX**
- **No `G1-verdict.md` exists** (confirmed) yet the spike unilaterally declared
  "E4's first build PR may open." The spike was a *dependency* of the gate, not
  the gate's decision — merging it can't substitute for the verdict. That's the
  PIVOT-laundering cycle-2 must-fix #1 was written to prevent.
- **PIVOT is now unreachable.** The lightened gate has no value below which the
  operator must declare failure; with sunk design cost + daily-driver motivation,
  "notice if it works" resolves to PASS by default.
- **The architecture's own failure class is invisible to it.** The two Theme-A/B
  silent failures (dropped index entries, recall false-negatives) produce no
  error and no symptom — a human can't notice the absence of a note they don't
  know exists. "Validate by real use" is structurally blind to exactly what the
  disposable-index design introduces.
**Fix (cheap, keeps it lightweight):** write the short verdict *before* any E4 PR;
retain **three** cheap signals only — (1) `claudron status` reports index-vs-vault
divergence (N on-disk notes missing from index, M ghost entries) — a real
instrument, automatable; (2) a cross-boundary recall tally that must be >0; (3) a
one-time keep/junk skim (a keep-rate number). One falsifiable PIVOT condition
makes it a gate again. No tracking tables.

### E — Decision C: sound, but under-documented with one unverified assumption · **MUST-FIX**
- **No dated decision artifact.** C lives only in a scope-note bolted onto the
  spike — the "ratified after the docs" anti-pattern. Needs its own dated doc with
  a *falsifiable* trigger, a named monitor for #644's trajectory, and the accepted
  reversal cost (re-derive E3 + un-park the fragment + re-cut bots — a fleet-wide
  migration).
- **The trigger may already be firing — VERIFY.** A skill wrapping the CLI is one
  blanket Bash grant; you cannot grant a bot `recall` (read) while denying
  `capture` (write) at the permission layer. If Claudlobby #644's grant model
  needs per-verb / read-vs-write differentiation per bot, trigger (a) is **already
  met** and MCP re-enters the path. Check #644's granularity before treating MCP
  as parked.
- **C narrows consumers and forfeits the vision.** The original E3 headline —
  "typed tools *any agent* discovers in-context" — is surrendered: the discovery
  surface is now clauDNA's skills, which exist only on a Claude-Code-+-clauDNA bot.
  A non-clauDNA / Cursor / Codex fleet member has no discoverable door and must
  hardcode `claudron recall` — which VAULT-STRUCTURE.md:121 explicitly forbids.
  Routing 100% of fleet access through a fast-moving sibling makes Claudron's #1
  metric (adoption beyond the maintainer) hostage to clauDNA, and risks quietly
  demoting Claudron to "a thing clauDNA wraps."
- **Parking strands cross-repo debt.** Claudlobby's `validator.py:243-254` asserts
  vault-present ⟹ `claudron` MCP config present; parking MCP makes that invariant
  permanently false (rots as a warning), and `CLAUDRON_VAULT_PATH` becomes a
  vestigial socket.
**Fix:** dated C decision doc (trigger + monitor + reversal cost); **verify #644
granularity**; give Claudron its *own* minimal vendor-neutral self-discovering
door (a thin `.mcp.json` recipe or a Claudron-owned always-loadable skill) so
discovery doesn't depend on clauDNA; file the Claudlobby validator/socket cleanup;
update VAULT-STRUCTURE.md §Consumption(b) to stop implying an MCP consumer.

## What did NOT survive / deflated
- "E4 blended ranking is dead-on-arrival" — overstated; the maturity term is
  *inert*, not broken (E4 ships fine, gains it when E5 lands). Kept only as a
  sequencing argument.
- The `--body` shell-injection framing is a *caller* hazard (the CLI itself is
  argparse-safe); it's a "skills must use `--stdin`" doc fix, not a Claudron bug.
- "CLAUDRON_VAULT_PATH silently breaks *everything*" — deflated: Claudlobby's
  dispatch path already works around it with explicit `--vault`; still a real
  1-line contract violation that bites the bare-hook path.

## Net
The re-scope's *directions* all hold — C, the lightweight gate, build-not-adopt.
But in lightening and demoting, the re-scope dropped four load-bearing pieces on
the floor: **the write-lock**, **the CLI-as-typed-contract hardening**, **the
gate's minimum instruments + verdict**, and **C's documentation + the #644
check**. And it mis-shaped the next build: **split E4 — graph slice forward,
SQLite deferred behind a measured trigger.** None of this is a pivot; it's the
hardening the fast re-scope skipped.
