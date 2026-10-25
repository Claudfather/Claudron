---
title: "Vault Structure Contract + enforcing init — the folder SSOT"
type: plan
status: draft
owner: chris
tags: [plan, epic, vault, structure, claudron, claudlobby]
created: 2026-07-09
updated: 2026-07-09
---

# Vault Structure Contract + enforcing `init`

Claudron already owns the *note* contract (SCHEMA.md — frontmatter, and a
`## Vault directory taxonomy` section that already sketches the note-tier tree).
What it does **not** yet own is the *tenancy* half of the directory contract:
who owns each top-level dir, what belongs in `_shared/` vs `<fleet>/shared/`,
how consumers reach it — nor does anything **enforce** the shape. Today that
tree is half-documented and unchecked — `init` scaffolds it, `_scan_vault`
discovers it, SCHEMA.md sketches its tiers, but nothing states the full
tenancy/consumption contract or validates a vault against it. This epic makes
the folder structure a first-class, documented, `validate`-checked contract —
the directory sibling of SCHEMA.md — so Claudlobby (and any tenant) can conform
to a stated shape instead of reverse-engineering one.

This is the Claudron-side counterpart to the Claudlobby "consumes Claudron"
epic (Claudfather/Claudlobby #509, P1/P2). Division of labor, ratified with the
operator 2026-07-09: **Claudron owns the vault folder-structure contract
(defines + enforces via `init`/`validate`) and the knowledge hub; Claudlobby
injects/manages fleet config files into that structure and its bots query
Claudron for knowledge.** The folder structure *is* the contract between the
two tools — the same pattern as the roadmap's E1 (Claudron owns SCHEMA.md as
SSOT, siblings conform).

## Where this sits in the roadmap

This is **not a new gated epic** — and the load-bearing reason to build it
pre-gate is that the **already-ratified G1 fleet dogfood needs a documented,
checkable structure to run**: a fleet can't conform to, or be audited against, a
contract that today exists only in `_scan_vault`'s head. That it *also* hardens
the personal vault (D4) is a bonus, not the warrant. **Release placement:** P1
(the doc) can land immediately; P2's `structure.py` targets a **0.2.x point
release** — after E1's frontmatter `validate` (0.2.0), before the G1-gated 0.3.0
— which is what makes "pre-G1 / extends E1" falsifiable rather than rhetorical:

- **Extends E1.** E1 gives `validate` a *frontmatter* lens; this adds a
  *directory-structure* lens to the same command. VAULT-STRUCTURE.md is the
  directory sibling of SCHEMA.md (Fork F3).
- **Formalizes what E5 already implies.** E5's promotion ladder
  (`05-lifecycle.md:69`: `memory/ → <fleet>/shared/ → _shared/ → pack`) is the
  content contract's backbone. This epic writes that tier model down as the
  *content* contract; it builds **no** promotion code — that stays E5.
- **Respects G1 and the D-decisions.** No cross-tenant query surface
  (portfolio non-goal — single-tenant pooling is intra-tenant); no change to the
  two-field `status`/`maturity` model (D11); the personal topology (D4,
  `_shared/` + `projects/<repo>/`) is extended, not replaced.
