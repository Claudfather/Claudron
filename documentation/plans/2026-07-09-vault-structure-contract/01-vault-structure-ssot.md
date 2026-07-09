---
title: "P1 — VAULT-STRUCTURE.md: the directory + content + consumption contract"
type: plan
status: draft
owner: chris
tags: [plan, vault, structure, documentation, claudron]
created: 2026-07-09
updated: 2026-07-09
---

# P1 — VAULT-STRUCTURE.md (the SSOT doc)

## Summary

Author `documentation/VAULT-STRUCTURE.md` — the single source of truth for the
vault's **directory** shape, the **content** contract (what belongs in each
knowledge tier), and the **consumption** contract (how consumers reach it).
Pure prose; **no code.** It is the directory sibling of SCHEMA.md (Fork F3) and
the thing P2 enforces. It formalizes what `init`/`_scan_vault` already do
implicitly and what E5 already designs for promotion — writing the shape down
so any tenant (Claudlobby's fleets and the operator's personal sessions alike)
conforms to a stated contract.

## Evidence (current state this documents)

- **The shape exists but is undocumented.** `init` scaffolds `_shared/` +
  `CONVENTIONS.md` (`vault.py:217,221`); `_scan_vault` discovers fleets as
  root-level dirs containing `fleet.yaml` (`vault.py:178-183`); `SKIP_DIRS`
  (`vault.py:37-41`, 7 entries incl. infra like `.git`/`__pycache__`) reserves
  top-level names — the *user-facing* subset being `_shared`/`shared`/`projects`;
  the vault-wide hub is a first-class field, `Vault.shared` (`vault.py:117-124`).
  No doc states any of this.
- **Personal topology is locked (D4):** `_shared/` + `projects/<repo>/`
  (`00-overview.md:68`). The fleet topology adds `<fleet>/` siblings — a
  superset, not a competitor.
- **Content is scope-by-location today, with no contract.** The type taxonomy
  (`knowledge/decisions/runbooks/planning`, `schema.py:93-100`) is **identical**
  for the hub and every fleet; nothing defines *what kind* of knowledge belongs
  vault-wide vs per-fleet. Only real asymmetry: `CONVENTIONS.md` is hub-only
  and always-injected (`session.py:94`).
- **The promotion ladder is already designed** (`05-lifecycle.md:69`):
  `memory/ → <fleet>/shared/ → _shared/ → pack`. This doc *cites* it; it builds
  nothing.
- **Consumers already read the hub through the abstraction, not the literal** —
  `recall`/`lookup` route via `Vault.shared`, so a documented "query, don't
  hardcode the path" rule matches reality and keeps the F5 hub-name deferral
  cheap.
- **Claudlobby already knows `<fleet>/shared/`:** `paths.py:311`
  (`shared_docs = fleet_dir / "shared"`).

## Implementation Plan

### Dependencies

- **E1** — SCHEMA.md must exist as the note-frontmatter SSOT so VAULT-STRUCTURE.md
  can cross-link it rather than restate frontmatter rules.

### Blocks

- **P2** (structure enforcement) — `validate` enforces what this doc states.
- Claudlobby sibling issues #1/#2 (overlay conformance, navigate-vs-query
  protocol) point at this doc.

### Steps

Create `documentation/VAULT-STRUCTURE.md` (`type: convention`, wiki folder
`conventions/`) with these sections:

1. **Directory contract + human on-ramp.** Open with a "start here"
   orientation for a human browsing the vault (where knowledge lives, where to
   drop a note by hand), then the tree from `00-overview.md#architecture`.
   Normative statements: one git repo per tenant vault; `_shared/` (or legacy
   `shared/`) at root is the vault marker; fleets are **flat** root-level dirs
   with a `fleet.yaml`; `runtime/` and `.env` are gitignored within the vault.
2. **Reserved names.** State that the user-facing reserved top-level names —
   `_shared`, `shared`, `projects` — are vault-internal and a fleet may not take
   them. These are the **subset** of `SKIP_DIRS` (`vault.py:37-41`) a human would
   collide with; the constant also holds infra names (`.git`, `__pycache__`)
   that never belong in a user-facing message. **Point at `SKIP_DIRS` as the
   source** — P2 derives the subset from it, no second list.
