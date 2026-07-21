# docs/ — placement guidance

Owned contract text. Files here are **normative for consumers** (fleet bots, clauDNA skills,
Claudlobby composition, any-agent integrations) — not repo commentary.

**What belongs here.** Contracts Claudron owns and keeps: the CLI ABI (`CLI_CONTRACT.md` — exit
codes, channels, `--json` envelope, vault resolution/environment), the any-agent integration front
door (`INTEGRATION.md`, boundary plan C1), the session-loop protocol (boundary plan C2). Note
schema and vault structure are the same register but live at the repo root (`SCHEMA.md`,
`VAULT-STRUCTURE.md`) with their approval gates.

**The register rules (short form — full set: boundary spec §10.4):**

- One owner per contract; the text lives here, versioned and PR-reviewed.
- Consumers point at this text or render it with a CI drift gate — never fork or re-assert it.
- A consumer needing a change PRs this repo first (the `SCHEMA.md` precedent, generalized).
- Never document a consumer by name as a mechanism — capabilities are declared to the engine.
- Breaking changes get CHANGELOG entries and a version window.

**What must never land here.** Repo-internal design records (those are
`documentation/plans/` — the plane doctrine); aspirational surfaces that are not shipped
(a contract for an unbuilt door is an R6 violation in the making — decision C's MCP spec stays
parked in `documentation/plans/` until its trigger fires).

**Placement test** (one line): must a consumer agree with this text to work? → here (or the
root SSOTs). Is it the repo deliberating with itself? → `documentation/plans/`. Full algorithm:
`documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3.
