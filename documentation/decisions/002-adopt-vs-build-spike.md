---
title: "Adopt-vs-build spike — the E4 indexer (Basic Memory / Graphify)"
type: plan
status: active
owner: chris
tags: [spike, gate, g1, e4, indexer, claudron]
created: 2026-07-18
updated: 2026-07-18
---

# Adopt-vs-build spike — the E4 indexer

**The G1 gate artifact** (per `2026-07-07-claudron-roadmap/00-overview.md` §Gate
G1): a build-vs-adopt decision that merges **before any E4 build PR opens**, so a
spike can't be bundled with — and rubber-stamp — the build it gates.

**Scope note (decision C, 2026-07-18):** E3/MCP is now demand-gated, so the
adopt targets are evaluated against **E4** — the SQLite FTS5 + wikilink-graph
indexer (`04-indexer.md`) — not the MCP server. Both candidates happen to ship
MCP servers; that is no longer the axis we're buying on.

## The question

Build E4's indexer ourselves — stdlib `sqlite3` + FTS5 (BM25) + an `edges`
table + `resolve_wikilinks`, ~4 small PRs per `04-indexer.md` — or **adopt Basic
Memory** / **consume Graphify**?

## Verdict (up front)

**BUILD E4. Adopt neither. Borrow two specific ideas.** Both tools independently
validate our "vault is the source of truth, the index is a disposable SQLite
mirror" bet; neither is adoptable without ceasing to be Claudron.

## Candidate 1 — Basic Memory → **do not adopt; build**

**What it is** (confirmed 2026-07-18): `basicmachines-co/basic-memory`, **~3.5k
stars, v0.22.1 (2026-06-13), 87 releases** — actively maintained, company-backed
(paid cloud tier atop free local OSS). Architecture is a **near-twin of ours**:
markdown files are the source of truth, a rebuildable **SQLite** database is a
secondary index; retrieval is **hybrid FTS + vector (FastEmbed) + wikilink-graph
traversal**. It is, in effect, a shipped superset of E4's wishlist *plus* the
embeddings we deliberately deferred.

