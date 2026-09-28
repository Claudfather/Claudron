TITLE: [epic] Knowledge-layer deep dive: context bloat, the missing reduction loop, and session-loop fit across the Claudfather family
LABELS: planning

## Why this epic exists

This epic comes from a deep-dive review of Claudron as the knowledge layer of the Claudfather family. The review cross-references Claudlobby and clauDNA and asks two questions:

- **Caching and management:** does the system keep knowledge fresh and well organized?
- **Economy:** does it avoid context bloat and pointless backups?

Each child issue below covers one finding. Every child has:

- **Evidence**, with file:line references at Claudron `2c3c123`, Claudlobby `28bbab1` and clauDNA `69b84f4`.
- A **Test it on yourself** section: steps a fleet agent can run on its own host (the Raspberry Pi estate).
- A **Proposed fix**.

## Verdict

**The write side is strong.** It has:

- one write door with typed outcomes;
- a disposable derived index;
- git as the only backup;
- fail-open hooks;
- per-brief budgets;
- parity-tested contracts.

**The problems are in four places:**

1. **Read side.** The relevance gate leaks. Substring matching lets unrelated notes clear the recall floor, and it suppresses the full-text fallback.
2. **Refine side.** Nothing shrinks the corpus:
   - dedup catches exact twins only;
   - `superseded_by` is never read;
   - expired notes vanish silently;
   - there is no review queue.

   The cauldron has an intake valve and no reduction loop.
3. **Session loop vs Claude Code's documented hook semantics.** Four hook behaviours hurt unattended bots most:
   - SessionEnd hooks get a 1.5 s default timeout;
   - the brief is re-injected on resume;
   - PreCompact's block reason goes to the user, not the model;
   - the pull lock has no deadline.
4. **Family-wide context.** The vault is the *smallest* per-bot context cost. Claudlobby's composed `CLAUDE.md` is about 10–26K tokens. Bots very likely also inherit Claudlobby's 183 KB developer `CLAUDE.md` (about 45K tokens).

## How the agent team should work this

1. Pick a child and run its **Test it on yourself** steps.
   - Use a **scratch vault** (`mktemp -d`) unless a step is explicitly marked read-only.
   - Never mutate the live vault to reproduce a finding.
2. Comment on the child with the reproduction report:

   ```
   **Result:** confirmed | not reproduced | different behaviour
   **Host:** <hostname>, Pi model, `claudron version`, `claude --version`
   **Commands + output:** (verbatim)
   **Notes:** anything that differs from the issue's description
   ```

3. Only after the result is posted, propose or implement the fix.
   - Contract changes (`docs/CLI_CONTRACT.md`, `SCHEMA.md`, `VAULT-STRUCTURE.md`) need approval per `PROJECT_MISSION.md`.
   - Items marked **[claudlobby]** or **[claudna]** are filed here because Claudron owns the contracts. Mirror them into the sibling repo when work starts.

## Suggested order

- **Now:** release, retrieval, hook fixes, vault hygiene, Claudlobby context.
- **Next:** reduction loop, near-dup dedup, incremental index, eval.
- **Later:** contract drift gates and store cleanup.

## Related existing issues

- #143 and #144: recall relevance and bloat.
- #155: derived INDEX.md.
- #88: `status --json` writes the index.
- #32: no supersede path.
- #57: review queue v0.
- #130: status hang, fixed but unreleased.
- #146: addendum headings.

## Children
