# Integrating any agent with Claudron

Canonical URL:
<https://github.com/Claudfather/Claudron/blob/main/docs/INTEGRATION.md>

Claudron is a knowledge engine over a directory of markdown files with YAML
frontmatter, kept in git. It answers two questions for an agent: *what does this
team already know about X* (**query-before**) and *how do I durably record what I
just learned* (**write-after**). The interface is a CLI with a typed `--json`
envelope — **any agent that can run a subprocess and parse JSON can consume the
hub.** There is no SDK to adopt, no daemon to run, no server to speak to, and no
requirement that you use Claude Code or any particular plugin.

This document is the front door for that integration. It is deliberately
**vendor-neutral**: nothing here names a specific agent, harness, or plugin as a
prerequisite. The normative surface it points at is
[`CLI_CONTRACT.md`](CLI_CONTRACT.md); this doc is under that contract's change
discipline (breaking changes get CHANGELOG entries), and where the two disagree,
`CLI_CONTRACT.md` wins.

---

## Get the CLI

Claudron is not on PyPI. The supported channels are a git checkout or a
pip-install straight from the repository. Python **≥ 3.10**; the only runtime
dependency is PyYAML.

```bash
# A pinned tag (recommended for anything reproducible)
pip install 'git+https://github.com/Claudfather/Claudron.git@<tag>'

# Or a working checkout
git clone https://github.com/Claudfather/Claudron.git
pip install -e ./Claudron
```

Both install a `claudron` entry point on `PATH`. Pin a tag for anything
reproducible — `@main` tracks head and will move under you.