- **Fleet dogfood rides the interim CLI wedge**, not E3's MCP server. A
  pilot-fleet dogfood consumes the vault via Claudlobby's already-shipped
  query-before preflight (#528, the "1e wedge"), so nothing here depends on the
  G1-gated E3.

## Architecture

One tenant vault, one git repo, serving the operator's personal sessions **and**
the fleets. On the deployment it *is* Claudlobby's gitignored `local/`; on the
operator's workstation it is a clone. The topology is a **superset of D4** —
personal `_shared/` + `projects/` plus fleet dirs:

```
vault/                       ← ONE git repo (= Claudlobby local/ on the deployment;
│                              a clone on the operator's workstation)
├── _shared/                 ← vault-wide knowledge hub (D4) — the crown jewel.
│                              Reserved name (SKIP_DIRS). Consumed by query, never
│                              by hardcoded path (see the consumption contract).
├── projects/<repo>/         ← personal per-project notes (D4). Reserved name.
├── <fleet>/                 ← a fleet (flat at root — Claudlobby- managed)
│   ├── fleet.yaml           ← config (Claudlobby writes; Claudron does NOT parse)
│   ├── library/  voices/    ← Claudlobby overlay content
│   ├── shared/              ← this fleet's knowledge (Claudron indexes it)
│   └── runtime/             ← generated bots — gitignored within the vault
├── .claudron/               ← Claudron index + vault marker
└── .env                     ← secrets — gitignored, per-machine, never via GitHub
```

Two tools, one structure:
- **Claudron** defines this shape (VAULT-STRUCTURE.md), scaffolds it (`init`),
  discovers fleets in it (`_scan_vault`: any root-level dir with a `fleet.yaml`),
  enforces it (`validate`), and indexes/serves the knowledge (`_shared/` +
  every `<fleet>/shared/`).
- **Claudlobby** injects/manages the fleet config files (`fleet.yaml`,
  `library/`, `voices/`, `runtime/`) into that structure. Its bots **navigate**
  the filesystem for config and **query** Claudron for knowledge.

## Decision Forks

All seven locked by the operator (Chris) on 2026-07-09; evidence is the
planning session that produced this doc. Documented even where "obvious" —
obvious to the author is not obvious to the next reader.

| ID | Decision | Options | Locked choice | Rationale / evidence |
|---|---|---|---|---|
| **F1** | Vault residence vs Claudlobby's `local/` | in-place (`local/` **is** the vault) · separate vault + `migrate` | **In-place** | Converges Claudlobby's vault-resolution with its overlay path — both read `local/<fleet>/fleet.yaml` (`paths.py:416-427`). `migrate` stays for importing a legacy install into a fresh vault. |
| **F2** | Structure enforcement posture | audit-only + `--fix` opt-in · audit + auto-repair | **Audit-only; `--fix` opt-in** | Detect and mutate are separate verbs (mirrors Claudlobby `diff`→`promote`); a check that rewrites the operator's git repo is surprising. |
| **F3** | Where the directory contract is documented | extend SCHEMA.md · new VAULT-STRUCTURE.md | **New VAULT-STRUCTURE.md** | Keeps note-schema and directory-layout as distinct concerns; two SSOT docs, cross-linked, with a drift check. |
| **F4** | Fleet layout | flat `<fleet>/` at root · nested `fleets/<fleet>/` | **Flat** | Claudlobby already lays fleets flat under `local/<fleet>/` (`paths.py:422`) and Claudron's `_scan_vault` already discovers fleets as root-level `fleet.yaml` dirs (`vault.py:178-183`) — the two agree on flat today; nested would break both plus ~14 un-centralized Claudlobby bash sites. |
| **F5** | Hub name | pick a human name now · keep `_shared/`, defer | **Keep `_shared/`, defer** | Rename cost is flat (no config field either way — ~10 hardcoded sites, insulated by the `vault.shared` abstraction), so deferring costs nothing extra; the name stays cheap to change **because** bots consume by query, not hardcoded path. `knowledge/` is out — collides with the reserved per-tier subdir. |
| **F6** | Fleet-scoped consumption | build isolation now · document + conditional | **Document; build only if dogfood needs it** | Tier-A cross-fleet pooling is the operator's *accepted* "one hub" behavior, not a bug; the real gap (fleet-blind `recall`) may not block a solo dogfood. |
| **F7** | Promotion (memory→fleet→vault-wide) | author here · align to E5 | **Align to E5** | The full ladder is already designed (`05-lifecycle.md:61-73`); interim promotion is manual (`capture --fleet` / `git mv`), the wedge habit. Build no promotion code here. |

## Companion Plans

- **E1 — Schema v1** (`01-schema.md`): SCHEMA.md is the note-frontmatter SSOT;
  VAULT-STRUCTURE.md (P1 here) is its directory sibling. P2 extends E1's
  `validate`.
- **E5 — Lifecycle & curation** (`05-lifecycle.md`): owns the promotion
  mechanism. P1's content contract *documents* E5's tier ladder; it implements
  none of it.
- **Claudfather/Claudlobby #509** (consumption epic): the conforming-consumer
  side — plan doc `documentation/plans/2026-07-07-claudron-consumption.md` in that
  repo. The placeholder issues below are its P1/P2 children. Note: that plan also
  numbers its forks F1–F7, but they cover *consumption* decisions (pin, install,
  graduation…), distinct from this plan's *structure* forks above.

## Risks

| Risk | Sev | Impact | Mitigation |
|---|---|---|---|
| `--fix` mutation escapes the vault | **High** | A symlinked `shared` lets `--fix` create dirs outside the repo — invisible to a "git status clean" check | P2: every created path `is_relative_to(vault.root)` (mirrors `engine.py:152`), symlink components rejected, creation-only, idempotent; a containment assertion **replaces** the git-clean test |
| VAULT-STRUCTURE.md drifts from SCHEMA.md (two SSOT docs, F3) | **Med** | Consumers follow contradictory contracts | Reciprocal cross-link + a **Claudron repo test** (`tests/`, not the per-vault lens — those docs never live in a vault) asserting both exist and reference each other. Honest limit: it checks existence, not semantic agreement |
| Cross-repo tier-set drift | **Med** | `SHARED_TIERS` (`vault.py:48-53`) and Claudlobby `composer.py:1876-1882` hardcode the shared-tier subdirs twice; match today, nothing ties them | Named as a Claudlobby sibling issue (single-source the tier set); flagged, not silently assumed |
| Both `_shared/` and `shared/` present drops a tree | **Med** | `_scan_vault` prefers `_shared`, the index skips `shared` — the non-preferred tree's knowledge silently vanishes | P2 `S4` warns on it (the only check that catches it) |
| Structure `validate` hard-codes a shape D4/E5 later evolve | **Med** | A check blocks a legitimate vault | Enforce **only** what VAULT-STRUCTURE.md states; reserved subset derives from `SKIP_DIRS`; unknown dirs warn (`other:`), never gate the default exit |
| Deferred hub rename (F5) accrues habit-debt | **Low** | "Rename later" gets stickier as `_shared/` spreads | Bots consume by query, not hardcoded path → a rename touches ~10 Claudron code sites + ~13 test/doc sites + a per-vault `git mv` + reserved-name accretion (old name lingers in `SKIP_DIRS`), but **zero bot instructions** |
| Cross-fleet pooling (F6) surprises a future multi-tenant user | **Low** | Fine for one operator; a fleet bot can read personal `projects/` notes | Documented as **intended for a single-tenant vault** (one tenant = the operator's own ventures); true separation is a separate vault; isolation path specced in P3, dormant |
| Scope creep into E5 promotion | **Low** | Epic balloons; E5 double-built | "What NOT To Do" fences promotion code; P1 links E5 instead of restating it |

## Complexity and Sequencing

| Phase | Size | Depends on | Parallel with | Delivers |
|---|---|---|---|---|
| [P1 — VAULT-STRUCTURE.md (the SSOT)](01-vault-structure-ssot.md) | S–M | E1 (SCHEMA.md exists) | — | The directory + content + consumption contract, as a doc. Pure prose; no code. |
| [P2 — Structure enforcement in `validate`/`init`](02-structure-enforcement.md) | M | P1 | P3 | `validate` gains a directory lens (audit-only); `--fix` opt-in; `init` scaffolds to the contract. |
| [P3 — Fleet-scoped consumption (conditional)](03-consumption-fleet-context.md) | S–M | P1 | P2 | Documents the Tier-A/recall scoping gaps; `derive_fleet()` + fleet-scoped `recall` **only if** the dogfood needs it. |

**Critical path:** P1 → P2. P3 is dogfood-gated and may never build (F6).

## Sibling-repo work this triggers (Claudlobby — filed as #509 children)

Each is a first-class deliverable with an acceptance criterion, not a docs
afterthought. **Filed and open** on Claudfather/Claudlobby: #560 (item 1) · #561
(item 2) · #562 (item 3) · #563 (item 4), plus #564 (the cross-repo tier-set
drift, from the ironclad review).

1. **Overlay-path conformance** — confirm Claudlobby resolves flat
   `local/<fleet>/` against VAULT-STRUCTURE.md; adopt the reserved-name list
   (forbid fleets named `_shared`/`shared`/`projects`). Evidence base:
   `paths.py:416-427`, the ~14 bash sites (`lib/*.sh`).
2. **Navigate-vs-query protocol** — a bot protocol doc: navigate the filesystem
   for *config*, query Claudron (`recall`/`lookup`) for *knowledge*; never
   hardcode the `_shared/` path (this is what makes F5's rename cheap).
3. **Vault consumption / mount wiring (both mechanisms)** — **(a)** the
   **composition-time** bridge already ships: `_resolve_vault_fleet`
   (`paths.py:104-130`, #300) reads the `.claudron` bridge file →
   `claudron.vault.detect()`. Its `.claudron`-fallback branch + `vault_root` are
   covered by `test_paths_integration.py`; only the **claudron-installed branch**
   (`paths.py:120-124`) is untested — add a stubbed-`detect` test for that branch,
   don't re-cover the fallback or rediscover the mechanism; **(b)** the
   **bot-runtime** `CLAUDRON_VAULT_PATH` → the hub (the bot.conf export emission
   at `composer.py:502-508` has no direct test — #532's `provided_by` tests
   exercise the adjacent collect/scaffold path, not the emission), dedup against
   the `claudron_vault_path` field (`config.py:364`); the `[vault]` extra is **already pinned** to `@v0.2.0`
   (`pyproject.toml:21`) — keep it pinned, bump deliberately.
4. **Pilot-fleet dogfood** — `git init` the deployment `local/` → `claudron
   init --adopt` in place → enable the interim query-before wedge (#528) on one
   fleet → clone to the operator's workstation. Note: `init --adopt` mass-mutates
   frontmatter (`vault.py:230-262`) — run it dry-run/backed-up first, on a
   committed tree.

## What NOT To Do

- Do **not** build promotion / `promote.py` / maturity transitions here — that
  is E5. P1 documents the ladder and links E5; it writes no lifecycle code.
- Do **not** make Claudron parse `fleet.yaml`. Claudron holds fleet files in
  the structure it defines; Claudlobby owns their content.
- Do **not** add a second reserved-name list — derive from `SKIP_DIRS`
  (`vault.py:37-39`) so it can't drift.
- Do **not** rename `_shared/` in this epic (F5). If it ever happens, it is its
  own PR touching ~10 Claudron code sites + ~13 test/doc sites + a per-vault
  `git mv` (the old name also lingers in `SKIP_DIRS`) — bounded, but not "~10".
- Do **not** add auto-repair as `validate`'s default (F2). `--fix` is opt-in.
