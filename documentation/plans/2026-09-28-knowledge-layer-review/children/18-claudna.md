TITLE: [claudna] CLI-contract drift, double capture prompt on compaction, and the ~/shared default
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{precompact}}, #{{home}}, #{{release}}, #{{drift}}.

**Belongs in clauDNA.** It is filed here with the epic; mirror it to Claudfather/clauDNA when work starts.

## Findings

### 1. The hand-copied CLI contract has drifted, with no drift gate

`skills/_shared/claudron-engine.md` §2-3 copies the Claudron CLI contract by hand and has already drifted:

- **It requires `status` fields the contract calls informational.** Those fields are `quarantined`, `index_present`, `index_fresh` and `warnings`. If one is missing, the response is treated as an engine failure and writes fall back to the raw tree, creating a second store.
- **It gates on `engine_version >= 0.4.0`,** not on `capabilities`.
- **It passes bodies via `--body`,** which the contract says MUST NOT happen. Claudron's `capture --update` has no `--stdin`, so Claudron needs a fix here too.
- **It ignores `written` and `warnings`,** so W108 ("note written but NOT committed") passes silently.

### 2. The PreCompact hook can prompt twice and keeps blocking

`plugin-hooks/precompact-reflect.sh` stands down only when both hold:

- the engine's `hook pre-compact` entry is registered; and
- `timeout 3 claudron status --json` reports version ≥ 0.4.0.

That probe hangs on Claudlobby vaults on 0.4.0, so both hooks block. That is **two prompts per compaction**. The probe also walks the whole vault on every compaction.

clauDNA also deletes its marker when it allows a compaction, so it **blocks every other compaction**. Claudron blocks once per session, and SETUP_GUIDE claims once per session too. See #{{precompact}} for why blocking may not reach the model at all.

### 3. The `~/shared` default turns `$HOME` into a vault

`init-project`'s default raw-tree root `~/shared` makes Claudron treat `$HOME` as the vault; see #{{home}}.

### 4. Smaller issues

- `/claudna:recall` re-renders the conventions and notes uncapped, duplicating the SessionStart brief.
- `publish` lacks capture's vault guard and no-fallback rule.
- `/claudna:index` claims to be the sole INDEX.md writer, which is stale since Claudron 0.5.0.
- clauDNA never calls `claudron index --navigation` after writes.
- The skill and agent descriptions total about 3K tokens and have no total budget.

## Test it on yourself

On the Pi, read-only:

```bash
time (timeout 3 claudron status --json >/dev/null); echo "exit=$?"       # >3s or 124 => clauDNA will not defer
ls ${TMPDIR:-/tmp}/claudna-reflected-* ${TMPDIR:-/tmp}/claudron-precompact-* 2>/dev/null | wc -l
```

After a compaction on a bot, count the "Before compacting" / reflect blocks in `.claudron/hooks.log` and in the transcript.

## Proposed fix

1. **Contract copy:**
   - require only the stable `status` fields;
   - gate on `capabilities`;
   - use `--stdin`;
   - surface `written` and `warnings`;
   - render the contract tables behind a CI drift gate, like `output-guide §3`.
2. **PreCompact:** defer on the settings-file check alone, now that 0.4.0 has shipped, and make the marker once-per-session.
3. **Raw-tree default:** change it away from `~/shared`.
4. **Recall:** add a budget and skip content already in the brief.
