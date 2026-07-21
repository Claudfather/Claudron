---
title: "Separation of Systems by Purpose — Claudron · clauDNA · Claudlobby boundary program"
type: plan
status: draft
owner: chris
created: 2026-07-20
tags: [system:claudron, system:claudna, system:claudlobby, boundaries, architecture, separation-of-concerns]
repos: [Claudfather/Claudron, Claudfather/clauDNA, Claudfather/Claudlobby]
---

# Separation of Systems by Purpose — Claudron · clauDNA · Claudlobby boundary program

> **What this is.** A facts-first, self-contained brief on the boundaries between **three**
> co-installed products — **Claudron** (referential), **clauDNA** (procedural), **Claudlobby**
> (runtime). Its purpose is to *seed a fresh, neutral boundary-visioning pass*. The brief is scoped
> to these three systems only: it does not reason about any other stack, and it treats the ecosystem
> umbrella and the evaluation arena as out of frame. §1–§9 are facts, questions, and constraints; the
> target-state (deliverables **a** and **b** in §7) is authored by the visioning pass and folds back
> here. **Status: draft — deliverable (a) authored (§10, 2026-07-20); deliverable (b) lives in
> `2026-07-20-boundary-rearchitecture/` (overview + 9 phase docs, this directory).**
>
> **How to use this spec — reason forward from purpose.** Do **not** ratify the thinking that
> produced this brief. One prior-thinking section is **sealed at the end** (Appendix Z), marked
> *challenge, do not adopt* — including the current human lean and the boundary the ecosystem already
> asserts. If you find yourself agreeing with Appendix Z quickly, treat that as a warning sign and
> push harder. The value of the pass is an independent boundary derived from §1–§9, even if it
> contradicts the appendix. Read the §5 prior art first.

---

## 1. What we are trying to do

Three repositories form one AI-native knowledge-and-fleet stack. Each asserts its purpose at its root,
and two of the three even name the whole boundary in prose — yet the boundary is **enforced only at
the roots and blurs at the internal seams**, where the three systems touch the same session lifecycle,
the same knowledge tree, and the same vault-path contract. We want to:

- **(a) Devise the boundaries** — a crisp, purpose-based definition of what each system *is for*, what
  belongs in it, and what must never leak in — derived from the facts below and expressed in a test a
  human or agent can apply to any file or capability.
- **(b) Propose the re-architecture** needed to satisfy those boundaries — what moves, what merges,
  what splits, what the interfaces between the systems are, and a sequenced migration path that keeps
  each repo shippable.
- **(c) Enforce it with CLAUDE.md system-wide** — author/refresh CLAUDE.md at the repo **roots and the
  internal subdirectory seams** so the boundary is legible and self-enforcing at the exact points
  where code and knowledge get placed.

**This is not a blank slate.** A boundary framework already exists (§5) — a purpose triad, a pair of
portable placement tests, a ratified vault contract, and a recorded consumption decision. The
re-architecture must extend that established direction and its language, or make an explicit, reasoned
case for revising it.

---

## 2. The three systems today (claimed purpose — quoted from each root CLAUDE.md)

### `Claudron` — the referential knowledge engine (the "SD card")
> *"Markdown-based knowledge engine for Claude Code agent fleets. Vaults are directories of markdown
> files with YAML frontmatter, searched via a two-tier strategy (frontmatter index + full-text
> fallback)."* (`CLAUDE.md`) — README sharpens it: *"the portable 'SD card' for your sessions'
> memory."*

- **Contains:** the `claudron/` Python package — `vault` (detection, scaffolding, tenancy),
  `knowledge` (two-tier search: Tier A frontmatter index + Tier B full-text), `schema`
  (frontmatter SSOT enforcement), `graph` (wikilink resolution + `related`/`links`), `promote`
  (maturity ladder), `locking` (flock + atomic writes), `session`/`hooks`/`sync` (the session loop),
  `cli`; the two ratified SSOTs **`SCHEMA.md`** (note frontmatter: 6 types, per-type status vocab,
  a `draft < verified < canonical` maturity ladder) and **`VAULT-STRUCTURE.md`** (directory,
  tenancy, scope, consumption, promotion); a disposable `.claudron/index.json`.
- **Its defining guarantees:** the substrate is **plain markdown in a git repo, forever** — no
  database is the source of truth. **One vault = one tenant**; scope is chosen by *location*, not by a
  `scope:` field. Writes are **creation-only and vault-contained** (symlink-escape guarded),
  serialized by a re-entrant `flock` + atomic `os.replace`. Single dependency: **PyYAML**. License:
  **MIT**.
- **Dependency posture:** a **standalone leaf** — works with no sibling installed; depends only on
  PyYAML. Distribution: `pip install` from a git clone/tag (**PyPI deferred**).

### `clauDNA` — the procedural capability layer (the "genome")
> *"Claude Code plugin pack distributed via the `Claudfather` marketplace. Ships skills, agents, and
> hooks as a single plugin (`claudna`). Marketplace install is the only supported channel."*
> (`CLAUDE.md`) — the mission is blunter about the boundary: *"Skills here are procedural (how to do
> X), not referential (what we know about X). Reference knowledge lives in Claudron, […] runtime is
> Claudlobby."* (`PROJECT_MISSION.md`)

- **Contains:** `skills/` (~37 skills — the plugin auto-discovers each dir; **there is no
  `commands/` dir, skills *are* the slash-commands**, invoked `/claudna:<skill>`), `agents/` (8),
  `plugin-hooks/` (lifecycle hooks + `hooks.json`), `project-template/`. The vault-facing surface:
  `/claudron` (read-only `lookup`/`status`), `/capture` (the single write door), `/recall`
  (session orientation) — each **shells the `claudron` CLI**.
- **Its defining rules:** **procedural, not referential** — the "genome" every bot inherits at
  startup. **"clauDNA ships no MCP servers — this engine *is* the CLI … the CLI is the contract
  floor"** (`skills/claudron/SKILL.md`). Marketplace install is the only channel.
- **Dependency posture:** a **consumer of Claudron** through the CLI (degrades to a frozen raw-tree
  fallback when Claudron is absent); installed **per bot** by Claudlobby.

### `Claudlobby` — the fleet runtime (the compositor)
> *"Compositor for Claude Code agent fleets. Transforms `fleet.yaml` + `library/` into runnable bot
> directories with isolated identities, MCP servers, skills, and systemd/launchd supervision."*
> (`CLAUDE.md`) — the charter names the whole loop: *"Bots install clauDNA via marketplace plugin,
> get distinct GitHub App identities, query Claudron before tasks and write findings after […]. The
> framework stays local-first: a fleet runs on a Pi in a closet with zero required hosted
> dependencies."* (`PROJECT_MISSION.md`)

