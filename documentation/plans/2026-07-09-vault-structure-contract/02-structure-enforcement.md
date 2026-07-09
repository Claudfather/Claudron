---
title: "P2 — Structure enforcement in validate/init (audit-only + --fix)"
type: plan
status: draft
owner: chris
tags: [plan, vault, structure, validate, cli, claudron]
created: 2026-07-09
updated: 2026-07-09
---

# P2 — Structure enforcement in `validate` / `init`

## Summary

Give `claudron validate` a **directory-structure lens** to sit beside its
existing frontmatter lens. Today `validate` only rglobs `*.md` and lints
frontmatter — it never checks the *directory contract*. This phase adds
structure checks that report drift as warnings and **exit non-zero without
mutating** (Fork F2), plus an opt-in `--fix` that **creates missing expected
dirs only** (never moves or deletes). `init` is extended to scaffold exactly the
shape VAULT-STRUCTURE.md (P1) documents.

## Evidence (current state this changes)

- **`validate` is frontmatter-only.** It lints notes; it has no notion of the
  directory contract. `is_conventions()` is the closest thing — a `parent.name
  in ("_shared", "shared")` check for a CONVENTIONS budget rule
  (`schema.py:522`) — but nothing validates the *tree*.
- **The shape is enforced only implicitly**, by `_scan_vault` treating unknown
  root dirs as `other:` (`vault.py:163-184`) and by `init`/`fleet add`
  scaffolding (`vault.py:217,221`; `cli.py:726-749`). Drift (a fleet missing
  `shared/`, a stray note at root, a fleet named `projects`) is silent.
- **The hub name is a hardcoded constant** (`SHARED_MARKERS`, `vault.py:41`;
  `SKIP_DIRS`, `vault.py:37-39`) but **consumers go through the `Vault.shared`
  abstraction** — so the structure check keys off `Vault`/`SKIP_DIRS`, never a
  fresh literal.

## Implementation Plan

### Dependencies

- **P1** — the contract must be written before it can be enforced. The check's
  reserved-name set and expected per-fleet shape derive from what P1 documents
  (and, mechanically, from `SKIP_DIRS`).

### Blocks

- Claudlobby sibling issue #1 (overlay conformance) — Claudlobby runs `validate`
  to confirm its `local/` conforms.
- The crog-eng-team dogfood (#4) — `init --adopt` + `validate` is the adoption
  path.

### Steps

1. **Add `claudron/structure.py`** — a pure, read-only checker
   `check_structure(vault: Vault) -> list[StructureFinding]`. Findings, each
   with a code + severity + path:
   - `S1` (warn) — no `_shared/`/`shared/` at root (vault marker absent).
   - `S2` (warn) — a fleet dir (has `fleet.yaml`) lacks `shared/`.
   - `S3` (error) — a top-level dir collides with a reserved name **and** carries
     a `fleet.yaml` (a fleet trying to take `projects`/`_shared`/`shared`).
     Reserved set = `SKIP_DIRS` (imported, not re-listed).
   - `S4` (warn) — an unrecognized top-level dir (not a fleet, not in
     `SKIP_DIRS`, not `projects/<repo>`) → reported as `other:`, **never an
     error** (extensibility escape hatch).
   - `S5` (warn) — VAULT-STRUCTURE.md and SCHEMA.md do not both exist and
     cross-reference each other (the two-SSOT drift guard from F3).
2. **Wire into `cmd_validate`** (`cli.py`): run `check_structure` after the
   frontmatter pass; print findings in the same report; **exit non-zero if any
   finding fires**; **never mutate** on the default path.
3. **Add `--fix` (opt-in, conservative).** Repairs **only** creation-safe
   findings: `S1` scaffold the hub (reuse `init`'s `scaffold_shared_tree`), `S2`
   create the missing `<fleet>/shared/` tree. `--fix` **never moves or deletes**
   — a stray note (a plausible `S4`) is reported with a suggested destination,
   not relocated. Print each action taken; re-run the check and exit 0 only if
   clean.
4. **Extend `init`** to scaffold the full documented shape (it already does
   `_shared/` + `CONVENTIONS.md`; ensure a fresh vault also validates clean —
   `init` then `validate` is a no-op).
5. **Reserved-name single-source guarantee:** `structure.py` imports `SKIP_DIRS`
   from `vault.py`; a test asserts no second hardcoded reserved list exists.

### New-file skeleton (`claudron/structure.py`)

```python
"""Directory-structure checks for a vault (the VAULT-STRUCTURE.md contract).

Read-only by default; the CLI's --fix path performs creation-only repairs.
Reserved names come from vault.SKIP_DIRS — never re-listed here.
"""
from dataclasses import dataclass
from .vault import Vault, SKIP_DIRS

@dataclass(frozen=True)
class StructureFinding:
    code: str        # S1..S5
    severity: str    # "warn" | "error"
    path: str
    message: str
    fixable: bool    # True only for creation-safe repairs (S1, S2)

def check_structure(vault: Vault) -> list[StructureFinding]:
    ...  # returns [] for a conforming vault
```

## Test Plan

Unit tests (`tests/test_structure.py`), each a tmp vault:
- Conforming vault → `check_structure` returns `[]`; `validate` exits 0.
- Fleet missing `shared/` → `S2` warn; `validate` exits 1; **`git status`
  clean afterward** (no mutation); `validate --fix` creates it, exits 0.
- Stray root dir → `S4` warn, `validate` exits 1, but **not** an error code and
  **not** touched by `--fix`.
- Dir named `projects/` with a `fleet.yaml` → `S3` error.
- Missing/one-way SCHEMA↔VAULT-STRUCTURE cross-link → `S5`.
- Reserved-name single-source: a test greps that `SKIP_DIRS` is the only
  reserved-name definition consumed by the checker.
- Golden: `check_structure` on the reference vault returns `[]`.

## Verification Checklist

- [ ] `claudron validate` on a drifted vault exits non-zero **and leaves the
      repo byte-identical** (`git status` clean).
- [ ] `claudron validate --fix` creates missing `shared/`/hub dirs and exits 0.
- [ ] No code path in `validate`/`--fix` moves or deletes an existing file.
- [ ] `claudron init && claudron validate` on a fresh vault is a clean no-op.
- [ ] `structure.py` imports `SKIP_DIRS`; no second reserved list (test-asserted).

## What NOT To Do

- `--fix` must **not** move or delete — creation-only. Relocating a stray note
  is a suggestion, never an action (F2).
- No auto-repair on the default `validate` path (F2).
- No fresh reserved-name literal — derive from `SKIP_DIRS`.
- Don't rename `_shared/` (F5) or touch promotion (E5).

## Context

Area: `claudron/` CLI + new `structure.py` · Effort: **M** · Risk: medium — it
introduces a mutation path (`--fix`), contained by creation-only scope + the
"repo unchanged on default path" test · Priority: **high** — the enforcing half
of the contract; Claudlobby conformance depends on it.
