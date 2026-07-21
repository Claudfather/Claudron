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

## Session-loop protocol

What a host's session lifecycle owes the knowledge layer, and who owes it.
The loop is **a protocol with roles, not a place**: no participant owns "the
session," each owns a role in it. Anything that installs these hooks, composes
them onto a bot, or co-inhabits the same events builds against this section.

### The four roles

<!-- doc-parity: SESSION_ROLES -->
| Role | Content class | Owner | Engine event |
|---|---|---|---|
| `R-continuity` — the workspace brief: git state, tickets, a handoff artifact | behavior | **The front-end.** The engine ships no handler for it and never will. | — |
| `R-recall` — the knowledge brief: durable notes, ranked and budgeted | engine op | **Claudron** | `session-start` |
| `R-capture-prompt` — the distill nudge at compaction | engine protocol | **Claudron** defines it; exactly one participant *holds* it per session | `pre-compact` |
| `R-sync` — pull at session start, push at session end | engine op | **Claudron** | `session-start`, `session-end` |

**The briefs co-inject by design — do not merge them.** A workspace brief and
a knowledge brief carry different content classes; two participants each
emitting one at SessionStart is the correct arrangement, not a duplication to
be resolved. What must not be duplicated is a *role*, and only one role is
contended: `R-capture-prompt`.

### Ordering, and the budget each brief owes

- **`sync --pull` precedes `recall`.** Not an implementation detail: recall
  reads the working tree, so recalling first briefs a second machine on state
  it already superseded. The engine also re-detects the vault after the pull —
  a pull can introduce whole tiers the pre-pull snapshot cannot see.
- **Recall abstains.** A match below the relevance floor injects nothing.
  Empty stdout is a valid brief; padding one is worse than skipping it.
- **`sync --push` happens at session end, bounded** (below). An expired push is
  not an error — the commits travel on the next session's push.
- **The recall brief is capped** at `session.BRIEF_TOKEN_BUDGET`, which covers
  everything the engine injects: the conventions block, the recalled notes, and
  the discovery hint. It degrades by *dropping notes*, never by truncating one
  mid-thought. The constant is the contract; its value is tuning and may change
  without a breaking-change entry.
  - **Stated limit.** The cap holds given a `CONVENTIONS.md` within its own
    budget (`SCHEMA.md` §W105). That block is the always-loaded layer and is
    injected unconditionally — past W105's ceiling it can carry the brief over
    the cap on its own. The layers below it still degrade correctly (zero notes,
    no hint) rather than compounding. Enforcement of the conventions budget is
    `validate`'s job, not recall's: the engine will not silently drop the layer
    a vault declared always-loaded.

**Combined-budget rule: there is none, deliberately.** Caps are per-brief. The
continuity brief is the front-end's to budget; the engine's brief never exceeds
its own cap (with the limit stated above); no participant budgets the total. The
rule is written down so that context creep at SessionStart has an owner *per
brief* rather than no owner at all — a cross-brief budget would require one
participant to police another's context, which no participant is entitled to do.

### The single-prompt rule, and how the prompt is claimed

**Exactly one `R-capture-prompt` holder per session.** Two block-prompts on one
compaction is a defect.

The claim is **structural** — nobody registers, nobody configures:

1. **The engine always prompts** wherever its `pre-compact` hook is installed,
   in text that names no front-end: it routes the agent to *its own* capture
   door, falling back to `claudron capture --stdin`. The engine does not sniff
   for consumers, and no environment variable, marker file, or holder field
   exists to claim the role with. (Register rule R5: capability is declared to
   the owner, never inferred. Here nothing needs declaring.)
2. **A front-end that ships its own capture prompt MUST defer** when the
   engine's `pre-compact` entry is registered. Detect it by the same identity
   `merge_settings` keys on — a hook command ending in `hook pre-compact` — in
   the host's hook-settings files (for Claude Code: the user, project, and local
   `settings.json`). Detect it there and nowhere else; an engine-install probe
   is not the same question and gets the standalone cases wrong.