- **Contains:** the `claudlobby/` compositor (`composer.py`, `validator.py`, `paths.py`, `commands/`),
  `library/` (composable sources of truth: expertise, skills, MCP fragments, guardrails, protocols),
  `lib/` (~63 bash lifecycle scripts — start/keepalive/dispatch/report-back/supervision),
  `templates/claude.md.j2` (the Jinja2 template that owns every bot's `CLAUDE.md`),
  `fleet.yaml.example`; generated bot dirs land in a gitignored `local/runtime/bots/<name>/`.
- **Its defining rules:** **local-first**, zero required hosted dependencies (a fleet runs on a Pi).
  **"Claudlobby does not define skills — clauDNA does."** Vault wiring is **declarative** (set it in
  `fleet.yaml`), not imperative. It **never stores or forks** the knowledge corpus; it only *consumes*
  the vault.
- **Dependency posture:** the **fleet runtime that consumes both** — it auto-installs the
  `claudna@Claudfather` plugin per bot and mounts a Claudron vault per bot — but **both are optional**
  (the `[vault]` extra is opt-in; a fleet can run with neither). Distribution: git clone + editable
  install (**not on PyPI**).

---

## 3. Cross-repo topology & dependency edges (verified)

```
                    ┌─────────────────────────────────────┐
                    │             Claudlobby              │  FLEET RUNTIME
                    │   fleet.yaml + library/ → bot dirs   │  (compositor; local-first;
                    │   tmux · launchd/systemd · Telegram  │   owns the wiring)
                    └──────┬──────────────────────────┬────┘
      installs per bot     │                          │   mounts vault per bot:
      claudna@Claudfather  │                          │   composer emits CLAUDRON_VAULT_PATH;
      (built-in default)   ▼                          │   .claudron bridge FILE at its root;
                      ┌─────────┐                      │   [vault] extra → vault.detect()/Vault.fleets
                      │ clauDNA │  /claudron ·         ▼
                      │ skills ·│  /capture ·     ┌──────────┐
                      │ agents ·│  /recall  ────▶ │ Claudron │  REFERENTIAL ENGINE
                      │ hooks   │  shell the      │  vault   │  (markdown+git; PyYAML-only;
                      │(plugin) │  claudron CLI   │  engine  │   the CLI is the consumption floor)
                      └─────────┘                 └──────────┘
                                                    ▲   ⋮
                       claudron plug/unplug/config/ │   ⋮  (an MCP door over the same engine is
                       migrate act back on a   ─────┘   ⋮   DECLARED but demand-gated + unbuilt —
                       Claudlobby install                   see §4.5)
```

- **Claudlobby → clauDNA:** auto-installs the `claudna@Claudfather` plugin per bot (a built-in fleet
  default); the session lifecycle invokes `/claudna:session resume|handoff` at start/stop.
- **Claudlobby → Claudron:** the composer emits **`CLAUDRON_VAULT_PATH`** per bot; a **`.claudron`
  bridge *file*** at the Claudlobby root points a checkout at the vault (parsed by `paths.py`); when
  the `[vault]` extra is installed it calls `claudron.vault.detect()` / `Vault.fleets`. *(The word
  "socket" in older plan docs is a metaphor — there is no Unix socket; it is a config file + an
  env var + an optional imported API.)*
- **clauDNA → Claudron:** `/claudron`, `/capture`, `/recall` **shell out to the `claudron` CLI**
  (`claudron lookup|status|recall|capture … --json`). This is the fleet's read+write door to the hub.
- **Claudron → Claudlobby:** the `plug` / `unplug` / `config` / `migrate` CLI verbs act **back on a
  Claudlobby install** (write the bridge file, migrate a fleet's shared docs into the vault); they
  print a clear error when no Claudlobby is found. So Claudron is Claudlobby-*aware* though
  Claudlobby-*independent*.
- **Claudron:** depends on neither sibling; the others are optional consumers of it.

---

## 4. Where the boundaries are weakly enforced (the drift — facts, not solutions)

These are the observed seams where "by purpose" has blurred. They are the material the re-architecture
(b) and the CLAUDE.md enforcement (c) must resolve.

1. **Two knowledge loops run at the same lifecycle events.** clauDNA and Claudron each install Claude
   Code hooks over the same session. At **SessionStart** both fire: clauDNA's `session-start.sh` emits
   a *local git + `gh`* continuity brief (`<claudna-session-briefing>` — branch, working tree, last
   handoff, open PRs; it does **not** call `claudron`), while Claudron's own SessionStart hook injects
   a *vault-recall* brief. Two briefs, one event, different content — coexisting, not merged. At
   **PreCompact** both once prompted a capture; this is now **partly reconciled** — Claudron's hook
   defers when the plugin is present (`hooks.py:62` `_claudna_installed()`, `:121` returns silently),
   ceding the capture prompt to `/claudna:capture`. Two index artifacts persist over the same tree:
   clauDNA's raw-tree **`INDEX.md`** scan (the frozen no-Claudron fallback) vs Claudron's
   **`.claudron/index.json`**. And two home conventions coexist: clauDNA's raw **`shared/{knowledge,
   decisions,runbooks,planning}`** tree vs Claudron's engine vault (**`_shared/`**, which `detect()`
   also accepts as `shared/` — `vault.py:44`). The overlap is real; the reconciliation is halfway.

2. **How a fleet bot consumes the hub is split by history, not design.** There are two doors. The
   **CLI-skill door** (clauDNA's `/claudron`/`/capture`/`/recall` over the `claudron` CLI) is the
   **shipped contract floor** that works on every bot today. The **MCP door** (Claudron's own MCP
   server) is **unbuilt and demand-gated** ("decision C" — `documentation/plans/2026-07-18-decision-c-
   mcp-demand-gated.md`; triggers are per-tool permission gating or a non-clauDNA MCP consumer,
   neither of which exists yet). Net: the runtime consumption path is *entirely* clauDNA's CLI door,
   which makes **Claudron's fleet adoption depend on clauDNA** — Claudron has no vendor-neutral fleet
   door of its own beyond the bare CLI.

3. **The write path is single-host-safe but multi-writer-unsettled.** Claudron serializes writes with
   a re-entrant `flock` + atomic `os.replace` (`locking.py`), and the live fleet write path is
   `/claudna:capture` → `claudron capture`. But `flock` is **per host**: two bots on two machines
   capturing concurrently are not mutually excluded — `sync` pulls `--rebase` and **quarantines** the
   conflict for a human. "Who may write, across how many machines, and what happens on collision" is
   *asserted* (effectively single-writer + quarantine) but not *enforced* by the boundary.

4. **The vault-path contract has three spellings and a stale consumer tail.** Claudron's CLI resolves
   `--vault` → `$CLAUDRON_VAULT_PATH` → `$CLAUDRON_VAULT` → walk-up (`cli.py:75–82`). Claudlobby's
   composer emits **`CLAUDRON_VAULT_PATH`** (`composer.py:610`); clauDNA reads **`CLAUDRON_VAULT` /
   `CLAUDRON_VAULT_PATH` / `SHARED_DOCS_PATH`** in that precedence; Claudron's own init text prints
   `export CLAUDRON_VAULT=…` (`cli.py:271`). They reconcile *only* by each side's precedence list —
   there is **no single named contract**. And a swept-but-not-finished tail: Claudlobby's
   `dispatch-task.sh:103` still passes `--vault` explicitly under a comment claiming *"the claudron
   CLI does not read CLAUDRON_VAULT_PATH itself"* — **true before the CLI gained env resolution
   (Claudron #62), false now**. The fix landed in the engine; the consumer's workaround and its
   comment linger. (A drift signal: fixes land, tails linger.)

5. **The runtime advertises a consumption door the engine hasn't shipped.** Claudlobby's `validator.py`
   (lines 403–414) warns, per bot, when `claudron_vault_path` is set but **no `claudron` MCP server is
   configured** ("the vault path won't be used without the Claudron MCP server"), and vice-versa — yet
   **`library/mcp/claudron.json` does not exist** (the fragment is a "gated surface, not yet
   available," slated for Claudron 0.3.0 per `claudron_compat.py`). So the runtime is wired to expect,
   and warns about the absence of, a door the engine never built; bots reach the vault through the CLI
   instead. A latent false invariant at the exact seam §4.2 describes.

6. **Enforcement lives only at repo roots.** CLAUDE.md surface across the three source repos = **3 root
   files, 0 internal-seam files.** (clauDNA additionally ships `project-template/CLAUDE.md` and
   Claudlobby `templates/claude.md.j2`, but those are **consumer-scaffolding templates** stamped into
   *bots and projects* — neither repo carries a CLAUDE.md at its *own* internal placement seams:
   Claudron's `claudron/` modules, clauDNA's `skills/` vs `skills/_shared/`, Claudlobby's `library/`
   vs `lib/` vs `claudlobby/`.) The boundary is asserted at each root but **absent where placement
   decisions actually happen.**

---

## 5. The boundary framework that already exists (prior art — build on this)

The ecosystem has already articulated boundary language. Extend it; don't reinvent it.

- **The purpose triad** — *procedural = clauDNA · referential = Claudron · runtime = Claudlobby.*
  Asserted verbatim in clauDNA's `PROJECT_MISSION.md` and Claudron's README "Position in the
  ecosystem." A clean three-word carve-up — the task is to turn it into a *test a file can be run
  through*, and to find where it under-determines (§4, Appendix Z).
- **Scope-by-location + two portable placement tests** (Claudron `VAULT-STRUCTURE.md`): a note's
  *directory is its visibility* (no `scope:` field). And two crisp tests already in the contract —
  **vs `_shared/`:** *"would this still hold if this repo didn't exist?"* (yes → shared, no →
  `projects/<repo>/`); **vs the repo's own `documentation/`:** *"is the repo speaking about itself, or
  is this the operator's outside view of it?"* Generalize this pair across the three *systems*.
- **The plane doctrine** — repo-authoritative records (architecture, ADRs, specs) travel *with the
  code* in `<repo>/documentation/`; the vault holds the operator/fleet's cross-repo *outside view*.
  The knowledge home and the code home are deliberately different planes.
- **"The CLI is the contract floor; MCP is an equivalent optional door"** (clauDNA F1 door note) —
  the interface pattern between a procedural consumer and the referential engine, already chosen.
- **The trust ladder** (Claudron `SCHEMA.md`): `maturity: draft < verified < canonical`, orthogonal
  to per-type `status`. Agents capture as `draft`; **humans promote**. The curation model is settled.
- **Predecessor docs — read first:** `documentation/plans/2026-07-09-claudna-claudron-
  reconciliation.md` (the hook/index overlap and how to unify it), `VAULT-STRUCTURE.md` (tenancy +
  consumption), `documentation/plans/2026-07-18-decision-c-mcp-demand-gated.md` (why the MCP door is
  parked), and the Claudron roadmap overview (`documentation/plans/2026-07-07-claudron-roadmap/
  00-overview.md`, locked decisions D1–D8). They set the direction this pass continues.

---

## 6. The triggering example (a concrete instance of the drift)

Make the abstract real by resolving this live case as a test of any proposed boundary:

A fleet bot's `fleet.yaml` sets `claudron_vault_path`, so Claudlobby's `validator.py` **warns that the
bot is misconfigured** — *"claudron_vault_path is set but no 'claudron' MCP server is configured — the
vault path won't be used without the Claudron MCP server."* But **there is no `claudron` MCP server to
configure**: `library/mcp/claudron.json` doesn't exist, and Claudron's MCP door is demand-gated and
unbuilt (§4.5). Meanwhile the bot reaches the vault perfectly well — through clauDNA's
`/claudron`/`/capture`/`/recall` shelling the CLI (§4.2). So the runtime **warns about the absence of a
door the system deliberately chose not to build**, because *"how a bot consumes the hub"* is split
across two repos — a shipped CLI door in clauDNA and a declared-but-parked MCP door in Claudron — with
no single owner. The tactical fix is a fragment or a one-line validator change; the architectural
question is **where the fleet-consumption door should live at all**, and whether Claudron needs a
vendor-neutral door of its own so its adoption isn't hostage to clauDNA. A correct boundary makes the
answer obvious.

*(A second live instance, if a write-side case is preferred: two bots on two machines each
`/claudna:capture` the same finding; the per-host `flock` doesn't span hosts, so `sync` quarantines the
collision for a human — §4.3. Same shape: three systems touch one durable write, and no boundary says
which one owns "the fleet's write path across machines.")*

---

## 7. Deliverables

### (a) Boundary definition
A per-system purpose statement + an **applicable placement test** (generalize the triad and Claudron's
two location tests) that, given any file or capability, yields exactly one home. Cover the hard cases
explicitly: the **session loop** (SessionStart briefs, PreCompact capture, the index — is it
procedural, referential, or a fourth concern?); the **fleet-consumption door** (CLI vs MCP; does
Claudron need a vendor-neutral door?); the **write path across hosts**; the **vault-path contract**
(one canonical name); and the *inverse* edge cases — a clauDNA skill that encodes referential
knowledge, or Claudron content that is really runtime. Output: a boundary spec (folds back into this
doc). **→ Authored: §10 below (2026-07-20).**

### (b) Re-architecture proposal
Target-state architecture across the three repos + the migration path: what moves/merges/splits; the
**interface** between systems (subprocess CLI-as-ABI vs a git-installed package vs in-repo — note the
no-PyPI constraint, §8); how the **two knowledge loops** unify (single hook owner, single index,
single marker) without breaking Claudron's standalone use or clauDNA's raw-tree fallback; how the
**consumption door** consolidates (keep decision C's CLI-floor default, or promote a vendor-neutral
Claudron door); how **create-only + the flock** stay honest across hosts; sequencing that keeps each
repo shippable. Output: a forge-style plan (overview + phases) → `ironclad` → `implement-plan`. A
repo-building plan graduates to its target repo; this cross-system boundary spec stays here.

### (c) System-wide CLAUDE.md enforcement
Root **and** internal-seam CLAUDE.md that make the boundary self-enforcing where placement happens.
Current surface is 3 root files, 0 internal-seam files. Candidate seams to evaluate (non-exhaustive):
Claudron `claudron/` (engine vs CLI vs hooks), the `SCHEMA.md`/`VAULT-STRUCTURE.md` SSOT pair;
clauDNA `skills/` vs `skills/_shared/`, `plugin-hooks/`; Claudlobby `library/` vs `lib/` vs
`claudlobby/`. Each should state: what belongs here, what must never land here, and the placement
test. Keep consistent with the CLAUDE.md **templates** clauDNA and Claudlobby already stamp into
projects and bots.

---

## 8. Constraints & non-negotiables (bound the solution space)

- **Substrate is plain markdown + git, forever** (Claudron D-decision) — no database is the source of
  truth; the index is derived and disposable.
- **Minimal-dependency posture is load-bearing:** Claudron is **PyYAML-only, MIT**; clauDNA is
  **marketplace-only**; Claudlobby is **local-first with zero required hosted dependencies**. A
  boundary that forces a heavy shared runtime violates all three identities.
- **MCP is an optional stdio door, never a daemon**, and is **demand-gated** (decision C). The CLI is
  the contract floor — any interface proposal must keep the CLI door whole.
- **Distribution channels are split and no cross-repo PyPI is assumed:** Claudron/Claudlobby → PyPI
  (deferred; today git-installed by tag — `claudlobby[vault]` pins `claudron @ …@v0.2.0`), clauDNA →
  the Claude Code marketplace. The realistic interfaces are the **CLI (subprocess ABI)**, a
  **git-installed extra**, or **in-repo** — not `pip install` from a public index.
- **One vault = one tenant; scope by location; no `scope:` field.** A second tenant is a separate
  vault, never a nested directory.
- **`.claudron/index.json` is derived and never hand-edited; curation is human-gated** — agents
  capture as `maturity: draft`, humans promote to `verified`/`canonical`.
- **Writes stay creation-only and vault-contained** (symlink-escape guarded), `flock` + atomic on the
  write path.
- **Preserve the existing non-overlaps:** *Claudlobby does not define skills — clauDNA does; Claudron
  never parses `fleet.yaml` — Claudlobby owns it.* These clean lines must survive the re-architecture.
- **Each repo must stay independently useful:** Claudron standalone (no clauDNA/Claudlobby), clauDNA
  degrading to its raw-tree fallback, Claudlobby running with neither optional consumer.
- **Governance:** `SCHEMA.md` and `VAULT-STRUCTURE.md` are ratified SSOTs; changes land via PR and
  require approval.

---

## 9. Success criteria

You'll know the boundary + re-architecture is right when:

1. **Every file and capability has one obvious home** under the placement test — the two-loops /
   consumption-door / write-path / vault-path ambiguities all resolve deterministically.
2. **No capability is implemented twice** across repos — one owner for the session loop (SessionStart
   brief, PreCompact capture, the index), one named vault-path contract, one write path.
3. **The triggering example (§6) has an unambiguous answer** — you can say exactly where the
   fleet-consumption door lives (and whether the phantom MCP mount is built, warned about, or removed)
   without a fork.
4. **A new contributor or agent can place any new file** by reading the nearest CLAUDE.md — legible at
   the seam, not just the root.
5. **Each repo remains independently shippable and independently useful** through the migration — no
   big-bang lockstep release, and no repo's core identity (PyYAML-only / marketplace-only /
   local-first) is compromised.

---

## 10. The boundary — deliverable (a), authored by the visioning pass (2026-07-20)

> Derived forward from §1–§9, verified against code at head: Claudron working checkout, clauDNA
> `release/v0.17.0` (worktree `61973ed`), Claudlobby `8124268`. Appendix Z was read last and
> challenged: where this section agrees with it, the grounds are stated independently; where it
> disagrees, the revision is explicit (§10.6). Facts found in verification that *amend* §1–§9 are
> ledgered in §10.8 — several materially change the picture.

### 10.1 The finding: the triad places content — and none of the drift is content

The purpose triad (*procedural / referential / runtime*) is a **content taxonomy**: it classifies an
artifact by what kind of thing it is — something an agent *executes*, something an agent *consults*,
something that *wires and runs* agents. For content it works, and this pass keeps it (§10.3).

But run the five §4 drift cases through it and the triad returns two or three defensible answers
each — because none of them *is* content:

| §4 case | what it actually is |
|---|---|
| two knowledge loops (§4.1) | a **protocol** — who fires what, in what order, at shared lifecycle events |
| consumption door (§4.2, §4.5, §6) | an **interface** — an ABI plus the right to say what consumes it |
| write path across hosts (§4.3) | three concerns fused: a **mechanism**, a **policy**, and a **protocol** |
| vault-path spellings (§4.4) | a **shared name** with no owner |
| root-only enforcement (§4.6) | contract text missing at the seams where placement happens |

The missing concept is a second register. Every artifact in the stack is either **content** (one
system's own material — the triad places it) or **contract** (anything two or more systems must
agree on: a name, a format, an ordering, a semantic). Contracts are not placed by kind; they are
placed by **ownership**. The stack already knows this in fragments — *"the CLI is the contract
floor"* (clauDNA F1), *"Sibling schema changes must PR Claudron first"* (`SCHEMA.md`), the plane
doctrine — but it has never been stated as a rule, so every contract that wasn't SCHEMA.md-shaped
(the env var, the session protocol, the door, the bridge file, the handoff artifact) grew up
ownerless. §4 is the list of ownerless contracts.

A second, independent finding from verification: the triad as practiced **conflates format with
ownership**. Claudlobby ships **44 `SKILL.md` files** under `library/skills/` (dispatch,
fleet-status, restart, sweep…) while its mission asserts *"Claudlobby does not define skills —
clauDNA does."* The files are right and the sentence is wrong: those are fleet-operations commands,
coupled to `lib/` lifecycle scripts and bot directories — they change when the *runtime* changes,
and would be dead weight in a marketplace plugin. "Skill" is a **format**; the triad's *procedural*
axis must read *what the behavior operates on*, not the file extension. The same correction applies
in reverse to clauDNA skills that embed reference payloads (§10.5.5).

### 10.2 Per-system purpose (sharpened: owns / consumes / never)

**Claudron — the knowledge system.**
*Owns:* the durable-knowledge substrate (markdown + git, forever) and **every operation on it** —
schema, structure, tenancy, search/ranking, graph, curation/promotion, write safety (flock +
atomic + dedup), transport (`sync`) — **and every contract by which anything consumes it**: the CLI
ABI, the vault-address contract, the write protocol, the session-loop protocol for knowledge events
(§10.5.1), and any future door over the same engine (MCP, demand-gated).
*Consumes:* nothing from its siblings. A standalone leaf; PyYAML-only; MIT.
*Never:* parses `fleet.yaml`; defines agent behavior; **knows a consumer by name** — today it sniffs
both siblings (`hooks.py:62` globs the plugin cache for `claudna`; `cli.py:104–113` walks for a
`library/`+`lib/` tree shape). Consumers declare themselves to the engine (config/env per contract);
the engine never goes looking.

**clauDNA — the behavior system.**
*Owns:* the portable engineering genome — skills, agents, hooks-as-behavior — distributed
marketplace-only; and its own surfaces (`/claudna:*` verbs, `SKILL_CONTRACT`, the `session.md`
handoff artifact).
*Consumes:* Claudron **through the published door** (shells the CLI; `requires: cli: claudron>=0.2`),
providing the ergonomics layer — verbs, prompts, envelope handling, the frozen raw-tree fallback
when no engine is present.
*Never:* owns transport, index, ranking, or schema (it renders SCHEMA.md with a CI drift gate — the
model pattern, §10.4); ships MCP servers; writes user settings; carries reference material that
changes when the *world* changes rather than when its *procedures* change (§10.5.5).

**Claudlobby — the composition system.**
*Owns:* `fleet.yaml` and everything composed from it — bot identities, plugin installs, env
contracts, permission grants (#644), supervision, dispatch, fleet-operations commands (the 44
`library/skills/` — format notwithstanding, they are runtime content); **policy** for what each bot
may do, including writer topology (§10.5.3).
*Consumes:* clauDNA as the default installed plugin; Claudron declaratively (emits
`CLAUDRON_VAULT_PATH`, reads the `.claudron` bridge, optional `[vault]` extra pinned `@v0.2.0`).
*Never:* implements knowledge mechanics or engineering-workflow behavior; **stores the long-lived
knowledge corpus** (its `library/lessons/` — 25 learned-the-hard-way notes — violates this today,
§10.5.5); **asserts a sibling's unshipped surface** (the `validator.py:403–414` phantom-MCP warning,
§10.5.2).

### 10.3 The placement test

Run any file or capability through this, in order. It terminates in exactly one home.

**Q0 — Contract?** *Must two or more systems agree on its name, shape, timing, or semantics?*
→ It is contract material. Place its **text** with its **owner** — the system that keeps the
promise (the provider of the invariant; tiebreak: whose users break first on incompatible change).
Everyone else holds **conformance** — a pointer, or a rendered copy with a CI drift gate — never a
fork, never a re-assertion. (Rules: §10.4.)

**Q1 — Executed?** *Is its job to steer an agent's actions when invoked?* (skill, agent def,
hook behavior, prompt, rubric)
→ Behavior. Home = **the system whose surface it operates**: engineering workflow → clauDNA;
fleet operations → Claudlobby; a host adapter for a contract → the contract's owner (Claudron's
`hooks.py` is the engine's Claude Code adapter). Embedded reference payload → apply **Q-closure**:
does it change when the *procedure* changes (closure — stays with the skill) or when the *world or
an SSOT* changes (library — it is referential; move it or render-with-gate)?

**Q2 — Consulted?** *Is its job to be true?* (findings, decisions, gotchas, specs, postmortems)
→ Referential. The plane doctrine, then the two location tests, unchanged: repo speaking about
itself → `<repo>/documentation/`; the operator/fleet's outside view → the vault, tier by *"would
this hold if the repo didn't exist?"* and reach (`VAULT-STRUCTURE.md`).

**Q3 — Composed?** *Is its job to wire, grant, or supervise?* (config, fragments, templates,
lifecycle scripts, units, grants)
→ Runtime. Claudlobby.

**Residue:** change-coupling. *What must change in the same commit when this changes?* Place it
with that. (This is the generalization of both location tests, the plane doctrine, and the
durability×coupling rule — they are all coupling tests.)

### 10.4 The contract register

The institution §4 was missing. Rules first, then the v1 register.

- **R1 — one owner.** Every cross-system agreement has exactly one owner: the system that keeps the
  promise.
- **R2 — text lives with the owner**, normative, versioned, PR-reviewed in the owner's repo.
- **R3 — consumers conform, never fork.** A pointer, or a rendered copy carrying a machine drift
  gate against the owner's text (the `output-guide.md §3` pattern — already shipped, already the
  model).
- **R4 — changes PR the owner.** Generalizes SCHEMA.md's *"sibling schema changes must PR Claudron
  first."*
- **R5 — owners never sniff consumers.** Capability is *declared to* the owner (env, config, an
  install artifact named by the contract) — never inferred from a consumer's name or tree shape.
- **R6 — consumers never assert an owner's unshipped surface.** Validate against the version you
  pin (`claudron_compat.py`'s floor table is the right shape; the phantom-MCP warning is the
  violation).
- **R7 — every contract states its version window** (clauDNA's `requires: cli: claudron>=0.2`
  already does).

| # | Contract | Owner | Authoritative text (today) | Status / gap |
|---|---|---|---|---|
| 1 | Note schema | Claudron | `SCHEMA.md` | ✓ ratified; consumers conformant |
| 2 | Vault structure & tenancy | Claudron | `VAULT-STRUCTURE.md` | ✓ ratified; §Consumption(b) still implies an MCP consumer — amend |
| 3 | CLI ABI (exit codes, channels, envelope, verbs) | Claudron | `docs/CLI_CONTRACT.md` | ✓ exists; missing §Environment and §Bridge-file; missing the any-agent `INTEGRATION.md` front door decision C already *cites as if it existed* |
| 4 | **Vault address** (env names, precedence, `.claudron` bridge format) | Claudron | **none — scattered** | the live fracture: engine reads `CLAUDRON_VAULT_PATH` → `CLAUDRON_VAULT` (`cli.py:75–84`); clauDNA reads `CLAUDRON_VAULT` → `CLAUDRON_VAULT_PATH` → `SHARED_DOCS_PATH` (**inverted**); `init` prints the deprecated spelling (`cli.py:271`); Claudlobby works around a fixed bug (`dispatch-task.sh:103`) |
| 5 | **Session-loop protocol** (roles, ordering, single-prompt rule, claim mechanism) | Claudron (knowledge roles) | **none — changelog lore** (clauDNA CHANGELOG 0.17.0 "hook stacking"; `hooks.py` docstrings) | the deferral is a name-sniff (`hooks.py:62`), violating R5; fleet bots run **no Claudron loop at all** (§10.5.1) |
| 6 | Write protocol (capture-only, `--stdin`, `written` signal, create-only, guarantee ladder) | Claudron | `CLI_CONTRACT.md` §capture (partial) | cross-host guarantee ladder undocumented; no `--source-url`, so clauDNA couples provenance to `session.py:_summary` behavior |
| 7 | Plugin skill surface (`/claudna:*`, `SKILL_CONTRACT`, `session.md` handoff artifact) | clauDNA | its repo | `session.md` is consumed by Claudlobby (`start-bot.sh:296–322`, `lib-common.sh:1098` parses `last_updated:`) but never declared a stable surface — register it |
| 8 | Fleet composition (fleet.yaml schema, bot env, grants, plugin defaults) | Claudlobby | its repo | ✓; `known_values.py:90–155` hand-tracks clauDNA's skill renames (R3 by hand — fragile, needs a gate or a feed) |
| 9 | Consumption-door policy (CLI floor; MCP demand-gate, triggers, monitor) | Claudron | decision-C doc | trigger 1 needs re-scoping after #644 (§10.5.2); monitor should be a named check, not a human habit |

### 10.5 The hard cases, resolved

#### 10.5.1 The session loop — a protocol with roles, not a place

The loop is not a fourth *system* (a shared package would violate marketplace-only distribution and
the standalone-leaf identity; a fourth repo adds a seam to a problem made of seams). It is the
stack's most important **contract**, and it decomposes exactly:

| role | content class | owner | today |
|---|---|---|---|
| R-continuity — workspace brief (git, `gh`, `session.md` handoff) | behavior | **clauDNA** | ✓ `session-start.sh`; never touches the vault |
| R-recall — knowledge brief (pull → recall, budgets, abstention) | engine op | **Claudron** | ✓ `hooks.py` / `session.py` |
| R-capture-prompt — the distill nudge (one per session) | engine protocol | **Claudron** defines; exactly one *holder* per session | clauDNA holds it when installed — but via Claudron's name-sniff |
| R-sync — pull at start, push at end | engine op | **Claudron** | ✓ clauDNA ships no SessionEnd hook, by design |

**The two loops do not merge — and they should not.** The two SessionStart briefs carry different
content classes (workspace continuity vs durable recall); co-injection is correct. What was wrong
was never the *number of briefs* — it was that the composition rules (who holds the capture prompt,
who syncs, in what order, under what combined budget) lived nowhere. The fix is a **session-loop
protocol** section in Claudron's consumption contract defining the four roles, the ordering
(pull precedes recall), the single-prompt rule, and the **claim mechanism** for R-capture-prompt:
a declared claim (composed env on fleets — Claudlobby sets it per bot; a specified install marker
otherwise), replacing the `hooks.py:62` plugin-cache sniff. Same zero-config outcome, but the rule
becomes contract text a third implementation could satisfy — today it is an implementation secret
between two repos' comments.

**The verification finding that reframes this case:** the fleet — the deployment the two-loops
question was asked about — runs **neither loop fully**. Nothing installs Claudron's hooks on a
composed bot (no composer path, no `lib/` script), so fleet bots get clauDNA's continuity brief and
capture prompt but **no vault pull-before-recall and no SessionEnd push**; vault sync on a fleet
host has no owner at all. The "two knowledge loops" of §4.1 are a *workstation* phenomenon; the
fleet's actual problem is **zero knowledge loops**. Wiring the loop per bot is composition —
Claudlobby's job, declaratively (`vault-wired ⇒ install the engine's hooks / claim schedule`), per
the protocol contract. This is the re-architecture's largest single work item (deliverable b).

The index question dissolves under the same contract: engine present ⇒ `.claudron/index.json` is
*the* index (derived, disposable); `INDEX.md` is the frozen fallback's artifact and a human
navigation convention — never consulted when the engine answers. clauDNA's fallback-freeze doc
already states this; it becomes contract text instead of consumer lore.

#### 10.5.2 The consumption door — Claudron owns the door; clauDNA is ergonomics over it

Reasoning from the facts alone: an engine whose only sanctioned fleet door is one consumer's skill
pack has its adoption gated by that consumer (§4.2 is real). But the cure is not a new transport —
the CLI **is** a vendor-neutral door (any agent that can run a subprocess can consume the hub;
`--json` is typed; the contract doc exists). What Claudron lacks is **ownership artifacts**, not a
door:

- **`docs/INTEGRATION.md`** — the any-agent quickstart decision C cites as its mitigation. **It
  does not exist** (verified: `docs/` holds only `CLI_CONTRACT.md`). Write it: resolve the vault
  (contract #4), query before / write after (contract #6), envelope discipline, no-engine behavior.
- **Discovery** — the honest residual of parking MCP is in-context discovery. For any host running
  Claudron's hooks, the recall brief *is* the in-context discovery channel (it already injects
  vault context per session; one hint line closes the loop). For foreign agents, their operator
  reads `INTEGRATION.md` — the same story as every CLI tool. True self-announcement for arbitrary
  MCP-speaking agents remains gated behind a *concrete* such consumer (trigger 2).
- **The runtime validates the door that exists.** `validator.py:403–414` warns vault-path ⟹ MCP
  config — the inverse of reality, and the §6 trigger. Invert it: vault-wired ⟹ `claudron` CLI
  resolvable (+ compat floor met, via `claudron_compat.py`, whose docstring already claims a doctor
  check that was never built). clauDNA's skills stay exactly what they are — the *ergonomics* of
  the door on Claude Code hosts: verbs, prompts, fallback. Ergonomics are replaceable; the door is
  not.

**Decision C: gate affirmed, framing revised, trigger re-scoped.** The demand-gate holds on
independent grounds — no MCP consumer exists, and §6's pain is a validator bug, not a missing
transport. But verification narrows trigger 1: the #644 grant machinery can now express per-verb
CLI gating (`Bash(claudron lookup *)` allow + `Bash(claudron capture *)` deny; deny-wins —
`composer.py:1307–1454`, grammar `validator.py:69–79`). That is pattern-grade, not structural — an
agent can spell an invocation many ways — so trigger 1 survives only in its adversarial-grade form:
*a fleet policy that must be non-circumventable at the permission layer*. For a cooperative fleet,
#644 already answers the read/write split. Net: MCP's remaining un-park conditions are (1′)
adversarial-grade per-verb enforcement, (2) a concrete non-clauDNA MCP consumer. The monitor
becomes a named check (compat floor + validator), not a human habit.

#### 10.5.3 The write path across hosts — mechanism / policy / protocol

Three concerns, three owners; §4.3 blurred because they were fused:

- **Mechanism — Claudron.** flock per host + atomic replace (`locking.py`, limits honestly
  documented), dedup-routes-not-rejects (`engine.py`), rebase + quarantine cross-host (`sync.py`).
- **Protocol — Claudron contract text.** All writes through `capture` (one engine path in);
  create-only, vault-contained; `--stdin` for programmatic writers; branch on `written`. Plus the
  missing piece: a **guarantee ladder**, stated in `CLI_CONTRACT.md` — *per-host: serialized
  (flock); cross-host: eventually consistent, conflicts quarantined for a human; multi-writer
  exclusion: out of scope by constraint* (it would demand a daemon — §8 forbids it). Collisions are
  rare by construction — create-only distinct slugs, derived index gitignored — leaving same-slug
  creates, `--update` appends, and `CONVENTIONS.md` as the honest conflict surface, which quarantine
  covers.
- **Policy — Claudlobby.** *Who* may write, from *which* bots, on *how many* hosts is writer
  topology — fleet policy, now expressible with #644 grants (single-writer-per-vault as the default
  fleet posture; capture granted to designated bots). Claudron never parses fleet.yaml; Claudlobby
  never implements locks.

