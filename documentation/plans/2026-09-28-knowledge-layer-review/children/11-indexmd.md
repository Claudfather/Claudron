TITLE: Generated INDEX.md still produces git conflicts across hosts — resolve by regeneration, not by a human
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #155, #{{gitignore}}.

## Finding

#155 made `INDEX.md` a derived file. That is right, but the file is still committed, and git still merges it textually.

When two hosts each capture into the same directory and regenerate, the notes merge cleanly but `INDEX.md` conflicts:

| Sync path | What happens |
|---|---|
| In-place (default) | "pull hit conflicts", quarantined `_shared/knowledge/INDEX.md`, conflict markers in the live tree, rebase stopped. That host's sync is wedged. |
| `CLAUDRON_SYNC_WORKTREE=1` | "integration conflicted … `_shared/knowledge/INDEX.md`". Refuses every run until a human intervenes. |

Generation is **deterministic**: the same note set produced a byte-identical `INDEX.md` after a fresh index. So regenerate-to-resolve is sound.

Once #155 PR 2 regenerates `INDEX.md` on every capture, any concurrent same-directory captures across hosts will conflict.

## Test it on yourself

Scratch only; two clones and a bare remote.

```bash
T=$(mktemp -d); export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare -b main $T/r.git; mkdir $T/a; cd $T/a && claudron init . && git init -q -b main . && git add -A && git commit -qm i && git remote add origin $T/r.git && git push -qu origin main
c(){ printf '{"type":"knowledge","title":"%s","body":"%s"}' "$2" "$2" | claudron --vault $1 capture --stdin >/dev/null; claudron --vault $1 index --navigation >/dev/null; (cd $1 && git add -A && git commit -qm nav); }
c $T/a seed && (cd $T/a && git push -q); git clone -q $T/r.git $T/b
c $T/a "From A" && (cd $T/a && git push -q); c $T/b "From B"
claudron --vault $T/b sync --json | jq .data.detail
```

## Proposed fix

**Preferred:**

1. Add `.gitattributes`: `**/INDEX.md merge=claudron-derived`.
2. Register a driver that keeps either side.
3. `sync` regenerates navigation after integration and commits the result.

Scope it only to files carrying the generated header.

**Alternative:** stop committing `INDEX.md`, since it is regenerable locally. Weigh that against its value for humans browsing GitHub.
