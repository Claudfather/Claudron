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

Three outcomes, and exactly what each entitles you to assume:

| State | How you observe it | What you may assume |
|---|---|---|
| **No CLI installed** | The process fails to start: `ENOENT` from `exec`, or shell exit **127** ("command not found"). Nothing is written to stdout. | No engine. Fall back to whatever you do without one — do not synthesize a vault path, and do not treat this as an error condition worth surfacing on every invocation. |
| **CLI present, no vault** | Exit **3**, stderr carries `no vault found`, stdout is empty. | The engine exists but has no address. Either resolve a vault (below) or degrade. This is a configuration state, not a failure of the engine. |
| **Engine ready** | Exit **0**, one JSON envelope on stdout with `ok: true`. | `data.engine_version` is the installed engine's version, and `data.root` is the absolute path of the resolved vault. Guard any feature you need on the version. |

```bash
# A complete probe, in four lines of shell
if out=$(claudron status --json 2>/dev/null); then
  version=$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["engine_version"])')
  root=$(printf '%s' "$out" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["root"])')
fi
```

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
  nothing rather than padding the brief with noise. An empty vault produces
  empty stdout.
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

Three rules, each of which has bitten a real consumer:

1. **Pass content via `--stdin` JSON, never `--body` string interpolation.**
   Note bodies are free text — quotes, newlines, backticks, `$(...)`. Building a
   `--body "…"` shell argument truncates the note or executes substitutions in
   *your* shell before `claudron` ever runs.
2. **Branch on `written`, not on the exit code.** Dedup *routes*, it does not
   reject: a near-duplicate returns `action: "suggest_update"` or
   `"suggest_supersede"` with **exit 0** and **`ok: true`** having written
   nothing. A consumer that treats exit 0 as "captured" silently drops the
   finding. `written` is `true` only for `created` and `updated`.
3. **Handle the suggestion, don't retry blindly.** On a `suggest_*` action,
   `data.path` names the existing note and `data.reason` says why. Append to it
   with `capture --update`, or force a new note with `--force` — as a deliberate
   choice, not a reflex.

`action: "rejected"` (validation failure) is the only write outcome that exits
1; its `errors` array carries the specific findings.

What the engine promises about durability across machines — per-host
serialization, cross-host eventual consistency with conflict quarantine, and
what is explicitly *not* guaranteed — is
[CLI_CONTRACT.md §Write guarantees](CLI_CONTRACT.md#write-guarantees). Read it
before you design a multi-writer topology.

---

## Session loop

If your host has session lifecycle events, the engine ships adapters that pull
before recalling and push at session end (`claudron hooks install`,
`claudron hook <event>`). They fail open by design: a broken vault, a missing
git binary, or a network stall must never break a session start.

The normative protocol — the roles, their ordering, and which participant owns
the capture prompt when several are installed — lands as a session-loop section
of `CLI_CONTRACT.md` (boundary program phase C2). Until then, treat
`claudron hooks install --write` as the supported wiring and read the adapters'
docstrings for current behavior.

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
