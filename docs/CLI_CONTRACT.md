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

**A health verdict is not a failure.** `sync --check` exits 0 for every state
it can report, `unknown` included. Anything else would put the clone's health
into the exit code, where a consumer could no longer tell a wedged vault from a
probe that did not run. Its envelope keeps `command: "sync"` and carries
`data.check: true` as the discriminator.

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
  `engine_version`** (below); `index --navigation` → the navigation result
  (§Command-specific contracts); `lookup` →
  `{query, results}`, each result `{title, score, match_type, tier, path, tags,
  maturity, trust, trusted}` (§Trust-aware reads); `related` →
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

### Gate a per-feature capability on `capabilities`, never on the version

`data.capabilities` is the list of named features this engine ships — the
**declaration**, per register rule R5: *capability is declared to the owner,
never inferred*. A consumer asks `"navigation" in data["capabilities"]` and
nothing else. Absent on an engine that predates the list, which is the correct
answer for every capability in it.

**`engine_version` is NOT a feature gate, and cannot be made into one.** It
answers *"is an engine here, and which one?"*; it does not answer *"can it do
X"*. Three ways of inferring the answer from it were measured and all three
fail:

| inference | why it fails |
|---|---|
| a version floor, e.g. `>= 0.5.0` | **Cannot be expressed.** `engine_version` is `0.5.0.dev0` on a build of the branch that ships the feature and `0.4.0` on the last release. PEP 440 sorts a dev release *before* its release, so `0.5.0.dev0 < 0.5.0`: the floor a CHANGELOG naturally invites is satisfied by **neither**, and the gate can never pass. `>= 0.5.0.dev0` is the expressible form, but it still gates on ship order rather than on the capability. |
| a **verb** probe (`claudron <verb> --help`; exit 2 on an unknown verb, measured) | Cannot see a new **flag** on a verb that already exists — `index` has been a verb since long before `--navigation`. |
| a **flag** probe (`claudron index --navigation --help`) | **Cannot fail.** argparse fires `--help` as a parse action and exits 0 *before* it reports unknown arguments, so this exits 0 on an engine with no such flag — measured against 0.4.0, whose `index --help` contains no `navigation`. The control: the same engine exits **2** for `index --navigation` *without* `--help`, so the parser does reject it; `--help` merely short-circuits first. A probe that cannot fail is worse than none, because it reads as a second line of defence. |

`engine_version` remains what it always was — identity and health, reported and
logged. `capabilities` is the gate.

These `data` fields of `status --json` are **stable** — machine consumers may
rely on them, and removing or retyping one is a breaking change:

| Field | Type | Meaning |
|---|---|---|
| `engine_version` | string | Installed engine version — identity and health, **never a feature gate** (above). `"0.0.0-dev"` when running from an uninstalled checkout; `X.Y.Z.devN` on a build between releases. |
| `capabilities` | array of string | Named features this engine ships (`claudron.CAPABILITIES`). **The feature gate.** Absent on an engine predating the list; a name is never removed or renamed without a breaking-change entry. |
| `root` | string | Absolute path of the resolved vault. |
| `total_docs` / `total_stale` | int | Vault-wide note counts. |
| `tiers` | object | Per-tier `{docs, stale, path}`. |
| `fleets` / `projects` | array | Names present in the vault. |
| `runs` | object | The ops log's liveness (#200 §5): `{last_run, last_ok_at, last_failure}`, each `null` until a run has logged. `last_run` is `{run_id, at, writes, failures, reverted}`, `last_failure` is `{run_id, at, kind, reason}`. Gate on `ops-log`. |

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
| 3 | walk up from CWD | discovery | Ascend from the working directory for a directory carrying the **`.claudron-vault` identity file** (VAULT-STRUCTURE.md), the way git ascends for `.git/`. A bare `_shared/` or `shared/` does not bind. |

An explicit address (rows 1–2) also opens a vault that has a `_shared/` (or
`shared/`) hub but no identity file yet — an address given on purpose is not a
guess, and it is what lets `doctor --fix` migrate such a vault. A path that
resolves but is neither is not a fallback — resolution stops and the command
exits 3. When nothing resolves, `claudron` exits **3** with the no-vault
message on stderr; when walk-up passed a vault that lacks only its identity
file, the message names it and the command that migrates it
(`claudron doctor --vault <path> --fix`).

