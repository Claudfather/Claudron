# Changelog

## Unreleased

### Added
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

### Changed
- `claudron init` prints a `next: claudron validate` pointer; a fresh `init`
  then `validate` is a clean no-op.

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
