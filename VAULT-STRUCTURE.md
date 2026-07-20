# Claudron Vault Structure — v1

**Status: ratified · the vault's directory, tenancy, and consumption contract —
the directory sibling of `SCHEMA.md` (P1 of Claudfather/Claudron#33).**

A **vault** is one git repository holding a single tenant's knowledge — the
operator's own ventures, personal and fleet alike. This document is normative for
**tenancy** (who owns which directory), **scope** (what belongs in which tier),
**consumption** (how agents reach it), and **promotion** (how knowledge rises),
and draws the full tenant tree. `SCHEMA.md` is normative for note frontmatter and
the note-filing taxonomy *within* each tier, and draws the knowledge tiers from
that side.

**Authority.** This document is the **sole** SSOT for the vault's directory
shape — `SCHEMA.md` (above) keeps only the note-filing layout and points here.
The two trees' note-tier structure is parity-guarded (`TestDocParity` in
`claudron/tests/test_schema.py`, tied to `schema.py`'s `TYPE_DIRS`); changes to
this contract after ratification require approval (`PROJECT_MISSION.md`,
"Requires approval").

## Start here

If you are a human opening a vault for the first time:

- **Vault-wide knowledge** — anything true across your whole operation — lives
  in `_shared/`. That is the hub; start there.
- **Personal per-repo notes** about a codebase you work on live in
  `projects/<repo>/`.
- **A fleet's own knowledge** lives under that fleet's `<fleet>/shared/`.
- To **drop a note by hand**, add a markdown file with frontmatter (see
  `SCHEMA.md`) to the right tier's `knowledge/`, `decisions/`, `runbooks/`, or
  `planning/` subdir — or let a bot file it with `claudron capture`.

## Directory contract

```
<vault>/                       # ONE git repo per tenant. On a Claudlobby deployment
                               #   the vault IS the gitignored local/ dir; a clone of
                               #   the same repo lives on the operator's workstation.
  _shared/                     # vault-wide knowledge hub. "shared/" is also accepted.
    CONVENTIONS.md             #   always-injected standing facts (<=120 tokens — SCHEMA.md)
    knowledge/                 #   the four note types (taxonomy owned by SCHEMA.md)
    decisions/
    runbooks/
    planning/
      active/  completed/      #   human filing split
  projects/<repo>/             # the operator's personal, per-repo notes (roadmap D4)
  <fleet>/                     # a fleet — a flat, root-level dir marked by fleet.yaml
    fleet.yaml                 #   fleet config. Claudlobby writes it; Claudron never parses it.
    .env  .gitignore           #   fleet secrets + fleet-local ignores (claudron fleet add writes both; never committed)
    library/  voices/          #   Claudlobby overlay content
    shared/                    #   this fleet's knowledge — the same four note types as _shared/
      knowledge/  decisions/  runbooks/  planning/{active,completed}/
    runtime/                   #   generated bot dirs — gitignored within the vault
  _packs/<name>/               # subscribed packs, read-only (E6)
  .claudron/                   # Claudron's derived index — gitignored, disposable, never hand-edited
  .gitignore                   # vault-root ignores: */runtime/, .env, .claudron/ (claudron init writes this)
```

The tree is normative. Beyond what its comments state:

- **One git repository per tenant vault** — self-contained. A second tenant (an
  employer's systems, another person's data) is a **separate vault**, never a
  directory inside this one.
- **`_shared/` (or legacy `shared/`) is the vault marker** — `detect()` keys on
  its presence at the root.
- **Fleets are discovered structurally** — `_scan_vault` treats any root-level
  dir containing a `fleet.yaml` as a fleet. There is no `fleets/` nesting layer.
- **Bridge file.** A `.claudron` *file* (distinct from the `.claudron/` index
  *dir*) may sit at a consumer's root: `claudron plug` writes it there (and
  `claudron config` reads it) to point the consumer's checkout at the vault — a
  resolution artifact, not vault structure (see Consumption).
- **Secrets never commit.** The vault-root `.gitignore`'s `.env` line ignores a
  `.env` at any depth — both each fleet's `<fleet>/.env` (also covered by the
  fleet's own `.gitignore`) and an optional vault-root `.env` for vault-wide
  per-machine secrets. `fleet add` scaffolds each fleet's `.env`+`.gitignore`;
  `init` writes (or, on `--adopt`, augments) the vault-root `.gitignore`; a
  root `.env` is the operator's to create.

This tree is the full tenant vault; `SCHEMA.md` §Vault directory taxonomy draws
the same knowledge tiers from the note-filing side. The Claudlobby-injected
config (`fleet.yaml`, `library/`, `voices/`, `runtime/`) is this document's.

## Reserved names

The top-level names **`_shared`, `shared`, `projects`, and `_packs`** are
vault-internal: a fleet may not take any of them (a fleet named `projects` would
collide with the personal tier; `_packs` is the E6 pack container, reserved
ahead of packs landing). These are the user-facing subset of `SKIP_DIRS`
(`claudron/vault.py`) — the names a human could collide with; `SKIP_DIRS` also
reserves infrastructure names (`.git` and friends). Read `SKIP_DIRS` for the full
set: it is the single source, and enforcement (P2) derives the reserved subset
from it — never a hand-copied second list.