> Breaking change (#183): walk-up bound any `_shared/` or `shared/`
> before; it now binds only on the identity file.

**`CLAUDRON_VAULT` (removed in 0.3.0).** An earlier lower-precedence spelling of
`CLAUDRON_VAULT_PATH`, removed rather than deprecated: read at all, a second
name that disagreed with the canonical one resolved a *different vault*. It is
not read, is not in the table above, and carries no warning. Rename any
straggler to `CLAUDRON_VAULT_PATH`.

**Consumer obligations.**

- Emit and read **only** `CLAUDRON_VAULT_PATH`. A consumer that still reads the
  removed name re-creates the two-vaults hazard in reverse — its resolution
  succeeding where the engine's fails is worse than both failing.
- `SHARED_DOCS_PATH` is **clauDNA's fallback-mode variable**, not part of this
  contract. It addresses a raw documentation tree when no engine is present, is
  never consulted on an engine path, and is out of scope here.
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
| **Across hosts** | **Eventually consistent, conflicts reported — never written into the tree.** `sync` commits, integrates the upstream **off the live tree** (row below), pushes. Conflicts are never auto-resolved: a conflicting note is reported by path and its local copy stays as it was, still served. A note that *arrives* carrying markers (committed that way on another host) is quarantined — excluded from index/lookup/recall until resolved; detection is stateless, on the file's content. |
| **A clone already stopped mid-rebase is refused, not repaired** | `sync` itself never starts a rebase in the live tree, so it never leaves one behind. A clone stopped mid-rebase by something else (an older engine, a human's `git pull --rebase`) is refused before anything is written, and `sync --check` names it `rebase-killed` or `rebase-conflict`. Repairing it stays the human's call: a conflict's markers are work in progress, and erasing them is worse than the wedge. |
| **`sync` never leaves markers in the vault** (#158; unconditional since #193) | Integration happens in a throwaway worktree, so a conflict or a kill leaves the live tree **byte-identical** — no `rebase-merge/`, no conflict markers, nothing half-checked-out. The live tree moves only by `merge --ff-only` or by one `reset --keep` to a tip built elsewhere. A conflict is reported **by path** in `detail`, and on a failed integration (`pulled: false`) `quarantined` names notes that **could not be integrated** rather than notes carrying markers; resolve by editing the note on the default branch and re-running `sync`. Why it matters: a stopped in-place rebase checks out the *other* side's files, and on 2026-09-09 that made a fleet's manifest, charter and projects file absent from disk — a review three weeks later reported them as never having existed and the fleet re-drafted both. |
| **`sync` refuses to run off the default branch** | A clone on a side branch is the one state where captures look durable in `git log` and exist on no other machine. `sync` refuses before writing anything — `refusing to sync: HEAD is on '<branch>', the vault syncs on '<default>' — checkout the default branch, or pass --branch <branch> to sync a side branch deliberately`. `--branch NAME` is the **only** override, and it must name the branch actually checked out. The refusal precedes the commit, so a refused sync adds nothing to the stranded branch. |
| **A stale `index.lock` expires; a live one is refused** | Git never expires `index.lock`, so one that outlives its process blocks every git WRITE while every git READ keeps working — which is why the last one went unnoticed for ten days: `status --porcelain` needs no lock, so the tree read "merely dirty" and `sync` blamed the dirty tree. `sync` now checks before its first write. A lock that is **both** older than 600 s **and** provably unheld is removed, and `detail` records `expired stale index.lock (age Ns, no owner)`. Anything else — fresh, held, or ownership unprobeable — returns `ok=False` with `refusing to sync: .git/index.lock is present (age Ns, owner held\|no owner\|unknown) — another git process may be running; nothing was written`. **Unknown ownership is never treated as no owner**: deleting a live lock corrupts the index, so ambiguity resolves to refusing. Ownership is read from the kernel (`lsof`, or GNU `fuser` only where `--version` says psmisc — BSD `fuser` exits 0 for an unheld file and so proves nothing), never from the lock file, which holds no pid. |
| **`sync --check` is THE git-health probe, and it never writes** | One bounded, read-only, offline verdict on the clone, for consumers that need to ask "is this healthy" without changing it. `status --json` cannot be that probe: it walks every note and rebuilds and WRITES the index, so asking mutates the subject and cannot be asked of a wedged or read-only tree — it is a **capability** probe, not a health probe. `--check` runs only query commands (`--no-optional-locks` included, because a plain `status` refreshes and rewrites the index), touches neither the index nor the journal, and answers with no network unless `--reach` is passed. Verdicts, in precedence order: `unknown` `stale-lock` `rebase-conflict` `rebase-killed` `merge` `detached` `side-branch` `dirty` `divergent` `behind` `ahead` `unreachable` `clean`. A side branch with and without an upstream share `side-branch`; the `upstream` field (name or `null`) tells them apart. **`unknown` means the check could not run** (git missing, a call timed out) and must never be read as healthy — a reader that cannot reach its source must not answer the same as one that found nothing wrong. **Every verdict exits 0**, including the bad ones: the state is in the envelope, never in the exit code, so "the check ran" and "the clone is healthy" stay separable. `--check` beside `--pull`/`--push` is a usage error (2); a vault that is not a git repository is an environment error (3). |
| **A failed `git add` names git's own message** | Previously an unchecked `add` fell through to a failing `commit`, and the porcelain re-read then reported `the working tree is not clean after the pre-pull commit` — true, useless, and pointing at the tree rather than the cause. `sync` now returns at the failed `add` with git's stderr in `detail`. |
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
    no hint) rather than compounding. Recall will not silently drop the layer a
    vault declared always-loaded, so the conventions budget is **reported, not
    enforced, and nothing hard-enforces it**: W105 is a warning in *both*
    validation tiers, so `validate --strict` surfaces an over-budget
    `CONVENTIONS.md` and still exits 0. A consumer that needs a hard ceiling
    gates on the warning code itself.

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

> The R5 plugin-glob shim that formerly bridged this transition was **removed in
> #85**; the claim is now structural end-to-end. A consumer's defer release keys
> on that removal release — ordering and rationale are in the CHANGELOG
> (`Removed`); clauDNA #254 is the waiting consumer.

### The hook-settings snippet — normative shape

`claudron hooks install` emits exactly this; a consumer that composes these
entries itself is a **rendered copy of an owned surface and MUST carry a drift
gate against this block** (register rule R3).

```json
{
  "hooks": {
    "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> --vault <absolute-vault-root> hook session-start"}]}],
    "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> --vault <absolute-vault-root> hook pre-compact"}]}],
    "SessionEnd": [{"matcher": "", "hooks": [{"type": "command", "command": "<absolute-executable> --vault <absolute-vault-root> hook session-end"}]}]
  }
}
```

- **Three events, one command form:** `<executable> --vault <vault-root> hook
  <event>`. `hook` is the runtime dispatch verb Claude Code invokes; `hooks
  install` is the installer verb a human or composer runs. Both spellings are
  contract.
- **The command names its vault (#183).** Walk-up ascends from the working
  directory, so it finds a vault only from inside one (and, since 0.5.2, only
  one carrying `.claudron-vault`). Without an address, a session started
  anywhere else (a repo checkout, or a GUI launch that skips the shell profile)
  finds no vault unless `CLAUDRON_VAULT_PATH` is set, and every hook silently
  does nothing.
  - **What `hooks install` records:** the vault it resolved, by the §Environment
    chain (`--vault`, then the env ladder, then walk-up), written as the global
    `--vault`, placed before `hook` so the identity suffix below survives.
  - **When nothing resolves,** it exits 3 and writes nothing, with or without
    `--write`: the dry run refuses too, rather than print a snippet with no
    address. An unaddressed hook is the failure this rule closes.
  - **The recorded address outranks the session's environment and working
    directory,** because `--vault` is first in the chain. A session started
    inside another vault's tree, or with `CLAUDRON_VAULT_PATH` naming another,
    still syncs the vault the hooks were installed for. So with two vaults and
    one user-level settings file, the hooks follow the install, not the
    directory; a project that should sync its own vault installs into its own
    settings file (`--settings`).
  - **To re-point,** re-run it. The identity rule replaces the old entries.
    Until then, hooks that name a vault which has moved fail open: exit 0, and
    one `no vault resolvable` line per event in the temp directory's
    `claudron-hooks.log`. The exception is an old path inside another vault's
    tree: walk-up from the address binds that vault instead.
  - **A composer** renders each consumer's own vault root.
  - **A settings file `--write` cannot merge into is refused, never rewritten**
    (#205): exit 3, the file unchanged, the reason on stderr. It must be a
    regular, readable UTF-8 file holding a JSON object; its `hooks`, when
    present, an object; and each of the three events, when present, a list of
    objects whose own `hooks` is a list of objects. Other events are not
    checked, since the install never touches them. `doctor` reads a settings
    file through the same reader, so every file it calls unparseable (`D009`)
    is one this refuses.
- **Why `--vault` and not `env` in the settings file.** An `env` block applies
  to every process in every session that loads that file: tool calls, MCP
  servers, the model's own shell, not only these hooks. Where several sessions
  share one settings file, it would re-point every Claudron call they make.
  `--vault` reaches exactly the three commands `hooks install` writes.
- **The vault root is shell-quoted when it needs it** (`shlex.quote`). Claude
  Code runs a hook command through a shell, and an unquoted path with a space
  would split. The executable is written as `hooks install` resolved it: a
  command prefix, which may be `<python> -m claudron.cli`.
- **The identity rule:** a Claudron hook entry is identified by its
  `hook <event>` command *suffix*, not by the full command string. That is what
  `merge_settings` keys on to replace a stale entry instead of appending beside
  it. A consumer that rewrites the command and drops the suffix gets a duplicate
  hook running every session, not a replacement.
- **The executable path must be absolute,** and so is the vault root. Hook
  context is not login shell context: `PATH` frequently does not carry a venv or
  pipx install. `hooks install` resolves both; a composer must resolve both per
  host too.
- **Checking an install:** `claudron doctor --settings <file>` compares a
  settings file's entries with this block (`D009`) and resolves each recorded
  address (`D010`); see `doctor` below.

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
| vault | `init`, `status`, `validate`, `doctor`, `index` |
| notes | `new`, `lookup`, `related`, `links`, `graph` |
| session | `recall`, `capture`, `sync`, `hooks` *(E2)* |
| fleet | `fleet add`, `fleet list` |
| integration | `plug`, `unplug`, `config`, `migrate` |
| curation | `promote` *(E5)* |
| harvest | `subjects`, `resolve`, `amend`, `revert-run` *(#200 §4)*, `tags` *(#200 §3)* |

## Command-specific contracts

- `validate [PATH]` — no arg: detected vault; directory: that subtree; file:
  that single note. A whole vault (no arg, or PATH is its root) is linted over
  its notes: the note tiers, the root `CONVENTIONS.md` and root-level notes, the
  scope the index, `status` and the quarantine scan read. A fleet's `library/`,
  `voices/` and `runtime/` are not notes, so a gitignored bot checkout under
  `runtime/` is never walked. An inner directory is walked as given.
  Lints note frontmatter (SCHEMA.md) and, when the target is
  a whole vault, its directory structure (VAULT-STRUCTURE.md — codes `S1`–`S4`,
  same `error`/`warning` model, so `--strict` gates structure warnings too).
  `--strict` applies the authoring tier. The default path never mutates; the
  opt-in **`--fix`** performs creation-only structure repairs (e.g. a fleet's
  missing `shared/`) strictly inside the vault root — it never moves, deletes,
  or follows a symlink out. Tip for humans: `validate --strict` previews
  exactly what the engine/bot write paths will accept. The `--json` envelope
  carries structure findings but no per-finding fixability flag; a machine
  consumer derives it from the code (`S1` is the fixable structure code).
- `sync` / `sync --ff-only` — **the envelope, the exit code and the summary
  line always agree** (#142). A run whose `data.detail` is non-empty (a
  refusal, a failed push, a timeout, a repair the human should know about)
  exits **1**, carries exactly one `G001` error whose `message` is that
  `detail`, so `ok` is `false`, and prints a summary line ending
  `— needs attention (see stderr)`; it never prints `nothing to do` or
  `already up to date`. A clean run exits 0 with `ok: true` and no errors.
  Branch on `ok` or the exit code; `detail` is prose. `sync --check` is
  unaffected: every verdict exits 0 (§Exit codes).
- `doctor [--fix] [--settings PATH]…` — **the vault's health-and-migration door** (#190). Diagnoses
  the vault against *this* engine's rules and names what `--fix` would change.
  - **Read-only unless `--fix` is passed** — no file, index or journal is
    written, which a test pins by fingerprinting the tree around a diagnosis.
    Its git leg is `sync --check`'s verdict (read-only, offline).
  - **Findings** are ordinary `Finding`s in the envelope: structure codes `S1`–`S4`
    as `validate` reports them, plus the `D` codes below. Exit **1** when any
    finding is an error, else **0** — the §Exit codes rule, no special case.

    <!-- doc-parity: DOCTOR_CODES -->
    | Code | Severity | Meaning | `--fix` acts? |
    |---|---|---|---|
    | `D001` | error | A migration is pending: the vault's format is older than the engine's | yes |
    | `D002` | error / warning | Notes carry schema findings (a count over the whole-vault note scope; `validate` has the detail) | no |
    | `D003` | warning | The index has drifted from the notes — `claudron index` | no |
    | `D004` | warning | Git health is not `clean`/`ahead`/`behind` (the `sync --check` verdict) | no |
    | `D005` | error | *(`--fix` only)* A migration needs a human decision; the chain stopped | — |
    | `D006` | error | *(`--fix` only)* A migration ran but is still needed; the chain stopped | — |
    | `D007` | error / warning | The identity file is unreadable (error), or records a format newer than the engine (warning) | no |
    | `D008` | warning | Tracked files match the ignore rules, so they keep being committed — a human decides (`git rm --cached`) | no |
    | `D009` | warning | *(per host)* A checked settings file's hook entries do not match the current snippet shape: an event with no claudron entry or with two, an entry with no `--vault`, or any other difference; or a declared settings file is missing or unreadable | no |
    | `D010` | error / warning | *(per host)* A hook entry will not reach a vault from where it runs. Error: its executable does not exist, its address resolves to nothing, or walk-up from the address binds another vault. Warning: its executable is a bare name, its address is not absolute, it resolves to a vault other than the one diagnosed, or it lies inside the diagnosed vault but is not its root | no |

  - **The per-host checks** (`D009`, `D010`, #204). A vault's hooks live in a
    Claude Code settings file on each host, outside the vault, so doctor checks
    the files it is given and never goes looking: `--settings PATH`
    (repeatable), or by default the file `hooks install --write` writes,
    `~/.claude/settings.json`. A consumer that composes the hooks into its own
    files passes those. Entries are found by the identity rule (§Session-loop
    protocol), compared with `settings_snippet` as this engine renders it, and
    each recorded address is resolved as the hook resolves it (§Environment).
    Nothing from a settings file is executed: the executable check is existence
    and the execute bit. A default file that does not exist, or that holds no
    claudron entry on any of the three events, is not a finding: that host never
    ran `hooks install`, so it has no loop to check. A partial install is a
    finding, and so is a declared file either way, since a consumer said the
    hooks live there. Each finding names its remedy: for an entry,
    `claudron --vault <vault> hooks install --write` with that file's
    `--settings` (or re-rendering the file, when a composer manages it); for a
    declared file that is missing, the same command with its path; for hooks
    that sync another vault, the same command with another settings file; and
    for a file that cannot be parsed (including a path that is not a regular
    file), repairing the file, since `hooks install --write` refuses it too. Re-installing replaces the whole hook
    group that holds a claudron entry, so a finding whose group also holds
    other commands says that re-installing drops them.

  - **Migrations shipped:** `m001` creates `.claudron-vault` (format 1);
    `m002` appends the missing F9 `.gitignore` rules (format 2). After the chain
    completes, `--fix` records the engine's format in the identity file, in the
    same commit.

  - **`data`**: `vault_format` (int — `claudron:` in the identity file, 0 when
    there is none) / `engine_format` (int — the vault is current when they are
    equal), `pending` (`[{id, version, title}]`),
    `fixable` (migration ids and finding codes `--fix` acts on), `schema`
    (`{errors, warnings}`), `index` (the `status` divergence dict), `git` (the
    `sync --check` `data`, or `null` for a vault that is not a git repository —
    a legal vault, so not a finding), `hooks` (one object per settings file
    checked, in order: `path` (absolute), `declared` (false for the default
    install target), `state` (`ok` / `absent` / `unreadable` / `not-installed`,
    the last for a file with no claudron entry on any event), and `entries`,
    each `{event, command, vault, resolves_to}`, where `vault` is the recorded
    address or `null` and `resolves_to` is the root that address binds or
    `null`), `fixed` (bool). With `--fix` also:
    `applied` (migration ids, in order), `repairs` (one line per action), and
    `commit` (`{committed, message, error}`, or `null` when nothing was written).
  - **`--fix`** applies fixable structure repairs, then pending migrations **in
    format order**, under the vault write lock. Migrations are idempotent,
    creation- or edit-only, never delete a note, and never write outside the
    vault root — an escape aborts the run (exit 1, `--fix aborted: …`). A
    migration that cannot decide something reports `D005` and stops rather than
    guess. What was written lands as **one commit**,
    `migrate(<ids>): claudron doctor --fix`, staging only those paths; a
    mid-rebase clone gets the files but not the commit, and says so in
    `data.commit.error`. The result is re-diagnosed, so `pending` after a
    successful run is `[]`.
  - `validate --fix` remains as an **alias** for the structure half of `doctor
    --fix`, and says so on stderr; `doctor` is the one repair door.
  - Gate on `"doctor" in status --json → data.capabilities` (§Capability probe).
  - Gate `--settings` on `"doctor-settings" in status --json → data.capabilities`.
    An engine without the flag exits 2 on it, and exits 0 when `--help` follows,
    so only the declared name can tell a consumer it is there (§Capability probe).
- `index [--full] [--navigation]` — rebuilds the derived index. **`--navigation`
  (engine 0.5.0)** additionally regenerates every directory's `INDEX.md` from
  that index, making it a *derived* file rather than a hand-appended one
  ([#155](https://github.com/Claudfather/Claudron/issues/155)). Idempotent: a
  second run writes nothing. Each generated file opens with
  `<!-- generated by claudron index --navigation; do not hand-edit -->`.
  - **A regeneration is not a blanket overwrite, and the split is observable.**
    An entry present in the file that the index does not know about is
    **preserved** verbatim under a marked section when its link target exists,
    and **dropped** when it does not. Preserving is the ruling rather than
    refusing: a door that refused a whole regeneration over one odd line would
    be switched off, and every `INDEX.md` would be hand-edited again.
  - **A description is not deleted just because the note has none.** The note's
    frontmatter `description:` wins whenever it exists — that disagreement is
    the conflict class this removes. Where the note has none, the description
    already in the file is **carried** rather than dropped, and reported. The
    engine never invents one.
  - **Neither outcome is ever silent.** `--json` `data` carries
    `navigation_written`, `navigation_unchanged` (both arrays of paths),
    `navigation_preserved`, `navigation_dropped`, `navigation_carried` (all
    three objects keyed by directory), `navigation_skipped` (object keyed by
    directory, value = the reason) and `navigation_bounds` (the human bound
    lines). Plain mode prints
    the same bound to **stderr** on every run, including when nothing was
    preserved or dropped — that is exactly when silence would be ambiguous.
    Branch on the JSON; `navigation_bounds` is prose and is not a parse target.
  - There is deliberately **no per-door version field** in the payload. The
    capability is gated on `status --json` → `data.engine_version` (§Capability
    probe); a second version concept beside the sanctioned one only makes a
    consumer guess which to read.
- **Memory homes** (#200 §2, SCHEMA.md §Memory homes): `entity`, `concept`,
  `person`, `project` and `practice` are types. `new` and `capture` take
  `--kind K` (and `kind` / `relations` on `--stdin`: `relations` is an object
  over the closed set `part_of, instance_of, depends_on, owned_by, supersedes,
  related`, each a list of wikilinks); a home files under `<home>/<kind>/`
  in a shared tier and `new` scaffolds its sections. `kind` on a type that
  isn't a home, or one that isn't a string, exits 2. A `person` note lives only
  in `_personal/person/`: `--project`/`--fleet` with one exits 2, and `capture`
  writes one only with `asserted_by: user` (`--asserted-by` or the `--stdin`
  key), else exit 2. `amend` refuses a fact or an alias about a person unless
  the user asserted it (`evidence.asserted_by` / `asserted_by`).
  `subjects` and `resolve` take `--home H` (the same filter as `--type`, and
  exclusive with it) and `--kind K`, and each subject carries `kind` and
  `relations`. `recall --json` gains `me`: the body of a trusted
  `_personal/person/me.md`, or `null` (absent, a draft, conflicted, or
  `BOT_NAME` set), rendered as `## About me`. Gate on
  `"memory-homes" in status --json → data.capabilities`.
- `new <type> "<title>"` — output always passes `validate --strict`. `owner`
  derivation: `--owner` → `git config user.name` → `$USER`. Slug collision
  errors (never silently overwrites); `--force` overrides. `--edit` without
  `$EDITOR` still writes the note and errors on stderr.
- `lookup` / `recall` — **trust-aware reads** (#200 §1). Each note has a read
  class, `trust` ∈ `{trusted, draft, external}` (SCHEMA.md §Reads: maturity ×
  origin); `trusted` is its boolean.
  - **`lookup` ranks every trusted note above every draft**, whatever the score;
    score orders notes within a class. An **`external`** draft is withheld
    unless **`--include-external`**. An authored draft is always included,
    labelled `(draft)`; an included external one, `(unverified draft)`.
  - **`recall --json`** adds `trust`, `trusted` and `source_url` to every note,
    and two keys to `data`: `unverified` (external drafts, newest first, at most
    `session.UNVERIFIED_LIMIT`, same entry shape) and `unverified_more` (how many
    more exist). An external draft never appears in `notes`.
  - **The brief** renders `unverified` after everything trusted, under its own
    header and a "never cite as fact" line, in whatever budget is left. Each line
    is title, type, path and `source_url`; the body is never shown, since the
    body is where someone else's instructions would be.
  - Gate on `"trust-aware-reads" in status --json → data.capabilities`. On an
    engine without it, `lookup` returns drafts ranked by score alone and
    `recall` has no `unverified` key, so a consumer splits drafts out itself.
- `subjects [--type T] [--project P]` — the **derived subject registry** (#200 §4): every live
  note (not archived or superseded) that facts can be filed under, by title.
  There is no stored registry; a subject exists because its note does. `--json`
  `data` is `{type, subjects}`, each `{title, path, type, aliases, sections,
  tags, maturity, trust, source_type, tier, updated, score, match_type, exact}`
  (`score`/`match_type`/`exact` `null` here). `sections` are the note's `##` headings. Drafts are included and
  labelled by `trust`: a writer must find the draft an earlier run wrote, or it
  files a twin. Gate on `"subjects" in status --json → data.capabilities`.
- `resolve --name N [--type T] [--project P] [--aliases a,b] [--alias NAME]... [--context TEXT] [--limit K]` —
  the top-K **candidate subjects** for a name, best first, same entry shape with
  `score` and `match_type` set. A candidate scores its best match over the name
  and aliases: exact title (100), exact alias (90), slug (85, `match_type:
  "slug"`), then title, tag and filename scoring. `exact` is true for the
  first three. Read it, not `match_type`, to tell the subject itself from a
  note that shares a word: a fuzzy title hit is labelled `title` too.
  `--alias NAME` (repeatable) adds one name each, for a name with a comma in
  it. `--project P` (on `subjects` too) keeps only notes in that project's
  tier: "staging DB" in one repo is not "staging DB" in another. `exact`,
  `tier`, `source_type`, `--project` and `--alias` are gated on
  `"subject-filing" in status --json → data.capabilities` (0.7.1): an older
  engine refuses the flags (exit 2) and omits the fields. `--context` only breaks ties
  among notes that already matched; it never adds one. **Choosing among the
  candidates is the caller's job**; `resolve` never picks, writes or runs a
  model. Same capability as `subjects`.
- `amend --stdin` — **fact-level section writes** on an existing note (#200 §4),
  through the same lock, lenient validation, index refresh and commit as
  `capture --update`. stdin is one JSON object: `note` (title, alias, slug or
  vault-relative path), `op`, `run_id` (optional), and per op:
  - `append_fact`: `section`, `fact`, `evidence` `{ref, date?, asserted_by?}`.
    A missing section is created (before `## History`).
  - `add_evidence`: `fact_id`, `evidence`.
  - `add_alias`: `alias` (added to frontmatter `aliases`).
  - `supersede_fact`: `fact_id`, `fact`, `evidence`. The old fact moves to
    `## History` as `- <text> — superseded <date> by fact:<new id>`.

  The fact format is SCHEMA.md §Facts. **Idempotent:** a fact whose id and
  evidence ref are already there is a no-op, and the same fact with a new ref
  adds only that ref, which is how recurrence is counted. `add_alias` refuses a
  name another note already has (title or alias). `--json` `data` is `{action, op, path, outcome,
  fact_id, reason, written}`: `action` ∈ `{updated, unchanged, rejected}`,
  `outcome` ∈ `{fact_added, evidence_added, alias_added, fact_superseded}`, and
  `written` is true only for `updated`. A malformed request (unknown op, a
  missing field, a `fact_id` that isn't live, a comment marker in the text, a
  taken alias, unparseable stdin, no note matching `note`) exits 2 and writes
  nothing; with `--json` it still prints an envelope (`ok: false`, one
  `errors` entry with code `request` — not a catalog code: the request, not the
  note, is at fault — and `data.action: "rejected"` with the refusal in
  `data.reason`), so a caller can tell a refused request from a broken engine.
  `rejected` from validation exits 1. An optional `expect_trust`
  (`trusted` | `draft` | `external`) is checked under the write lock against
  the note as it is then: if the note no longer reads as that class (a person
  promoted it after the caller resolved it) and the op would write, it is
  refused and nothing is written; a replay that would write nothing is still
  `unchanged`. `expect_trust` and the refusal envelope are gated on
  `subject-filing` (0.7.1). Gate on
  `"amend" in status --json → data.capabilities`.
- `tags [--resolve TAG...]` — the **tag registry** (#200 §3, SCHEMA.md §Tags):
  `--json` `data` is `{registry, tags, unregistered, noncanonical_in_use, other,
  problems}`. `registry` is the vault-relative path or `null` when the vault
  has none; `tags` lists each registered tag (`name, description, aliases,
  status, merged_into, count`); `unregistered` the tags in use under a
  registered facet that the registry doesn't name; `noncanonical_in_use` the
  aliases and deprecated tags notes still carry, with their `canonical` form;
  `other` how many tags in use sit outside every facet (a consumer's own
  namespaces); `problems` what is wrong with the file. `--resolve` answers
  `{registry, resolved: {tag: canonical}}`. `new` and `capture` write
  canonical tags (case-insensitive; aliases and deprecated tags resolved). Gate on
  `"tags" in status --json → data.capabilities`.
- **Operations log** (#200 §5, capability `ops-log`): one JSONL file per run and
  per session under the vault's gitignored `.claudron/` —
  `runs/<run_id>/ops.jsonl` and `sessions/<session_id>/ops.jsonl` — local and
  never synced. Every line carries `v` (1), `ts`, `kind`, `session_id`,
  `run_id`, `emitter` (`claudron`) and `event_id`, then the kind's fields.
  A run logs `write` (`verb`, `path`) for each committed write,
  `write.uncommitted` when the commit failed (W108), `write.refused` and
  `write.routed` (dedup) for what it asked for that didn't land, and
  `run.reverted`. A session's hooks log `recall.served` (the `trusted`,
  `drafts` and `unverified` paths the brief showed, after its budget) and
  `sync.push` (`ok`, `detail`). Logging is best-effort and never fails the
  write it logs; an id that isn't a safe directory name isn't logged, and
  nothing is logged in a git vault whose `.gitignore` lacks `.claudron/` (sync
  would otherwise commit the logs; `doctor --fix` adds the rule). Each of
  `runs/` and `sessions/` keeps the 200 logs most recently appended to; pruning
  removes only a log and the directory it leaves empty. Gate on
  `"ops-log" in status --json → data.capabilities`.
- **Runs** (#200 §4): `capture`, `capture --update` and `amend` take
  `--run-id ID` (or a `run_id` key on stdin). The write is committed at once,
  like any write (§Write guarantees), and its commit message ends
  `Claudron-Run: ID`. An ID is 1–64 letters, digits, `.`, `_` or `-`, starting
  with a letter or digit; a bad one, or `--run-id` with `--no-commit`, exits 2
  before anything is written.
  - `revert-run ID` reverts **every** commit carrying the trailer that isn't
    reverted yet, newest first, as **one** commit
    (`revert-run(<actor>): ID`, with a `This reverts commit <sha>.` line per
    commit). If any of them conflicts with later edits, **none** is reverted:
    exit 1, tree and index as they were. A run with no commits, a wedged tree,
    or a plain-directory vault also exits 1. Reverting twice → `unchanged`.
  - `--json` `data` is `{run_id, action, commits, revert, reason}`, `action` ∈
    `{reverted, unchanged}`.
  - Gate on `"runs" in status --json → data.capabilities`.
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
    and `--source-type {url,file,inline,session}` (equally, the `source_url` /
    `source_type` keys of the `--stdin` JSON) write the SCHEMA.md optional
    fields of the same names. Both are omitted from the note when unset.
    `source_type` accepts only SCHEMA.md's vocabulary **on both spellings** —
    the flag and the `--stdin` key alike; anything else is a usage error
    (exit 2). **A consumer must not fold provenance into a body
    line** — the first substantive body line is what the recall brief shows as
    a note's summary, so a `Source:` line there both spends the summary and
    couples the consumer to how that summary is picked.
  - **`tags` takes one grammar on both spellings.** The `--tags` flag and the
    `tags` key of the `--stdin` JSON normalize identically: a string is
    comma-separated (split, whitespace-stripped, empty segments dropped); a
    JSON array is taken element-wise. A bare scalar is one tag — never a
    character sequence.
  - **Programmatic writers MUST pass content via `--stdin` JSON, never `--body`
    string interpolation.** Note bodies are free text (quotes, newlines,
    `$(...)`, backticks); building a `--body "…"` shell argument truncates the
    note or executes substitutions in the caller's shell before `claudron` runs.
    `--stdin` carries arbitrary content safely.
- `init --adopt` — additionally backfills missing `updated` from file mtime
  (the one sanctioned mutation, at adoption time only).
