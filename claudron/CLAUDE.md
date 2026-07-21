# claudron/ — placement guidance

The engine package. Module map lives in the root CLAUDE.md; this file is the boundary at the
seam — what belongs where inside the package, and what must never land here.

**Engine vs CLI vs hooks:**

- **Engine modules** (`engine`, `knowledge`, `schema`, `structure`, `vault`, `graph`, `session`,
  `sync`, `locking`, `promote`) never print — stdout/stderr belong to `cli.py` per
  `docs/CLI_CONTRACT.md` (§Channels is load-bearing: hooks inject stdout verbatim).
- **Every note write goes through `engine.py`** — `new`, `capture`, and any future door share one
  validate/dedup/index path. A second write path is a boundary bug.
- **`hooks.py` is the Claude Code adapter** of the session-loop contract: fail-open (exit 0,
  nothing on stdout, log to `.claudron/hooks.log`), budget-bounded, and **never consumer-naming** —
  deferral/claiming is declared config per the contract, not a sniff of a sibling's install tree.
- **`cli.py` maps engine results to the contract** (exit codes, `--json` envelope) and owns all
  argument parsing.

**What must never land here:**

- Consumer names or tree-shapes (no "is clauDNA installed?", no Claudlobby directory walks) —
  consumers declare themselves via contract env/config.
- `fleet.yaml` parsing — Claudlobby owns it; the engine sees fleets only as vault directories
  (`<fleet>/fleet.yaml` is a *marker*, never parsed).
- Skill/procedure content or delivery — clauDNA's.
- A new dependency — PyYAML-only is a ratified identity.

**Placement test** (one line): a contract change (exit code, envelope, env name, hook event)
touches `docs/` + the parity test in the same commit; engine logic that doesn't change a promise
stays inside the module that owns the concern. Full algorithm:
`documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3.
