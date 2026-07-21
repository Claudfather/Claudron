# Claudron CLI Contract

Normative for every `claudron` command, current and future. Machine
consumers (hooks, fleet bots, CI) build against this; changes are breaking
changes and get CHANGELOG entries.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. **Warnings do not change the exit code.** |
| 1 | Findings: validation errors, review-queue items |
| 2 | Usage error (bad arguments) |
| 3 | Environment error (no vault resolvable, git missing) |

CI that wants to gate on warnings runs `validate --strict` (which promotes
the gateable warnings to errors) rather than parsing warning counts.

> Breaking change at 0.2.0: no-vault previously exited 2; it is now 3.

## Channels

**stdout carries payload only; every diagnostic goes to stderr.** This rule
is load-bearing: session hooks inject command stdout directly into agent
context (E2 `recall`), so a stray progress line on stdout becomes garbage in
a session brief. A parametrized channel-discipline test enforces this across
the command table.

## `--json` envelope

One shape, every command:

```json
{
  "ok": true,
  "command": "validate",
  "data": { },
  "warnings": [ {"code": "W101", "severity": "warning", "path": "…",
                 "field": "updated", "line": null, "message": "…"} ],
  "errors": [ ]
}
```

- `errors` / `warnings` are the authoritative finding lists; each element is
  a serialized `Finding` (see SCHEMA.md §Validation) — never a bare string.
- `data` is the per-command payload: `validate` → summary counts + per-note
  breakdown; `new` → `{"path": "…"}`; `status` → the health dict **plus
  `engine_version`** (below); `lookup` →
  `{query, results}`; `related` →
  `{note, related: [{path, title, tier, direction, hops}]}` (`direction` ∈
  `out`/`in`/`both` for a direct neighbor, else `N-hop`); `links` →
  `{broken: [{src, target}], orphans: [path]}` (both keys always present in
  `--json`; the `--broken`/`--orphans` flags filter human output only).
- `ok` is `errors == []` (warnings don't flip it).

> Breaking change at 0.2.0: `status --json`, `lookup --json`, and
> `config --json` previously emitted three ad-hoc shapes; all now emit the
> envelope (their old payloads live under `data`).

### Capability probe

`status --json`'s `data` carries **`engine_version`** (the installed
`claudron.__version__`). This is the sanctioned way to ask *"is an engine here,
and which one?"* — one probe, off an envelope a consumer already parses. A
consumer that needs a newer field guards on it; it never infers the engine's
version from an installed package pin, a plugin manifest, or a private
detection ladder.

These `data` fields of `status --json` are **stable** — machine consumers may
rely on them, and removing or retyping one is a breaking change:

| Field | Type | Meaning |
|---|---|---|
| `engine_version` | string | Installed engine version. `"0.0.0-dev"` when running from an uninstalled checkout. |
| `root` | string | Absolute path of the resolved vault. |
| `total_docs` / `total_stale` | int | Vault-wide note counts. |
| `tiers` | object | Per-tier `{docs, stale, path}`. |
| `fleets` / `projects` | array | Names present in the vault. |

Everything else under `status --json` is informational and may change without
a breaking-change entry.

## Environment

<!-- doc-parity: ENVIRONMENT -->

The **vault address** — the one normative statement of how a `claudron`
invocation finds its vault. Rows are in **precedence order**: the first that
yields a path wins, and a hit is never re-checked against a lower row.

| # | Source | Kind | Behavior |
|---|---|---|---|
| 1 | `--vault PATH` | flag | Explicit; wins over everything. Accepted by every subcommand. |
| 2 | `CLAUDRON_VAULT_PATH` | env | **The canonical name.** What Claudlobby's composer emits per bot; what any integrator should set. |
| 3 | walk up from CWD | discovery | Ascend from the working directory for a `_shared/` (or `shared/`) marker, the way git ascends for `.git/`. |
| — | `CLAUDRON_VAULT` | removed (0.3.0) | **Not read.** Was a second spelling of row 2; see the migration note below. |

