---
title: "E4 — Indexer v2: SQLite mirror, wikilink graph, real search"
type: plan
status: active
owner: chris
tags: [epic, indexer, search, sqlite, claudron]
created: 2026-07-07
updated: 2026-07-07
---

# E4 — Indexer v2: SQLite mirror, wikilink graph, real search

**Release:** 0.4.0 · **Depends on:** E1 (+ E2's dogfood queries for the eval
set) · **Parallel with:** E3, E6 · **Blocks:** E5 PR2–4 (E5 PR1 may pull
forward) · **Gated by:** G1 (incl. the adopt-vs-build spike)

## Goal

Replace the JSON frontmatter cache with a SQLite mirror — notes, full-text,
and wikilink edges — using nothing beyond the standard library. Retrieval
stops being heuristic substring scoring and becomes blended ranking: BM25
full-text + frontmatter boosts + tier priority + recency. `resolve_wikilinks`
stops being a stub. The mission's core retrieval principle ("graph traversal
over vector similarity; vector search as escape valve") gets its graph — and
the code finally matches the mission's own words ("an indexer maintains a
SQLite mirror"): today's `index.json` is the deviation, not this epic.

On issue #10, scoped honestly (panel): #10's headline ask is *semantic*
("'auth tokens' won't find 'OAuth credential rotation'"), which this epic
deliberately defers to the designed `[vector]` tier. E4 addresses #10's scale
and incremental-reindex halves; the issue stays open, annotated — not closed.

## Design

- **`.claudron/index.db`** (gitignored, rebuildable at will — the vault
  remains the only source of truth):
  - `notes` — frontmatter columns (title, type, status, tags JSON, aliases
    JSON, tier, path, created, updated, expires, owner) + content hash + mtime
  - `notes_fts` — FTS5 virtual table over title/headings/body (BM25)
  - `edges` — `(src_path, target_text, resolved_path NULL-able)` — unresolved
    links are first-class (they mark wanted notes)
  - `meta` — schema_version, built_at
- **Incremental reindex:** diff by mtime+hash per file; add/update/remove
  changed rows only. Replaces today's any-file-newer → full JSON rebuild.
  `claudron index --full` remains the nuke-and-rebuild.
- **No daemon, no watcher** in this epic: reindex runs on-demand at
  lookup/serve time when staleness is detected (cheap stat-walk already
  exists). A `watchdog`-based `[watch]` extra is explicitly deferred until
  dogfood shows staleness pain.
- **Ranking:** BM25 score normalized, then boosts: exact title/alias > tag >
  heading; tier priority (project > fleet > shared > other) as tiebreak;
  recency decay on `updated`; `maturity` boost (canonical > verified > draft,
  the D11 trust axis); terminal/expired down-ranked-and-labeled when a
  `superseded_by` pointer exists, filtered otherwise (as today).
- **Graph API:** `resolve_wikilinks(text, vault)` implemented per SCHEMA.md
  resolution rules (title → alias → slug, case-insensitive);
  `claudron links --broken --orphans` report; `related(path, hops=1|2)`
  engine call backing E3's `claudron_related` and a new
  `claudron related <note>` CLI.
- **Embeddings: deferred but designed (D6, amended by F2).** Field evidence
  moved this from "maybe never" to "expected upgrade with named triggers":
  both mature markdown-first systems added local-embedding hybrid fusion
  (obsidian-second-brain measured recall@10 80→91%, paraphrased 17→46%; Basic
  Memory made hybrid the default with keyword fallback). This epic therefore
  **designs** the hybrid tier and implements none of it:
  - `vectors` table reserved in the SQLite schema (not created)
  - Fusion spec: reciprocal-rank fusion of BM25 + vector scores, local model
    only (Ollama/FastEmbed-class), **silent lexical fallback + kill switch**
    (both adopted verbatim from the field patterns), shipped later as a
    `[vector]` extra — never default, never hosted
  - **Named triggers to build it:** paraphrase-miss rate on the eval set
    crosses agreed threshold, or the dogfood vault passes ~1k notes (the edge
    of attested FTS5-only territory)

## Compatibility

