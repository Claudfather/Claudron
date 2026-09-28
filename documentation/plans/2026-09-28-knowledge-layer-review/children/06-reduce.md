TITLE: No reduction loop: superseded_by is never followed, expired notes vanish silently, no review queue
LABELS: enhancement,planning,priority:medium

Part of #{{EPIC}}. Related: #57, #32, #146, #19, #{{dedup}}, #{{lobby-stores}}.

## Finding

Knowledge only accumulates:

- **`superseded_by` is never read by any code** (grep). SCHEMA.md §The two axes says search "follows `superseded_by` to the successor".
- **Past-`expires` notes are dropped** from lookup and recall by default (`knowledge.py:462`). `status` shows only a stale *count* and never lists which notes.
- **There is no `claudron review`.** E5 PRs 2–4 are unshipped. The 2026-07-19 measurement found the real vault 0% promoted.
- **`capture --update` appends addenda forever.** The brief summarizes a note's *first* body line, so newer information never surfaces.

**Cross-repo trap.** Claudlobby's `library/resources/frontmatter-schema.md:57` and `library/protocols/shared-documentation-vault.md:56` say knowledge "defaults to a 90-day `expires:` TTL".

- The engine applies no such default.
- Any bot that follows that protocol writes notes that silently drop out of recall 90 days later.
- Nothing surfaces those notes afterwards.

## Test it on yourself

**Live vault, read-only:**

```bash
grep -rl '^expires:' "$VAULT"/_shared "$VAULT"/*/shared 2>/dev/null | wc -l          # notes carrying expires
grep -rl '^superseded_by:' "$VAULT" 2>/dev/null | wc -l
claudron status --json | jq '.data.total_stale, .data.lifecycle'
```

**Scratch vault:**

1. Write a note with `expires: 2026-01-01`.
2. Run `claudron lookup <its title>`: it returns nothing.
3. Add `--include-expired`: now it is found.

## Proposed fix

1. **`claudron review --json`** (E5 PR3). It should list:
   - expired notes;
   - TTL-stale notes;
   - drafts idle for more than N days;
   - near-duplicate clusters;
   - orphans and broken links;
   - quarantined notes.
2. A Claudlobby librarian job to drain the queue.
3. **Follow `superseded_by`.** Down-rank the old note and surface the successor.
4. **Label expired notes** in results instead of hiding them.
5. **`capture --supersede <note>`** (#32).
6. **Consolidate addenda**, or summarize from `description:`.
7. Make Claudlobby's schema copy stop promising a 90-day default.
