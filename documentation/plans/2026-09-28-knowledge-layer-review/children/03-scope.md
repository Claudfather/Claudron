TITLE: Fleet bots' SessionStart recall is scoped to the vault's own dir name ("local") — hooks need a declared scope
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{retrieval}}, #{{lobby-context}}.

## Finding

The SessionStart hook calls `recall(vault, project=derive_project())` (`claudron/hooks.py:111`). `derive_project()` walks up from cwd to the first `.git` (`session.py:48`).

Claudlobby bots run from `local/<fleet>/runtime/bots/<bot>/` (`lib/start-bot.sh`), which sits inside the vault. The vault *is* `local/`, a git repo. So for every bot:

- the project term resolves to **`local`**;
- that term substring-matches any title containing "local";
- every bot gets the same irrelevant notes at every start and every compaction.

The hook command form `<exe> hook <event>` (`CLI_CONTRACT.md` §hook-settings snippet) gives a composer no way to declare scope. Captures also default to `_shared/`, while the Claudlobby protocol claims they land in the fleet tier.

## Evidence (simulated with the documented layout)

The brief a bot receives is headed `## Recalled context — local` and lists "Local-first sync tradeoffs" and "Localization string freeze".

## Test it on yourself

**Read-only, on the Pi.**

```bash
cd "$BOT_DIR"   # your own runtime dir
python3 -c "from claudron.session import derive_project; print(derive_project())"
claudron recall --json | jq '{project: .data.project, notes: [.data.notes[].title]}'
```

Report:

- the derived project;
- whether any recalled note is relevant to your role.

## Proposed fix

**Contract change, needs approval.** Let the hook accept a declared scope:

- via env, e.g. `CLAUDRON_RECALL_FLEET` / `CLAUDRON_RECALL_PROJECT`, or flags on `hook session-start`;
- the composer sets it per bot.

Also:

- When `derive_project()` lands on the vault root itself, treat the project as *unknown* (conventions only), never as the dir name.
- Claudlobby: compose `--fleet <name>` guidance into bots' capture instructions.
