---
title: "E5 — Lifecycle & curation: the cauldron refines"
type: plan
status: active
owner: chris
tags: [epic, lifecycle, curation, promotion, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E5 — Lifecycle & curation: the cauldron refines

**Release:** 0.5.0 · **Depends on:** E4 for PR2–4 (near-dup clusters, queue
queries) — **PR1 (lifecycle verbs) needs only E1 and may pull forward to
≤0.3.0** so curation exists at or before the fleet write door opens (panel:
align-to-mission; the mission says curation is "built in from day one") ·
**Implements:** the empty `promote.py`

## Goal

Make the cauldron metaphor real: raw bot findings go in, refined canon comes
out, and everything between is visible and workable. Without lifecycle,
bot-written vaults rot — this epic is where curation stops being a stub.
Supersedes issue #11 (see below — it is *not* closed as asked) and partially
closes #12.

## Design

**Trust lifecycle (per-note `maturity` — the D11 trust axis, a separate field
from the activity `status`; fields reserved in E1):**

```
maturity:  draft ──promote──► verified ──promote──► canonical
status:    active | completed | superseded | archived   (orthogonal —
           a canonical note can be superseded; both axes rank in E4)
```

- Bot captures (E2/E3) enter as `maturity: draft` by default; humans may write
  any maturity
- `claudron promote <note> --to verified|canonical` — human-triggered in v1;
  records `promoted_by`, `promoted_at`; `--demote` exists and is logged the
  same way. **The human gate is for `canonical` only and it is deliberate** —
  fully automated curation has shipped in the field with zero longitudinal
  anti-rot evidence (F5); the gate is the conservative side of an open bet
- Ranking (E4) boosts canonical > verified > draft on the maturity axis;
  recall briefs (E2) label maturity so consumers weigh trust
- **Personal-vault curation story (panel question, answered):** `claudron
  review` is human-runnable from day one — the fleet-less dogfood user *is*
  the librarian, working the same queue interactively that a Claudlobby bot
  later drains on cron. The librarian bot is the automation of the workflow,
  not the workflow itself
- **Supersession over decay (F5, binding):** `expires` and TTL are *review
  triggers*, never deletion or silent-removal triggers. The terminal path for
  stale knowledge is explicit: update it, or supersede it (`superseded_by:
  [[New Note]]` + status `superseded`) — superseded notes stay queryable and
  flagged, exactly as the mission promises. The existing lookup behavior
  (expired excluded by default, `--include-expired` opt-in) is softened to
  down-rank-and-label once a note has a `superseded_by` pointer, so agents
  land on the successor via the link rather than losing the trail

**Tier promotion (where a note lives = who sees it):**

Extends claudlobby's promotion ladder (`shared-documentation.md:47-49`) —
with the mapping corrected per the panel: claudlobby's rungs are `memory/` →
`shared/` → **`library/`**, where the top rung is *cross-deployment via PR to
the open-source repo*. Claudron's vault `_shared/` slots in as a **middle
rung** (fleet-overlay → whole-vault visibility); the true analogue of
claudlobby's `library/` is **E6 packs** (cross-deployment via git). So the
full ladder reads: bot `memory/` → fleet `<fleet>/shared/` → vault `_shared/`
→ pack (E6). (The "ratified-but-unadopted" label belongs to claudlobby's
INDEX.md ADR, not its ladder doc — descriptor corrected.)

- `claudron promote <note> --to-tier shared|_shared` — moves the file,
  preserves history (`git mv` when in a repo), stamps provenance. **No
  inbound-link rewriting** (panel: cost-benefit + engineering): wikilink
  resolution is title→alias→slug, *path-independent by design*, so a tier
  move breaks zero inbound links; the machinery the draft planned was the
  epic's own top corruption risk spent on a non-problem. Instead: a post-move
  edges-table assertion (all inbound links still resolve) and a duplicate-
  title check across tiers (already a `validate` warning from E1)
- **Issue #11 superseded, not closed:** #11's hard requirement is *direct*
  cross-fleet reads with no copying — this design rejects that in favor of
  auditable promotion (tenant boundary stays simple; the escape hatch is
  promotion). #11 gets closed as superseded-by-design with that rationale,
  not marked delivered.

**Review queue (the librarian's worklist):**

- `claudron review` — surfaces: expired (`expires` past), TTL-stale
  (`updated` + 90d default), drafts idle >N days, unresolved-link hotspots,
  near-duplicate clusters (title/alias similarity from E4), and
  **contradiction candidates** (same-topic notes with conflicting status or
  divergent recent updates — the category Karpathy's lint pass leads with, F5)
- `--json` output shaped for a Claudlobby librarian bot to work through on
  cron — the fleet's first standing curation job; the mission's "librarian"
  cron in claudlobby's INDEX convention finally gets its tool
- Terminal statuses stay queryable but flagged (existing behavior, kept)

**Capture-time categorization (issue #12 — partially, honestly):**

- `claudron capture --suggest` returns tier/type/tags suggestions computed
  from the finding text + existing corpus (tag co-occurrence, title
  similarity) for the *writing agent* to accept or override — the agent
  chooses, Claudron suggests. No LLM at index time, ever (mission non-goal).
- #12 asks for *auto-route by default*; suggest-first is the deliberate v1
  subset (route-by-default graduates only once dogfood shows suggestion
  precision is high — a named gate, since low-precision suggestions compound
  the "nobody runs the review queue" risk). #12 stays open, annotated, until
  routing ships.

## Phased PRs

| PR | Scope |
|---|---|
| 1 | maturity lifecycle + `promote --to` + provenance stamps + ranking boost — **needs only E1; pull-forward candidate to ≤0.3.0** |
| 2 | tier promotion (`--to-tier`, git-aware move, post-move edges assertion — no link rewriting) |
| 3 | `review` queue + `--json` librarian contract + docs for the cron pattern and the human (fleet-less) workflow |
| 4 | `capture --suggest` + supersede/annotate #11 and #12 per above |

## Acceptance criteria

- Full loop demonstrated on the dogfood vault: a bot draft → human `promote`
  → canonical, provenance visible in frontmatter and `git log`
- Tier promotion: post-move edges assertion passes (zero broken inbound links
  — proven by resolution, not by rewriting)
- `claudron review --json` drained weekly for two consecutive weeks — by the
  maintainer directly during fleet-less dogfood, by a claudlobby bot once a
  fleet exists
- Lifecycle metric live: % drafts reaching verified/canonical `maturity`
  reported by `claudron status`

## Non-goals

- Automated promotion (N-bot voting, LLM judges) — v1 promotion is human;
  the provenance schema leaves room, Claudosseum-style gates can come later
- Cross-fleet query surface (rejected; promotion is the mechanism)
- Editing/rewriting note content during curation (curation moves and stamps;
  content changes are normal edits)

## Risks

- **Nobody runs the review queue** → wire it into the maintainer fleet as a
  standing bot job in the same PR that ships it; a queue without a worker is
  a dashboard.
- **Promotion friction → everything stays draft** → `promote` must be
  one-command cheap; recall labels (not hides) drafts so un-promoted knowledge
  still circulates with correct trust signals.
- **Tier-move mistakes** → dry-run default (`--apply` to execute), post-move
  edges assertion, and the vault is git — revert is always available. (The
  draft's "link rewrite corrupts notes" risk was retired with the rewrite
  machinery itself — moves no longer touch note bodies.)
- **Heuristic noise** (contradiction candidates, `--suggest`) → both are
  precision-gated: if dogfood shows low precision, they stay suggestions/
  queue-flags and #12 routing does not graduate — queue noise compounds the
  "nobody runs the queue" risk, so noisy heuristics lose their queue slots.

## Field evidence

See [07-field-research.md](07-field-research.md). **F5 validates this epic's
shape and amends one behavior.** Validated: maintenance-by-review as the
curation mechanism (Karpathy's lint: contradictions, superseded claims,
orphans, missing cross-references — our `review` queue is that list), cron
librarian agents as the worker (obsidian-second-brain ships four; our
claudlobby librarian bot is the fleet-native version), and capture-at-
compaction feeding the queue. Amended: no verified system deletes on TTL —
supersession is the primitive, hence the `superseded_by` field (E1) and the
review-trigger-not-deletion semantics above.

**The open bet this epic deliberately takes the conservative side of:** fully
automated curation (auto contradiction-resolution, no human gate) has shipped
in the wild but carries zero longitudinal anti-rot evidence, and its critics
predict LLM-content-poisoning over time. Claudron keeps the human gate for
`canonical` in v1; the provenance schema leaves room to loosen later with
evidence. Two unverified formal results to re-check at epic kickoff (they
would strengthen, not change, this design): a gated proposed→active lifecycle
as a formal analogue of draft→verified→canonical (arXiv 2606.00007), and
commit-reveal vote concealment as the highest-value multi-reviewer defense —
relevant if promotion ever becomes N-bot voting.
