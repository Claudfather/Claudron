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

Give `claudron validate` a **directory-structure lens** beside its existing
frontmatter lens (today it only rglobs `*.md` and lints frontmatter —
`schema.py:506`, `cli.py:598-637`). Structure findings flow through Claudron's
**existing** `error`/`warning` severity model, so they honor the CLI contract
(`docs/CLI_CONTRACT.md:11` — *"warnings do not change the exit code,"* `--strict`
gates warnings, `:16`): **errors gate exit; warnings gate only under `--strict`**.
An opt-in `--fix` performs **creation-only** repairs inside a hard containment
boundary — never moves, deletes, or escapes the vault root. `init` scaffolds
exactly the shape VAULT-STRUCTURE.md (P1) documents.

## Evidence (current state this changes)

- **`validate` is frontmatter-only.** `validate_path` rglobs `*.md` and lints
  frontmatter (`schema.py:506`, `cli.py:598-637`); no tree-shape check.
  `is_conventions()` (`schema.py:522`) is the closest thing, and it's a
  CONVENTIONS budget rule, not a structure check.
- **The exit-code contract is normative.** `validate` returns `1 if errors else
  0` (`cli.py:637`); `docs/CLI_CONTRACT.md:11` guarantees warnings don't change
  the exit code, and `:16` names `--strict` as the sanctioned warning-gate.
  Structure findings must obey this, not invent a third rule.
- **A `Finding` type + `--json` envelope already exist** (`schema.py`;
  `cli.py:42-55`), with `severity ∈ {error, warning}`, `.line`, `.to_dict()`.
  Reuse it — a divergent shape (`severity:"warn"`, no `.line`/`.to_dict()`)
  vanishes from `--json` and throws `AttributeError` in the report path.
- **Drift is silent only on the hand-created/adopted vector.** `_scan_vault`
  tolerates unknown dirs (`vault.py:163-184`; the `other:` tag itself is applied
  by the index in `knowledge.py`, not `_scan_vault`); `init`/`fleet add` scaffold
  (`vault.py:217,221`; `cli.py:726-749`). But `fleet add` **already**
  rejects reserved names (`_RESERVED_FLEET_NAMES = SKIP_DIRS`, `cli.py:723,
  730-735`), so the enforcement gap is only the non-`fleet add` path.
- **Reserved names are a *subset* of `SKIP_DIRS`.** The constant
  (`vault.py:37-39`) holds 7 entries incl. infra (`.git`, `__pycache__`); the
  *user-facing* reserved names are `_shared`/`shared`/`projects`. Derive the
  subset; never re-list.
- **Hub name hardcoded, but consumers use `Vault.shared`** — so the check keys
  off `Vault`/`SKIP_DIRS`, never a fresh literal.

## Implementation Plan

### Dependencies

- **P1** — the contract must be written before it can be enforced; the check's
  reserved subset and expected per-fleet shape derive from what P1 documents
  (and, mechanically, from `SKIP_DIRS`).

### Blocks

- Claudlobby sibling issue #1 (overlay conformance) — Claudlobby runs `validate`
  to confirm its `local/` conforms.