A path that resolves but is not a vault (no `_shared/`) is not a fallback —
resolution stops and the command exits 3. When nothing resolves, `claudron`
exits **3** with the no-vault message on stderr.

**Migration — `CLAUDRON_VAULT` (removed in 0.3.0).** The name was read as a
lower-precedence alias of `CLAUDRON_VAULT_PATH` through 0.2.x. It was removed
rather than deprecated: with both set and disagreeing, engine and consumers
resolved *different vaults*, and an alias that is read at all keeps that hazard
alive. There is no warning phase.

The one trace it leaves, on **stderr** only: when `CLAUDRON_VAULT` is set and
the engine resolved something *else*, one line names the removal and the
canonical name. That covers both confusing outcomes — no vault resolving
(appended to the exit-3 message) **and** a *successful* resolution of a
different vault than 0.2.x would have chosen. The second is the damaging one:
it exits 0, so an unwarned caller writes notes into a vault they did not
intend. Hook invocations warn too, on stderr, which is never injected into a
session. A `CLAUDRON_VAULT` that agrees with the vault actually resolved is
not confusing and stays silent, so this never becomes ambient noise.

**Consumer obligations.**

- Emit and read **only** `CLAUDRON_VAULT_PATH`. A consumer that still reads the
  removed name re-creates the two-vaults hazard in reverse — its resolution
  succeeding where the engine's fails is worse than both failing.
- `SHARED_DOCS_PATH` is **clauDNA's fallback-mode variable**, not part of this
  contract. It addresses a raw documentation tree when no engine is present, is
  never consulted on an engine path, and is out of scope for this removal.
- Do not invent additional names. A new address source is a change to this
  table, PR'd here first (register rule R4).

## Bridge file

`.claudron` at a consumer's root is a **resolution artifact, not vault
structure** — it lives in the consumer's tree, never in the vault, and the
vault is valid without one.

```
# .claudron — auto-generated by claudron plug
vault=/absolute/path/to/vault
```

- Format: shell-sourceable `key=value`, one per line. `#` begins a comment
  line; blank lines are ignored; surrounding whitespace is stripped. `vault` is
  the only key defined today.
- **Written** by `claudron plug <vault>` at the consumer root; removed by
  `claudron unplug`; read back by `claudron config`.
- **Read** by consumers that need to point a checkout at a vault without an
  ambient environment (Claudlobby's composition-time fleet resolution is the
  shipped case).

**The engine does not resolve its own vault from a bridge file.** A consumer
that has one passes the path it read via `--vault`, or exports
`CLAUDRON_VAULT_PATH`. This is deliberate: the §Environment ladder stays
one-directional and identical on every host, so a command's resolution never
depends on where in a consumer's tree it happened to be run. (Claudron #46
proposed the opposite — a plugged-vault fallback at the bottom of the ladder —
and is declined on those grounds.)

## Write guarantees

The honest ladder. Each rung states what the engine promises and what it does
not; consumers building fleet write policy build against these, not against
observed behavior.

| Scope | Guarantee |
|---|---|
| **Within one host** | **Serialized.** Every mutator (`capture`, `capture --update`, `promote`, `sync`) holds a cross-process `flock` over its read→write→index critical section and writes via temp-then-`os.replace`, so concurrent writers cannot drop an index entry or leave a torn file. |
| **Across hosts** | **Eventually consistent, conflicts quarantined.** `sync` commits, pulls `--rebase`, pushes. Conflicts are never auto-resolved: the rebase stops, markers are left for a human, and marker-bearing notes are excluded from index/lookup/recall until resolved. |
| **Multi-writer exclusion** | **Out of scope, by constraint.** Guaranteeing at-most-one writer across hosts requires a coordinating daemon; the engine is a CLI over markdown + git and will not grow one. Writer topology is fleet policy, expressed by the composer's grants — not by the engine. |

**Stated limits.** `flock` is a no-op where `fcntl` is unavailable (Windows)
and can be a silent per-host no-op on some network filesystems (NFS without
lockd, SMB/CIFS) — on such a mount two hosts are not serialized. A git-synced
vault should live on a local filesystem. Atomic replace guarantees
reader-atomicity, not crash-durability (no `fsync`) — acceptable because the
vault is git-backed.