## Content contract — the knowledge tiers

What *kind* of knowledge belongs where:

| Tier | Where | Holds |
|---|---|---|
| bot memory | a bot's private `memory/` | a single bot's private, unshared working state |
| project | `projects/<repo>/` | the operator's personal, per-repo notes (ranked highest in a query) |
| fleet | `<fleet>/shared/` | knowledge scoped to one fleet's mission |
| vault-wide | `_shared/` | knowledge true across the whole tenant (cross-fleet) |

- **Scope is chosen by location** — the directory you write to *is* the
  visibility declaration; there is deliberately no `scope:` / `visibility:`
  frontmatter field in v1.
- **The note taxonomy is identical across tiers** —
  `knowledge/decisions/runbooks/planning` mean the same thing everywhere
  (`SCHEMA.md`).
- **Knowledge rises, never sideways** — a finding is promoted up when it earns
  broader visibility (see Promotion); it is never copied between fleets.

### `projects/<repo>/` — the operator's outside view of a repo

`projects/<repo>/` holds what the vault (operator + fleet) knows about a codebase
that does **not belong in that repo's own `documentation/`**. Repo-authoritative
records — architecture, ADRs, specs, design decisions — travel *with the code* on
the repo plane (`<repo>/documentation/`), versioned alongside it. The vault's
project tier is the **outside view**: the cross-repo, operational, and provenance
knowledge a repo would never self-document —

- operational gotchas ("flaky on Sundays — upstream cron"), cross-repo workflow
  ("deploy after `narrative`"), how the repo fits the operator's wider world;
- durable **residue** promoted from point-in-time work — an audit finding or a
  review tidbit that outlives its artifact (§Promotion).

Two tests place a note:

- **vs `_shared/`** — *would this still hold if this repo didn't exist?*
  **Yes → `_shared/`** (project-independent). **No → `projects/<repo>/`.**
- **vs the repo's own `documentation/`** — *is the repo speaking about itself, or
  is this the operator/fleet's take on it?* **Repo's own → repo plane. Outside
  view → `projects/<repo>/`.**

At creation the directory is scaffolded with a `CLAUDE.md` carrying this guidance,
so any agent filing here meets the boundary in-context.

## Consumption contract

- **Navigate for config, query for knowledge.** An agent reads *configuration*
  (its `fleet.yaml`, its overlay files) by walking the filesystem. It reaches
  *knowledge* by asking Claudron — `claudron recall` / `lookup` — never by opening
  tier files by hand.
- **Never hardcode the `_shared/` path.** Consumers reach the hub through
  Claudron's resolution (`Vault.shared`), not a literal path — which is what keeps
  the hub's name cheap to change.
- **Merge + precedence.** A query returns the union of `_shared/`, the operator's
  `projects/` notes, and fleet notes, ranked by tier priority (`tier_priority`,
  function-local in `lookup()`, `claudron/knowledge.py`) — the top three
  `project > fleet > shared` of the precedence `SCHEMA.md` §Wikilinks applies to
  link ambiguity.
- **Single-tenant pooling is intended.** Because one vault = one tenant, a query
  pools across fleets and can surface the operator's personal `projects/` notes —
  recall is fleet-blind today. That is the desired "one hub" behavior, not a leak;
  true separation is a separate vault (see the directory contract). Fleet-scoped
  recall, should a fleet ever need isolation, is specced conditionally in P3.

Two mechanisms resolve a vault; the contract governs both:

- **(a) Composition-time** — Claudlobby's `_resolve_vault_fleet` reads the
  `.claudron` bridge file at its root and, when the `[vault]` extra is installed,
  calls `claudron.vault.detect()` → `vault.fleets[fleet]`; its caller then falls
  back to a plain `local/<fleet>/` overlay when no vault resolves.
- **(b) Bot-runtime** — the composed `CLAUDRON_VAULT_PATH` env var (emitted by
  Claudlobby's `composer.py`) points a running bot's **Claudron CLI** at the vault
  (per the resolution order in docs/CLI_CONTRACT.md; the CLI reading this var
  landed in #62). The CLI is the
  fleet-consumption door (clauDNA's `/claudron`, `/capture`, `/recall` wrap it);
  an MCP server over the same engine is **demand-gated** (decision C — see
  `documentation/plans/2026-07-18-decision-c-mcp-demand-gated.md`), not required
  for a bot to reach the hub.

## Promotion

Knowledge rises on the ladder E5 designs (`05-lifecycle.md`):

```
bot memory/  ->  <fleet>/shared/  ->  _shared/  ->  pack (E6)
```

Reproduced here as the *model*; `05-lifecycle.md` owns the *mechanism* and the
ladder's canonical form. **Interim:** until E5's `claudron promote` ships,
promotion is manual — `claudron capture --fleet <name>` to file at a tier, or
`git mv` to move a note up.

## Related

- **`SCHEMA.md`** — note frontmatter, types, status/maturity, and the note-filing
  taxonomy within each tier.
- **`documentation/plans/2026-07-07-claudron-roadmap/05-lifecycle.md`** — the E5
  promotion mechanism.
- **Claudfather/Claudlobby #509** — the consumption epic: how Claudlobby conforms
  to this contract.
