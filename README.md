# Claudron

Markdown-based knowledge engine for Claude Code agent fleets.

A vault is a directory of markdown files with YAML frontmatter and wikilinks. Bots write findings, decisions, and gotchas into the vault during operation. An indexer maintains a fast lookup cache so bots can query context before starting tasks.

The substrate is plain markdown files in a git repo -- humans can browse with any editor, the data is portable, and everything is version-controlled.

## Install

```bash
pip install -e '.[dev]'
```

## Quick start

```bash
# Scaffold a new vault
claudron init my-vault
cd my-vault

# Check vault health
claudron status

# Search for knowledge
claudron lookup "auth patterns" --tags jwt

# Rebuild the search index
claudron index --rebuild

# Register vault with a claudlobby fleet
claudron plug --fleet my-fleet --root /path/to/claudlobby
```

## CLI commands

| Command | Purpose |
|---------|---------|
| `init` | Scaffold a new vault with `_shared/` structure |
| `status` | Vault contents and health summary |
| `lookup` | Search vault knowledge by title, tags, or content |
| `index` | Build or rebuild the Tier A frontmatter index |
| `config` | Show resolved vault configuration |
| `plug` | Register vault with a claudlobby installation |
| `unplug` | Disconnect vault from claudlobby |
| `fleet add` | Scaffold a fleet overlay inside the vault |
| `fleet list` | List fleet overlays in the vault |
| `migrate` | Migrate shared docs from a claudlobby fleet into the vault |
| `version` | Print version |

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
status: active
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