**Minimum version: `0.3.0`** for everything described here — that release
introduced the capability probe (`engine_version`) and removed the
`CLAUDRON_VAULT` environment name. Confirm what you actually got by probing
(next section) rather than trusting the pin. A consumer that must also support
`0.2.x` should read [§Environment](CLI_CONTRACT.md#environment) first: on those
versions there is no `engine_version` field and both environment names are read.

---

## Step 0 — detect the engine

**Probe once, at startup, and branch. Never assume.** The probe is a single
command whose envelope you already know how to parse:

```bash
claudron status --json
```

Three outcomes, and exactly what each entitles you to assume. **Branch on the
exit code, never on message text** — exit codes are contract
([§Exit codes](CLI_CONTRACT.md#exit-codes)); the wording on stderr is not.

| State | How you observe it | What you may assume |
|---|---|---|
| **No CLI installed** | The process fails to start: `ENOENT` from `exec`, or shell exit **127**. Nothing on stdout. | No engine. Fall back to whatever you do without one — do not synthesize a vault path, and do not surface this as an error on every invocation. |
| **CLI present, no vault** | Exit **3**, stdout empty, an explanation on stderr. | The engine exists but has no address. Either resolve a vault (below) or degrade. A configuration state, not a failure of the engine. |
| **Engine ready** | Exit **0**, one JSON envelope on stdout with `ok: true`. | `data.engine_version` is the installed engine's version and `data.root` is the resolved vault. Guard any feature you need on the version. |

```bash
# A probe that distinguishes all three states
out=$(claudron status --json 2>/dev/null); rc=$?
case $rc in
  0)   # engine ready — `engine_version` is absent before 0.3.0, so default it
       read -r version root <<<"$(printf '%s' "$out" | python3 -c '
import json,sys
d = json.load(sys.stdin)["data"]
print(d.get("engine_version", "0.0.0"), d["root"])')" ;;
  3)   echo "claudron installed, no vault resolvable" >&2 ;;
  127) echo "no claudron on PATH" >&2 ;;
esac
```

Two details that bite: `engine_version` **does not exist before 0.3.0**, so
index it defensively or a pre-0.3.0 engine crashes your probe instead of
reporting its version; and the `2>/dev/null` above discards stderr, which is
where the engine explains an exit 3 — drop the redirect while debugging.

`engine_version` and the rest of the stable `status --json` field set are
documented in [CLI_CONTRACT.md §Capability probe](CLI_CONTRACT.md#capability-probe).
Read the engine's version from this probe and nowhere else — not from an
installed package pin, not from a plugin manifest. A pin governs what you
*import*; the probe reports what will actually *run*.

### `status --json` is a CAPABILITY probe, not a HEALTH probe

Use it to learn what the engine can do. Do **not** use it to ask whether a
vault clone is healthy, for two reasons that both bite in production: it walks
every note in the tree, and it rebuilds and **writes** the index on its way to
an answer. On a large vault that is slow enough to be an outage of its own, and
on a wedged or read-only clone it cannot answer at all — which is exactly when
you most need it to.

Ask `sync --check` instead. It is bounded, read-only, and offline by default:

```bash
claudron sync --check --json
```

```json
{
  "ok": true,
  "command": "sync",
  "data": {
    "check": true,
    "state": "clean",
    "branch": "main",
    "default_branch": "main",
    "upstream": "origin/main",
    "ahead": 0, "behind": 0,
    "uncommitted": 0, "uncommitted_oldest_age_s": null,
    "lock_age_s": null, "interrupted": null,
    "last_sync_ok_at": "2026-09-22T17:04:11+00:00",
    "detail": ""
  }
}
```

**Key on `state`.** The full vocabulary, in the precedence the engine applies:

| state | what it means for you |
|---|---|
| `clean` | on the default branch, in sync, nothing uncommitted |
| `ahead` / `behind` / `divergent` | local and remote have drifted; `ahead`/`behind` carry the counts |
| `dirty` | uncommitted files; `uncommitted_oldest_age_s` says how long they have sat |
| `side-branch` | the clone is not on its default branch. Work here reaches no other machine |
| `detached` | HEAD is on no branch at all |
| `rebase-conflict` | a rebase stopped on a conflict. **A human's work in progress — do not repair it** |
| `rebase-killed` | a rebase was killed mid-replay. `claudron sync` cleans this up |
| `merge` | a merge is in progress |
| `stale-lock` | an `index.lock` older than ten minutes: every write in the vault is failing |
| `unreachable` | the remote could not be contacted (only ever returned with `--reach`) |
| `unknown` | **the check could not run.** Never read this as healthy |

Three contract points worth building against:

- **Every verdict exits 0**, including the bad ones. The exit code tells you
  whether the *check ran*; `state` tells you whether the *clone is healthy*.
  Reserve nonzero for 2 (usage) and 3 (no vault, or not a git repository).
- **`unknown` is not `clean`.** It means git was missing or a call timed out,
  so nothing was determined. Treating it as healthy rebuilds the silence this
  door exists to end: a stopped rebase once read as healthy to every probe for
  twelve days.
- **`--reach` is opt-in.** Without it no network call happens, so a watchdog
  polling this is never gated on the remote being up. `unreachable` can only
  appear when you asked for it.

`last_sync_ok_at` is the denominator for "when did this clone last actually
sync": `sync` records every attempt, and `--check` only ever reads it. It is
`null` on a clone that has never synced under a version that writes it — which
is a different fact from a clone that is failing, so do not collapse them.

---

### Gate a feature on `capabilities`, never on the version

To ask "does this engine have the door I need", read the declaration:

```bash
claudron status --json | jq '.data.capabilities'
# ["navigation"]
```

```python
caps = data.get("capabilities", [])          # absent on older engines
if "navigation" in caps:
    ...                                       # call the door
```

That is the whole gate. It is a **declaration** — register rule R5, *capability
is declared to the owner, never inferred* — and it is absent on an engine that
predates the list, which is the correct answer for every name in it.

**Do not infer it from `engine_version`.** That field answers *"is an engine
here, and which one?"*, not *"can it do X"*. All three of the obvious
inferences were measured and all three fail:

- **A version floor cannot be expressed.** `engine_version` is `0.5.0.dev0` on a
  build of the branch that ships a feature and `0.4.0` on the last release. PEP
  440 sorts a dev release *before* its release, so `0.5.0.dev0 < 0.5.0` — a
  `>= 0.5.0` floor is satisfied by **neither** and can never pass.
- **A verb probe cannot see a flag.** `claudron <verb> --help` does exit 2 on an
  unknown verb, but `index` has been a verb far longer than `--navigation`.
- **A flag probe cannot fail.** `claudron index --navigation --help` exits **0**
  on an engine with no such flag, because argparse fires `--help` as a parse
  action and exits before reporting unknown arguments. The control: the same
  engine exits 2 for `index --navigation` *without* `--help`.

---

## Hello world

Copy-paste, end to end. It creates a throwaway vault, writes one note through
the engine, and proves recall serves it back.

```bash
# 1. Create a scratch vault
claudron init /tmp/scratch-vault
export CLAUDRON_VAULT_PATH=/tmp/scratch-vault

# 2. Confirm the engine sees it
claudron status --json

# 3. Write a note through the door (JSON on stdin — never string-interpolated)
echo '{"type":"knowledge","title":"Hello Claudron","body":"The engine round-trips a capture into recall.","tags":["hello"]}' \
  | claudron capture --stdin --json

# 4. Read it back as an injectable brief
claudron recall --query hello
```

Step 3 prints `"action": "created"` and `"written": true`. Step 4 prints the
vault's conventions, the note you just wrote, and a one-line pointer back at the
two doors. Delete `/tmp/scratch-vault` when you are done — nothing outside it was
touched.

If step 2 exits 3, the vault address did not reach the engine; see the next
section.

---

## Resolve a vault

One table governs this, and it lives in the contract:
**[CLI_CONTRACT.md §Environment](CLI_CONTRACT.md#environment)**. The short form:

1. `--vault PATH` — explicit, wins over everything.
2. `CLAUDRON_VAULT_PATH` — the canonical environment name. Set this.
3. Walk up from the working directory for a `_shared/` marker.

Emit and read **only** `CLAUDRON_VAULT_PATH`. Do not invent additional names; a
new address source is a change to that table, PR'd against this repository
first. If your integration keeps a per-checkout pointer file, see
[§Bridge file](CLI_CONTRACT.md#bridge-file) — but note the engine never resolves
its own vault from one: read it yourself and pass `--vault`.

---

## Query before you work

Two verbs, two shapes. Both exit 0 on "nothing matched" — an empty result is an
answer, not an error.

```bash
# The session brief: conventions + ranked notes, ready to inject as context
claudron recall --project my-repo --query "connection pooling"

# Structured search, for when you want to rank or filter yourself
claudron lookup --json "connection pooling"
```

- **`recall`** emits markdown on stdout, budget-capped, intended to be injected
  verbatim into an agent's context. It **abstains**: a weak match injects
  nothing rather than padding the brief with noise. A vault with no matching
  notes still emits its `CONVENTIONS.md` block if it has one — treat "empty
  stdout" as the only reliable no-content signal, not "no output at all".
- **`lookup --json`** emits the standard envelope with `data.results`. Use this
  when you need scores, paths, or your own ranking.
- **Never parse human output.** Every command's human rendering is free to
  change; the `--json` envelope is the contract.
- **stdout is payload only.** Every diagnostic goes to stderr — that rule exists
  precisely so a consumer can pipe stdout into a context window without
  sanitizing it.

---

## Write after you learn

All writes go through one door.

```bash
echo '{"type":"knowledge","title":"Neon pool exhaustion","body":"…","tags":["neon"],"project":"my-repo"}' \
  | claudron capture --stdin --json
```

Three rules, each of which has bitten a real consumer. The normative statement
of all three is
[CLI_CONTRACT.md §capture](CLI_CONTRACT.md#command-specific-contracts) — read it
once; what follows is orientation, not a second copy.

1. **Pass content via `--stdin` JSON, never `--body` string interpolation.**
   Note bodies are free text, so a `--body "…"` argument is a shell-injection
   and truncation hazard in *your* process, before `claudron` ever starts.
2. **Branch on `written`, not on the exit code.** Dedup routes rather than
   rejecting, so a command can succeed having written nothing. A consumer that
   reads exit 0 as "captured" silently drops the finding.
3. **Handle the suggestion, don't retry blindly.** When the result is a dedup
   route, `data.path` names the existing note and `data.reason` says why — pick
   `--update` or `--force` deliberately.

The `action` vocabulary, which values set `written`, and which one exits 1 are
all in §capture. Do not hard-code the list from memory.

What the engine promises about durability across machines — per-host
serialization, cross-host eventual consistency with conflict quarantine, and
what is explicitly *not* guaranteed — is
[CLI_CONTRACT.md §Write guarantees](CLI_CONTRACT.md#write-guarantees). Read it
before you design a multi-writer topology.

### Never hand-append to `INDEX.md` — call the door

From engine **0.5.0**, each directory's `INDEX.md` is **derived from the index**,
not hand-maintained ([#155](https://github.com/Claudfather/Claudron/issues/155)).
A front-end that appends a line to it is writing into a file the next
regeneration rewrites, and — before that — into the single most conflict-prone
file in the vault: six of the nine merge conflicts in the 2026-09-21 repair were
`INDEX.md`, and the same entry carried different description text in different
versions, so no line-based merge could resolve them.

```bash
claudron index --navigation          # regenerate every directory's INDEX.md
```

`capture` will do it for the directory it wrote to once #155 PR 2 lands; until
then, call the door after a write. Running it twice changes nothing.

It is not a blanket overwrite, so you do not lose hand-written pointers: an
entry the index does not know about is **preserved** verbatim under a marked
section when its target exists, and **dropped** when the target does not (it
navigates nowhere). A description is likewise never deleted just because the
note has none: the note's frontmatter wins where it exists, and otherwise the
description already in the file is **carried**. All three are reported on every
run — in `--json` under `navigation_preserved` / `navigation_dropped` /
`navigation_carried`, and in the bound printed to stderr in plain mode. Do not
parse the stderr bound; branch on the JSON.

---

## Session loop

If your host has session lifecycle events, the engine ships adapters that pull
before recalling and push at session end. `claudron hooks install --write` is
the supported wiring; `claudron hook <event>` is what the host then invokes.
They fail open by design: a broken vault, a missing git binary, or a network
stall must never break a session start.

The normative protocol is
**[CLI_CONTRACT.md §Session-loop protocol](CLI_CONTRACT.md#session-loop-protocol)** —
the four roles and who owns each, the pull-before-recall ordering, the budgets,
the hook-settings shape, and the fail-open contract. Read it before you install
these hooks beside anything else that touches the same events. Two obligations
bind an integration that ships its **own** capture prompt:

- **One capture prompt per session.** If you emit your own distill nudge at
  compaction, you must defer when the engine's `pre-compact` entry is
  registered — detected by a hook command ending in `hook pre-compact` in the
  host's settings files. Both prompting is a defect; the protocol section
  specifies the detection exactly. The engine now prompts unconditionally where
  its hook is installed (the earlier R5 shim that yielded to a detected
  front-end was removed in #85), so a front-end's defer keys on that
  shim-removal engine release: ship your defer at or after it. Deferring against
  an older engine that still carries the shim means both sides yield and
  *nobody* prompts — the ordering rationale is in the engine CHANGELOG
  (`Removed`).
- **Composed hook entries are a rendered copy.** If you generate the settings
  block yourself instead of running `hooks install`, gate it against the shape
  in that section (register rule R3) — a drifted copy silently runs stale hooks
  on every host you compose.
- **A capture is durable when it returns; you do not need to run `sync` for a
  note to exist in history.** The write door commits the note it wrote, inside
  the lock it already holds (`capture(<actor>): <title>`). Before this, the note
  existed on one disk until something else ran — on one host that window was
  twelve days and 62 paths.

  Two consequences for an integration. **`ok` does not mean committed**: if the
  commit fails (a wedged tree, a rejecting hook) the note is still on disk, the
  result stays `ok`, and a `W108` rides the envelope's `warnings` array — never
  `errors`, because nothing about the write failed. **Do not retry a write on a
  W108**; the note is there and the next `sync` commits it. And a vault that is
  not a git repository is silent: no commit, no warning.

  `--no-commit` exists for a caller batching several captures and committing
  them itself. It is an escape hatch, not a default: it restores the window.

- **A hook never rewrites history, and never syncs a side branch.** SessionStart
  fetches and `merge --ff-only`; it does not commit and does not rebase. If you
  install your own SessionStart pull, it must be `claudron sync --ff-only` (or
  the equivalent), **not** `claudron sync` and not `git pull --rebase`.

  The reason is a budget mismatch rather than a preference. A session-start pull
  runs on a latency budget — the engine's is 2 s — and a budget that is right
  for latency is wrong for a history rewrite: the only two outcomes of a 2 s
  rebase on a busy host are *nothing to do* and *killed part-way*, and a killed
  replay detaches HEAD and leaves commits reachable from no branch. On the host
  that produced this rule, one pick completed and 58 stayed pending, and the
  tree sat detached for six hours. SessionStart is not rare: hosts fire it on
  startup, resume, clear **and compaction**, so a long-running agent was
  rewriting its own vault tree at an unpredictable moment mid-session.

  `fetch` writes only under `.git/` and `merge --ff-only` is a single
  ref-and-tree update, so the same 2 s budget is honest for them: killing either
  one leaves the working tree as it was.

  **A clone that cannot fast-forward is left alone, and that is the contract,
  not a degradation.** `sync --ff-only` reports `ok` with a `local_ahead` count;
  it does not rebase to resolve the divergence. Something scheduled has to do
  that — `claudron sync` (which does rebase) from a job with an honest budget.
  **If your integration ships no such scheduled reconciliation, a divergent
  clone stays `ahead` indefinitely.** That state is safe and it is *visible*
  (`claudron sync --check --json` reports it), which is why it is the right
  default — but it is not self-resolving, and an integration that never
  reconciles will accumulate divergence. Say so to your operators, and give them
  a way to see it.

---

## Conformance checklist

An integration is conformant when every one of these is true. Each is stated so
it can be checked without reading another document.

- [ ] The integration probes for the engine by running `claudron status --json`
      and branching on its three outcomes (missing binary / exit 3 / exit 0),
      rather than assuming an engine is present.
- [ ] The engine's version is read from `data.engine_version` in that probe's
      output, and any version-dependent behavior is guarded on it — never on an
      installed package pin or a plugin manifest.
- [ ] The vault address is passed as `--vault PATH` or exported as
      `CLAUDRON_VAULT_PATH`, and no other environment variable name is emitted
      or read for it.
- [ ] Structured data is taken from `--json` output only; no code path parses
      the human-readable rendering of any command.
- [ ] Note content is passed to `capture` as JSON on stdin; no code path builds
      a `--body` argument by interpolating text into a shell command.
- [ ] After a capture, the integration branches on the `written` field (or
      equivalently on `action`) to decide whether a note landed — never on the
      process exit code alone.
- [ ] A `suggest_update` or `suggest_supersede` result is surfaced or acted on
      deliberately; it is never discarded as a no-op success.
- [ ] Exit code 3 is handled as "no vault resolvable" — a configuration state
      the integration can report or degrade from — and is distinguished from
      exit 1 (findings) and exit 2 (bad arguments).
- [ ] If the integration emits its own capture prompt at compaction, it emits
      nothing when a hook command ending in `hook pre-compact` is already
      registered in the host's settings — exactly one capture prompt reaches a
      session. An integration with no prompt of its own has nothing to do here.
- [ ] The integration does not write into the vault directly with its own file
      operations; every note it creates goes through `claudron capture`.
- [ ] The integration does not fork, restate, or paraphrase any contract text as
      its own normative rule; it links to `CLI_CONTRACT.md`, or renders a copy
      with an automated drift check against it.
- [ ] A change the integration needs in any of the above is proposed as a pull
      request against this repository before it is implemented downstream.

*(For readers tracing the boundary spec: these correspond to register rules
R3–R7 and contracts #3, #4 and #6 in
`documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.4. The
checklist stands on its own; the cross-reference is for provenance.)*

---

## Where to go next

| You want… | Read |
|---|---|
| Exit codes, channels, the `--json` envelope, per-command contracts | [`CLI_CONTRACT.md`](CLI_CONTRACT.md) |
| What a valid note looks like — types, required fields, status vocabularies | [`../SCHEMA.md`](../SCHEMA.md) |
| The vault's directory contract and tenancy model | [`../VAULT-STRUCTURE.md`](../VAULT-STRUCTURE.md) |
