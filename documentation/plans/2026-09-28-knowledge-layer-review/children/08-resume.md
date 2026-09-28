TITLE: SessionStart brief is re-injected on every resume (hook ignores `source`), stacking copies in context
LABELS: bug

Part of #{{EPIC}}. Related: #{{precompact}}, #{{budget}}.

## Finding

The hook is installed with `"matcher": ""`, and `hook_session_start` never reads the payload (`claudron/hooks.py:114`). Two statements from the Claude Code hooks reference (https://code.claude.com/docs/en/hooks) combine badly:

- SessionStart fires on `startup | resume | clear | compact | fork`.
- "Claude Code saves the injected text in the session transcript … SessionStart hooks run again on resume."

So every `--resume`, `--continue` or `/resume` adds another copy of the brief on top of the one already in the transcript. It also re-runs the pull, up to 2 s, on the critical path of the first response.

clauDNA's own SessionStart already uses `matcher: "startup|clear"`.

## Test it on yourself

**On a bot, read-only:**

1. Start a session.
2. Exit.
3. Run `claude --continue`.
4. Ask the model to quote every "## Recalled context" block it can see.
5. Report the count. It should be 2 if the finding is confirmed.

**Or inspect the transcript JSONL for repeated SessionStart hook output:**

```bash
grep -c 'Recalled context' ~/.claude/projects/*/<session-id>.jsonl
```

## Proposed fix

- Read `payload["source"]`:
  - `startup`, `clear`: full brief.
  - `compact`: full brief (the old one was summarized away), plus the capture prompt from #{{precompact}}.
  - `resume`, `fork`: nothing, or a one-line delta if the vault changed.
- Optionally use `seconds_since_last_response` to decide whether a refresh is worth it.
- This is a session-loop contract change. Update `docs/CLI_CONTRACT.md` §Ordering too.
