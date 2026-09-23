# Changelog

## Unreleased

### Changed
- **A capture is a commit: the write door commits the note it wrote ([#157](https://github.com/Claudfather/Claudron/issues/157)).**

  A captured note was not durable until something else ran — `engine.capture` wrote the file, `sync()` committed it whenever it happened to run next, and between them the note existed on **one disk**. Measured on a live host: **62 uncommitted paths, oldest written twelve days earlier, 17 under `_shared/knowledge/`** — on the storage whose failure is that host's known outage cause. Durability is the one property a knowledge layer must not defer.

  **ORDERING IS THE WHOLE PROPERTY, and the change is strictly additive.** The file is written first and committed second, inside the `vault_write_lock` the door already holds. Every failure path therefore leaves an *uncommitted note on disk* — which is exactly the behaviour being replaced, so no path can be a regression in the property the change exists to improve. Pinned by tests that fail the commit for real, at **both** steps: a rejecting `pre-commit` hook (the commit fails) and a held `index.lock` (the stage fails). The note survives both.

  **`ok` does not become "committed".** A failed commit keeps `ok=True`, leaves the note on disk, and attaches a `W108` warning — in the envelope's `warnings` array, never `errors`, because nothing about the *write* failed. A consumer keying on `errors` would otherwise read an uncommitted note as a failed write and retry a write that already succeeded. W108 is a warning in **both** catalog tiers, the only member describing a note's surroundings rather than its content.

  **A wedged tree is refused, not attempted — and the capture still lands.** A capture must never repair a mid-surgery repository and must never be refused because of one. A vault that is not a git repository is **silent**: no commit, no warning, because a warning there would fire on every capture of a perfectly good plain directory.

  **The safety net stays**, and `commit_paths` is now shared by both. `sync`'s commit catches everything written *around* the door — a hand-edited plan, a bot writing with a shell redirect, which this estate still does — and says `vault sync: N straggler(s)` rather than `N change(s)` so the two commit classes stay countable in `git log`. Deleting it because captures commit themselves would strand exactly that population.

  `commit_paths` returns a `CommitOutcome` naming the step rather than the bare `CompletedProcess` #157 specified: `sync` must tell a failed *stage* (a refusal naming git's own message) from a failed *commit* (`committed=False`, carry on), and recovering that from the returned process means reading argv — which was wrong twice, first positionally (`run_git` injects an identity prefix for `commit` only, so positions shift) and then as a membership test that depended on a test double populating `args` faithfully. Naming the step removes the inference.

  **Cost, measured rather than reasoned about — and it SCALES WITH HOST LOAD, which a single figure would have hidden.** Reference SD-card host (`/dev/mmcblk0p2`), paired and interleaved with `--no-commit` as the control so both arms share the same minutes of load, n=14 each:

  | load | median delta | p90 gap | worst rep |
  |---|---|---|---|
  | ~4.0 | **+16 ms** (10% of a capture) | +76 ms | **+899 ms** |
  | ~6.0 | **+36 ms** (22% of a capture) | +45 ms | +96 ms |

  So the honest claim is **+16 to +36 ms at the median depending on load, 10–22% of a capture**, with a tail that reaches ~900 ms — a git commit on a loaded SD card occasionally takes about a second. The mean is reported by the harness only to show what that tail does to it (+101 ms against a +16 ms median on the first run); a mean alone overstates the typical cost and a median alone hides the tail.

  **The harness is committed** (`claudron/tests/bench_capture_commit.py`, not collected by pytest), because a number justifying a design decision must travel with its repro or it expires the moment anyone doubts it. The load dependence above was only visible *because* it is re-runnable — the first measurement reported +16 ms as though it were a property of the change.

  **On reconciliation cost**, since this makes the commit graph denser and that lands on the door [#156](https://github.com/Claudfather/Claudron/issues/156) just changed: a rebase replays each local commit at **~13–37 ms** (measured at 1/5/20/50 commits, noisy on SD under load), so a day's fleet divergence of 20–60 commits is roughly **0.3–1.8 s** of replay — 1–6% of `sync`'s 30 s budget. **This is safe to land only because #156 landed first.** Under the old 2-second SessionStart budget a denser graph would have made the killed-rebase wedge *more* likely, which is the outage this programme exists to close; #156 moved the rebase to a door with an honest budget, and the ordering in the programme is load-bearing rather than incidental.

### Changed
- **The SessionStart hook fast-forwards and never rewrites the live tree ([#156](https://github.com/Claudfather/Claudron/issues/156)).**

  **A budget that is right for latency is wrong for a history rewrite.** The hook ran `sync(pull=True)` on a 2 s budget: that commits whatever is on disk and then runs `git pull --rebase` in the live tree, and the only two outcomes of a 2 s rebase on a busy host are *nothing to do* and *killed part-way*. A killed replay detaches HEAD and leaves commits reachable from no branch. On the host that produced this issue the kill landed at 14:08:39 on 2026-09-09 — one pick completed, 58 pending, no conflict — and the tree sat detached until 20:22. SessionStart is not a rare event: hosts fire it on startup, resume, clear **and compaction**, so a long-running agent was rewriting its own vault at an unpredictable moment mid-session, and no discipline could prevent it.

  **`pull_ff_only` replaces it: fetch, then `merge --ff-only`. Never add, never commit, never rebase.** The safety is structural rather than budgeted — `fetch` writes only under `.git/`, so killing it leaves the working tree untouched, and `merge --ff-only` is a single ref-and-tree update with no replay to interrupt. That is what makes the same 2 s budget honest here and dishonest for a rebase.

  **The fetch names the upstream's own remote and ref, not the default branch.** On a clone tracking something else, fetching the default branch by name leaves `@{upstream}` stale, and the `merge --ff-only @{upstream}` that follows then fast-forwards onto a ref nobody refreshed — a silent no-op that reads as success. Pinned by a test that records argv on a branch whose upstream is not the default.

  **Refusals are `sync()`'s, reused rather than restated**: mid-surgery through `_interrupted_state`, a side branch through `_refuse_off_default` (shipped by [#152](https://github.com/Claudfather/Claudron/issues/152)). A door that only fast-forwards is not a reason to relax the side-branch rule — a side branch is refused because work accrues where nothing else can see it, which fast-forwarding does not fix.

  **NOT FAST-FORWARDABLE IS NOT AN ERROR, and the issue's own spec could not be followed here.** It asked for `detail = "not fast-forwardable: N local commit(s) await reconciliation"` **and** `ok=True`. Those cannot both hold: `SyncResult.ok` is derived as `not detail`. Following it literally would make every `ahead` clone report `ok=False` and train each hook to log a degradation on a healthy vault — the false-signal class [#149](https://github.com/Claudfather/Claudron/issues/149) is about. So the count rides a new `SyncResult.local_ahead` and `detail` stays empty, which honours the stated intent and the documented contract on `detail` ("non-empty exactly when something needs the human") at the same time.

  **`claudron sync --ff-only`** runs the same door, so "matches the hook's behaviour" is a shared implementation rather than a claim two call sites must independently keep true. A full `claudron sync` still rebases and is for a scheduled reconciliation with an honest budget — never a hook.

  **What an integration with no scheduled reconciliation now gets: an honest `ahead` state, and nothing that resolves it.** That is the deliberate trade. An un-reconciled `ahead` is safe and *visible* — `sync --check --json` reports it — where a killed rebase is neither, which is why this lands without waiting on the scheduled door. But it is not self-resolving: a deployment that never runs a reconciliation will accumulate divergence. `docs/INTEGRATION.md` §Session loop states that obligation to front-ends.

  **The `--rebase` pin records argv from the real git door rather than grepping source**, and carries its own anti-vacuity guard: a cycle that issues no `fetch` fails with *"the --rebase assertion is vacuous"* instead of passing. A grep-pinned test would pass on a file that merely lacks the string — including when the rebase has moved behind a variable, a helper, or a second module.

### Added
- **`claudron sync --check --json` — a read-only, git-only health verdict for consumers ([#154](https://github.com/Claudfather/Claudron/issues/154)).**

  **The state names are the deliverable, not the implementation.** Two consumers key on them (the supervisor's doctor rung and its scheduled vault-sync job), and an implementation can be rewritten where a keyed-on name cannot. `CHECK_STATES` is written once and is both the vocabulary and the precedence: `unknown` `stale-lock` `rebase-conflict` `rebase-killed` `merge` `detached` `side-branch` `dirty` `divergent` `behind` `ahead` `unreachable` `clean`. Its members are deliberately the words the repair doors already use, so "what `sync` refuses" and "what `check` reports" are not two vocabularies a reader has to translate between. A side branch with and without an upstream share `side-branch`, told apart by the `upstream` field.

  **`unknown` is the one value with no row in the design's state table, and the important one.** That table enumerates states of the CLONE and says nothing about a check that could not RUN. Returning `clean` when git is missing or a call times out rebuilds the exact silence this door exists to end — for twelve days every probe on the outage host reported the engine healthy. It carries its reason in `detail`, survives serialisation, and `CheckResult.ok` is false for it.

  **Read-only is the point, and the pin caught a real write on its first run.** The door this replaces, `status --json`, walks every note and rebuilds and WRITES the index, so asking "is this healthy" mutated the subject and could not be asked of a wedged or read-only tree. The new door's own test failed with *check() wrote the index*: a plain `git status --porcelain` refreshes the index stat cache and writes `.git/index` to do it. Measured — touch a tracked file, run `status`, and the index mtime moves; under `--no-optional-locks` it does not — and a live vault's files are touched constantly, so the defect would have been rebuilt inside its own replacement. The pin is a whitelist of subcommands rather than an mtime check, because a mutation that happened to change nothing would pass the latter.

  **Every verdict exits 0, including the bad ones.** The state lives in the envelope (`data.check: true` discriminates it; `command` stays `sync`), never in the exit code, so a consumer never has to choose between "the check ran" and "the clone is healthy". `--check` beside `--pull`/`--push` is a usage error (2); a vault that is not a git repository is an environment error (3), which is what `sync` already does for that condition.

  **Offline by default.** No network call happens unless `--reach` is passed, so a watchdog polling this is never gated on the remote being up; `unreachable` can only appear when asked for.

  Also a small journal `sync` writes and `check` only reads (`.claudron/sync.json`, gitignored): every exit from the locked section records the attempt, so REFUSALS count too — a clone refusing for a week and one nobody has asked to sync are otherwise identical, and telling them apart is the denominator [#149](https://github.com/Claudfather/Claudron/issues/149) asks for. Best-effort by construction; losing it never fails a sync.

  `docs/CLI_CONTRACT.md` and `docs/INTEGRATION.md` now say plainly that `status --json` is a **capability** probe and this is the **health** probe.

### Fixed
- **`_default_branch` answers `None` instead of guessing `main`, and a vault bootstrapped locally can sync again ([#154](https://github.com/Claudfather/Claudron/issues/154), defect in [#152](https://github.com/Claudfather/Claudron/issues/152)).** It fell back to a hardcoded `"main"` when neither `refs/remotes/origin/HEAD` nor `init.defaultBranch` could answer — a guess wearing the grammar of a fact. Three measured conditions make it fire together on git 2.39.5: a bare `git init` names its branch `master`; the bootstrap every new vault takes (`git init` + `git remote add` + `git push -u`, or cloning a still-empty remote) leaves `origin/HEAD` unset; and a host may have no `init.defaultBranch`. `claudron sync` then refused every run with *HEAD is on 'master', the vault syncs on 'main'* — a new vault that could never sync at all, so its captures reached no other machine, which is this program's own outage rebuilt by the check meant to prevent it. `_refuse_off_default` now weighs TWO facts before standing down, and an undetermined default is not on its own one of them — see below. `sync --check` reports `default_branch: null` so the condition is visible.

  **The first version of this fix widened the pass instead of narrowing the refusal, and review caught it with a construction rather than an argument.** A mature vault on a GENUINE side branch loses `origin/HEAD` too — a pruned remote ref, a reclone, a hand-rolled `remote add` — and in that state the guard was simply absent. Reproduced: a vault with real shared history, three commits of its own on `docs/side`, and no `origin/HEAD` was committed AND pushed with no refusal at all, `sync` creating the side branch on the remote. So `_is_bootstrap` requires BOTH facts — the default branch could not be determined **and** there is no other branch this clone could be supposed to be on — with "cannot say" landing on the refusing side, the same shape and the same fail-safe direction as `_killed_rebase` and `_is_expirable`. Refusing a genuine bootstrap costs one confused user an override the refusal itself prints; passing a diverged mature vault is the outage.

  **The obvious second fact does not work, which is why it is pinned as a test.** "Does this clone hold commits reaching no remote" (`rev-list --count HEAD --not --remotes`) reads **zero** on that adversarial vault, because the side branch had already been pushed — the history is on a remote, just on the wrong branch. That is the outage's own shape (59 commits off the default branch, 53 reaching no remote, so 6 that did), so a predicate satisfied by it is no predicate. The fact that discriminates is whether any other branch exists beside this one. `sync --check` reports `side-branch` for the same clone through the same predicate, so the health door and the refusal door cannot disagree about one vault.

  **And the side-branch tests were green on a coincidence.** `synced_pair` clones its remote while the remote is still empty, so git never writes `origin/HEAD` — `_default_branch` could not determine anything in those tests either, and they passed because the guess happened to equal the fixture's branch name. The predicate they exist to pin had never been exercised. The fixture now does what a real clone of a non-empty repository does.

- **`sync` aborts a rebase it killed, and refuses to run off the default branch ([#152](https://github.com/Claudfather/Claudron/issues/152)).** Both halves fired on a live fleet host and together produced a twelve-day outage: the clone was left on a side branch and quietly accumulated 59 commits that never reached the default branch (53 reaching no remote at all), then a hook-driven sync on a 2-second budget began replaying all 59, was killed after its first pick, and left the tree detached mid-rebase with the default branch's files checked out. A fleet's mission, charter and project manifest vanished from disk and a downstream compose then ran from the reverted manifest, while every sync refused and printed success-shaped output.

  **The discrimination is the whole fix, and getting it backwards is worse than the bug.** `sync` already distinguished a rebase stopped on a *conflict* — markers a human must see, and possibly a resolution already begun — from one *killed* mid-replay, which has no markers and nothing to resolve. It then handled both the same way and left the tree wedged "for the human". A killed replay is now aborted and the tree restored, with `detail` saying so; a conflict is left exactly as before. `_killed_rebase` requires **both** of its facts to say "killed" — no unmerged paths **and** no `stopped-sha` — so an ambiguous state is treated as a conflict. The asymmetry is deliberate: failing toward "leave it" costs a refusal, failing the other way costs a human's work. The signature is the one measured on the clone that wedged: a todo list and `done`, no `stopped-sha`, zero unmerged paths.

  **A clone on a side branch is now refused before anything is written.** That state is where captures look durable in `git log` and exist on no other machine, and the refusal precedes the commit on purpose — a refusal that committed first would strand one more commit every time it fired. `--branch NAME` is the only override and must name the branch actually checked out, so it stays a deliberate act rather than a blanket opt-out. `_default_branch` strips the `origin/` prefix, which is load-bearing rather than cosmetic: `symbolic-ref refs/remotes/origin/HEAD` answers `origin/main` while `symbolic-ref HEAD` answers `main`, so an unstripped comparison refuses every healthy clone — mutation-confirmed, it fails five existing tests including the main round-trip.

  Two #147 tests now pass `--branch`: their subject is which upstream a rebase targets on a feature branch, not whether a side branch may be synced, and the flag keeps them testing that.
- **A stale `.git/index.lock` is expired when provably ownerless, refused when not ([#153](https://github.com/Claudfather/Claudron/issues/153)).** Git never expires `index.lock` — it assumes the process that made it will remove it. A host reset that catches a git write leaves one behind, and from then on every `add`, `commit`, `checkout` and `rebase` in the vault fails while **every git read keeps working**. That asymmetry is why the last one went unnoticed for ten and a half days: `status --porcelain` needs no lock, so the tree read "merely dirty", and `sync` reported `the working tree is not clean after the pre-pull commit` — true, useless, and pointing at the tree rather than the cause. One such lock sat for 914,102 s and blocked every vault write for the whole of a separate outage.

  **An ownerless lock expires; a live one is refused, and ambiguity counts as live.** Deleting someone's lock is the one destructive act here — a lock whose holder is still running means a real concurrent write, and stealing it corrupts the index. So `_is_expirable` requires **both** facts: older than 600 s **and** provably unheld. Age alone is not licence (a slow write on a loaded SD card is old and live) and a lone "no owner" is not either (a probe run between git's `open` and its first write reports none). `None` — "the platform cannot say" — never behaves like `False`. Same shape and the same fail-safe direction as #152's `_killed_rebase`.

  **Ownership comes from the kernel, not from the file, and that removes the pid-reuse hazard by construction.** Measured: a live `index.lock` caught mid-write holds **no pid at all** — git writes the new index into it — so there is nothing in the file to read and no recorded pid to be reused. `lsof -t` reports whoever holds the fd *right now*, which is by definition a living process (exit 0 with pids when held, exit 1 when not — both directions measured here). GNU `fuser` is used only where `--version` identifies psmisc, because BSD `fuser` exits 0 for an unheld file and so can never evidence absence; where neither tool is available the answer is `None` and the lock is left alone.

  **A failed `git add` now returns with git's own message** instead of falling through to a failing `commit` whose symptom then got reported. A repair this run performed is also never silently dropped: an expired lock is composed into whatever `detail` the rest of the run produces, so a sync that quietly fixed a ten-day wedge says so.

  **The side-branch refusal runs first, so a refused sync deletes nothing.** Where #152's check and this one meet, ordering is a decision rather than an accident: `_refuse_off_default` only reads, while expiring a lock removes a file, and a sync that is going to refuse anyway must not perform the one destructive act on its way out. It also keeps the expiry note honest — the off-default refusal assigns `detail` directly rather than composing it, so a repair performed before it would be dropped from the report.


### Added
- **Gitignore rules for Claude fleet bot telemetry ([Claudlobby#874](https://github.com/Claudfather/Claudlobby/issues/874)).** Narrow any-depth ignore rules for `data/events/fleet-*.jsonl`, `data/.last-tool-call`, `data/.idle` — the files Claudlobby supervision hooks can write relative to the session cwd when the bot environment is absent. Defence-in-depth behind the #874 writer fix: a broad `git add` in an agent checkout can no longer stage fleet telemetry into this public repo. No product paths match these patterns.

### Changed
- **A scalar `tags:` is one tag, not a character sequence — Tier A now applies the same coercion Tier B always did ([#101](https://github.com/Claudfather/Claudron/issues/101)).** The two frontmatter parse paths had diverged: `_parse_doc` (Tier B) coerced `tags: foo` to `["foo"]`, while `index_entry` (Tier A) stored the raw scalar — so `_score_index_entry` iterated the *string* and a scalar-tagged note scored as `['f','o','o']`: the full tag word could never match (`lookup singleton` on a `tags: singleton` note returned nothing). All three coercion sites (`_parse_doc` tags, `index_entry` tags + aliases) now route through one `_as_str_list`, which also totalizes the edge Tier B used to crash on (`tags: 5` → TypeError mid-scan; now `["5"]` — the second deliberate behavior change, both pinned by tests that fail on the pre-fix code). Index entries for scalar-tagged notes change shape on disk (`"tags": "foo"` → `["foo"]`) at the next index rebuild; the entry contract was always `tags: list`, so this is the shape becoming reliable, not changing.
- **knowledge.py scoring/resolution internals de-duplicated and typed ([#106](https://github.com/Claudfather/Claudron/issues/106), [#107](https://github.com/Claudfather/Claudron/issues/107)).** The tag-exact/tag-partial/filename scoring triple — byte-identical between `_score_index_entry`'s single-phrase block and its per-token loop — now lives once in `_score_term(...)`, with the blocks' only real differences (title weight; whether the word-boundary bonus applies) as keyword arguments. `ResolutionIndex = tuple` becomes a `NamedTuple` (`by_title` / `by_alias` / `by_slug`), so the 3-map shape is visible in the type and `resolve_target` reads fields by name; tuple behavior (unpacking, immutability) is unchanged. Behavior-preservation proven two ways: a 132-case scoring+resolution battery (exact/substr/boundary/tag/partial/filename/multi-token/cap paths; title→alias→slug fall-through with tier-then-path tiebreaks) is byte-identical between main and this change, and the full suite stays green.
- **`schema._tier` renamed `_resolve_code`; `_child_dirs` is now the one dir-walk filter ([#110](https://github.com/Claudfather/Claudron/issues/110), [#111](https://github.com/Claudfather/Claudron/issues/111)).** The private validation-tier code resolver no longer squats on the codebase's dominant "tier" token (vault/search Tier A/B, `note_tiers()` loop vars) — one def, one caller, mechanical rename. The sorted/real-dirs/no-dotfiles walk filter, previously spelled out three times, is `_child_dirs` everywhere: the primitive gains `skip: frozenset[str] = SKIP_DIRS`, and the two sites that must visit reserved names — the projects scan and the structure audit's root walk (whose S2 check *audits* reserved dirs) — pass `skip=frozenset()` instead of hand-rolling the filter. Emission order and discovery are unchanged: a canary vault exercising S2 + S3 + fleet overlay + projects produces byte-identical `validate` and `status --json` output against main; full suite green.
- **PROJECT_MISSION.md no longer frames SQLite as the current index backend ([#114](https://github.com/Claudfather/Claudron/issues/114)).** The doc's own 2026-07-21 supersession stamps establish the index shipped as derived JSON (`.claudron/index.json`, no SQLite mirror) — yet the approval gate said "Adopting a non-SQLite storage backend" (presupposing SQLite is the status quo) and the graph-DB rejection said "SQLite + an edges table is plenty" (reading a deferred E4 item as shipped). Both now state the JSON index as current and the SQLite mirror as the deferred ceiling (E4, #18), preserving each line's original force: index-backend changes stay approval-gated — including graduating to SQLite — and real graph DBs stay rejected. Doc-only; the forward SQLite/graph work remains #18's.
- **`run_hook` now owns the whole hook prologue, not just the exception guard ([#108](https://github.com/Claudfather/Claudron/issues/108)).** Each handler repeated the same two lines the boundary's docstring claimed to centralize — drain the stdin payload, exit 0 when no vault resolved. The boundary now drains once, guards once, and passes the parsed payload to handlers (`(vault, payload)`, vault non-optional). Two deliberate observable deltas: the no-vault path logs uniformly for **every** event ("no vault resolvable — nothing to do", to the tmp fallback log) where before only session-start logged (and said "nothing injected"); and `hook_session_end`'s `SyncError` catch is **kept, deliberately** — a git-less vault raises `SyncError` on every push, so that catch is the *expected-degradation* logger ("sync --push skipped", symmetric with the pull side's load-bearing catch in `session_start_brief`), and dropping it would relabel a normal condition as "hook failed open" in the hooks' only observability channel. Wire behavior is untouched: a 7-invocation canary (no-vault + non-git vault × all three events, incl. the pre-compact block/pass pair) has byte-identical stdout and exit codes against main; full suite green.
- **vault.py no longer forks schema.py's frontmatter primitives ([#100](https://github.com/Claudfather/Claudron/issues/100)).** `parse_frontmatter`'s inline fence walk is now `split_fence` (the dead import comes alive; schema.py's "single home of the fence protocol" claim is finally true), and `backfill_updated`'s inline insert loop is now `set_frontmatter_field(text, "updated", stamp)` guarded by `new != text` — same `touched` count, no-op writes still skipped. One deliberate fix rode along in the primitive: `set_frontmatter_field` now matches **top-level keys only** — an indented nested line (`metadata:` / `  updated: ...`) used to be replaced and de-indented, corrupting the mapping, anywhere the primitive stamps real notes (the engine.py addendum stamp today, adopt-backfill after this change); it now inserts a fresh top-level field and leaves nested lines alone, exactly what backfill's inline walk already did. Two fail-on-main tests pin the tightening; a 39-probe fence-edge battery (CRLF / unclosed fence / no-`created:` / non-mapping YAML / nested sub-keys) is byte-identical against main outside the two nested probes of the primitive itself; full suite green.

### Removed
- **The two paired 0.3.0-era back-compat shims are retired — the `CLAUDRON_VAULT` env softener and the claudlobby-root tree-walk deprecation ([#102](https://github.com/Claudfather/Claudron/issues/102)).** Both eased the 0.3.0 `CLAUDRON_VAULT` removal; a full minor past 0.4.0, the migration window is closed. Gone: the softener subsystem (`REMOVED_VAULT_ENV_VARS`, `_ALIAS_REMOVED_IN`, `_shadowed_removed_vars`, `_removed_var_hint`, `_warn_shadowed_vault`) that emitted a one-line stderr note whenever a set `CLAUDRON_VAULT` shadowed the vault that actually resolved; and the `_resolve_claudlobby_root` wrapper whose only job was an stderr "deprecated: … tree-shape walk" nag around the pure `_detect_claudlobby_root` detector — callers (`plug`/`unplug`/`config`/`migrate`, via `_require_claudlobby_root`) now use the detector directly. **Behavior change (stderr; breaking, documented and test-pinned):** `claudron` no longer prints the removed-var softener on any path (resolution, the exit-3 message, or hooks), and the four claudlobby-root commands no longer nag when they auto-detect the root by tree shape — the walk itself is unchanged and still resolves, and `--claudlobby <path>` still preempts it. `CLAUDRON_VAULT` remains fully removed (never read); the softener was its only remaining trace. `docs/CLI_CONTRACT.md` §Environment drops the removed-name table row and trims the migration prose to a one-paragraph "removed, rename" note; the ~15 `test_cli.py` softener assertions and `test_plug.py::TestTreeWalkDeprecation` are removed, with the walk's still-live resolution re-pinned as silent. Coordinated cut: Claudlobby and clauDNA were audited and depend on neither shim (both emit/read only `CLAUDRON_VAULT_PATH`, neither invokes the tree-walk subcommands), so no consumer breaks. Ships as a breaking `0.5.x` release. (boundary program; tech-debt #102)

### Fixed
- **`claudron status` no longer walks the entire vault root — a large fleet subtree made it hang, which shut the knowledge door fleet-wide ([#130](https://github.com/Claudfather/Claudron/issues/130)).** `scan_quarantine`'s full-vault branch enumerated `vault.root.rglob("*.md")`, but on a Claudlobby-provisioned vault the root also holds every fleet's `runtime/` — 238,493 files on the reporting box — so `status --json` never returned. `/claudna:capture` gates on that Step 0 envelope, so a health check that could not complete blocked every capture while the engine underneath was perfectly healthy (`version`, `lookup` and `recall` all answer in under a second off the prebuilt index). The scan now walks `note_tiers()` — the same scope `build_index` and adopt-backfill already share ([#41](https://github.com/Claudfather/Claudron/issues/41)) — with `skip_non_notes=False`, plus two paths that belong to no tier and are named explicitly so the scoping cannot narrow coverage in silence: the vault-root `CONVENTIONS.md` (tiers start one level down, at `_shared/<subdir>`) and stray root-level notes (one directory listing, never a descent). The broad walk was never buying scope — `_SKIP_NAMES` drops `CONVENTIONS.md` by name, and that one filename is what it was really reaching for — so `iter_markdown_files` gains a keyword-only `skip_non_notes` opt-out rather than a second walker, keeping one enumerator across all four consumers. Measured on the reporting vault: enumeration `0.01s` over 311 candidates and `status --json` `rc=0` in `0.58s`, against a pre-fix walk that traversed 512,583 entries in 15s without finishing. Four tests pin it — the runtime-descent guard fails on the pre-fix code, and three coverage guards fail under mutation if a fix buys speed by seeing less.
- **A `--stdin` `tags` comma-string no longer char-explodes into the written note; `tags` now takes one grammar on both spellings ([#51](https://github.com/Claudfather/Claudron/issues/51), part 1).** `capture --stdin` took the payload's `tags` value raw, so a JSON string (`"tags": "a,b"`) reached compose-time iteration and was walked character-by-character into the note (`tags: ["a", ",", "b"]`) — and a stray scalar (`"tags": 5`) crashed compose mid-write. The flag and the `--stdin` key now normalize through one `_tags_arg` door (the `source_type` both-spellings precedent): a string uses the documented flag grammar — comma-split, whitespace-stripped, empty segments dropped — an array is taken element-wise, and any other scalar is one tag via `schema._as_str_list`, matching the read side (#101). `new --tags` routes through the same door, so the flag also now strips padding and drops empty segments (previously `"a, b"` produced a literal `" b"` tag). Three fail-on-main pins cover string/array/scalar; the grammar is a contract row in docs/CLI_CONTRACT.md. Part 2 of #51 (`free_slug` near-dup widening) is deliberately not here — it pairs with the content-hash dedup work.

## 0.4.0 — 2026-07-23

### Added
- **`docs/CLI_CONTRACT.md` §Session-loop protocol** — the session loop is now
  contract text instead of two repos' changelog lore. It names the four roles
  and their owners (continuity is the front-end's; recall, the capture prompt,
  and sync are the engine's), states that the two SessionStart briefs
  **co-inject by design**, pins pull-before-recall, gives the recall brief's
  budget one stated limit, fixes the **single-prompt rule** and how the prompt
  is claimed, publishes the **hook-settings snippet shape** a composer renders
  against, and states the fail-open contract with its per-event timeout
  budgets. Doc-parity tests pin the role table to `HOOK_EVENTS`, the snippet to
  `settings_snippet()`, and the timeouts to their constants.
  (boundary program C2; contract #5)
- **`capture --source-url URL` and `--source-type {url,file,inline}`** (also the
  `source_url` / `source_type` keys of the `--stdin` JSON) write the SCHEMA.md
  optional fields of the same names. Both fields have been in the schema since
  v1; capture dropped them, so consumers folded provenance into a trailing body
  line — coupling themselves to how the recall brief picks a note's summary.
  Provenance now has a transport. `source_type` accepts only the schema's
  vocabulary, on both spellings — the flag and the `--stdin` key alike. Closes
  #44; `source_url` as a *dedup signal*, `last_verified`, and typed anchors
  remain #55's under EPIC #54. (boundary program C2, fork F7)

### Changed
- **The PreCompact capture prompt names no front-end.** It routes the agent
  through *its own* capture door, falling back to `claudron capture --stdin` —
  and it now says `--stdin` rather than demonstrating the `--body` string
  interpolation §capture forbids. The engine's rule is that it always prompts
  where its hook is installed and never sniffs for consumers; a front-end
  shipping its own prompt defers when it finds the engine's registered
  `hook pre-compact` entry. (boundary program C2, fork F1)

### Removed
- **The PreCompact plugin-install-tree glob is gone — the engine no longer
  sniffs for a front-end.** It was the engine's last piece of consumer-name
  sniffing (register rule R5); with it deleted, `hooks.py` names no consumer and
  the engine **always prompts** where its PreCompact hook is installed. The
  end-state test C2 wrote and skip-marked is now enabled. **Behavior change for
  co-installed hosts:** a host running both the engine's hook and a front-end
  that still prompts unconditionally now sees the engine's prompt too — a
  bounded double-prompt window until that front-end ships its defer, accepted
  deliberately (the reverse — both sides yielding so *nobody* prompts, silently
  — is the failure F1's ordering prevents). **Release ordering is mandatory:
  this removal must precede or accompany the front-end's defer release** — it is
  the release clauDNA #254's defer keys on. (boundary program, fork F1; #85;
  clauDNA #253/#254 is the waiting consumer)

## 0.3.0 — 2026-07-20

### Removed (breaking)
- **`CLAUDRON_VAULT` is no longer read.** The vault address resolves via
  `--vault` → `$CLAUDRON_VAULT_PATH` → walk-up, and nothing else. The name was
  a lower-precedence alias through 0.2.x; with both set and disagreeing, the
  engine and its consumers resolved *different vaults*, so it is cut rather
  than deprecated — an alias that is read at all keeps that hazard alive.
  There is no warning phase. **Migration:** rename the variable. The single
  softener, on stderr: whenever `CLAUDRON_VAULT` is set and the engine resolved
  something *else* — including a successful resolution and the session hooks —
  one line names the removal and the canonical name. The damaging case is not
  the failure but the silent success: 0.2.x would have used the vault the dead
  name points at, so an unwarned 0.3.0 would write notes into a different one.
  A dead name that agrees with what resolved stays silent. (boundary program
  C1, fork F3)

### Added
- **`docs/CLI_CONTRACT.md` grew the contracts it was missing.** §Environment is
  now the one normative, precedence-ordered statement of the vault address
  (§Flags defers to it); §Bridge file specifies the `.claudron` `vault=<path>`
  format as a *resolution artifact, not vault structure*; §Write guarantees
  states the cross-host ladder honestly — per-host serialized, cross-host
  eventually consistent with conflict quarantine, multi-writer exclusion out of
  scope by constraint — with its limits and named conflict surface. Previously
  these lived only in `locking.py` / `sync.py` docstrings and one `§Flags` line.
  (boundary program C1; contracts #3/#4/#6)
- **`docs/INTEGRATION.md`** — the vendor-neutral any-agent front door: install
  channels, engine detection (step 0), a runnable hello-world, the
  query-before / write-after loop, and a conformance checklist. Decision C
  cited this document as its mitigation; it had never been written. It is under
  `CLI_CONTRACT.md`'s change discipline. (boundary program C1, fork F5)
- **`status --json` reports `engine_version`** plus a documented stable field
  set (`root`, `total_docs`, `total_stale`, `tiers`, `fleets`, `projects`).
  This is the sanctioned capability probe: consumers read the engine's version
  off an envelope they already parse, instead of maintaining private detection
  ladders. (boundary program C1)
- The recall brief ends with a one-line discovery hint naming
  `claudron lookup` and `claudron capture --stdin`. Its cost is reserved
  *before* notes are laid out, so a budget-saturated brief still teaches the
  door — for any host running the engine's hooks, the brief is the in-context
  discovery channel. (boundary program C1)
- `claudron validate` gained a **directory-structure lens** beside its
  frontmatter lens: it audits a vault's shape against `VAULT-STRUCTURE.md`
  (codes `S1`–`S4`) through the existing `error`/`warning` model, so structure
  warnings honor `--strict` and appear in `--json` exactly like frontmatter
  findings. (P2, #33)
- `claudron validate --fix` — opt-in, **creation-only** structure repair
  (creates a fleet's missing `shared/`), contained inside the vault root
  (`is_relative_to` + symlink-escape rejection); never moves or deletes, and is
  idempotent. (P2, #33)
- `claudron/structure.py` — the pure `check_structure(vault)` audit + the
  guarded `fix_structure`; user-facing reserved names derive from
  `vault.SKIP_DIRS` (no second list), and the SCHEMA↔VAULT-STRUCTURE
  cross-reference is guarded by `TestDocParity`.
- **The wikilink graph** (E4's scale-free half; SQLite/FTS5 deferred).
  `resolve_wikilinks` is no longer a stub — it resolves `[[Target]]` per
  SCHEMA.md (title→alias→slug, case-insensitive; ambiguity → higher tier;
  unresolved links first-class). New **`claudron related <note>`** (wikilink
  neighbors, 1–2 hops, in/out/both direction) and **`claudron links
  [--broken] [--orphans]`** (unresolved links + orphan notes). (#65/#66)
- **Maturity lifecycle** (E5 PR1). **`claudron promote <note> --to
  draft|verified|canonical [--by]`** walks the trust axis with `promoted_by` /
  `promoted_at` provenance (demotion is the same verb; the human running it is
  the gate). `lookup` ranks canonical > verified > draft above tier; `claudron
  status` reports the maturity breakdown + `promoted_pct`. (#68)
- `claudron status` reports **index-vs-vault divergence** (missing / ghost /
  corrupt) — the silent-failure detector for the disposable index. (#62)

### Changed
- **Vault writes are now serialized and atomic.** Every mutator (`capture`,
  `capture --update`, `promote`, `sync`) holds a cross-process `flock` over its
  read→write→index critical section and writes via temp-then-`os.replace`, so
  concurrent fleet writes can't drop an index entry or leave a torn file. (#62)
- `claudron` resolves the vault via `--vault` → `$CLAUDRON_VAULT_PATH` →
  walk-up, now stated once and normatively in `docs/CLI_CONTRACT.md`
  §Environment and pinned to the resolver by a doc-parity test. Reading
  `CLAUDRON_VAULT_PATH` (the var Claudlobby emits per bot) makes the CLI the
  fleet's contract floor. (#62, #30)
- **`claudron plug` / `config` / `migrate` / `unplug`: the Claudlobby
  tree-shape walk is deprecated.** Resolving a consumer root by walking for a
  `library/` + `lib/` directory pair now emits a one-line stderr deprecation
  pointing at `--claudlobby <path>`; passing the flag is silent. Resolution
  behavior is unchanged — the walk still works, and its removal is a later
  release. (boundary program C1)
- The `capture` `--json` result carries **`written`** (true only when a note
  actually landed) so a wrapper branches on it, not the exit code — a
  `suggest_*` dedup route succeeds having written nothing. (#62)
- `claudron init` prints a `next: claudron validate` pointer; a fresh `init`
  then `validate` is a clean no-op.
- **PreCompact hook now defers to clauDNA when it is installed.** Both plugins
  register a PreCompact hook, and Claude Code fires all of them — so with
  clauDNA present the event was double-prompted for capture. `hook_pre_compact`
  now returns silently (exit 0, no block) when `_claudna_installed()`, letting
  clauDNA's hook own the single capture prompt (a bare `/claudna:capture`
  distills the session). Claudron-only installs are unchanged — they keep the
  prompt. This also drops the stale `/reflect` wording the clauDNA-aware branch
  carried (clauDNA retired `/reflect` into `/capture`), so no prompt references
  a skill that no longer exists.

### Fixed
- **Dedup is now content-aware, not title-only.** `find_duplicate` keyed solely
  on title/alias/slug, so byte-identical content re-captured under a different
  (or copy-mangled) title was silently written as a duplicate. Index entries now
  carry a title-independent body `content_hash` (`schema.content_fingerprint`),
  and dedup matches on it alongside the name set; an empty body yields no content
  signal and falls back to the name set. `index.json` schema bumps to `2` (a
  mismatch forces one rebuild). (#52)
- **Deleted notes no longer linger as ghost index entries.** mtime-forward
  staleness cannot see a deletion (a removed file leaves nothing newer), so a
  deleted note kept matching in dedup and lookup until the next `index --full`.
  `load_index` now prunes entries whose note is gone from disk and rewrites the
  index. (#52)
- **Index staleness is scoped to note tiers, not the whole vault tree.**
  `index_is_stale` walked `root.rglob("*.md")`, sweeping in a fleet's
  `runtime`/`library`/`voices` overlays — tens of thousands of never-indexed
  files — which held the index perpetually "stale" and forced a re-walk on every
  capture/lookup. It now walks only `note_tiers`, the same scope `build_index`
  indexes. (#52)

## 0.2.0 — 2026-07-09

**The SD card release** (roadmap E1+E2, EPIC #14): the schema contract and
the full personal session loop — recall at SessionStart, guarded capture,
git sync across machines, quarantined conflicts, fail-open hooks.

### Added
- `SCHEMA.md` — the ratified note schema (tri-repo SSOT): six types,
  per-type status vocabularies, the `status`/`maturity` axis split, closed
  error catalog E001–E007/W101–W107, wikilink grammar, referential-only
  boundary, `pack.yaml` v0 reservation. (#22)
- `docs/CLI_CONTRACT.md` — exit codes, `--json` envelope, channel
  discipline, command groups. (#22)
- `claudron validate [PATH] [--strict]` — schema linter: lenient adoption
  tier by default, strict authoring tier for engine/write paths; stable
  `Finding` structs in `--json` output; never mutates.
- `claudron/schema.py` — the executable schema: vocabularies bound to
  SCHEMA.md by a doc-parity test, `parse_note` (reports broken YAML instead
  of swallowing it), date handling that never crashes on near-dates.
- Reference vault (`examples/reference-vault/`) + fixture corpus with a
  typed expectation manifest. (#22)
- `_shared/planning/{active,completed}` joins the scaffold and the walked
  tiers — vault-level planning docs are now indexed and searchable
  (deliberately reverses #4). (#22)
- `claudron new <type> "<title>"` — scaffold a schema-valid note (passes
  `validate --strict` by construction): owner derived from
  `--owner`/git/`$USER`, per-type directory routing, YAML-safe quoting for
  titles/tags, slug-collision guard with `--force`, vault-containment and
  fleet-registration guards on `--project`/`--fleet`. (#24)
- `claudron init --adopt` backfills missing `updated` from file mtime —
  line-level insert, formatting preserved. (#24)
- `claudron recall` — the session-start context brief: always-loaded
  `CONVENTIONS.md`, project-tier notes (recency-first), shared matches
  behind an abstention floor (weak matches inject nothing); hard token
  budget; index-only on the implicit default. (#25)
- `claudron capture` + the write engine (`engine.py`) — one guarded write
  path (CLI, and E3's MCP door next): strict validation of the artifact,
  index-backed dedup that routes (`suggest_update`/`suggest_supersede`)
  instead of rejecting, `--update` addendums, `--stdin` JSON for bots;
  the write path maintains the index (no rebuild-per-write). (#26)
- `claudron sync` — commit → pull `--rebase` → push; conflicts left as
  markers and **quarantined** (stateless: excluded from search until the
  file is fixed); scan bounded to what the pull changed. (#27)
- The hook pack — SessionStart (bounded pull → recall brief), PreCompact
  (block-once capture prompt, clauDNA-aware), SessionEnd (bounded push);
  **fail-open by contract** (a hook never breaks a session); `claudron
  hooks install` prints or `--write`-merges the settings block
  (self-replacing on executable moves). (#27)
- `claudron init --personal` — the two-command bootstrap: vault + git repo
  + a smoke-tested first note (capture → recall proven at bootstrap) +
  machine-B one-liners. (#28)
- Vault scaffold travels: `.gitkeep` per tier leaf + the CONVENTIONS.md
  template at init (git drops empty dirs — a young vault's clone was
  undetectable). (#27)

### Changed (breaking)
- **Exit codes:** environment errors (no vault resolvable, no claudlobby
  root) now exit `3`; previously `2`. `2` is reserved for usage errors.
- **`--json` output:** `status`, `lookup`, `config`, `index`, `version`,
  and `init` now emit the standard envelope
  `{ok, command, data, warnings, errors}` — previously three ad-hoc
  shapes. Old payloads live under `data` unchanged:
  `status --json` `.total_docs` → `.data.total_docs`;
  `lookup --json` `.results` → `.data.results`;
  `config --json` `.vault` → `.data.vault`.
- **Channels:** diagnostics moved off stdout (`lookup` "no results",
  `index` progress, `status` index-state/warnings → stderr). stdout is
  payload-only — session hooks inject it verbatim.
- Ratified decisions (`status: ratified`) are now exempt from staleness
  *and* remain in default `lookup` results (previously the terminal-status
  set both aged and hid them — one set became two:
  `STALENESS_DONE`/`LOOKUP_EXCLUDED`).

### Fixed
- `claudron --vault X <cmd>` no longer loses the vault path on Python
  3.14 (argparse subparser defaults override top-level values; the
  subcommand `--vault` now uses `SUPPRESS`).
- Vault detection no longer matches case-insensitively on macOS —
  `/Users/Shared` made `detect()` treat `/Users` as a vault and walk the
  entire home directory.
- `CONVENTIONS.md` is no longer indexed/searched as a note (it is the
  always-loaded layer; `validate` budget-checks it instead).

## 0.1.0 — 2026-05-19

Initial extraction from Claudlobby (#1): vault detection/scaffolding,
two-tier lookup, JSON frontmatter index, plug/unplug/config/migrate,
fleet overlays.
