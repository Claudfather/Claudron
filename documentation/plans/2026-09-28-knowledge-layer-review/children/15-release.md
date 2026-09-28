TITLE: Cut Claudron 0.5.0 — two months of sync-safety fixes (incl. the status hang) haven't reached fleets pinned to 0.4.0
LABELS: planning,priority:medium

Part of #{{EPIC}}. Related: #130, #136, #151, #{{drift}}, #{{claudna}}.

## Finding

- The last tag is **0.4.0 (2026-07-23)**.
- Claudlobby pins the `[vault]` extra `@v0.4.0` (claudlobby `pyproject.toml:28`).
- Everything under `CHANGELOG.md` "Unreleased" is not on fleets, including:
  - the SessionStart ff-only fix (#156);
  - capture-commits (#157);
  - the worktree integration (#158);
  - the stale `index.lock` expiry (#153);
  - the `status` walk scoping that fixed the hang on fleet vaults (#130).

**Knock-on effect.** clauDNA stands down its PreCompact prompt only if `claudron status --json` answers within 3 s. On 0.4.0 against Claudlobby vaults, it hangs. So bots likely get **two** capture prompts per compaction, which the contract calls a defect (see #{{claudna}}).

## Test it on yourself

**Read-only, on the Pi:**

```bash
claudron version; pip show claudron 2>/dev/null | grep -i version
which -a claudron                                   # #151: more than one install?
time (timeout 30 claudron status --json >/dev/null); echo "exit=$?"
```

## Proposed fix

1. Resolve #136, the publish-path guards.
2. Tag 0.5.0.
3. Bump Claudlobby's pin and the host CLI.
4. Re-run the tests from the other children afterwards, since several behaviours differ between 0.4.0 and HEAD.