**Why not adopt — it fails on all four of our pillars:**
- **License: AGPL-3.0-or-later — a hard blocker.** Importing it as a library
  virally relicenses the combined Claudron work to AGPL (with the §13 network
  clause). You cannot embed it and keep Claudron MIT; the only arm's-length path
  is running it as a separate rival server (two schemas, two indexes — which
  defeats E4's purpose).
- **Schema SSOT: lost.** Basic Memory's entity / observation (`- [category]
  fact`) / relation markup + `permalink` **is** its schema; adopting it demotes
  `SCHEMA.md` from governing SSOT to "must conform to Basic Memory's shapes."
- **PyYAML-only minimalism: dead.** You inherit ~25 deps — FastAPI, SQLAlchemy,
  Alembic, fastmcp, and an embeddings/LLM stack as **core** (`fastembed`,
  `sqlite-vec`, `openai`, `litellm`) — and Python ≥3.12.
- **CLI contract: doesn't map.** It's MCP/daemon-first (FastAPI service +
  file-watcher), not a thin argparse CLI with our `--json` envelope, exit codes,
  and `CLI_CONTRACT.md`. Embeddings-deferred is also *reversed* — they're core.

**What it IS to us:** the best possible **reference implementation** — independent
convergence on our exact architecture proves the E4 design is sound.
**Borrow (design, not code):** its FTS + wikilink-graph + sync-pipeline layering
as a design reference, and its **"hybrid search as default with keyword
fallback"** posture as the model for our *deferred* `[vector]` tier and its
named build-triggers (D6/F2).

## Candidate 2 — Graphify → **not a dependency at all; borrow ideas only**

**What it is** (confirmed 2026-07-18 via GitHub API + repo): `Graphify-Labs/graphify`
— **MIT, Python 3.10+, ~90k stars** — is **not a graph engine or library.** It's
an **AI-coding-assistant *skill*** (a `/graphify` slash command for Claude Code /
Cursor / Codex, plus a CLI) that turns a folder of code/docs into a queryable
knowledge graph: tree-sitter AST parsing for code (deterministic, local) **+ an
LLM pass (needs a Claude API key)** for non-code, assembled with NetworkX +
Leiden community detection, persisted as `graph.json`. It is GraphRAG **without
embeddings** ("a graph it can trace and cite").

**Maturity caveat:** the star count is loud but young — repo **created 2026-04-03
(<4 months old), pre-1.0 (v0.9.x), releasing every 1–2 days, ~550 open issues.**
Viral-hype trajectory; stars ≠ production hardness.

**Why not — it's a different problem *and* there's nothing to link against.**
Graphify **maps** a codebase; it does not **accumulate governed memory** ("a map,
not a brain"). Its edges come from AST + LLM concept-extraction — there is **no
`[[wikilink]]` edge derivation** and no unresolved-link-as-first-class-node. And
it's a skill + CLI persisting `graph.json`, **not an embeddable graph API** — so
it can't even be "consumed as a library." E4's actual need (regex `[[...]]` →
`edges` rows, resolve, traverse with recursive CTEs) is a few dozen lines of
stdlib; adopting Graphify would drag in NetworkX + graspologic + tree-sitter **+
a Claude API key** and a second, conflicting graph store, to solve a problem we
don't have.

**What it IS to us:** a **complement, not a competitor** — a bot can *map* a repo
with the Graphify skill and *remember* what the fleet learned with Claudron; and
its 90k-star "traversable graph over vector similarity, no embeddings" thesis is
loud market validation of Claudron's core bet.
**Borrow (ideas only):** its `EXTRACTED`/`INFERRED`/`AMBIGUOUS` **edge-provenance**
tags (E4's edges are author-written = `EXTRACTED`; resolved-vs-unresolved maps
onto this cleanly; tag `INFERRED` only if a `[vector]` tier ever adds
machine-derived relations); **Leiden community detection** as a plausible *future*
"related-notes clustering" experiment; and its **published-benchmark discipline**
as the model for publishing E4's before/after recall@10 numbers.

## What's ours either way — untouched by either tool

The schema SSOT (`SCHEMA.md`), recall/capture CLI semantics + the `--json`
envelope contract, the vault-is-SSOT / index-disposable substrate, the
`status`/`maturity` two-axis model, packs (E6), and scenario export. These are
Claudron's value; neither candidate provides or preserves them.

## Why build wins on our criteria

| Criterion | Build E4 | Adopt Basic Memory | Adopt Graphify |
|---|---|---|---|
| Dependencies | stdlib `sqlite3` only | ~25 (incl. LLM stack) | heavy graph engine |
| License | stays MIT | **AGPL — viral** | MIT (but wrong problem) |
| Schema SSOT | ours | theirs | theirs |
| CLI `--json` contract | preserved | lost (daemon-first) | lost |
| Effort | 4 small PRs (`04-indexer.md`) | integrate + relicense + reshape | integrate a mapper we don't need |
| Embeddings | deferred by design | core, non-optional | n/a |

The disposable-derived-index pattern is field consensus (both tools do it); we
build the **minimal** version of that consensus and keep everything that makes
Claudron itself.

## Conditions that would flip this (named triggers)

- **Basic Memory never flips to wholesale adopt** (AGPL forecloses it). If E4's
  hybrid `[vector]` tier is ever built, vendor the *narrow* pieces as an optional
  extra — **FastEmbed / sqlite-vec** (permissive, embeddable) — not Basic Memory.
- **Graphify never becomes a dependency** — it's a complementary *skill*, not a
  library to link against. Only relevant if Claudron ever grows a
  repo-understanding feature, and even then it runs alongside, not inside.

## Consequence

This settles only the **adopt-vs-build (HOW) sub-question**: if we build E4's
engine, we build it ourselves. It does **not** authorize opening the SQLite PR —
that WHEN/what-shape call belongs to the re-scope (`2026-07-18-ironclad-rescope-record.md`
Theme C + `G1-verdict.md`), which **splits E4**: pull the scale-free **graph
slice** (`resolve_wikilinks` + `links`/`related`) forward and **defer the
SQLite/FTS5 mirror** behind the measured D6/F2 trigger. Opening any E4 build PR
still requires a **G1-verdict PASS** (a merged spike is a gate *dependency*, not
the verdict). E3/MCP stays demand-gated (decision C); the adopt-vs-build question
for a *future* MCP server, if a trigger ever fires, is a separate, later spike.
