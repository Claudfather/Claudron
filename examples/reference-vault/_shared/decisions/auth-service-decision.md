---
title: Auth Service Decision
type: decision
status: ratified
maturity: canonical
owner: chris
tags: [adr, auth]
created: 2026-06-18
updated: 2026-06-18
schema_version: 1
---

# Auth Service Decision

All services validate JWTs locally with RS256 against the shared JWKS;
auth-service is the single issuer. Symmetric signing was rejected: key
distribution to N services multiplies the blast radius of one leak.

Consequences recorded in [[JWT Validation Gotchas]].