**The conflict surface, named.** Collisions are rare by construction: writes
are create-only with distinct slugs and the derived index is gitignored. What
remains is same-slug creates on two hosts, `--update` appends to the same note,
and concurrent edits to `CONVENTIONS.md`. Two mitigations cover it: dedup
**routes before the write** (a near-duplicate returns `suggest_update` /
`suggest_supersede` having written nothing), and quarantine keeps a conflicted
note out of every read path until a human resolves it — so a conflict degrades
recall rather than corrupting it.

## Flags

- `--vault PATH` and `--json` are accepted by every subcommand (implemented
  via a shared parent parser — `claudron status --json` parses).
- Vault resolution: see §Environment — the precedence-ordered table there is
  the one normative statement, and a doc-parity test pins it to the resolver.
- Scoping: `--project NAME` / `--fleet NAME` where meaningful; they are
  mutually exclusive wherever both exist.

## Command groups (`--help` taxonomy)

| Group | Commands |
|---|---|
| vault | `init`, `status`, `validate`, `index` |
| notes | `new`, `lookup`, `related`, `links` |
| session | `recall`, `capture`, `sync`, `hooks` *(E2)* |
| fleet | `fleet add`, `fleet list` |
| integration | `plug`, `unplug`, `config`, `migrate` |
| curation | `promote`, `review` *(E5)* |
| packs | `pack …`, `scenarios export` *(E6)* |

## Command-specific contracts

- `validate [PATH]` — no arg: detected vault; directory: that subtree; file:
  that single note. Lints note frontmatter (SCHEMA.md) and, when the target is
  a whole vault, its directory structure (VAULT-STRUCTURE.md — codes `S1`–`S4`,
  same `error`/`warning` model, so `--strict` gates structure warnings too).
  `--strict` applies the authoring tier. The default path never mutates; the
  opt-in **`--fix`** performs creation-only structure repairs (e.g. a fleet's
  missing `shared/`) strictly inside the vault root — it never moves, deletes,
  or follows a symlink out. Tip for humans: `validate --strict` previews
  exactly what the engine/bot write paths will accept. The `--json` envelope
  carries structure findings but no per-finding fixability flag; a machine
  consumer derives it from the code (`S1` is the fixable structure code).
- `new <type> "<title>"` — output always passes `validate --strict`. `owner`
  derivation: `--owner` → `git config user.name` → `$USER`. Slug collision
  errors (never silently overwrites); `--force` overrides. `--edit` without
  `$EDITOR` still writes the note and errors on stderr.
- `capture` / `capture --update` — the write door (shared engine with a future
  MCP `claudron_write`). The `--json` `data` payload is the typed write result:
  `{action, path, reason, written}`.
  - **`action` ∈ `{created, updated, suggest_update, suggest_supersede, rejected}`**;
    `written` is `true` only for `created`/`updated`.
  - **`written`/`action` — not the exit code — is the "a note landed" signal.**
    Dedup *routes, never hard-rejects*: a near-duplicate returns
    `suggest_update`/`suggest_supersede` with **exit 0** and **`ok:true`** having
    written nothing (the human/agent is asked to `--update` or `--force`). A
    consumer that treats exit 0 / `ok:true` as "captured" silently drops the
    finding — branch on `written`. `rejected` (validation failure) is the only
    write outcome that exits 1. (This `written` signal is specific to
    dedup-routed `capture`; the authoring door `new` always writes-or-errors —
    exit 0 means the note landed — so it carries no `written` field.)
  - **Programmatic writers MUST pass content via `--stdin` JSON, never `--body`
    string interpolation.** Note bodies are free text (quotes, newlines,
    `$(...)`, backticks); building a `--body "…"` shell argument truncates the
    note or executes substitutions in the caller's shell before `claudron` runs.
    `--stdin` carries arbitrary content safely.
- `init --adopt` — additionally backfills missing `updated` from file mtime
  (the one sanctioned mutation, at adoption time only).