Both standalone modes fall out for free: with no engine entry the front-end
prompts; with no front-end the engine prompts.

> **Transitional shim (temporary, and ordered).** Until a front-end's defer
> ships, the engine yields to one it can see in the plugin install tree. That
> glob is the single R5 exception in the engine and is deleted on a stated
> condition — the front-end's defer release. **The removal ordering is
> mandatory: the engine's shim-removal release precedes or accompanies that
> defer release.** Defer-first while the shim lives means both sides yield and
> *nobody* prompts, silently; the reverse ordering's worst case is a bounded
> double-prompt window, accepted deliberately.

### The hook-settings snippet — normative shape

`claudron hooks install` emits exactly this; a consumer that composes these
entries itself is a **rendered copy of an owned surface and MUST carry a drift
gate against this block** (register rule R3).

```json
{
  "hooks": {
    "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> hook session-start"}]}],
    "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> hook pre-compact"}]}],
    "SessionEnd": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> hook session-end"}]}]
  }
}
```

- **Three events, one command form:** `<executable> hook <event>`. `hook` is
  the runtime dispatch verb Claude Code invokes; `hooks install` is the
  installer verb a human or composer runs. Both spellings are contract.
- **The identity rule:** a Claudron hook entry is identified by its
  `hook <event>` command *suffix*, not by the full command string. That is what
  `merge_settings` keys on to replace a stale entry instead of appending beside
  it. A consumer that rewrites the command and drops the suffix gets a duplicate
  hook running every session, not a replacement.
- **The executable path must be absolute.** Hook context is not login shell
  context: `PATH` frequently does not carry a venv or pipx install.
  `hooks install` resolves it; a composer must resolve it per host too.

### Fail-open, and the per-event budgets

**A hook never breaks a session.** On any error — unresolvable vault, missing
git, a stalled network, an exception class nobody anticipated — the hook emits
nothing on stdout, appends a line to `.claudron/hooks.log`, and exits **0**.
This is why hook stdout can be injected verbatim: the only thing that ever
reaches it is a brief.

Fail-open alone does not save a *stalled* call, so the two hooks that touch the
network are hard-bounded:

<!-- doc-parity: HOOK_TIMEOUTS -->
| Event | Bounded operation | Budget | On expiry |
|---|---|---|---|
| `session-start` | `sync --pull` | `2.0s` | Pull abandoned; the brief renders from local state. |
| `pre-compact` | none — no I/O | — | — |
| `session-end` | `sync --push` | `10.0s` | Push abandoned; the commits travel on the next session's push. |

These budgets are contract: a fleet composer sizes session startup against
them. Diagnostics from a degraded hook go to `.claudron/hooks.log` — never to
stdout, and never to stderr where a host might surface them as a session error.

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
  - **Provenance rides in frontmatter, not in the body.** `--source-url URL`
    and `--source-type {url,file,inline}` (equally, the `source_url` /
    `source_type` keys of the `--stdin` JSON) write the SCHEMA.md optional
    fields of the same names. Both are omitted from the note when unset.
    `--source-type` accepts only SCHEMA.md's vocabulary; anything else is a
    usage error (exit 2). **A consumer must not fold provenance into a body
    line** — the first substantive body line is what the recall brief shows as
    a note's summary, so a `Source:` line there both spends the summary and
    couples the consumer to how that summary is picked.
  - **Programmatic writers MUST pass content via `--stdin` JSON, never `--body`
    string interpolation.** Note bodies are free text (quotes, newlines,
    `$(...)`, backticks); building a `--body "…"` shell argument truncates the
    note or executes substitutions in the caller's shell before `claudron` runs.
    `--stdin` carries arbitrary content safely.
- `init --adopt` — additionally backfills missing `updated` from file mtime
  (the one sanctioned mutation, at adoption time only).
