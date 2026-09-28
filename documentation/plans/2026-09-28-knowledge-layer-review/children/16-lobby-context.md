TITLE: [claudlobby] Per-bot context: inherited 183 KB developer CLAUDE.md, unbounded composed CLAUDE.md, lessons loaded twice, stacked briefs
LABELS: enhancement,priority:medium

Part of #{{EPIC}}. Related: #{{scope}}, #{{budget}}, #{{lobby-stores}}.

**Belongs in Claudlobby.** It is filed here with the epic. Mirror it to Claudfather/Claudlobby when work starts.

## Findings

1. **Every bot probably loads the developer CLAUDE.md (inference; needs a live check).**
   - Bot dirs live inside the Claudlobby checkout: `runtime/bots/<name>/` or `local/<fleet>/runtime/bots/<name>/`.
   - The Claude Code memory docs say "CLAUDE.md … files in the directory hierarchy above the working directory are loaded at launch".
   - So every bot very likely loads Claudlobby's **developer `CLAUDE.md`: 183,022 bytes, about 45K tokens.**
   - No `claudeMdExcludes` is composed anywhere.
2. **Composed `CLAUDE.md` has no size limit.** Measured with the real composer on the shipped example fleet:

   | Bot | Composed size |
   |---|---|
   | lead | 100–104 KB, about 25K tokens (`protocols/dispatch.md` alone is 19 KB) |
   | workers | about 40 KB |
   | vault-wired worker with lessons | 55 KB |

   - The example `defaults:` block adds the same 36 KB to every bot.
   - Every MCP server silently inlines its whole `integrations/<name>.md`.
3. **Lessons are loaded twice.** They were migrated to the vault, but `composer.py:2040` still pastes listed lessons into vault-wired bots (12 KB in the example). In addition:
   - `diff.py`, `newbot.py` and `precedent-check` still route new content into the frozen `library/lessons/`;
   - `fleet.yaml.seed` lists already-migrated lessons.
4. **Three briefs at startup.** Bots get the engine recall brief, `brief --boot`, and clauDNA's interactive briefing. `CLAUDNA_SESSION_BRIEFING=0` is never set for bots.

## Test it on yourself

**On one live bot, read-only:**

1. Run `/memory` and list every CLAUDE.md that is loaded, with its path.
2. Then run:

```bash
wc -c "$BOT_DIR/CLAUDE.md"
grep -c '^## Lessons' "$BOT_DIR/CLAUDE.md"
```

3. Report the context usage shown in the first turn of a fresh session.

## Proposed fix

1. Compose `claudeMdExcludes` for the Claudlobby repo's `CLAUDE.md`, or move `runtime/` outside the checkout.
2. Add a per-bot composed-size budget to `validate` and `doctor`, and record byte counts in the defaults baseline.
3. Turn heavy protocols and integrations into skills or pointers.
4. Skip or warn on `lessons:` for vault-wired bots, and fix the three stale entry points.
5. Set `CLAUDNA_SESSION_BRIEFING=0` for bots.
6. Claudlobby should own the combined per-bot budget, which the Claudron contract deliberately leaves unowned.
