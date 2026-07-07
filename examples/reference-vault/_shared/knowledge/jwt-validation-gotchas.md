---
title: JWT Validation Gotchas
type: knowledge
status: current
maturity: verified
owner: mason
tags: [auth, jwt]
aliases: [JWT Gotchas]
created: 2026-06-20
updated: 2026-07-05
confidence: high
schema_version: 1
---

# JWT Validation Gotchas

Clock skew between services breaks `exp` validation — allow 30s leeway (as
of 2026-06, confirmed across three services). Key rotation requires serving
the old JWKS for one full token lifetime; see the ratified
[[Auth Service Decision]] for why RS256 is mandatory.

Rate limiting interacts badly with token refresh storms — see
[[Rate Limiting Strategy]] (not yet written).
