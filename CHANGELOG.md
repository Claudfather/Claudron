# Changelog

## Unreleased

### Changed
- **A scalar `tags:` is one tag, not a character sequence — Tier A now applies the same coercion Tier B always did ([#101](https://github.com/Claudfather/Claudron/issues/101)).** The two frontmatter parse paths had diverged: `_parse_doc` (Tier B) coerced `tags: foo` to `["foo"]`, while `index_entry` (Tier A) stored the raw scalar — so `_score_index_entry` iterated the *string* and a scalar-tagged note scored as `['f','o','o']`: the full tag word could never match (`lookup singleton` on a `tags: singleton` note returned nothing). All three coercion sites (`_parse_doc` tags, `index_entry` tags + aliases) now route through one `_as_str_list`, which also totalizes the edge Tier B used to crash on (`tags: 5` → TypeError mid-scan; now `["5"]` — the second deliberate behavior change, both pinned by tests that fail on the pre-fix code). Index entries for scalar-tagged notes change shape on disk (`"tags": "foo"` → `["foo"]`) at the next index rebuild; the entry contract was always `tags: list`, so this is the shape becoming reliable, not changing.
- **knowledge.py scoring/resolution internals de-duplicated and typed ([#106](https://github.com/Claudfather/Claudron/issues/106), [#107](https://github.com/Claudfather/Claudron/issues/107)).** The tag-exact/tag-partial/filename scoring triple — byte-identical between `_score_index_entry`'s single-phrase block and its per-token loop — now lives once in `_score_term(...)`, with the blocks' only real differences (title weight; whether the word-boundary bonus applies) as keyword arguments. `ResolutionIndex = tuple` becomes a `NamedTuple` (`by_title` / `by_alias` / `by_slug`), so the 3-map shape is visible in the type and `resolve_target` reads fields by name; tuple behavior (unpacking, immutability) is unchanged. Behavior-preservation proven two ways: a 132-case scoring+resolution battery (exact/substr/boundary/tag/partial/filename/multi-token/cap paths; title→alias→slug fall-through with tier-then-path tiebreaks) is byte-identical between main and this change, and the full suite stays green.
- **`schema._tier` renamed `_resolve_code`; `_child_dirs` is now the one dir-walk filter ([#110](https://github.com/Claudfather/Claudron/issues/110), [#111](https://github.com/Claudfather/Claudron/issues/111)).** The private validation-tier code resolver no longer squats on the codebase's dominant "tier" token (vault/search Tier A/B, `note_tiers()` loop vars) — one def, one caller, mechanical rename. The sorted/real-dirs/no-dotfiles walk filter, previously spelled out three times, is `_child_dirs` everywhere: the primitive gains `skip: frozenset[str] = SKIP_DIRS`, and the two sites that must visit reserved names — the projects scan and the structure audit's root walk (whose S2 check *audits* reserved dirs) — pass `skip=frozenset()` instead of hand-rolling the filter. Emission order and discovery are unchanged: a canary vault exercising S2 + S3 + fleet overlay + projects produces byte-identical `validate` and `status --json` output against main; full suite green.
- **PROJECT_MISSION.md no longer frames SQLite as the current index backend ([#114](https://github.com/Claudfather/Claudron/issues/114)).** The doc's own 2026-07-21 supersession stamps establish the index shipped as derived JSON (`.claudron/index.json`, no SQLite mirror) — yet the approval gate said "Adopting a non-SQLite storage backend" (presupposing SQLite is the status quo) and the graph-DB rejection said "SQLite + an edges table is plenty" (reading a deferred E4 item as shipped). Both now state the JSON index as current and the SQLite mirror as the deferred ceiling (E4, #18), preserving each line's original force: index-backend changes stay approval-gated — including graduating to SQLite — and real graph DBs stay rejected. Doc-only; the forward SQLite/graph work remains #18's.
- **`run_hook` now owns the whole hook prologue, not just the exception guard ([#108](https://github.com/Claudfather/Claudron/issues/108)).** Each handler repeated the same two lines the boundary's docstring claimed to centralize — drain the stdin payload, exit 0 when no vault resolved. The boundary now drains once, guards once, and passes the parsed payload to handlers (`(vault, payload)`, vault non-optional). Two deliberate observable deltas: the no-vault path logs uniformly for **every** event ("no vault resolvable — nothing to do", to the tmp fallback log) where before only session-start logged (and said "nothing injected"); and `hook_session_end`'s `SyncError` catch is **kept, deliberately** — a git-less vault raises `SyncError` on every push, so that catch is the *expected-degradation* logger ("sync --push skipped", symmetric with the pull side's load-bearing catch in `session_start_brief`), and dropping it would relabel a normal condition as "hook failed open" in the hooks' only observability channel. Wire behavior is untouched: a 7-invocation canary (no-vault + non-git vault × all three events, incl. the pre-compact block/pass pair) has byte-identical stdout and exit codes against main; full suite green.

### Fixed
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
