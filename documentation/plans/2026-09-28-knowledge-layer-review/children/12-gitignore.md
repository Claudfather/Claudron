TITLE: Vault .gitignore + sync's `add -A` safety net commit bot telemetry, nested-fleet runtime/, and *.bak into vault history
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{indexmd}}, #{{lobby-stores}}, Claudfather/Claudlobby#874.

## Finding

The vault `.gitignore` template (`claudron/vault.py:124`) contains only:

- `*/runtime/`
- `.env`
- `.claudron/`

`sync`'s straggler safety net runs `git add -A` (`sync.py` `commit_paths(root, [])`), so everything else gets committed. Three problems follow.

1. **Telemetry droppings are committed.** The bot-telemetry patterns that Claudron's *own repo* `.gitignore` carries for Claudlobby#874 are missing from the vault template:
   - `**/data/events/fleet-*.jsonl`
   - `.last-tool-call`
   - `.idle`

   Reproduced: sync committed `data/events/fleet-*.jsonl`, `.last-tool-call`, and a stray `notes-scratch.txt`. A growing JSONL file becomes a new blob on every sync.
2. **Nested fleets' `runtime/` is not ignored.** `*/runtime/` does not match `sys/fleet/runtime/`; verified with `git check-ignore`.
   - A comment at `vault.py` says not to "fix" this pattern. It predates `.claudron-system` nesting.
   - Only fleets made by `claudron fleet add` get their own `runtime/` ignore. Claudlobby's `migrate-fleet-to-system.sh` writes none.
   - Bot runtime dirs hold generated config, memory and identity files.
3. **`*.bak` files are committed.** Claudlobby `new-bot` writes `fleet.yaml.bak` inside the vault.

## Test it on yourself

**Live vault, read-only. Run this first; it matters most:**

```bash
cd "$VAULT"
for d in */*/runtime */runtime; do [ -d "$d" ] && printf '%s: ' "$d" && (git check-ignore -q "$d/x" && echo ignored || echo NOT-IGNORED); done
git log --since=30.days --name-only --format= | grep -E 'data/events|\.last-tool-call|\.idle|\.bak$|/runtime/' | sort | uniq -c | sort -rn | head
du -sh .git
```

## Proposed fix

1. Change the template to `**/runtime/`, and add:
   - `**/data/events/fleet-*.jsonl`
   - `**/data/.last-tool-call`
   - `**/data/.idle`
   - `*.bak`
2. `validate --fix` or `init --adopt` should augment existing vaults with these patterns.
3. Make the safety net sweep an **allowlist**: note-tier markdown, `CONVENTIONS.md`, `INDEX.md`, fleet overlay files. Report everything else as unexpected instead of committing it.
4. If the check above finds committed junk, plan a history cleanup separately.
