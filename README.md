# Claudron

Markdown-based knowledge engine for Claude Code agent fleets.

A vault is a directory of markdown files with YAML frontmatter and wikilinks. Bots write findings, decisions, and gotchas into the vault during operation. An indexer maintains a fast lookup cache so bots can query context before starting tasks.

The substrate is plain markdown files in a git repo -- humans can browse with any editor, the data is portable, and everything is version-controlled.

## Install

From a local clone:

```bash
pip install .
```

For development (includes pytest):

```bash
pip install -e '.[dev]'
```

## Quick start

```bash
# Scaffold a new vault
claudron init my-vault
cd my-vault

# Write a schema-valid note (owner derived from git config / $USER)
claudron new knowledge "Auth Patterns Across Services" --tags auth,jwt

# Lint the vault against SCHEMA.md (lenient adoption tier)
claudron validate

# Check vault health
claudron status

# Search for knowledge
claudron lookup "auth patterns"

# Adopting an existing docs directory? --adopt also backfills missing
# `updated` fields from file mtimes:
claudron init ./existing-docs --adopt

# Register vault with a claudlobby fleet
claudron plug ./my-vault --claudlobby /path/to/claudlobby
```

## CLI commands

Claudron works standalone as a knowledge engine. Commands marked with **(claudlobby)** require a claudlobby installation and will print a clear error if one isn't found.

| Command | Purpose |
|---------|---------|
| `init` | Scaffold a new vault (`--adopt` converts + backfills an existing directory) |
| `new` | Scaffold a schema-valid note in the right tier (passes `validate --strict`) |
| `validate` | Lint notes against `SCHEMA.md` — lenient by default, `--strict` = the authoring/engine tier |
| `status` | Vault contents and health summary |
| `lookup` | Search vault knowledge by title, tags, or content |
| `index` | Build or rebuild the frontmatter index |
| `version` | Print version |
| `fleet add` | Scaffold a fleet overlay inside the vault |
| `fleet list` | List fleet overlays in the vault |
| `plug` | Register vault with a claudlobby installation **(claudlobby)** |
| `unplug` | Disconnect vault from claudlobby **(claudlobby)** |
| `config` | Show resolved vault configuration **(claudlobby)** |
| `migrate` | Migrate shared docs from a claudlobby fleet into the vault **(claudlobby)** |

## Vault structure

```
my-vault/
  _shared/
    knowledge/     # Cross-cutting learnings
    decisions/     # Architecture decision records
    runbooks/      # Operational procedures
  projects/
    <repo>/        # Per-repo knowledge
  <fleet>/         # Fleet overlays (optional)
    shared/
      knowledge/
  .claudron/
    index.json     # Tier A frontmatter index (gitignored)
```

## Search tiers

- **Tier A** -- Frontmatter index (`.claudron/index.json`). Fast title/tag/alias matching without reading file bodies.
- **Tier B** -- Full-text scan of markdown bodies. Fallback when Tier A misses or scores below threshold.

## Note format

```markdown
---
title: Auth Patterns Across Services
type: knowledge
status: current
owner: mason
tags: [auth, jwt, architecture]
created: 2026-04-01
updated: 2026-05-01
---

# Auth Patterns Across Services

All services use JWT with RS256...
```

## Position in the ecosystem

- **Claudron** stores reference knowledge (findings, decisions, gotchas).
- **clauDNA** stores procedural knowledge (skills, slash commands).
- **Claudlobby** runs bots that read from and write to the vault.

## License

MIT
