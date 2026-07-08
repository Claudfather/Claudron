---
title: Deploy Rollback Runbook
type: runbook
status: current
owner: alex
tags: [deploy, operations]
created: 2026-05-30
updated: 2026-07-01
last_verified: 2026-07-01
schema_version: 1
---

# Deploy Rollback Runbook

Rollbacks are image-tag reverts, not new builds. The previous tag stays
warm for 24h after every deploy. Database migrations are forward-only —
a rollback never reverses one, so releases that migrate must be
backward-compatible for one version.
