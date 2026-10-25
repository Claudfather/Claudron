---
title: "The vault write path — capture is a commit, and the live tree only fast-forwards"
type: decision
status: draft
owner: chris
tags: [decision, sync, capture, vault, git, resilience, claudron, claudlobby]
created: 2026-09-21
updated: 2026-09-22
---

# The vault write path — capture is a commit, and the live tree only fast-forwards

**Status: draft, issues filed 2026-09-22** — written from a 12-day vault outage on a live fleet host (2026-09-09 → 2026-09-21), reconstructed from the reflog, the rebase state on disk, `hooks.log`, and the installed `sync.py` (main at `70df0c5`). Two decisions, one contract, and the sequencing that turns them into issues. The mechanical fixes that need no design (abort a killed rebase, refuse a side branch, expire a stale lock, a read-only health door) are filed as their own issues and only referenced here.

## Summary

Today the vault is a single git working tree that every bot on a host reads its fleet configuration from and writes its knowledge into. The sync door commits whatever is on disk, then runs `git pull --rebase` **on that same live tree**, then pushes. Two properties of that shape produced the outage and will produce the next one:

1. **Knowledge is not durable until something else runs.** `capture` writes a file; `sync` commits it later. Between the two, the note exists only on one host's disk. On the outage host that gap was twelve days and 62 paths, on an SD card whose failure mode is the host's known outage cause.
2. **The live tree is also the integration workbench.** A rebase replays commits *in place*, so anything that stops it — a conflict, a timeout, a reboot — leaves the tree the fleet is reading half-rewritten, and the first thing a stopped rebase does is check out the *other* side's files. That is how a fleet's mission statement, its charter file and its projects file silently reverted on disk, and how a system review three weeks later reported them missing.

**Decision 1 — capture is a commit.** The write door commits the note it wrote, under the write lock it already holds. A note is durable the moment the door returns. Sync stops owning commits and becomes push and pull only, with `git add -A` demoted to a safety net for files written around the door.

**Decision 2 — the live tree only fast-forwards.** No rebase, merge or reset ever runs on the checkout the fleet reads. Integration happens somewhere that can be killed without consequence: first in a throwaway worktree, later on per-host branches reconciled by a scheduled job. The live tree moves only by `merge --ff-only`, or by one atomic `reset --keep` to a tip that was fully built elsewhere.

