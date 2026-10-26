---
title: Contract register
type: knowledge
status: current
owner: chris
tags: [contracts, boundaries, claudron, claudna, claudlobby]
created: 2026-10-26
updated: 2026-10-26
---

# Contract register

Every agreement between Claudron, clauDNA and Claudlobby: its one owner, where its authoritative
text lives, and its status. The rules each row follows (R1–R8: one owner, text lives with the owner,
consumers conform and never fork, …) are ratified in
[`../decisions/005-claudfather-boundary-separation.md` §10.4](../decisions/005-claudfather-boundary-separation.md#104-the-contract-register).

This table was part of that decision until 2026-10-26 (#237). It moved here because its status column
changes as contracts ship, and a ratified decision does not. Update a row in the PR that changes
its contract.

| # | Contract | Owner | Authoritative text (today) | Status / gap |
|---|---|---|---|---|
| 1 | Note schema | Claudron | `SCHEMA.md` | ✓ ratified; consumers conformant |
| 2 | Vault structure & tenancy | Claudron | `VAULT-STRUCTURE.md` | ✓ ratified; §Consumption(b) still implies an MCP consumer — amend |
| 3 | CLI ABI (exit codes, channels, envelope, verbs) | Claudron | `documentation/specs/CLI_CONTRACT.md` | ✓ exists; missing §Environment and §Bridge-file; missing the any-agent `INTEGRATION.md` front door decision C already *cites as if it existed* |
| 4 | **Vault address** (env names, precedence, `.claudron` bridge format) | Claudron | **none — scattered** | the live fracture: engine reads `CLAUDRON_VAULT_PATH` → `CLAUDRON_VAULT` (`cli.py:75–84`); clauDNA reads `CLAUDRON_VAULT` → `CLAUDRON_VAULT_PATH` → `SHARED_DOCS_PATH` (**inverted**); `init` prints the deprecated spelling (`cli.py:271`); Claudlobby works around a fixed bug (`dispatch-task.sh:103`) |
| 5 | **Session-loop protocol** (roles, ordering, single-prompt rule, claim mechanism) | Claudron (knowledge roles) | `documentation/specs/CLI_CONTRACT.md` §Session-loop protocol *(amended 2026-10-04 — was "none — changelog lore"; C2 #84 landed it, 0.4.0)* | ✓ the claim is structural — a front-end defers on the registered `hook pre-compact` entry; the `hooks.py:62` sniff is gone (R5 met); Claudlobby composes the loop per bot behind an R3 gate (`tests/test_claudron_loop.py`); a second host's snippet is row 12 |
| 6 | Write protocol (capture-only, `--stdin`, `written` signal, create-only, guarantee ladder) | Claudron | `CLI_CONTRACT.md` §capture (partial) | cross-host guarantee ladder undocumented; no `--source-url`, so clauDNA couples provenance to `session.py:_summary` behavior |
| 7 | Plugin skill surface (`/claudna:*`, `SKILL_CONTRACT`, `session.md` handoff artifact) | clauDNA | its repo | `session.md` is consumed by Claudlobby (`start-bot.sh:296–322`, `lib-common.sh:1098` parses `last_updated:`) but never declared a stable surface — register it |
| 8 | Fleet composition (fleet.yaml schema, bot env, grants, plugin defaults) | Claudlobby | its repo | ✓; `known_values.py:90–155` hand-tracks clauDNA's skill renames (R3 by hand — fragile, needs a gate or a feed) |
| 9 | Consumption-door policy (CLI floor; MCP demand-gate, triggers, monitor) | Claudron | decision-C doc | trigger 1 needs re-scoping after #644 (§10.5.2); monitor should be a named check, not a human habit |
| 10 | **Session join key** `(agent_cli, session_id)` — `agent_cli ∈ {claude, codex}`; `session_id` the id the agent CLI hands its hooks, in the class `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` — stated **here, once**: clauDNA `lib/claudna/session_store/paths.py:32` (`_SID_RE`) and Claudron `ops.py:33` (`_ID_RE`) are its two copies; neither test cites this row yet — the Claudron ops-log follow-up, which waits on canary C1 (a recorded Codex `session_id`), and its clauDNA mirror pin each copy to it, and if C1 widens the class both move together; plane uid `sess_` + sha256(`session_alias(id, agent_cli)`)[:32], where `session_alias(platform_session_id, agent_cli="claude")` is the raw id for `claude` (the default) and `"<agent_cli>:" + id` otherwise (Claudlobby#2145 F2) | Claudlobby | `claudlobby/plane/ids.py:83-108`: `session_alias(platform_session_id, agent_cli="claude")` composed into `derive_session_uid(platform_session_id, agent_cli="claude")` — the F2 material rule exists in that one function and nowhere else; its text in `documentation/architecture/observable-plane.md:69` *(amended 2026-10-11 — was **planned**; P1 Claudlobby Half A shipped it, Claudlobby#2203, and its release was activated on the floor host 2026-10-11; P1 Claudlobby Task 10)* | consumers conform: clauDNA keys sessions by `session_id` and records `agent_cli` at open (P1 clauDNA); P2's intake sets its session `subject = session_alias(id, agent_cli)` and its test pins the composition, not a coincidence; Claudron treats provenance — `session:<sid>:<seg>` for `claude`, `session:<agent_cli>/<sid>:<seg>` otherwise (F9) — as an opaque string in both channels (`engine.py:160-161`, `amend.py:37,63,84`) — no engine change; the normalized session attribute carries the same key (§10.2) |
| 11 | **clauDNA export contract** — `claudna.export/1`: item `session.agent_cli` (P1), `--include-skipped` status items, `segment{sealed_at,sealed_by,counts}` and the `entrypoint.json` record (`claudna.entrypoint/1`, F16, P3) | clauDNA | [`documentation/specs/2026-09-28-session-store-design.md` §8 at v0.28.0](https://github.com/Claudfather/clauDNA/blob/v0.28.0/documentation/specs/2026-09-28-session-store-design.md#8-readers-and-the-export-door): envelope shipped in v0.23.0; `session.agent_cli` in v0.27.0; P3 additions shipped in [v0.28.0](https://github.com/Claudfather/clauDNA/releases/tag/v0.28.0), commit `fe665ea6ce6cdaba95bc8692de09b1f1f6b87b77` (clauDNA#411/#412) | planned consumer: Claudlobby's `session-export` job (P3/6b) conforms to the owner's §8 and reads `entrypoint.json` for the door's path — never Claude Code's `installed_plugins.json` (F16); R6: the owner release exists; consumer integration and host activation are separate gates |
| 12 | **Codex session-loop snippet** — the normative Codex `hooks.json` shape for the engine's roles, selected by `--agent-cli codex`; same `hook <event>` identity suffix | Claudron | Shipped source: [`documentation/specs/CLI_CONTRACT.md` §Codex session-loop snippet](CLI_CONTRACT.md#codex-session-loop-snippet), renderer/install/doctor in `hooks.py`/`cli.py`/`doctor.py`, parity in `claudron/tests/test_codex_hooks.py`; gate on `"codex-session-loop" in status --json → data.capabilities` | R6: consumers compose only after a release declaring the capability. R-capture-prompt is held on SessionStart(source=compact) stdout; the noninjecting `hook pre-compact` identity remains for released structural deferral. Controlled native C1/C3 observations and limits are recorded in the 2026-10-16 P4 owner plan. |
