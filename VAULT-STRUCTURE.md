# Claudron Vault Structure — v1

**Status: draft · SSOT for the vault's directory shape, content contract, and
consumption contract (P1 of Claudfather/Claudron#33).**
Sibling to `SCHEMA.md`: SCHEMA.md is normative for note frontmatter and the
note-filing taxonomy *within* each tier; this document is normative for
**tenancy** (who owns which directory), **scope** (what knowledge belongs in
which tier), **consumption** (how agents reach it), and **promotion** (how
knowledge rises between tiers). The directory tree below draws the same
knowledge-tier structure SCHEMA.md defines in §Vault directory taxonomy,
extended with the Claudlobby-injected fleet config; the two are cross-linked and
their shared tier structure is guarded against drift by P2's parity test.
Changes after ratification require approval
(`PROJECT_MISSION.md`, "Requires approval").

A **vault** is one git repository holding a single tenant's knowledge — the
operator's own ventures, personal and fleet alike. Everything an agent fleet or
a human at the keyboard needs to *find* prior knowledge and *file* new knowledge
lives here, in a shape any tenant can conform to without reverse-engineering
`_scan_vault`.

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
- You never edit `.claudron/`; it is a derived index Claudron rebuilds.

## Directory contract

```
<vault>/                       # ONE git repo per tenant. On a Claudlobby deployment
                               #   the vault IS the gitignored local/ dir; a clone of
                               #   the same repo lives on the operator's workstation.
  _shared/                     # vault-wide knowledge hub. "shared/" is also accepted.
    CONVENTIONS.md             #   always-injected standing facts (<=120 tokens — SCHEMA.md)
    knowledge/                 #   the four note tiers (taxonomy owned by SCHEMA.md)
    decisions/
    runbooks/
    planning/
      active/  completed/      #   human filing split; the status field is the machine state
  projects/<repo>/             # the operator's personal, per-repo notes (roadmap D4)
  <fleet>/                     # a fleet — a FLAT, root-level dir marked by fleet.yaml
    fleet.yaml                 #   fleet config. Claudlobby writes it; Claudron never parses it.
    library/  voices/          #   Claudlobby overlay content
    shared/                    #   this fleet's knowledge — the same four tiers as _shared/
      knowledge/  decisions/  runbooks/  planning/{active,completed}/
    runtime/                   #   generated bot dirs — gitignored within the vault
  _packs/<name>/               # subscribed packs, read-only (E6)
  .claudron/                   # Claudron's derived index — gitignored, disposable
  .env                         # secrets — gitignored, per-machine, NEVER committed / via GitHub
```

Normative:

- **One git repository per tenant vault.** A vault is self-contained. A second
  tenant (an employer's systems, another person's data) is a **separate vault**,
  never a directory inside this one.
- **`_shared/` (or legacy `shared/`) at the root is the vault marker** — its
  presence is how `detect()` recognizes a directory as a vault.
- **Fleets are flat, root-level directories**, each marked by a `fleet.yaml`.
  `_scan_vault` discovers a fleet as any root-level dir containing `fleet.yaml`;
  there is no `fleets/` nesting layer.
- **`runtime/` and `.env` are gitignored within the vault** — generated bot
  directories and secrets never enter the tenant's history.
- **The `.claudron/` index dir is derived and disposable** — Claudron rebuilds
  it; never hand-edit it or commit meaningful state into it.
- **Bridge file.** A `.claudron` *file* (distinct from the `.claudron/` index
  *dir*) may sit at a consumer's root: Claudlobby writes it (via `plug`/`config`)
  to bridge its checkout to the vault. It is a resolution artifact, not
  vault-internal structure — see Consumption.

The knowledge-tier structure above matches `SCHEMA.md` §Vault directory
taxonomy; this tree adds the Claudlobby-injected fleet config (`fleet.yaml`,
`library/`, `voices/`, `runtime/`). SCHEMA.md stays authoritative for the note
taxonomy *within* each tier; this document is authoritative for tenancy, scope,
and consumption. The two are cross-linked and their shared tier structure is
guarded against drift by P2's parity test.

## Reserved names

The top-level names **`_shared`, `shared`, and `projects`** are vault-internal:
a fleet may not take any of them (a fleet named `projects` would collide with the
personal tier). These three are the *user-facing* subset of `SKIP_DIRS`
(`claudron/vault.py:37-39`) — the names a human could collide with. `SKIP_DIRS`
also holds infrastructure names (`.git`, `.github`, `.claudron`, `__pycache__`)
that never belong in a user-facing "reserved" message.

`SKIP_DIRS` is the single source: enforcement (P2) and any consumer deriving the
reserved set read it — never a hand-copied second list.

## Content contract — three tiers

What *kind* of knowledge belongs where is chosen by **location**, not by a
frontmatter field:

| Tier | Where | Holds |
|---|---|---|
| bot memory | a bot's private `memory/` | a single bot's private, unshared working state |
| fleet | `<fleet>/shared/` | knowledge scoped to one fleet's mission |
| vault-wide | `_shared/` | knowledge true across the tenant (cross-fleet + the operator's own) |

Rules:

- **Scope is chosen by location** — the directory you write to *is* the
  visibility declaration. There is deliberately **no `scope:` / `visibility:`
  frontmatter field** in v1; a note's tier is where it sits.
- **The note taxonomy is identical across tiers.**
  `knowledge/decisions/runbooks/planning` mean the same thing in `_shared/` and in
  every `<fleet>/shared/` (SCHEMA.md).
- **Knowledge rises; it does not leak sideways.** A finding is promoted up
  (bot → fleet → vault-wide) when it earns broader visibility; it is never copied
  laterally between fleets. Promotion is the only path up (see Promotion).

## Consumption contract

- **Navigate for config, query for knowledge.** An agent reads *configuration*
  (its `fleet.yaml`, its overlay files) by walking the known filesystem. It
  reaches *knowledge* by asking Claudron — `claudron recall` / `lookup` — never by
  opening tier files by hand.
- **Never hardcode the `_shared/` path.** Consumers reach the hub through
  Claudron's resolution (`Vault.shared`, `vault.py:117-124`), not a literal path.
  This is what keeps the hub's name cheap to change.
- **Merge + precedence.** A query returns the union of `_shared/` and the
  in-scope fleet notes, tie-broken by tier priority `project > fleet > shared`
  (`claudron/knowledge.py:430-437`) — the same ordering SCHEMA.md §Wikilinks
  applies to link ambiguity (there extended with `pack`).
- **Single-tenant pooling is intended.** Because one vault = one tenant, a fleet
  bot's query can surface the operator's personal `projects/` notes. That is the
  desired "one hub" behavior for a solo operator, not a leak — the boundary for
  true separation is a **separate vault**. (Fleet-scoped recall, should a fleet
  ever need isolation, is specced conditionally in P3.)

Two mechanisms resolve a vault; the contract governs both, so a consumer audits
them rather than rediscovering them:

- **(a) Composition-time** — Claudlobby's `_resolve_vault_fleet`
  (`paths.py:104-130`) reads the `.claudron` bridge file at its root and, when the
  `[vault]` extra is installed, calls `claudron.vault.detect()` →
  `vault.fleets[fleet]`, falling back to a plain `local/<fleet>/` overlay.
- **(b) Bot-runtime** — the composed `CLAUDRON_VAULT_PATH` env var
  (`composer.py:502-508`) points a running bot's Claudron CLI/MCP at the vault.

## Promotion

Knowledge rises through the tiers on the ladder E5 owns:

```
bot memory/  ->  <fleet>/shared/  ->  _shared/  ->  pack (E6)
```

This document states the *model*; `05-lifecycle.md` owns the *mechanism*.
**Interim:** until E5's `claudron promote` ships, promotion is manual —
`claudron capture --fleet <name>` to file at a tier, or `git mv` to move a note
up. No lifecycle rules live here; see E5.

## Related

- **`SCHEMA.md`** — note frontmatter, types, status/maturity, and the note-filing
  taxonomy within each tier. This document is its directory/tenancy/consumption
  sibling; the two cross-link and are parity-checked (P2).
- **`documentation/plans/2026-07-07-claudron-roadmap/05-lifecycle.md`** — the E5
  promotion mechanism.
- **Claudfather/Claudlobby #509** — the consumption epic: how Claudlobby conforms
  to this contract.