3. **Content contract (three tiers).** Define what belongs where:
   - bot `memory/` — a bot's private, unshared working state.
   - `<fleet>/shared/` — knowledge scoped to one fleet's mission.
   - `_shared/` — vault-wide knowledge (cross-fleet + the operator's own).
   State the rule plainly: **scope is chosen by location** (which dir you write
   to), the *type* taxonomy is identical across tiers, and knowledge **rises**
   (memory → fleet → vault-wide) via promotion, never leaks sideways. Note that
   a `scope:`/`visibility:` frontmatter field is **explicitly deferred** — the
   contract is location-based for v1.
4. **Consumption contract.** Normative: bots **navigate** the filesystem for
   *config* and **query** Claudron (`recall`/`lookup`) for *knowledge*; they
   **must not hardcode** the `_shared/` path (this rule is what makes the F5
   rename cheap). Document the existing merge + precedence honestly: a query
   returns `_shared/` + fleet notes, tie-broken `project > fleet > shared`
   (`knowledge.py:430-437`); cross-fleet pooling is **intended for a
   single-tenant vault** (see P3 for the fleet-scoping gap and its conditional
   fix). State the consequence plainly: single-tenant pooling means a fleet
   bot's query can surface the operator's personal `projects/` notes. This
   reconciles with D4's "work knowledge stays out" by reading **one tenant = the
   operator's own ventures**; the boundary for true separation (employer
   systems, another person's data) is a **separate vault**, not a dir inside
   this one.
5. **Promotion model (prose only).** Reproduce the E5 ladder
   (`memory/ → <fleet>/shared/ → _shared/ → pack`) as the *model*, link
   `05-lifecycle.md` for the *mechanism*, and state the **interim**: promotion
   is manual today (`capture --fleet` / `git mv`) until E5's `promote` ships.
6. **Reciprocal cross-link.** VAULT-STRUCTURE.md links SCHEMA.md ("notes:
   frontmatter") and SCHEMA.md gains a one-line pointer back ("layout: see
   VAULT-STRUCTURE.md"). A Claudron **repo test** (`tests/`, not the per-vault
   lens — these docs never live inside a vault) asserts both exist and
   cross-link. Honest limit: the test checks existence, not semantic agreement.

## Test Plan

Doc-only, but falsifiable:
- The doc's user-facing reserved names are the subset `{_shared, shared,
  projects}` derived from `SKIP_DIRS` (P2 asserts the derivation, not verbatim
  equality — the constant also carries infra names).
- The tier ladder matches E5's model (`05-lifecycle.md`) — asserted by meaning,
  not pinned to a line number (which would couple this doc to E5's churn).
- A reader following the doc scaffolds a vault that `_scan_vault` discovers
  without an `other:` surprise (validated once P2 lands).

## Verification Checklist

- [ ] `documentation/VAULT-STRUCTURE.md` exists with all six sections, opening
      with a human "start here" on-ramp.
- [ ] User-facing reserved names are the subset `{_shared, shared, projects}`
      derived from `SKIP_DIRS` (`vault.py:37-41`); infra names excluded.
- [ ] Promotion section links E5 and states "manual interim"; contains **no**
      new lifecycle rules.
- [ ] SCHEMA.md ↔ VAULT-STRUCTURE.md cross-link both directions.
- [ ] No `scope:`/`visibility:` field introduced (deferred, stated as such).

## What NOT To Do

- No promotion/lifecycle rules — link E5, don't restate it.
- No new reserved-name list — cite `SKIP_DIRS`.
- No `scope:` frontmatter field — location is the scope for v1.
- Don't rename `_shared/` (F5).

## Context

Area: documentation (Claudron) · Effort: **S–M** · Risk: low (prose; the risk is
drift, handled by the cross-link repo test P2 adds) · Priority: **high** — blocks
P2 and both Claudlobby conformance issues.
