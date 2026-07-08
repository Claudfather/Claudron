# Changelog

## [Unreleased] — 0.2.0

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