#### 10.5.4 The vault address — one name, one owner, one table

Worse than §4.4 stated: not three spellings but **inverted precedence** — with both vars set and
disagreeing, the engine and clauDNA resolve *different vaults*. Resolution: contract #4, owned by
Claudron as a §Environment table in `CLI_CONTRACT.md`. Canonical name: **`CLAUDRON_VAULT_PATH`**
(what the composer already emits, what the CLI already reads first). `CLAUDRON_VAULT` becomes a
deprecated alias (read second, warn, removal scheduled); `SHARED_DOCS_PATH` is clauDNA
fallback-mode-only, never consulted when an engine is present. The `.claudron` bridge-file format
(`vault=<path>`) is the same contract's §Bridge. Consumer fixes fall out mechanically: clauDNA
re-orders its ladder; `cli.py:271` prints the canonical name; `dispatch-task.sh:103` drops the
workaround and its false comment.

#### 10.5.5 The inverse cases — closure vs library, format vs ownership

- **clauDNA skills embedding reference material** (verified inventory: `audit/*/scan-categories.md`
  at 205/121 lines, infra verb files carrying vendor-CLI references, the dbt cheat-sheet, ironclad
  lenses): apply Q-closure. A rubric that versions with the *method* is procedural closure — it
  stays. Content that tracks the *world or an SSOT* is a library — move it to the vault (or render
  it with a drift gate, the §output-guide pattern). The observable signal for promotion: the fleet
  starts *consulting* it outside the skill's execution.