Together these retire the two failure classes above. They do not retire the operational ones — a wedged tree still needs detecting and a stale lock still needs expiring — which is why those ship first as plain fixes. And they leave one gap open by design, named here so it is not mistaken for a closure: **the safety-net commit is host-attributed, not fleet-attributed.** A host runs several fleets against one vault, and a `sync` run by one fleet's bot sweeps every fleet's stragglers into one commit whose message names the host (reproduced live on 2026-09-22: one fleet's pull committed two files another fleet had written). Decision 1 shrinks that sweep to the files written around the door; it does not make the sweep say whose files they were. The cheap refinement, carried on the capture-is-a-commit issue, is one straggler commit per top-level fleet directory, or a message that lists the directories swept — either makes the sweep auditable without changing who runs it.

## Context — what actually happened

Dates are real; host identifiers are omitted because this document is public.

| When | What | Which default was missing |
|---|---|---|
| ~2026-08-22 | The host's vault clone was switched to a docs branch and never switched back. | Nothing refuses branch operations inside the vault (Claudlobby #745 is prose). |
| 08-22 → 09-09 | 59 sync commits landed on the side branch; 53 were never pushed. A mission expansion, a charter file and a projects file were among them. | Sync commits to whatever branch is checked out and pushes `HEAD`; no door says "you are not on main". |
| 2026-09-09 14:08 | The SessionStart hook ran `sync --pull` on its **2-second budget** (`hooks.py:38`). The then-current `pull --rebase origin HEAD` began replaying all 59 commits onto the remote default branch; the timeout killed git after the first pick. The tree was left detached, mid-rebase, with main's files checked out. | A timeout that can kill a local replay (`sync.py` `SyncTimeout` docstring says exactly this); no abort on the way out. |
| 2026-09-09 20:22 | A later sync committed one more note **onto the detached HEAD** — reachable from no branch. | Fixed since by #147's refusal (installed on the host). |
| 2026-09-10 23:13 | The host hard-reset. A boot-time git process died holding `.git/index.lock`. | Git never expires locks; nothing else does either. |
| 09-10 → 09-21 | Every hook-driven sync refused, correctly, and logged the refusal to `.claudron/hooks.log` — a file nothing reads (#149). The hooks call `sync()` directly and never `cmd_sync`, so whether anyone ran the bare CLI in this window is not in the evidence; had they, `cmd_sync` would have printed `sync: nothing to do` on stdout beside the real reason on stderr — the #142 shape, reconstructed from the cited source rather than observed. Bots wrote 62 paths into the wedged tree. A deploy session ran `generate` from the reverted manifest, so the running fleet lost its mission expansion. | No scheduled reconciliation (#43), no health rung (Claudlobby #1650), no provenance check on the manifest the compositor reads. |
| 2026-09-21 | Repaired by hand: bundle, rescue commit, `rebase --quit`, `checkout -B main origin/main`, two merges (9 conflicts, 6 of them `INDEX.md`), push. | — |

Three facts from the repair matter for the design:

- **Six of nine conflicts were `INDEX.md` files**, and every one resolved as the same mechanical union of entries. Navigation files that are hand-appended by every writer are the dominant conflict source, and they are derivable from the index Claudron already builds.
- **The killed rebase had no conflict markers.** `sync.py`'s "never abort, the human needs the markers" rule (the conflict branch, lines 289–305) is right for a conflict and wrong for a kill; the two states need opposite responses and are distinguishable (`stopped-sha` absent, zero unmerged paths).
- **The tree the fleet reads was rewritten by an operation nobody intended.** No amount of sync hardening fixes that while integration happens in place.

## The states of a vault clone, and what each door does with them

The rule from the estate's own doctrine: when a process stops to ask, the defect is the unmodeled state. So the states are enumerated first, and every door below is defined against all of them.

| # | State | Today (`sync.py` main) | After this design |
|---|---|---|---|
| S1 | On default branch, clean, in sync | commit nothing, pull no-op, push no-op | same |
| S2 | On default branch, clean, ahead | pull rebases in place (no-op replay), push | fast-forward check, push |
| S3 | On default branch, clean, behind | pull rebases in place | `merge --ff-only` on the live tree |
| S4 | On default branch, dirty (files written around the door) | `add -A` + commit, then pull in place | safety-net commit (capture already committed its own), then S2/S3 |
| S5 | On a side branch with upstream | commits and pushes **to the side branch**; rebases onto its upstream | **refused** by every door that moves the tree — `sync`, the hooks' `pull --ff-only`, the scheduled job — unless `sync --branch <name>` is passed by hand; the health door reports it |
| S6 | On a side branch, no upstream | pull skipped, push creates the remote branch | refused, as S5. S5 and S6 share the verdict `side-branch`; the envelope's `upstream` field (name or `null`) is what tells them apart, so the 13 states map to 12 verdict values |
| S7 | Detached HEAD | refused (#147) | refused; health door reports it |
| S8 | Rebase stopped on a conflict | refused (#147); markers stay for the human | cannot occur on the live tree; occurs only in the worktree, where the worktree is discarded and the conflict reported |
| S9 | Rebase killed mid-replay (no conflict) | refused (#147); left for the human | `rebase --abort` on the way out of the kill; the live tree is never in this state once integration moves off it |
| S10 | Merge in progress | refused | as S8 |
| S11 | Stale `index.lock`, no owner | every write fails with git's "another process" text | expired when older than a threshold and no git process is alive; reported otherwise |
| S12 | Remote unreachable | pull/push fail, detail set | same. The health door's default verdict is computed **offline** (it must answer in under a second with no network); `unreachable` is reported only when the caller passes `--reach`, so a consumer that wants "cannot reach" distinguished from "behind" asks for it |
| S13 | Divergent: local commits not on remote and remote commits not local | rebase in place | worktree rebase, or per-host branch reconciliation; the live tree waits and reports |

Every state a consumer can be asked about must be a distinct verdict on the health door (below). A door that collapses S9 into S8, or S12 into S1, recreates the outage's silence.

## Decision 1 — capture is a commit

**Mechanics.** `engine.capture` and `engine.append_addendum` already hold `vault_write_lock` while they write (`engine.py:288`, `:343`). Inside that lock, after `atomic_write_text`, the door runs `git add -- <path> [<navigation files>]` and `git commit` with the same identity fallback sync uses (`_FALLBACK_IDENTITY`). One subject format, everywhere: `capture(<actor>): <title>`, where `<actor>` is `CLAUDRON_ACTOR`, else `BOT_NAME`, else `operator`; the body's first line carries `type: <type>; tier: <tier>; path: <relative path>`. The vault is private, and attribution is the one thing the shared git identity cannot otherwise record (Claudlobby #1039).

**What sync becomes.** `sync()` keeps its `git add -A` step as a safety net for files written around the door — bots on this estate still write planning docs with a shell redirect — but the commit is no longer the thing that makes knowledge durable. The safety-net commit message says so (`vault sync: N straggler(s) from <host>`), so the two classes stay countable and the direct-write habit stays visible.

**Failure modes, in the order they should be handled.**

- Commit fails (no identity, lock contention, disk full): the note is on disk and the door returns `ok: true` with a `warning` naming the commit failure. A note that exists and was not committed is strictly better than a refused capture, and the safety net will pick it up.
- Commit is slow: measured on an SD-card host, `git commit` of one file is well under a second. The write lock is already held for the write; the commit extends the critical section by that much. If a host measures worse, the door gets a `--no-commit` escape, never a silent skip.
- The index (`.claudron/`) is gitignored and derived, so it is never part of the commit.

**Non-goals.** Capture does not pull and does not push. Network stays out of the write path so that an offline host can still capture, which is the property the SessionStart budget was protecting.

## Decision 2 — the live tree only fast-forwards

**Phase 1 — integrate in a throwaway worktree.** When the live tree is in S13 (divergent), sync does not rebase it. It resolves the upstream to a commit id in the live tree (`git rev-parse @{upstream}` — a detached worktree has no upstream of its own, so the target must be a sha), creates `git worktree add --detach <tmp> HEAD`, gives the worktree a temporary branch (`git switch -c tmp/integrate-<ts>`; git refuses to rebase a detached HEAD), and rebases *there* onto that sha. On success it moves the live tree with one `git reset --keep <rebased-tip>`, which moves the current branch ref **and** updates the working tree in a single operation, refusing if a straggler write would be clobbered (that is S4, handled first). The worktree and its temporary branch are then removed. On any failure the worktree is removed and the live tree is untouched; the failure is reported with the conflicted paths. A kill mid-replay leaves a stale worktree, which the next run prunes. The timeout can then be as tight as the hook wants, because the thing it kills is disposable. Measured on a two-clone fixture: the live tree's HEAD is unchanged until the reset, and after it the branch sits at the rebased tip, clean, zero behind.

The reset has its own interruption window, and it is bounded rather than zero. `git reset --keep` writes the branch ref atomically (git's lockfile-and-rename), then rewrites the working-tree files that differ between the old and new tips. A kill inside that window leaves the branch at the new tip with a working tree that lags it by some of those files — a state the health door reports as `dirty` (tracked files differing from HEAD), never as detached or mid-rebase, and one the next run repairs with the same idempotent `reset --keep HEAD`. The window is the time to rewrite the changed files, sub-second on this vault; the exposure is a partially stale read until the next run, not a lost commit and not a reverted manifest. That is the residual the design accepts in exchange for removing the multi-commit replay window, and it is why the reset is done under the write lock with the timeout released for that one step.

**Phase 2 — per-host branches, reconciled on a schedule.** Each host pushes to `sync/<host>` instead of main. A reconciliation job — the scheduled door Claudron #43 plans, run by the fleet supervisor as a dormant host job on one host — merges every `sync/*` into main with `INDEX.md` regenerated rather than merged, and each host's live tree then `merge --ff-only origin/main`. No rebase runs anywhere near a live tree, conflicts happen in one known place on a schedule, and a host that cannot reach the remote simply accumulates commits on its own branch.

Phase 1 is a contained change to `sync.py` and ships first. Phase 2 needs the reconciliation job to exist and is the end state. Both keep the repository shape a human already understands.

**Why not just keep a single branch and be careful.** The estate's bots write to this tree from 21 sessions on one host and from a second host. "Be careful" was the design for a month, and its one lapse cost twelve days of knowledge durability and a silent mission revert.

## The contract with the fleet supervisor

Claudlobby consumes siblings by contract, never by assertion. It must not run `git status` in the vault and reason about the output, and it must not use `claudron status --json` as a health probe: that command walks the whole tree (#134) and rebuilds and **writes** the index (#88) — a read-path diagnostic that mutates the repository.

The door is **`claudron sync --check --json`**: git-only, read-only, bounded, one envelope:

```json
{"ok": true, "command": "sync",
 "data": {"check": true, "state": "clean|ahead|behind|dirty|side-branch|detached|rebase-conflict|rebase-killed|merge|stale-lock|divergent|unreachable",
          "branch": "main", "default_branch": "main", "upstream": "origin/main",
          "ahead": 0, "behind": 0, "uncommitted": 0, "uncommitted_oldest_age_s": null,
          "lock_age_s": null, "interrupted": null, "last_sync_ok_at": "2026-09-21T16:12:03Z"},
 "warnings": [], "errors": []}
```

The default branch is resolved as `git symbolic-ref --short refs/remotes/origin/HEAD` **with the `origin/` prefix stripped** (measured: the raw value is `origin/main` while `symbolic-ref --short HEAD` is `main`, so an unstripped comparison refuses every healthy clone), falling back to `init.defaultBranch`, then to a local branch named `main`. Exit codes follow the CLI contract: 0 for a verdict (including bad news), 2 for a usage error, 3 when no vault resolves; the verdict itself is always in the envelope, never in the exit code. The state vocabulary is the S-table above (twelve values for thirteen states, S5/S6 sharing `side-branch`). Consumers on the supervisor side: the doctor rung (Claudlobby #1650), the fleet-pulse watchdog, and the dormant `vault-sync` host job, which records every outcome on the observable plane so "last successful sync" has a denominator (#149). `last_sync_ok_at` is read from a small journal that `sync()` writes on every run; `--check` itself never writes.

## Sequencing

Ordered so that nothing waits on a design decision it does not need. The issues (filed 2026-09-22): Claudron #152 (abort a killed rebase, refuse a side branch), #153 (stale `index.lock`), #154 (`sync --check --json`), #155 (`INDEX.md` from the index), #156 (hooks pull `--ff-only`), #157 (capture is a commit), #158 (the live tree only fast-forwards); Claudlobby #1720 (vault git-state guard hook), #1721 (dormant `vault-sync` host job), #1722 (manifest provenance), #1723 (protocol points at the navigation door), and a comment on #1650 (the detection rung).

1. **Mechanical, no dependencies.** Sync aborts a killed rebase and refuses a side branch (#152). Sync expires a stale lock (#153). Supervisor: the vault git-state guard hook (Claudlobby #1720); the manifest provenance rung (Claudlobby #1722).
2. **The contract.** `claudron sync --check --json` (#154). Then the supervisor's doctor and pulse rungs consume it (Claudlobby #1650), and the dormant `vault-sync` host job runs the door on a cadence and records outcomes (Claudlobby #1721).
3. **Stop rewriting live trees from hooks.** SessionStart pulls with `--ff-only` only, within its budget; commits and reconciliation move to the scheduled job (#156).
4. **Decision 1.** Capture commits (#157).
5. **Decision 2, phase 1.** Worktree-isolated integration (#158).
6. **Navigation as a derived file.** `INDEX.md` generated from the index (#155); the fleet's shared-documentation protocol points at the door (Claudlobby #1723).
7. **Decision 2, phase 2.** Per-host branches and the reconciliation job (filed when #158 has run for a fortnight).

## Open questions for the owner

1. **Direct writes.** Bots still write planning docs with a shell redirect, bypassing capture. Keep tolerating that through the safety net, or route it through `claudron capture --stdin` and guard the rest? The safety net is the recommendation; the guard hook can warn on direct writes later without blocking.
2. **Where the reconciler runs.** A dormant host job on the primary host is estate-native and needs no CI minutes on a private repository; a GitHub Action is host-independent. Recommendation: host job first, because the supervisor already has the job pattern and the alert path.
3. **Who owns `INDEX.md`.** Today an indexing skill is the declared sole writer and bots append lines by hand anyway. Recommendation: Claudron generates it from the index it already builds, and the skill becomes a thin caller.
4. **Attribution in commit messages.** The vault is private, so a bot name in the commit subject is acceptable. Confirm.

## Related

- Claudron: #142 (success-shaped failure), #147 (refusal on a mid-surgery tree, landed), #43 (scheduled reconciliation), #149 (no denominator), #88 and #134 (status is not a probe), #140 (untracked canonical content).
- Claudlobby: #1650 (detection rung), #745 (vault-hygiene guardrail), #1039 (attribution), #1638 (restart context loss, the sibling outage class).
