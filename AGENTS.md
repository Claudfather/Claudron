# Claudron

Markdown-based knowledge engine for Codex agent fleets. Vaults are directories of markdown files with YAML frontmatter, searched via a two-tier strategy (frontmatter index + full-text fallback).

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
  vault.py        # Vault detection, scaffolding, validation, status, indexing
  knowledge.py    # Search engine: Tier A (index) + Tier B (full-text)
  promote.py      # Tier promotion (stub, Phase 3)
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
