TITLE: SessionEnd hook runs under Claude Code's 1.5 s default timeout — the contract's 10 s push budget is unreachable
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{lock}}, #{{resume}}.

## Finding

The Claude Code hooks reference (https://code.claude.com/docs/en/hooks, §SessionEnd) says:

> "SessionEnd hooks have a default timeout of 1.5 seconds … You can give a hook more time … set `timeout` in that hook's configuration … up to 60 seconds."

Claudron's installed hook entry carries no timeout:

- `settings_snippet` (`claudron/hooks.py:203`) emits no `timeout` field.
- Claudlobby composes a drift-gated copy of that snippet, so bots have none either.

The effective budget is therefore 1.5 s, not the `10.0s` that `CLI_CONTRACT.md` HOOK_TIMEOUTS promises. That 1.5 s covers:

- Python startup;
- the pre-flight git calls;
- the commit;
- the network push.

A kill can land mid-`git add`/`commit`. That would leave a `.git/index.lock` behind. This is a hypothesis, but it is consistent with the stale-lock incidents that motivated #153.

## Evidence

- Measured locally, with no network and a local bare remote: the hook took 0.22–0.25 s.
- The risk is real pushes to GitHub from a Pi.

## Test it on yourself

**On the Pi, in the live vault's session environment:**

```bash
cd "$VAULT"
echo '{"session_id":"probe"}' > /tmp/se.json
/usr/bin/time -f '%e s' claudron hook session-end < /tmp/se.json
tail -5 "$VAULT/.claudron/hooks.log"
```

Run it 5 times with a pending straggler commit, and report the timings.

Also check whether any `index.lock` or `sync --push degraded` lines appear in `hooks.log` after normal bot session ends.

## Proposed fix

1. Add `"timeout": 15` to each hook entry in `settings_snippet`. This is a contract edit to the snippet block.
2. Claudlobby's R3 gate will then force the composer copy to follow.
3. Document `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` for plugin or other installs.