- `lookup()` keeps its signature and result shape; `cli.py` untouched except
  new subcommands. **The "Tier A / Tier B" vocabulary retires with the
  mechanism it named** (panel: inherited vocabulary outlives its model) —
  docs and code say "frontmatter boosts" and "full-text" from here on.
- JSON `index.json` is dropped, along with the now-dead `SCHEMA_VERSION`
  staleness gate (`vault.py:29`, `knowledge.py:189`) — auto-migration =
  rebuild. `sqlite3` is stdlib everywhere Claudron supports (py ≥3.10; FTS5
  compiled in on macOS/Linux default builds — CI asserts it and `validate`
  gains a doctor check).
- **The FTS5-less fallback is degraded mode, not status quo** (panel): scan
  mode is the exact 5.7%-recall regime this epic exists to escape, and at the
  F3 target scale it is materially worse, not equivalent. It stays as the
  safety net, but `status` and recall briefs surface "degraded search mode"
  persistently — not a one-time warning a user never sees again.

## Phased PRs

| PR | Scope |
|---|---|
| 1 | SQLite mirror + incremental reindex behind existing `lookup` (parity, no ranking change) |
| 2 | FTS5 + blended ranking + **`lookup --explain`** (per-result score decomposition + abstention-threshold verdicts for near-misses — the harness computes these numbers anyway; exposing them answers "why didn't my note surface" and feeds the F2 trigger) (+ eval harness: seeded from E2 PR4's checked-in set, **paraphrased variants included** — the F2 blind spot; the eval lands red before the ranking code) |
| 3 | edges table + `resolve_wikilinks` + `links`/`related` |
| 4 | E3 `claudron_related` cutover to edges; JSON index removal + migration note |

## Acceptance criteria

- Reindex after touching 1 file in a 1k-note vault: <100ms; full rebuild <5s
- Ranking eval: blended ranking beats current heuristic on the dogfood query
  set (E2 gives us real queries; the set is checked into `tests/eval/`)
- `resolve_wikilinks` handles title/alias/slug + case per SCHEMA.md, returns
  unresolved entries rather than dropping them
- `claudron lookup` results unchanged in shape; downstream (E2 recall, E3
  tools) require zero changes
- Graceful degradation proven in CI: FTS5-less build falls back to scan mode
  with a warning, not a crash

## Non-goals

- Embeddings/vector search (reserved table only)
- File watcher/daemon (`[watch]` extra deferred)
- Graph algorithms beyond 1–2-hop neighbors (no PageRank, no communities)
- Cross-vault/federated indexing (packs index locally like any tier — E6)

## Risks

- **FTS5 availability on exotic Pythons** → doctor check + scan fallback
  (above), surfaced persistently as degraded mode — the fallback is today's
  shipped behavior, which at target scale is the quality cliff, not parity.
- **Ranking regressions feel worse than absolute quality** → parity PR first,
  ranking PR second with the eval harness as the gate.
- **Index/vault divergence bugs** → the mirror is disposable by contract;
  `--full` rebuild is always safe and documented as the first debug step.

## Field evidence

See [07-field-research.md](07-field-research.md). This epic is where the
research bites hardest:

- **F2 makes ranking quality existential, with numbers:** naive keyword
  retrieval scored **5.7% recall@10**; BM25-grade fixes (stopwords,
  log-saturated TF, length normalization — exactly what FTS5's BM25 provides)
  took it to **80%**. Claudron's current substring-scoring heuristic sits on
  the wrong side of that gap; this epic crosses it.
- **F3 sets the ceiling for index-only retrieval at ~100–200 pages** — Tier A
  (frontmatter index) alone cannot serve the hundreds-to-low-thousands target;
  the FTS tier is load-bearing, not a fallback. The INDEX.md-as-catalog stays
  for humans; agents get real search.
- **F7 validates the exact architecture** — graph in the markdown, traversal
  from a derived rebuildable SQLite index — as Basic Memory's shipped design,
  with the in-database-graph MCP servers as the contrast class Claudron
  deliberately isn't.
- **Caveat carried forward:** the recall numbers are single-author,
  self-measured, one ~1,150-note vault; attested scale tops out ~1,200 notes.
  Hence the eval harness ships *in this epic* — Claudron measures its own
  vault instead of trusting the field's.
