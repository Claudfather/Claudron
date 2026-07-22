---
title: "Boundary re-architecture — implementing §10 across Claudron · clauDNA · Claudlobby"
type: plan
status: draft
owner: chris
tags: [plan, epic, boundaries, architecture, claudron, claudna, claudlobby]
created: 2026-07-20
updated: 2026-07-20
---

# Boundary re-architecture — overview

## Summary

Implements the boundary ratified-for-review in
[`../2026-07-20-claudfather-boundary-separation.md`](../2026-07-20-claudfather-boundary-separation.md) §10:
the **contract register** gets owners and text, the five §4 drifts get their one-home resolutions, and
the fleet gets the knowledge loop it currently lacks. Nine phases, one PR each, three repos, sequenced
so every repo stays independently shippable at every point — no lockstep release, no identity
compromise (PyYAML-only / marketplace-only / local-first all preserved).

## Architecture

Target state, in one paragraph per repo:

- **Claudron** owns its consumption surface as a product: `docs/CLI_CONTRACT.md` grows §Environment
  (the vault-address table) and §Write-guarantees (the cross-host ladder); a new `docs/INTEGRATION.md`
  is the any-agent front door; a new session-loop protocol section defines the four roles
  (continuity / recall / capture-prompt / sync), their ordering, and a **declared claim mechanism**
  for the capture prompt that retires the `hooks.py:62` plugin sniff. The engine stops knowing
  consumers by name (R5) and gains `capture --source-url` so consumers stop coupling to
  `_summary()` behavior.
- **clauDNA** stays the ergonomics layer over the door: re-orders its env ladder to the contract
  (`CLAUDRON_VAULT_PATH` first), declares its `session.md` handoff artifact a stable surface with a
  minimal field contract, adopts `--source-url`, and (wave 3) runs the Q-closure triage over
  skill-embedded reference content. The raw-tree fallback stays frozen, untouched.
- **Claudlobby** validates the door that exists (validator inversion + `claudron_compat` floor check;
  the phantom-MCP warning dies), drops the `dispatch-task.sh` workaround, **wires the fleet knowledge
  loop** (composer installs the engine's hooks + sets the claim env when a bot is vault-wired),
  returns the `library/lessons/` corpus to the vault and composes from it, stamps the vault door into
  the bot template, and gains conformance gates (known_values rename-map drift gate). The mission
  sentence is reworded to what was always meant: engineering-workflow behavior is clauDNA's;
  fleet-operations commands are runtime content.

The interface between systems stays **CLI-as-ABI (subprocess)** everywhere a knowledge operation
crosses a repo boundary — the only interface compatible with all three identities and the no-PyPI
constraint. The `[vault]` git-extra remains the one sanctioned *import* seam (composition-time fleet
resolution only, already pinned `@v0.2.0`, routed through `paths.py`); nothing new imports Claudron
at runtime. **No compose-time `claudron` CLI use anywhere** (F4 locked away the one candidate);
knowledge reaches bots at session time through the loop. In-repo duplication is
retired where found (lessons corpus, hand-tracked rename map); every rendered copy of an owner
surface carries a drift gate (R3), including the hook-settings snippet L2 composes. MCP remains
demand-gated per decision C with the re-scoped trigger (§10.5.2). R5 residue is scheduled, not
hidden: C2 retires the hooks sniff; C1 deprecates the Claudlobby tree-walk (`cli.py:104–113`).

**Program gates.** (1) *Wave-1 entry:* boundary spec §10 placements ratified and forks F1–F8 locked
— the ironclad review cycle is the ratification venue; no approval-gated SSOT amendment merges
before its fork is locked. **[discharged 2026-07-20.]** (2) *Issue-tracker reconciliation (wave-1
task):* execute Claudlobby #654's promised re-scope of #511/#512/#513, close-or-re-scope #513/#251,
and reconcile the in-flight #560–564 branch work with L-phase scope before wave-1 Claudlobby PRs
open. **[discharged 2026-07-22: #511/#512 re-scoped to CLI-verb framing (MCP-fragment scope parked);
#513/#251 closed as mooted by decision C.]** (3) *Post-wave-2 checkpoint:* after L2 soaks on the
dogfood fleet, verify the loop actually accumulates knowledge before wave-3 effort is spent —
"wiring landed" and "mission advanced" are verified separately. **Soak criteria (transplanted from
the retired Claudlobby #513, ≥2-week soak on a ≥25-note corpus):** (i) lookup fires on ≥50% of
dispatches; (ii) ≥3 observed hit-used-in-output instances (impact, not activity); (iii) dispatch
P95 within 10% of baseline; (iv) cold-start + RSS within the fleet's budgets; (v) weekly
vault-hygiene sweep returns zero hits; (vi) flat counters trigger a doctor check before being read
as non-adoption. *Soak-fail branch:* stay opt-in, make mechanical injection the default query path,
re-run. Honesty line: this is n=1 dogfood evidence — holding until a second operator demands the
loop is a legitimate outcome, not a failure. Publish the counters to Claudron #14/#17 (the
ecosystem's first ≥2-writer field data on the F8 write-chokepoint bet).

## Companion plans

- **Source of truth:** `../2026-07-20-claudfather-boundary-separation.md` §10 (the boundary this
  implements). Do not re-litigate placements here; PR against that doc instead.
- **Supersedes the open items of** `../2026-07-09-claudna-claudron-reconciliation.md` (its
  "Open decisions" — marker, brief ownership, index maintenance — are answered by §10.5.1 and
  phases C2/L2; its "one owner per hook" framing is revised to one-owner-per-role).
- **Amends** `../2026-07-18-decision-c-mcp-demand-gated.md` (trigger 1 re-scoped after #644 —
  the Claudron-side amendment lands in phase C1; L1 carries the Claudlobby-side pointer) and
  `VAULT-STRUCTURE.md` §Consumption(b) (approval-gated, phase C1).
- **Consumes/dedups the issue-tracker layer:** Claudlobby EPIC #509 + children #511/#512/#513
  (stale MCP-fragment scope; L1/L2 dedup into their re-scoped forms), #560–564 (in-flight
  consumption work on the same surfaces), #251 (mooted by decision C); Claudron #30 (env drift —
  closed by C1), #44 + #55/EPIC #54 (provenance — cited by C2/F7), #43 (the F2 timer variant's
  tracked home), #46 (plugged-vault resolution default — answered by C1).
