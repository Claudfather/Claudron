# Claudron

Markdown-based knowledge engine for Claude Code agent fleets. Vaults are directories of markdown files with YAML frontmatter, searched via a two-tier strategy (frontmatter index + full-text fallback).

## Ecosystem boundary

Claudron is the stack's **knowledge system**: it owns the durable-knowledge substrate
(markdown + git, forever), every operation on it, and **every contract by which anything consumes
it** — the CLI ABI, the vault-address contract, the write protocol, the session-loop protocol.
Agent behavior is clauDNA's; fleet composition and policy are Claudlobby's. The local rules:

- **Contracts have one owner: this repo.** `SCHEMA.md`, `VAULT-STRUCTURE.md`, and `docs/` are
  normative; siblings conform (pointer, or rendered copy with a drift gate) and PR here to change
  them. See `docs/CLAUDE.md`.
- **The engine never knows a consumer by name.** No sniffing sibling install trees or tree shapes;
  consumers declare themselves via the contract (env, bridge file). If a change needs
  "is clauDNA/Claudlobby present?", it needs a declared setting instead.
- **Referential only.** No `skill` type, no executable procedures in the vault — that boundary is
  schema-enforced (`SCHEMA.md` §Note types, W103).
- **Placement test** (one line): does it operate on knowledge or promise how knowledge is
  consumed? → here. Steers an agent → clauDNA; wires a fleet → Claudlobby. Full algorithm:
  `documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3.

## Working on this repo

```bash
pip install -e '.[dev]'
pytest
```

## Package structure

```
claudron/
  __init__.py     # Public API: detect, lookup, resolve_wikilinks
  cli.py          # CLI entry point, argparse subcommands
  vault.py        # Vault detection, scaffolding, status, tenancy
  knowledge.py    # Search engine: Tier A (index) + Tier B (full-text)
  engine.py       # The write engine: compose, validate, dedup — one path in
  schema.py       # Frontmatter SSOT enforcement (parity-tested against SCHEMA.md)
  structure.py    # Vault directory-structure validation (VAULT-STRUCTURE.md)
  graph.py        # Wikilink graph: related, links, HTML render
  session.py      # Session loop: recall + the injectable brief
  sync.py         # Git leg: commit, pull --rebase, push, quarantine
  hooks.py        # Claude Code lifecycle adapters (fail-open)
  locking.py      # flock + atomic writes (the write-safety floor)
  promote.py      # Maturity promotion (E5)
  tests/
    conftest.py   # Shared fixtures (vault_dir, vault_with_projects, etc.)
    test_*.py     # Per-module tests
```

## Key concepts

- **Vault** -- directory with `_shared/` (or `shared/`) marker at root. Detection walks up from CWD like git walks up for `.git/`.
- **Tier A** -- `.claudron/index.json` frontmatter cache. Cheap title/tag matching.
- **Tier B** -- full-text body scan. Fallback when index misses.
- **Fleet overlay** -- `<fleet-name>/shared/` inside the vault for fleet-scoped knowledge.

## Conventions

- CLI commands follow the pattern: resolve vault via `_resolve_vault(args)`, then operate; the CLI surface contract (exit codes, `--json` envelope, stdout/stderr) is `docs/CLI_CONTRACT.md`.
- Note frontmatter is governed by `SCHEMA.md` (the ratified SSOT — types, per-type status vocabularies, required/optional fields). Don't enumerate fields here; point there.
- Tests use `tmp_path` fixtures from conftest.py. No real filesystem or network access.
- Single dependency: PyYAML. Keep it minimal.
