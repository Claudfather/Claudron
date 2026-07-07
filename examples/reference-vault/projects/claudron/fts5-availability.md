---
title: FTS5 Availability Notes
type: knowledge
status: current
maturity: draft
owner: capture-bot
tags: [sqlite, fts5, claudron]
created: 2026-07-04
updated: 2026-07-04
confidence: medium
source_url: https://sqlite.org/fts5.html
source_type: url
schema_version: 1
---

# FTS5 Availability Notes

FTS5 is compiled into the default macOS and most Linux system Pythons (as
of 2026-07, sqlite.org/fts5.html); exotic builds may omit it — detect with
a `CREATE VIRTUAL TABLE` probe, fall back to scan mode with a persistent
degraded-mode notice.