- **Relation to the roadmap** (`../2026-07-07-claudron-roadmap/00-overview.md`): C2+L2 deliver the
  *socket half* of E3 (fleet session integration) with zero MCP surface; E4/E5/E6 are untouched.

## Phases

**Status ledger** — the single place phase state is tracked (phase-doc banners are a convenience,
this table is authoritative). Update it in the PR that changes a phase's state.

| # | State | As of | Evidence |
|---|---|---|---|
| C1 | ✅ shipped | 2026-07-21 | Claudron #79 → `219b440`, released v0.3.0 |
| D1 | ✅ shipped (partial by design) | 2026-07-22 | clauDNA #253 merged; **steps 4 + 5 carried to clauDNA #254** (F1 ordering: the defer ships at/after the shim-removal release; `--source-url` now exists post-C2) |
| C2 | ✅ shipped | 2026-07-22 | Claudron #84 → `b6363a2`; closed #44 + #81; CHANGELOG `Deprecated` anchor for the shim in place (clauDNA #254 keys on it). **Shim removal is its own release — tracked as Claudron #85**, F1-ordered before #254's defer |
| L1 | 🟡 in review | 2026-07-22 | Claudlobby #665 (mergeable); program gate 2 discharged — #511/#512 re-scoped, #513/#251 closed (decision C) |
| X1 | 🟡 in review | 2026-07-22 | Claudron root+seams merged in #79; sibling PRs open — clauDNA #255, Claudlobby #664; Claudron mission-hygiene rider #82 |
| L2 · L3 · D2 · L4 | ⬜ not started | — | downstream; L2 unblocked by C2 (protocol + snippet shape are contract text) |

**Open follow-up trackers** (owned, out of any single phase): Claudron #85 (F1 shim removal — the F1-ordered release), clauDNA #254 (D1 steps 4+5), Claudron #83 (no CI — the register's drift gates don't run on PRs), clauDNA #256 (`project-template/CLAUDE.md` lacks the vault seam). Program gate 2 is discharged (above); gate 3 (post-wave-2 checkpoint) now carries #513's soak criteria (below).

