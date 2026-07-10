# Project Mission — Claudron

## What this project is

Claudron is a markdown-based knowledge graph designed for agent fleets. Each deployment owns a vault — a directory of markdown files with YAML frontmatter and wikilinks — and bots read and write to it via an MCP server. The vault is the source of truth; an indexer maintains a SQLite mirror for fast queries and optional vector similarity.

The metaphor: a cauldron. Raw observations from bots go in (findings, decisions, gotchas). They mix with prior content via wikilinks, get cross-referenced, get curated. Refined patterns come out — both as queryable context for future bots and as candidates for promotion into skills.

It's deliberately not "Obsidian for bots." Obsidian is one possible editor a human can use to browse the vault. The substrate is plain markdown files in a git repo, which means humans can use any editor, the data is portable, and everything is version-controlled.

## What it's becoming

The default knowledge substrate for Claudfather bots, and a standalone OSS project for any agent fleet. Vaults are git repos owned by the tenant. Hybrid retrieval combines graph traversal (for "what's related to what I know") with vector search (for "I don't know where to start"). Public packs let deployments share curated subsets without giving up local control. Federation across instances may come in v2 or never.

## North star

A hive mind any agent fleet can run locally and optionally federate.

## Guiding principles

- **Markdown + frontmatter + wikilinks as source of truth.** No proprietary format. The vault is plain files in a git repo. If Claudron disappears, the data still works.
- **Local-first vault.** Tenants own their vaults. No data leaves the tenant unless they explicitly publish a public pack.
- **Graph traversal over vector similarity.** Vector search is a useful escape valve for "I don't know what I'm looking for." Explicit links are the primary structure. Wikilinks are written by bots as part of recording findings, not inferred post-hoc.
- **Provenance and lifecycle.** Every note tracks who wrote it, when, with what confidence, in what status. Old or deprecated content stays queryable but flagged.
- **Procedural vs. referential is enforced.** Claudron stores reference content. Procedural knowledge (skills) belongs in clauDNA. The schema makes the distinction enforceable.
- **Curation is part of the model.** Bot-written content gets noisy fast without a lifecycle. Draft → verified → canonical with explicit promotion is built in from day one.
- **Pack publishing as opt-in federation.** Federation happens through git, not through a centralized service. A public pack is just a public git repo.

## Position in the ecosystem

**Consumes:** findings written by Claudlobby bots during operation; subscribed public packs from other Claudron deployments; manual curation by humans editing the vault directly.

**Produces:** queryable context that bots fetch before tasks; public packs that other deployments can subscribe to; real-world scenarios that Claudosseum can pull as battle inputs (local for private arena, public packs for public arena); pattern detections that may seed new skill candidates for Claudosseum.

**Sibling boundaries:**
- Claudron does not store skills. clauDNA does.
- Claudron does not evaluate or promote anything to skills. Claudosseum does.
- Claudron does not run bots. Claudlobby does.
- Claudron does not require a hosted service. It runs entirely on a tenant's own infrastructure.

## In bounds for autonomous work

**Standing permissions:**
- Bug fixes in MCP server, indexer, CLI
- Documentation including the reference vault
- Test additions and coverage improvements
- Performance improvements to indexer (incremental rebuild, query latency)
- New CLI helper commands (read-only diagnostics, vault validation)
- Improvements to graph traversal and search ranking that don't change the API
- Additional example notes in the reference vault

**Current sprint focus:**
1. Note schema spec: types, required frontmatter, link conventions, `pack.yaml` format. Highest-leverage decision and blocks everything else.
2. MCP server v0.1: read, write, traverse, search tools that bots can call
3. Indexer: file watcher → SQLite mirror with frontmatter index and wikilink edges table
4. CLI: `claudron init`, vault path config, pack subscription config
5. Pack publisher: command that exports a curated subset of a vault as a properly-structured pack repo
6. Reference vault as documentation: a small example vault demonstrating the format, hosted in the Claudron repo

## Requires approval

- Note schema changes after v0.1 ships (highest-leverage and breaks downstream consumers)
- Vault directory-structure contract changes (`VAULT-STRUCTURE.md`) after ratification — the directory shape is an SSOT consumers conform to
- `pack.yaml` format changes
- New required frontmatter fields on existing note types
- Adding any hosted dependency to the default install path
- Changes to MCP tool surface (additions, signature changes)
- Federation work or any cross-tenant query capability (deliberately out of scope for v1)
- Adopting a non-SQLite storage backend for the index

## Success metrics

- Vault adoption: deployments using Claudron beyond just the maintainer
- Notes per vault growing over time (knowledge accumulation actually working)
- Query volume per vault (bots actually using it before tasks)
- Public packs published and subscribed (federation-by-git getting traction)
- Note lifecycle progression: % of drafts reaching verified or canonical status
- Pack subscription depth (vaults pulling from multiple packs)
- Indexer rebuild time staying flat as vault size grows

## What we choose not to build

- **Hosted vault storage.** Vaults are git repos owned by tenants. We are not running storage for anyone's knowledge base.
- **A central registry of public packs.** Discovery is informal at first — GitHub topics, README links, word of mouth. A central registry can come later if needed; building it now is premature.
- **A graph database backend.** SQLite + an edges table is plenty for the scale Claudron targets. Real graph DBs (Neo4j etc.) add operational burden without proportional value at this scale.
- **LLM-driven entity extraction at indexing time.** GraphRAG-style pipelines that use LLMs to build the graph are interesting but cost money, add latency, and aren't necessary when bots are writing wikilinks themselves.
- **A human-facing browse UI.** Obsidian, VS Code, and any other markdown editor work fine for human browsing. We won't build a custom UI for a problem already solved.
- **Real-time multi-writer collaboration.** Git's last-write-wins handles the multi-writer case for our scale. Conflict resolution UIs and operational transforms are overkill for the agent-fleet use case.
- **Cross-tenant queries by default.** Federation, if it happens at all, is opt-in instance-to-instance with explicit consent. There's no Claudron-wide query surface.