- **Claudlobby's knowledge categories** (`library/lessons/` 25 notes, `resources/`,
  `integrations/`, `protocols/`, `principles/`): `lessons/` is squarely the corpus the mission
  assigns to Claudron — operational findings, incident residue. Target: fleet-consumed knowledge
  lives in the vault (`_shared/` or fleet tier per the location tests); Claudlobby *composes from*
  the vault (it already resolves fleet overlays from it) rather than owning a parallel corpus.
  Delivery (composed-into-CLAUDE.md vs queried) is a runtime choice; **ownership of durable
  knowledge is not**. `resources/`/`integrations/`/`protocols/` triage the same way in deliverable
  (b) — composition *config* stays, world-truth moves.
- **Claudlobby's 44 skills**: stay (§10.1 — format ≠ ownership); the mission sentence is reworded
  to say what was always meant: *engineering-workflow* behavior is clauDNA's; fleet-operations
  commands are runtime content.
- **Claudron's runtime-flavored surfaces**: `plug`/`config`/`migrate` are consumption-contract
  tooling and stay — but the *Claudlobby tree-shape walk* (`cli.py:104–113`) and the *clauDNA
  plugin sniff* (`hooks.py:62`) are R5 violations in the engine; both retire in favor of declared
  contract artifacts (the bridge file the caller names; the claimed capture-prompt env).