| # | Phase | Repo | Size | Delivers |
|---|---|---|---|---|
| C1 | [Own the door](01-c1-own-the-door.md) | Claudron | M | §Environment + §Bridge + §Write-guarantees + engine version surface in CLI_CONTRACT; `docs/INTEGRATION.md`; VAULT-STRUCTURE §Consumption(b) amendment; decision-C amendment; tree-walk deprecation; `init` text fix; recall-brief discovery hint |
| C2 | [Session-loop protocol](02-c2-session-protocol.md) | Claudron | M | The four-role protocol + hook-snippet shape + consumer-defer rule as contract text (F1 locked: engine always prompts, generic text; sniff → transitional shim); `capture --source-url`/`--source-type` (per F7, cites #44/#54) |
| D1 | [clauDNA conformance](03-d1-claudna-conformance.md) | clauDNA | S | Env ladder re-ordered to contract #4; `session.md` declared stable (minimal fields); provenance via `--source-url` (capability-probe-guarded) |
| L1 | [Validate the real door](04-l1-validate-the-real-door.md) | Claudlobby | M | Validator inversion (CLI-door check via paths.py, phantom-MCP deleted); COMPAT_FLOOR amended (parked ≠ unmet) + doctor check wired incl. loop-execution evidence; `dispatch-task.sh` false comment removed; #511 dedup |
| L2 | [Wire the fleet loop](05-l2-fleet-loop-wiring.md) | Claudlobby | L | vault-wired ⇒ engine hooks installed per bot (single prompt via F1's consumer-defer); narrow verb grants (no wildcard); N-bot contention test; snippet parity gate |
| L3 | [Return the corpus](06-l3-corpus-return.md) | Claudlobby | M | lessons triage ledger → behavior-class re-homed in-context, referential subset to vault + CONVENTIONS.md promotions (no renderer, F4 locked); template stamps the door; mission sentences reworded |
| D2 | [Closure triage](07-d2-closure-triage.md) | clauDNA | S | Q-closure rule in the authoring guide; spec §10.5.5 inventory adopted as the ledger; moves gated on the promotion signal |
| L4 | [Conformance gates](08-l4-conformance-gates.md) | Claudlobby | S | rename-map drift gate (stale-live-values); hook-snippet parity gate; boundary invariants in CI (no direct vault reads) |
| X1 | [CLAUDE.md seam enforcement](09-x1-claude-md-enforcement.md) | all three | M | Root refresh + internal-seam CLAUDE.md per repo (texts authored: Claudron working tree + `docs/boundary-claude-md-seams` branches in both siblings); mission-hygiene rider |

## Complexity and Sequencing

| Phase | Size | Depends on | Parallel with |
|---|---|---|---|
| C1 | M | — | X1 |
| C2 | M | C1 (contract doc exists to extend) | D1 (its non-provenance half), L1 |
| D1 | S | C1; C2 for the `--source-url` step (probe-guarded, can trail) | L1 |
| L1 | M | C1 (validates against the named contract); #511 re-scope | D1, C2 |
| L2 | L | C1 + C2 (protocol, snippet shape, claim env); #644 P4 sequencing confirmed | L3 |
| L3 | M | C1 (adopt/migrate path documented); its ledger reuses D2's method | L2 |
| D2 | S | C1 (INTEGRATION/contract docs to cite; drift-gate precedent is clauDNA's own output-guide §3) | L4 |
| L4 | S | L1 | D2 |
| X1 | M | — (content ratified by §10; texts exist on the landing branches) | everything |

**Progress (2026-07-22):** the contract-authoring spine is shipped — **C1, D1, C2 merged**; L1
(#665) and X1 (#255/#664/#82) in review; both program gates that fenced wave 1 are discharged. L2
is unblocked. The critical-path prerequisite (C2's protocol + snippet shape as contract text) is met.

**Critical path:** C1 → C2 → L2 (the fleet loop is the largest payoff and sits deepest).
**Wave 1** (kills the live fractures): C1, L1, D1, X1 — after the wave-1 entry gate (forks locked).
**Wave 2** (the loop): C2, L2, **plus L4 in full** (its gates should exist before waves 2–3 create
the most new conformance surface; nothing in it waits on L3 anymore).
**Wave 3** (the corpus + hygiene): L3, D2. Each wave leaves all three repos releasable; every
phase is additive except the two locked cuts (F3's alias removal in C1; F1's shim removal on its
ordered schedule).

## Decision Forks

- **F1 — capture-prompt claim mechanism.** *Context:* §10.5.1 retires the `hooks.py:62` name-sniff.
  *Decision:* **(c′) structural consumer-defers** — chosen over the env-var claim (a) and the
  marker-file first-writer handshake (b) via `/weigh-development-paths` (2026-07-20, greenfield
  lens): the engine **always prompts** (front-end-neutral text: "distill through your capture
  door") wherever its PreCompact hook is installed and never sniffs consumers; **clauDNA's hook
  defers** when it finds the engine's registered `hook pre-compact` entry in the settings files it
  already reads (`pretooluse-permissions.sh` precedent; the grep identity is C2's normative
  `hook <event>` suffix — contract text, not implementation). The engine's glob sniff becomes a
  **transitional shim with a meetable removal condition** (deleted once clauDNA's defer ships).
  Zero new config surface; both standalone modes correct (bare clauDNA: no engine entry ⇒ clauDNA
  prompts; bare Claudron: engine prompts). **Release-ordering rule (mandatory):** the engine's
  shim-removal release precedes or accompanies clauDNA's defer release — defer-first while the
  shim lives means both sides yield and nobody prompts; the reverse ordering's worst case is a
  bounded double-prompt window. Rejected: (a) grandfathered the R5 sniff forever on workstations
  and added a permanent env contract; (b) guarantees at-most-one prompt but not the right one
  (winner = hook firing order). Reversal condition recorded: if post-wave-2 transcripts show the
  generic prompt degrading capture quality vs the direct `/claudna:capture` instruction, (a)
  remains buildable without unwinding (c′). *Ratifier:* chris (2026-07-20). *Status:* **locked**.
- **F2 — fleet loop wiring shape.** *Context:* fleet bots run no Claudron loop (§10.8.2). *Options:*
  (a) per-bot standard hooks (uniform loop; flock + bounded timeouts already handle shared-host
  concurrency); (b) host-level sync timer + per-bot recall-only hooks (one syncer per host; briefs
  stale-bounded by timer cadence) — tracked home: Claudron #43 (deployed-fleet vault sync); (c)
  dispatch-wedge only (status quo, no session loop). *Decision:* **(a)** — one loop shape
  everywhere, no new machinery, degradation already fail-open; (b)/#43 is the named escalation if
  L2's N-bot contention test or the post-wave-2 checkpoint shows push loss. *Ratifier:* chris
  (2026-07-20). *Status:* **locked**.
- **F3 — alias deprecation schedule.** *Context:* `CLAUDRON_VAULT` must not live forever
  (`SHARED_DOCS_PATH` is **out of deprecation scope** — it is the fallback mode's variable and only
  loses standing on engine paths, per D1). *Options:* (a) warn-then-remove: alias read + stderr
  warning now, removal at a target release single-sourced as one constant with a time-bomb test;
  (b) hard cut now (all known consumers are in-house and pinned; the grep sweep is the safety);
  (c) keep indefinitely. *Decision:* **(b) hard cut in C1** — the alias read is deleted, not
  deprecated; no warning machinery, no constant, no time-bomb. Softener (zero ongoing cost): when
  no vault resolves *and* the dead `CLAUDRON_VAULT` is set, the exit-3 message names the removal
  and the new var — the dotfile straggler is told at the moment of confusion. Consequences: the
  pre-merge grep sweep (three repos + dogfood vault) becomes a C1 gate; the CHANGELOG carries the
  breaking-change entry; D1 drops `CLAUDRON_VAULT` from clauDNA's ladder entirely (a consumer
  reading a var the engine ignores would re-create the two-vaults hazard in reverse). *Ratifier:*
  chris (2026-07-20). *Status:* **locked**.
  - **Amendment A1 (2026-07-21, post-C1) — the softener is broader than "zero ongoing cost."**
    C1 as shipped emits the removed-var hint on **every** invocation where `CLAUDRON_VAULT` is set
    and shadows what actually resolved — not only the exit-3 path — including the hook path
    (`cli.py:184`, `:828`), at the cost of a `detect()` walk per invocation when the dead name is
    present. **Authorized retroactively on the merits:** the failure the original softener missed is
    the *silent wrong-vault* case — a straggler dotfile exporting `CLAUDRON_VAULT` no longer errors,
    it silently resolves somewhere else, and an exit-3-only hint never fires. That is the more
    dangerous state and it deserves the diagnostic. **Recorded as an amendment because the process
    was wrong:** the implementation exceeded a locked fork and `docs/CLI_CONTRACT.md:108–116` was
    edited to describe the new behavior, i.e. the contract followed the code. Under R1–R4 the
    obligation runs the other way — a change that outgrows a locked decision amends the decision
    first. **Standing rule for every later phase:** if an implementation outgrows a locked fork,
    stop and amend the fork; never ratify code by editing the contract it violates. What stays
    forbidden under F3 is unchanged: no alias read, no warn-then-remove schedule, no time-bomb test.
    *Ratifier:* chris (2026-07-21).
- **F4 — lessons migration mode.** *Context:* `library/lessons/` (26 files incl. README) is
  corpus-class content in the runtime repo — but adversarial review showed it is **mixed-class**
  (e.g. `messaging-channel-discipline.md` is Q1 behavior, not Q2 reference; a behavior rule
  rendered as a vault pointer is inert). *Options:* (a) triage ledger first (D2's method:
  behavior-class lessons re-home to `protocols/`/guardrail slots and keep rendering in-context;
  referential lessons migrate through the door), then compose-from-vault renderer for the
  referential subset + freeze; (b) leave in place, dual-home new lessons (drift by construction);
  (c) leave + freeze, vault-only for new lessons, no migration; (d) migrate + freeze + door-stamp
  **without** a compose renderer — promote the few always-relevant lessons into `CONVENTIONS.md`,
  rely on L2's recall for the rest. *Decision:* **(d)** — the renderer was L3's largest complexity
  item and its pointer-shaped output duplicates what recall delivers ranked at session time;
  behavior-class delivery is preserved by the ledger's re-homing (protocols/guardrails render
  in-context in every mode). Consequences: L3 shrinks L→M; the program's only compose-time CLI use
  disappears (the interface rule is now absolute); L4 loses its trailing L3 dependency. Reversal
  condition: the post-wave-2 checkpoint showing migrated lessons not surfacing via recall re-opens
  the renderer against evidence. *Ratifier:* chris (2026-07-20). *Status:* **locked**.
- **F5 — INTEGRATION.md scope.** *Context:* decision C cites a vendor-neutral any-agent doc as its
  mitigation, but `docs/INTEGRATION.md` does not exist — the scope must be fixed before writing it.
  *Options:* (a) get-the-CLI install section + copy-paste hello-world (init scratch vault →
  `capture --stdin` → `recall`) + engine-detection step 0 (version/capability probe per C1's
  contract addition) + conformance checklist (self-contained testable sentences; R-numbers as
  parenthetical cross-refs only); (b) (a) plus a `claudron doctor` self-check command. *Decision:*
  **(a)** — the hello-world is the integrator's self-check; fleet-grade diagnosis lives in
  Claudlobby's doctor; no new CLI surface. The doc is under CLI_CONTRACT's change discipline and
  gets a canonical GitHub URL for cross-repo citation. *Ratifier:* chris (2026-07-20).
  *Status:* **locked**.
- **F6 — session.md surface.** *Context:* Claudlobby parses clauDNA's private artifact
  (`lib-common.sh:1098`, `start-bot.sh:296–322`). *Options:* (a) clauDNA declares a minimal stable
  subset (existence + `last_updated:`), Claudlobby limits parsing to it; (b) Claudlobby stops
  parsing fields (mtime-only gating); (c) full schema for session.md. *Decision:* **(a)** —
  smallest stable promise covering the observed consumption (existence + `last_updated:` ISO
  timestamp); the rest stays informal. *Ratifier:* chris (2026-07-20). *Status:* **locked**.
- **F7 — provenance transport.** *Context:* clauDNA folds provenance into a trailing body line
  keyed to `session.py:_summary` behavior (contract #6's gap) — **and the feature is already
  tracked open work**: Claudron #44 ("capture drops source_url/source_type") and #55 under EPIC #54
  (curator spine: fuller field set incl. `last_verified`, typed anchors). *Options:* (a) one schema
  gate now covering #44's set (`source_url` + `source_type`, optional fields), closing #44 on land,
  with #54/#55's extra fields explicitly deferred to that epic; (b) `source_url` only now (second
  schema gate later when #54 proceeds); (c) bless the trailing-body-line convention in SCHEMA.md.
  *Decision:* **(a)** — one approval-gated schema change (both optional fields, #44's set), close
  #44 on land, extras explicitly deferred to #54; ends the `_summary()` coupling; (c) would have
  canonized an accident. Already reflected in C2 step 3 / D1 step 5. *Ratifier:* chris
  (2026-07-20, schema approval gate). *Status:* **locked**.
- **F8 — rename-map conformance.** *Context:* `known_values.py:90–155` hand-tracks clauDNA skill
  renames. *Options:* (a) CI drift gate: parse the map's **live values** (current verb forms),
  strip to skill-dir tokens, compare against the resolved clauDNA ref's `skills/` dirs — ref from
  `bot.claudna_version` when set, marketplace-latest otherwise; promise is **stale-live-values
  only** (a *new* clauDNA rename with no map entry is undetectable by construction); (b) clauDNA
  ships a machine-readable rename manifest Claudlobby consumes (the only option that catches new
  renames); (c) freeze the map, accept staleness. *Lean:* (a) now — no new clauDNA surface, gate
  runs where the copy lives (R3); (b) is the named upgrade if a rename ships unnoticed.
  *Decision:* **(a)** with the stale-live-values promise stated in the gate's docstring.
  *Ratifier:* chris (2026-07-20). *Status:* **locked**.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **[high]** Silent push loss at fleet scale — N concurrent SessionEnd pushes serialize on the flock under a 10s fail-open budget; a timed-out push logs to a file nothing reads | the loop is dead on part of the fleet with no observer | L2 adds an N-bot (≥8) contention test; doctor's claudron section surfaces loop-execution evidence (hooks.log degradation recency, last push timestamp); unpushed commits travel on the next SessionEnd; escalate to F2(b)/#43 if the test shows loss |
| **[high]** Wildcard `Bash(claudron *)` grants would defeat human-gated curation | bots could promote their own drafts, rewire bridges, bulk-migrate | L2 composes a narrow verb allowlist only (lookup/recall/capture/status); fresh-box asserts a vault-wired bot cannot run `claudron promote`; program-wide What-NOT rule below |
| **[med]** Rendered-copy drift on the composed hook snippet | every vault-wired bot silently runs stale hooks | the snippet shape is C2 contract text; L4 parity gate compares composer output against the pinned engine's `settings_snippet()` |
| **[med]** Alias hard-cut breaks an unseen consumer (F3 locked: cut in C1) | broken resolution on stragglers — chiefly human dotfiles `init` itself taught | pre-merge grep sweep across all three repos + the dogfood vault (a C1 gate); the exit-3 message names the removed var when it's set; CHANGELOG breaking-change entry |
| **[med]** Lessons migration mis-classes behavior rules as reference | behavior lessons go inert as vault pointers | F4 lean (a): triage ledger before migration; behavior-class lessons re-home to protocols/guardrails and keep rendering in-context |
| **[med]** clauDNA release cadence (marketplace) lags engine changes | mixed-version fleets | every consumer change is capability-probe-guarded (C1's version surface, `claudron_compat`); no phase requires simultaneous releases; the `[vault]` pin governs only the imported API — host CLI version is read via the probe, never assumed from the pin |
| **[low]** F1 transition mis-orders and the prompt disappears (defer-first while the shim lives ⇒ both yield) | silent no-prompt window on co-installed hosts | the release-ordering rule is locked into F1 and both phase docs: engine shim-removal precedes or accompanies clauDNA's defer; the reverse ordering's worst case is a bounded double-prompt window, chosen deliberately |
| **[med]** Solo-maintainer stall mid-program (base rate is real) | half-migrated seams | waves are independently valuable; wave 1 alone retires the live fractures (§4.4, §4.5, §6); nothing in wave 1 opens a migration that wave 2 must close; D2 is the named first cut |
| **[low]** VAULT-STRUCTURE amendment trips the approval gate unnoticed | contract change without ratification | C1 names the gate in its PR description; the §Consumption(b) diff is quoted in full |

## What NOT To Do (program-wide)

- Do **not** build the MCP server in any phase — decision C holds with the re-scoped trigger;
  this program removes the *reasons* it kept getting proposed (phantom warning, missing docs).
- Do **not** merge the two SessionStart briefs — §10.5.1 keeps them two by design.
- Do **not** move Claudlobby's 44 fleet-ops skills to clauDNA — §10.1 resolves format ≠ ownership;
  only the mission *sentence* changes.
- Do **not** introduce a shared runtime package or any new cross-repo import — CLI-as-ABI is the
  boundary; the `[vault]` extra stays composition-time-only, behind `paths.py`.
- Do **not** unfreeze the raw-tree fallback while touching clauDNA conformance.
- Do **not** compose a wildcard `Bash(claudron *)` grant anywhere — curation is human-gated
  (spec §8); vault-wired bots get the narrow verb allowlist only.
- Do **not** ship a rendered copy of any owner surface without a drift gate (R3) — the rule
  applies to this program's own artifacts first (the hook snippet, the rename map).

## Context

Area: cross-repo architecture · Effort: program of 9 single-PR phases (S×2, M×5, L×2) ·
Risk: medium (all phases reversible; migrations gated behind renderers/parity checks) ·
Priority: wave 1 high (live fractures), wave 2 high (fleet loop is the mission payoff),
wave 3 medium.
