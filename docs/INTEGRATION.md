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
`0.2.x` should read [§Environment](CLI_CONTRACT.md#environment)'s migration note
first: on those versions there is no `engine_version` field and both
environment names are read.

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
  specifies the detection exactly.
- **Composed hook entries are a rendered copy.** If you generate the settings
  block yourself instead of running `hooks install`, gate it against the shape
  in that section (register rule R3) — a drifted copy silently runs stale hooks
  on every host you compose.

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