- **The template tail**: `templates/claude.md.j2` §Shared Documentation still stamps the legacy
  raw-tree convention into every bot; when a bot is vault-wired it should stamp the door
  (`/claudna:recall`, `/claudna:capture`, contract #4) instead.

#### 10.5.6 The triggering example (§6), answered

The bot is not misconfigured; the validator is asserting a door the engine deliberately never
shipped (an R6 violation). The fleet-consumption door **is Claudron's CLI contract**; the bot
already walks through it via clauDNA's skills. Fix: validator inverts to check the CLI door
(claudron resolvable + vault detected + compat floor); the phantom-MCP cross-check is deleted, and
`library/mcp/claudron.json` stays unbuilt until decision C's re-scoped triggers fire. No fork
needed — the boundary names one owner and the answer falls out.

### 10.6 Where this extends vs revises the prior art

**Extends (independent grounds):** the triad, kept as the content register with sharpened questions;
the two location tests + plane doctrine, generalized to the change-coupling residue rule; the trust
ladder and curation model, untouched; decision C's demand-gate, affirmed (with trigger 1 re-scoped
on the #644 facts); the fallback-freeze and render-with-drift-gate patterns, promoted from consumer
lore to register rules (R3, R6).

**Revises (explicit departures from Appendix Z's lean):**
1. *"The triad is the finished boundary"* — no: it is half. It places content only, conflates
   format with ownership at `library/skills/`, and cannot place any of §4. The contract register is
   the other half.
2. *"One vault, one hook owner"* (2026-07-09 lean) — revised to **one owner per role**: the briefs
   legitimately stay two; capture-prompt and sync get single owners; the composition rule becomes
   contract text with a declared claim, not a name-sniff. And the premise was workstation-scoped:
   the fleet's real state is *zero* loops, which no "one hook owner" framing would have caught.
3. *"Decision C routes fleet consumption through clauDNA"* — reframed: **the door is Claudron's CLI
   contract; clauDNA is ergonomics over it.** Same shipped bits, inverted ownership — and the
   inversion is what removes the hostage problem (§4.2), obligates `INTEGRATION.md`, inverts the
   validator, and makes "does Claudron need a vendor-neutral door?" dissolve: it has one; it never
   *owned* it.
4. The session loop is not "a fourth concern needing a home" — it is a **contract needing an
   owner**, plus one missing deployment (the fleet).

### 10.7 Placement drill (the test, run)

| artifact | Q-path | home |
|---|---|---|
| `audit/security/scan-categories.md` | Q1 → closure (versions with the method) | clauDNA, stays |
| `library/lessons/*.md` (25) | Q2 → outside view, fleet-durable | vault tier; Claudlobby composes from it |
| `library/skills/dispatch/` | Q1 → operates the runtime | Claudlobby, stays |
| `hooks.py` | Q1 → adapter of the engine's contract | Claudron (sniff retired per R5) |
| `CLAUDRON_VAULT_PATH` name | Q0 → contract #4 | Claudron text; consumers conform |
| `session-start.sh` brief | Q1 → workspace behavior | clauDNA, stays |
| `validator.py` vault↔MCP check | Q0 → R6 violation | inverted to CLI-door check |
| `claude.md.j2` §Shared Documentation | Q3 → composition template | Claudlobby; content updated to stamp the door |
| `output-guide.md §3` enum table | Q0 → rendered copy w/ gate | conformant — the model |
| `session.md` handoff artifact | Q0 → contract #7 | clauDNA declares it; Claudlobby consumes it |
| "which bot may capture" | Q3 → policy | Claudlobby grants (#644) |
| `INTEGRATION.md` (missing) | Q0 → owner artifact of #3 | Claudron `docs/` |
| PreCompact prompt text | Q0 → R-capture-prompt holder | Claudron defines; one holder per session |
| a flaky-deploy gotcha about repo X | Q2 → outside view | vault `projects/X/` |
| `fleet.yaml` schema | Q3/Q0 → contract #8 | Claudlobby |

Fifteen artifacts, one home each — including every §4 ambiguity and the §6 trigger (criteria §9.1,
§9.3). No capability is left implemented twice once the register's gaps close (§9.2): one session
protocol, one address table, one write path, one door.

### 10.8 Verification deltas — facts found that amend §1–§9

1. **The env fracture is inverted precedence, not just three spellings** (§4.4 understated it):
   clauDNA resolves `CLAUDRON_VAULT` *first*; the engine resolves `CLAUDRON_VAULT_PATH` first. Both
   set and disagreeing ⇒ two different vaults.
2. **Fleet bots run no Claudron session loop** (§4.1 framed two loops; the fleet has zero): nothing
   installs the engine's hooks per bot; vault sync on fleet hosts is unowned. R-recall arrives only
   via the opt-in `dispatch-task.sh` pointer wedge for manager bots.
3. **#644 landed per-verb CLI gating** (pattern-grade): decision C's "grounded capability gap" — a
   skill wrapping the CLI is one blanket grant — is no longer true as stated; trigger 1 narrows to
   adversarial-grade enforcement (§10.5.2).
4. **"Claudlobby does not define skills" is false at head** — 44 `SKILL.md` files; resolved as
   format-vs-ownership (§10.1), sentence to be reworded, files stay.
5. **`library/lessons/` is a 25-note knowledge corpus in the runtime repo** — the clearest
   referential-content-in-runtime case (§10.5.5).
6. **`docs/INTEGRATION.md` does not exist** though decision C cites it as the vendor-neutral
   mitigation; the prior ironclad (rescope record §E) flagged this and the #644 check — both were
   still open.
7. **`claudron_compat.py`'s docstring claims a `doctor` check that was never built** (its only
   consumer is its own test) — a small R6-adjacent drift on the runtime side.
8. **The `[vault]` extra is now pinned** (`claudron @ …@v0.2.0`) — §3's roadmap-era "unpinned"
   caveat is resolved.
9. **clauDNA ships no SessionEnd hook by explicit design** ("SessionEnd is Claudron's `sync
   --push`", CHANGELOG 0.17.0) — the role split of §10.5.1 is already half-practiced.
10. **`known_values.py:90–155` hand-tracks clauDNA's skill renames** — an unregistered, gate-less
    conformance copy (contract #8's gap).
11. **capture lacks `--source-url`**, so clauDNA folds provenance into a trailing body line keyed to
    `session.py:_summary`'s behavior — a consumer coupled to an engine implementation detail
    (contract #6's gap).

---

## Appendix Z — SEALED: prior thinking from the ecosystem *(challenge; do not adopt)*

> Read this **last**, and treat it as one fallible input. It includes the boundary the ecosystem
> already asserts and the direction recent sessions landed on — **agreement is a warning sign, not a
> confirmation.** The value of the visioning pass is an independent boundary derived from §1–§9, even
> if it contradicts everything below.

- **The current lean — the triad is treated as settled:** *procedural = clauDNA / referential =
  Claudron / runtime = Claudlobby*, taken as the finished boundary. Pressure-test whether the triad
  actually places *every* file, or whether it conflates ≥2 axes. The sharpest suspect: **the session
  loop** — hooks, the SessionStart briefs, the PreCompact capture cadence, the index — is neither
  cleanly procedural nor cleanly referential, and today it lives *split* across clauDNA's hooks and
  Claudron's hooks (§4.1). If the triad can't name one owner for the loop, the triad is incomplete.
- **Where recent thinking landed (decision C, 2026-07-18):** the fleet-consumption door is clauDNA's
  CLI-skill door **by default**; Claudron's MCP server is **parked, demand-gated** (triggers:
  per-tool permission gating tied to Claudlobby's permissions epic, or a non-clauDNA MCP consumer —
  neither exists yet). Challenge: does routing *all* fleet consumption through clauDNA make Claudron's
  adoption **hostage to clauDNA** (a single point of failure)? Should Claudron own a vendor-neutral
  door regardless — and if so, is that door the CLI itself, promoted to a first-class product surface?
- **The reconciliation lean (2026-07-09):** point clauDNA's knowledge home at the Claudron vault; pick
  **a single owner per hook** so SessionStart/PreCompact don't double-fire; let `/capture` be the
  fleet's write verb while Claudron owns transport + index + ranking. **Partly executed** already
  (Claudron's PreCompact defers to clauDNA; both markers accepted). Challenge: is *"one vault, one
  hook owner"* the right unification — or is the session loop a **fourth concern** that deserves a
  single home rather than being split-then-reconciled forever?
- **The substrate/curation bets (treated as settled):** markdown + git forever; MCP optional-stdio,
  never a daemon; SQLite/FTS5 deferred behind a *measured* trigger (a recall eval showed ~95% recall@5
  at small-to-mid vault sizes); **curation-first** retrieval (promote to `canonical`, build hubs) as
  the default scaling route. Stress-test the **inverse red-team** too: how much of clauDNA's ~37
  "procedural" skills actually encode *referential* knowledge that belongs as Claudron notes — and is
  any "referential" Claudron surface actually *runtime*?
- **Known unknowns the prior thinking did not resolve:** the exact home for **session-loop
  orchestration** (clauDNA? Claudron? a shared contract?); whether the two knowledge loops **truly
  merge** or are legitimately separate-by-purpose (local git/`gh` continuity vs vault recall); whether
  Claudron needs its **own vendor-neutral fleet door**; the real cost of **CLI-as-ABI across hosts**
  (the multi-writer / quarantine boundary, §4.3); and whether the split vault-path spellings (§4.4)
  point to a missing single **config contract** the three systems should share.

---

*Origin: authored 2026-07-20 from the three repos' current state — Claudron @ working checkout;
clauDNA @ the shipped v0.17.0 line (the Claudron-integration release); Claudlobby @ HEAD. A
facts-first brief that seeds a neutral boundary-visioning pass; §1–§9 are facts, Appendix Z is sealed
prior thinking to challenge.*
