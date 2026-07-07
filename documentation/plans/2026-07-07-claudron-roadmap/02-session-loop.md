---
title: "E2 — Session loop v0: the SD card"
type: plan
status: active
owner: chris
tags: [epic, hooks, session, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E2 — Session loop v0: the SD card

**Release:** 0.2.0 (with E1) · **Depends on:** E1 · **Blocks:** nothing (E3/E4 improve it)

## Goal

A working personal knowledge loop with zero new dependencies and no MCP:
Claude Code sessions **recall** vault context at start, **capture** findings at
end, and the vault **syncs** across machines via git. This is the wedge (D1):
the maintainer feels the SD card daily, and every later epic upgrades a loop
that's already spinning.

The loop mirrors what clauDNA's skills already do for fleet bots
(`/remember → work → /learn → /reflect`), but engine-backed, hook-driven, and
personal-vault-first.

## Deliverables

1. **`claudron recall [--project <name>] [--query <terms>]`** — session-start
   context brief. Given the repo name (derived from cwd or `--project`),
   returns top-K notes: project tier first, then fleet/shared; compact
   markdown brief mode (title + one-line summary + path, hard token budget)
   for hook injection, `--json` for programmatic use. Uses today's `lookup`;
   gets better under E4 without interface change. Two rules from field
   evidence: the vault's `CONVENTIONS.md` (E1) is injected **unconditionally**
   (the always-loaded critical-facts layer, F4/F6), and everything else sits
   behind a **relevance threshold — abstention is first-class**: a weak match
   injects nothing rather than something (blind top-k injection measurably
   harms coding agents in the one — unverified — study that tested it;
   cheap insurance either way).
2. **`claudron capture`** — the guarded write path. Input: structured finding
   (stdin JSON or flags: `--type, --title, --tags, --project, --body`).
   Behavior: schema-validate (E1), slug the filename, place in the right tier,
   **dedup check** (exact/near title + alias match → warn and suggest update
   instead of create; `--update <path>` appends a dated addendum section).
   Output: created/updated path. This is where "bot-written content gets noisy
   fast" is stopped on day one — nothing writes to the vault except through
   validate-and-dedup.
3. **Hook pack, shipped in-repo (`hooks/`):**
   - `SessionStart` → **`sync --pull` (hard ~2s timeout, offline fail-open:
     serve local state and note staleness in the brief)**, then inject the
     `claudron recall` brief for the current repo. Pull must precede recall or
     machine B's brief predates machine A's push — the panel caught that the
     acceptance test fails without this placement
   - `PreCompact` + `SessionEnd` → prompt the agent to distill session
     findings through `claudron capture` (prompt-based hook; capture remains
     agent-judged). The compaction event as capture point is field-validated
     (F5); clauDNA's `precompact-reflect.sh` is the exact block-and-instruct
     template to copy (session-keyed `${TMPDIR}` marker, one prompt per
     session). **PreCompact stacking:** clauDNA users already get a
     `/reflect` prompt at the same event — the hook detects the claudna
     plugin and defers to a combined prompt (capture = vault-write half of
     reflect) rather than double-prompting; document the ordering either way
   - **Failure posture (contract):** hooks fail open — on any error inject
     *nothing*, log to `.claudron/hooks.log`, surface hook health in
     `claudron status`. An error trace injected into every session start is
     the "hook fatigue" risk realized
   - `claudron hooks install` **prints** the settings.json snippet by default;
     `--write` applies it after showing a diff. The *principle* (never
     silently write user settings) is clauDNA's; the `--write` apply path is
     **net-new, more permissive than that precedent** — say so in the docs.
     The snippet embeds the **absolute path to the resolved executable** (or
     `python -m claudron`) so venv/pipx installs survive hook context, where
     `.zshrc` PATH and env vars may be absent
4. **`claudron sync`** — thin git wrapper: `pull --rebase` → push; push
   fires at SessionEnd, pull at SessionStart (above). Conflict policy stated
   and enforced by convention: one-file-per-topic + single-writer-per-note
   makes conflicts rare; on conflict, report and leave markers for the human —
   never auto-resolve content. **Assumption documented in non-goals: one
   writer per machine** — two concurrent sessions on one machine can contend
   on `git index.lock`; concurrency is designed once, in E3, not discovered
   here.
5. **`claudron init --personal` quickstart** — the panel's time-to-hello-world
   fix (field benchmark is 2 commands; the draft's docs-only path was 6+
   steps): scaffolds the private vault repo (with E1's CONVENTIONS.md),
   prints/installs hooks, runs a doctor-style smoke test (capture a test note
   → recall finds it), prints the machine-B one-liner. Bootstrap docs shrink
   to invoking it.

## The loop, end to end

```
machine A session:  SessionStart → recall brief injected
                    ... work ...
                    PreCompact/SessionEnd → capture finding → vault commit
                    claudron sync (hook-triggered or manual) → push
machine B session:  SessionStart → recall brief now includes A's finding
```

## Phased PRs

| PR | Scope |
|---|---|
| 1 | `recall` (brief + json modes) with tests |
| 2 | **`engine.py` — the shared validate/dedup/slug module** (named home so E3's `write` imports it rather than reimplementing) + `capture` on top of it, with tests |
| 3 | hook pack (sync-then-recall SessionStart, fail-open contract, PreCompact stacking) + `hooks install` (print/`--write`) |
| 4 | `sync` + `init --personal` quickstart + dogfood checklist + **seed eval set** (checked-in query/expected-hit list incl. paraphrase variants, so the F2 hybrid-trigger metric has data before E4's harness) |

## Acceptance criteria

- The literal SD-card test: finding captured on machine A → machine B's next
  SessionStart (pull-then-recall) brief includes it, offline machine B still
  gets a brief (fail-open proven)
- `capture` refuses schema-invalid input with actionable errors; near-dup
  titles trigger the update path
- `recall` brief stays under its token budget on a 500-note vault; SessionStart
  hook total latency inside its budget (~2s pull timeout + recall)
- Time-to-hello-world: fresh machine → first recall brief via `init
  --personal` in minutes, not a docs crawl (measured in the dogfood checklist)
- Two weeks of dogfood: notes/week > 0 and trending up; saved-me tally live
  (feeds Gate G1)

## Non-goals

- MCP tools (E3) — hooks shell the CLI here
- Auto-capture without agent judgment (capture is prompted, not scraped)
- Sync daemons/watchers — sync is explicit or hook-triggered, never background
- Multi-writer concurrency — E2 assumes one writer per machine (documented
  above); vault-level locking is E3's problem, designed once
- E1+E2 is a complete, shippable product on its own (panel: first-principles).
  If fleet demand never materializes past Gate G1, the SD card still stands —
  the fleet epics extend it, they don't redeem it
- Absorbing Claude Code's native per-project memory or clauDNA's `~/.claude/notes`
  — they coexist; a later bridge may promote from them into the vault

## Risks

- **Recall noise** (brief injects irrelevant context) → hard token budget,
  project-tier-first ordering, and `--query` hint from the hook; E4's ranking
  is the real fix.
- **Capture spam** (agent writes low-value notes) → dedup gate + E5's draft
  status means captures enter as drafts, not canon.
- **Hook fatigue** (user disables hooks) → briefs must stay short; measure and
  tune during dogfood before evangelizing.

## Field evidence

See [07-field-research.md](07-field-research.md). This epic's loop is the
field's converged loop: capture at the compaction/session boundary via hooks
(F5 — shipped as post-compaction background agents plus cron librarians in
obsidian-second-brain), an always-loaded conventions/critical-facts layer
(F4/F6), git as the sync fabric (F1 — "Obsidian Sync, iCloud, Syncthing, and
Git-based sync all work without modification" precisely because the substrate
is plain files). The abstention threshold on recall answers the
memory-injection-harm caution (arXiv 2604.27283 — unverified, treated as
cheap insurance, not proof). The dedup-gated write path anticipates F8's
multi-writer gap ahead of E3 exposing it to fleets.
