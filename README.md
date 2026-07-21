# Claudron

Markdown-based knowledge engine for Claude Code agent fleets — the portable
"SD card" for your sessions' memory.

A vault is a directory of markdown files with YAML frontmatter and wikilinks.
Sessions and bots write findings, decisions, and gotchas into the vault as
they work; every new session starts with a context brief recalled from it.
Clone the vault on any machine and your accumulated knowledge travels with
you: what you learn on machine A surfaces in machine B's next session.

The substrate is plain markdown files in a git repo -- humans can browse with any editor, the data is portable, and everything is version-controlled.

## The session loop (the SD card)

```bash
# One-command bootstrap: vault + git repo + smoke-tested first note
claudron init ~/vault --personal

# Wire it into Claude Code (SessionStart pull+brief, PreCompact capture
# prompt, SessionEnd push) — prints the settings block; --write merges it
claudron --vault ~/vault hooks install --write

# That's it. Sessions now recall context at start and are prompted to
# capture durable findings before compaction. To span machines:
git -C ~/vault remote add origin <private-repo-url> && git -C ~/vault push -u origin main
# ...and on the other machine:
git clone <private-repo-url> ~/vault && claudron hooks install --write
```

The loop, end to end: `SessionStart → sync --pull → recall brief injected →
work → PreCompact prompts claudron capture → SessionEnd → sync --push` —
and the next machine's SessionStart picks it up.

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
| `init` | Scaffold a new vault (`--adopt` converts + backfills; `--personal` bootstraps the full SD card) |
| `recall` | Session-start context brief: conventions + project notes + relevant shared notes (stdout is the injectable payload) |
| `capture` | Write a finding through the guarded engine — validated, dedup-routed (`suggest_update`/`suggest_supersede`), never silently dropped |
| `sync` | Commit vault changes, pull `--rebase`, push; conflicts quarantined until a human resolves |
| `hook` / `hooks install` | Claude Code lifecycle glue (SessionStart/PreCompact/SessionEnd), fail-open by contract |
| `new` | Scaffold a schema-valid note in the right tier (passes `validate --strict`) |
| `validate` | Lint notes against `SCHEMA.md` — lenient by default, `--strict` = the authoring/engine tier |
| `status` | Vault contents and health summary (incl. conflict quarantine) |
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

### Integrating any agent

The door is the CLI, and it is vendor-neutral — any agent that can run a
subprocess and parse JSON can consume the hub, with no plugin and no server.
**[`docs/INTEGRATION.md`](docs/INTEGRATION.md)** is the front door: install
channels, the engine-detection probe, a copy-paste hello-world, the
query-before / write-after loop, and a conformance checklist. The normative
surface it points at is [`docs/CLI_CONTRACT.md`](docs/CLI_CONTRACT.md).

## License

MIT