- The pilot-fleet dogfood (#4).

### Steps

1. **Add `claudron/structure.py`** — a pure, read-only
   `check_structure(vault: Vault) -> list[Finding]` **reusing `schema.Finding`**
   (add an additive `fixable: bool` and a `code` per its docstring's
   additive-field allowance; do **not** fork the class). Findings use the
   existing `error`/`warning` vocabulary:
   - `S1` (**warning**, fixable) — a fleet dir (has `fleet.yaml`) lacks `shared/`.
   - `S2` (**error**) — a **hand-created/adopted** top-level dir collides with a
     reserved name and carries a `fleet.yaml`. Must **raw-walk** the root, not
     iterate `vault.fleets` (which pre-filters reserved names out, `vault.py:180`);
     this is the audit-time backstop for the vector `fleet add` already guards.
   - `S3` (**warning**) — an unrecognized top-level dir (not a fleet, not in
     `SKIP_DIRS`, not `projects/<repo>`): the `other:` extensibility hatch. A
     warning, so a deliberately-extended vault (`vault/experiments/`) never
     red-fails the default `validate`.
   - `S4` (**warning**) — **both** `_shared/` and `shared/` present:
     `_scan_vault` prefers `_shared` (`vault.py:165`) and the index skips
     `shared` as a SKIP_DIR (`knowledge.py:207-210`), silently dropping the
     non-preferred tree. A data-loss hazard nothing else catches.

   Two checks are deliberately **not** here: the "no vault marker" case (a
   `Vault` can't exist without the marker — `vault.py:154-159` — so `validate`
   already errors upstream on a markerless dir), and the SCHEMA↔VAULT-STRUCTURE
   cross-link drift-guard (F3), which is a **Claudron repo test**, since those
   docs never live inside a vault (they'd false-positive on every real vault and
   break `init && validate`).
2. **Wire into `cmd_validate`** (`cli.py`): run `check_structure` after the
   frontmatter pass; findings flow through the **same** report + `--json`
   envelope; exit code = **1 iff any error fires** (structure or frontmatter),
   **warnings gate only under the existing `--strict`**. Never mutate on the
   default path. When fixable findings are present, print a stderr footer naming
   them and the exact `--fix` command (no silent switch).
3. **Add `--fix` (opt-in, creation-only, contained).** Repairs only
   creation-safe findings (`S1` → create `<fleet>/shared/`; hub scaffolding
   stays in `init`). Hard guards: every target path must be
   `is_relative_to(vault.root)` (mirror `resolve_target_dir`, `engine.py:152`),
   reject symlinked path components (no escape), pin `exist_ok=True`, and be
   idempotent (re-run = no-op). Print each action; re-run the check and exit 0
   only if clean. **Never moves or deletes** — a stray dir/note is reported with
   a suggested destination, never relocated. Register `--fix` in `--help` and
   fix its help string, which currently promises "never mutates" (`cli.py:923`);
   sync `docs/CLI_CONTRACT.md` + CHANGELOG.
4. **Extend `init`** to scaffold the full documented shape (it already does
   `_shared/` + `CONVENTIONS.md`; ensure `init` then `validate` is a clean
   no-op) and print a next-step pointer.
5. **Reserved-name single-source:** `structure.py` imports `SKIP_DIRS` from
   `vault.py`; the user-facing reserved set is the **subset**
   `{_shared, shared, projects}` derived from it; a test asserts the derivation
   (no second hardcoded list) and that infra names (`.git`, `__pycache__`) never
   reach a user-facing message.

### Reusing the existing Finding (`claudron/schema.py`)

```python
# structure.py — no new Finding type; extend the existing one.
from .schema import Finding          # severity ∈ {"error","warning"}, .line, .to_dict()
from .vault import Vault, SKIP_DIRS

USER_RESERVED = {"_shared", "shared", "projects"}   # subset of SKIP_DIRS (infra names excluded)

def check_structure(vault: Vault) -> list[Finding]:
    ...   # [] for a conforming vault; findings carry code S1..S4 + fixable
```

## Test Plan

Unit tests (`tests/test_structure.py`), each a tmp vault:
- Conforming vault → `check_structure` returns `[]`; `validate` exits 0.
- Fleet missing `shared/` → `S1` **warning**; `validate` exits **0** by default,
  **1 under `--strict`**; `--fix` creates it, exits 0.
- **`--fix` containment:** a fleet `shared` that is a **symlink out of the repo**
  is rejected (not followed); assert every created path
  `is_relative_to(vault.root)`. This replaces a "git status clean" assertion —
  which can't see a symlink escape.
- Unknown root dir (`vault/experiments/`) → `S3` **warning**, exit 0 by default
  (extensibility preserved); untouched by `--fix`.
- Hand-created `projects/` dir carrying a `fleet.yaml` → `S2` **error**, exit 1
  (raw-walk reaches it though `vault.fleets` filters it).
- Both `_shared/` and `shared/` present → `S4` **warning**.
- `--json`: structure findings appear in the envelope (proving `schema.Finding`
  reuse, not a divergent shape).
- **Repo-level test** (NOT the per-vault lens): the F3 drift guard is two parts.
  (a) **Tier-structure parity** — *already delivered early in P1* as
  `TestDocParity::test_vault_structure_tree_matches_schema_tiers`: it asserts
  every note-tier dir in `schema.py`'s `TYPE_DIRS` appears in *both* trees. This
  is the assertion the original spec omitted — existence + a cross-link alone
  would not catch a tier renamed in one tree. (b) **Cross-reference existence** —
  that SCHEMA.md and VAULT-STRUCTURE.md exist and point at each other; add it to
  the same `TestDocParity` class, not a separate `test_docs_crosslink.py`.
- Reserved-name single-source: the user-facing set derives from `SKIP_DIRS` and
  excludes infra names.
- Golden: `check_structure` on `examples/reference-vault/` returns `[]`, and
  `init && validate` there is a no-op.

## Verification Checklist

- [ ] `claudron validate` exit code obeys the CLI contract: **1 iff an error
      fires**; a lone structure **warning** exits 0 (and 1 under `--strict`) —
      identical to how frontmatter warnings behave.
- [ ] Structure findings appear in `validate --json` (they use `schema.Finding`).
- [ ] `claudron validate --fix` creates missing `<fleet>/shared/` dirs, every
      created path is `is_relative_to(vault.root)`, a symlink-escape is rejected,
      and re-running is a no-op (idempotent).
- [ ] No code path in `validate`/`--fix` moves or deletes an existing file; the
      `--fix` help string no longer claims "never mutates".
- [ ] `claudron init && claudron validate` on a fresh vault **and** on
      `examples/reference-vault/` is a clean no-op.
- [ ] `structure.py` derives the user-facing reserved set from `SKIP_DIRS`
      (subset, infra excluded); no second list (test-asserted).

## What NOT To Do

- `--fix` must **not** move or delete — creation-only, and only inside the
  `is_relative_to(root)` boundary (F2).
- No auto-repair on the default `validate` path (F2).
- Do **not** invent a new exit rule — reuse `error` + `--strict` (the CLI
  contract). Warnings do not gate the default exit.
- Do **not** put the SCHEMA↔VAULT-STRUCTURE cross-link check in the per-vault
  lens — it is a repo test.
- No fresh reserved-name literal, and no infra names in user messages — derive
  the subset from `SKIP_DIRS`.
- Don't rename `_shared/` (F5) or touch promotion (E5).

## Context

Area: `claudron/` CLI + new `structure.py` (reusing `schema.Finding`) · Effort:
**M** · Risk: medium — the `--fix` mutation path is the risk, contained by
`is_relative_to(root)` + symlink rejection + creation-only scope + the
containment assertion (which replaces the insufficient git-clean test) ·
Priority: **high** — the enforcing half of the contract; Claudlobby conformance
depends on it.
