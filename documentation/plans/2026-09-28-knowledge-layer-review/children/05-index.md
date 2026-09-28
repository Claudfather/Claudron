TITLE: Index freshness is mtime-only: a git-mv'd note drops out of the index (dedup twins it); rebuilds are all-or-nothing
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{dedup}}, #88.

## Finding

`index_is_stale` (`claudron/vault.py:681`) declares the index stale only when some note file is **newer** than `index.json`. Two consequences follow.

**Renamed notes vanish from the index.**

- A rename keeps the file's mtime. `git mv` is the documented interim promotion path (VAULT-STRUCTURE.md §Promotion).
- So after a move the index is judged fresh.
- `load_index` then prunes the old path as a ghost, and the new path is never added.
- The moved note becomes invisible to dedup and to index-only recall. Only `status` notices it, as `divergence.missing`.

**Any single change forces a full rebuild.**

- `ensure_index` = load or full rebuild, and the rebuild reads and parses every note with pure-Python `yaml.safe_load`.

## Evidence (reproduced)

- `git mv _shared/knowledge/jwt-validation-gotchas.md projects/api/`, then re-capturing the same title, gave `created` (a twin). `status` then reported `missing: 1`.
- Timings, measured on a cloud VM (a Pi will be slower):

| Notes | Full rebuild | Recall after **one** changed note |
|---|---|---|
| 1,000 | 0.43 s | 0.86 s |
| 5,000 | 2.07 s | 4.18 s |

- SessionStart fires after every compaction, so this cost recurs.

## Test it on yourself

**Scratch vault:**

```bash
V=$(mktemp -d)/v && claudron init "$V" && cd "$V" && git init -q . && mkdir -p projects/x
printf '{"type":"knowledge","title":"Moved note","body":"x"}' | claudron --vault "$V" capture --stdin >/dev/null
git add -A && git -c user.name=t -c user.email=t@t commit -qm s
git mv _shared/knowledge/moved-note.md projects/x/
printf '{"type":"knowledge","title":"Moved note","body":"y"}' | claudron --vault "$V" capture --stdin --json | jq -r .data.action   # expect: created
claudron --vault "$V" status --json | jq .data.divergence
```

**Live vault, read-only:**

- `claudron status --json | jq .data.divergence`
- Time `claudron recall` from a bot dir right after a pull.

## Proposed fix

1. Store `{path: (mtime_ns, size)}` in the index manifest.
2. Staleness becomes a set-and-stat diff, so renames are detected.
3. Rebuild incrementally: re-parse only changed or new paths, and drop gone ones.
4. Use `yaml.CSafeLoader` when available. It is still PyYAML-only.
