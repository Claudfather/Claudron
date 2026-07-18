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
  breakdown; `new` → `{"path": "…"}`; `status` → the health dict; `lookup` →
  `{query, results}`.
- `ok` is `errors == []` (warnings don't flip it).

> Breaking change at 0.2.0: `status --json`, `lookup --json`, and
> `config --json` previously emitted three ad-hoc shapes; all now emit the
> envelope (their old payloads live under `data`).

## Flags

- `--vault PATH` and `--json` are accepted by every subcommand (implemented
  via a shared parent parser — `claudron status --json` parses).
- Vault resolution order: `--vault` → `$CLAUDRON_VAULT_PATH` →
  `$CLAUDRON_VAULT` → walk up from CWD.
- Scoping: `--project NAME` / `--fleet NAME` where meaningful; they are
  mutually exclusive wherever both exist.

## Command groups (`--help` taxonomy)

| Group | Commands |
|---|---|
| vault | `init`, `status`, `validate`, `index` |
| notes | `new`, `lookup` |
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
