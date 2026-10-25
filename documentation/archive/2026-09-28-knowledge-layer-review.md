---
title: Knowledge-layer deep dive — review record
type: review
status: completed
created: 2026-09-28
---

# Knowledge-layer deep dive — review record

**Living work item:** [Claudfather/Claudron#170](https://github.com/Claudfather/Claudron/issues/170).
Its sub-issues are #171–#188.

**This file is a pointer, not a copy.**

- The findings, reproduction steps, fixes, fork decisions and progress live on the issues.
- Update the issues, not this file.

The original issue drafts and the `create-issues.sh` script that filed them are in git history (commit `a09e79d`).

## What was reviewed

The review looked at Claudron as the knowledge layer of the Claudfather family, cross-referenced with Claudlobby and clauDNA. It asked:

- does the family keep knowledge caching and management smart;
- does it avoid context bloat;
- does it avoid pointless backups?

| Repo | Commit reviewed |
|---|---|
| Claudron | `2c3c123` |
| Claudlobby | `28bbab1` |
| clauDNA | `69b84f4` |

**How the review was done:**

- Claudron was read end to end, and every Claudron finding was reproduced against the shipped CLI in scratch vaults.
- Hook behaviour was checked against the Claude Code hooks and memory reference, fetched 2026-09-26.
- Sibling findings came from read-only audits. The high-impact ones were re-verified.

## Verdict

**The write side is strong.** It has:

- one write door;
- a derived, disposable index;
- git as the only backup;
- fail-open hooks;
- per-brief budgets;
- parity-tested contracts.

**The gaps are in four places.**

1. **Read.** Substring scoring lets unrelated notes past the recall floor and suppresses the full-text fallback (#171, #173).
2. **Refine.** Nothing shrinks the corpus (#174, #176):
   - dedup catches exact twins only;
   - `superseded_by` is never read;
   - expiry hides notes silently;
   - there is no review queue.
3. **Session loop.** Hook behaviour differs from the documented Claude Code semantics (#177–#180):
   - SessionEnd has a 1.5 s default timeout;
   - the brief is re-injected on resume;
   - the PreCompact reason goes to the user, not the model;
   - the pull lock has no deadline.
4. **Family context.** The vault is the smallest per-bot context cost. Composition and inherited `CLAUDE.md` files dominate (#186).

## Process

The fleet agent team worked the epic in four gated phases:

1. Reproduce every finding on the Pi estate.
2. Stress-test the plan (`/claudna:ironclad`).
3. Resolve forks F1–F11, with a human decision on each.
4. Implement (`/claudna:forge` → `/claudna:build-all`), with before/after evidence per sub-issue.

The full prompt and every gate outcome are recorded as comments on #170.
