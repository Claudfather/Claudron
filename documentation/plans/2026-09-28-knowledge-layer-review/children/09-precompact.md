TITLE: PreCompact capture prompt likely never reaches the model on unattended bots (block reason goes to the user; auto-compaction can fail the request)
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{resume}}, #{{claudna}}.

## Finding

`hook_pre_compact` returns `{"decision":"block","reason":"Before compacting: distill … Then retry the compaction."}` once per session (`claudron/hooks.py:122`).

The Claude Code hooks reference (§PreCompact) says:

> "For a manual `/compact`, the stderr message is shown to the user. You can also block by returning JSON with `"decision": "block"`."

> "Blocking automatic compaction … If compaction was triggered proactively … Claude Code skips it and the conversation continues uncompacted. If compaction was triggered to recover from a context-limit error … the underlying error surfaces and the current request fails."

Nothing in the docs says the **model** sees the reason. For an unattended bot, which only gets auto-compaction:

- the nudge probably never reaches the agent, which is the one case the R-capture-prompt role exists for;
- at worst, the block fails a request.

clauDNA's `precompact-reflect.sh` has the same exposure, and it blocks every other compaction attempt.

## Test it on yourself

**This needs a live check; it is the key unknown.** Run it on one bot in a throwaway session:

1. Fill context until auto-compaction triggers, or run `/compact`.
2. Record:
   - whether the model ever acted on or quoted the "distill this session's durable findings" text;
   - whether a request failed;
   - whether any capture happened (`git -C "$VAULT" log --since=1.hour --oneline | grep capture`).
3. Also check `.claudron/hooks.log` and the transcript JSONL for the block.

## Proposed fix

**Contract change.** Move the capture prompt to a model-visible channel:

- **SessionStart with `source=compact`.** Its stdout goes into context. Phrase it factually, per the docs' prompt-injection guidance, e.g. "Durable findings in the summary above belong in the vault: `claudron capture --stdin`".
- **And/or a `Stop` hook with `decision: block`,** once per session. The docs say its reason "is fed back to Claude as its next instruction".

Keep the single-holder rule, and update clauDNA's defer logic to match.
