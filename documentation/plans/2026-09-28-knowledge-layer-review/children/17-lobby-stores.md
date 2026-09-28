TITLE: [claudlobby] Unmanaged knowledge stores and write-door bypasses: control plane, bot memory, /graduate, schema fork
LABELS: enhancement,planning

Part of #{{EPIC}}. Related: #{{reduce}}, #{{gitignore}}, #{{lock}}.

This issue belongs in Claudlobby. It is filed here with the epic; mirror it to Claudfather/Claudlobby when work starts.

## Findings

**1. The control plane is an unmanaged second knowledge store.**
- The `communications` table is full-text indexed, stores full message bodies, and is never pruned (`plane/retention.py`; about 505k rows noted in its migration).
- It has no backup.
- Digest `reusable` findings and fleet-observe findings never reach the vault.

**2. Bot `memory/` has no lifecycle.**
- It is never pruned or versioned.
- `move-bot` and `memory-migrate` copy it instead of moving it.
- It is orphaned when a bot is removed from `fleet.yaml`.
- `/graduate` is its only way up, and `/graduate`:
  - writes files directly;
  - scans and regenerates INDEX.md;
  - leaves pointer files behind.

  All three contradict the vault protocol.

**3. Writes bypass Claudron's write door.**
- `shared-documentation-vault.md` tells bots to "edit the note in place" and to edit working docs directly.
- The vault git guard allows raw `commit` and `push`.
- Those writes skip validation, dedup and index maintenance.

**4. The frontmatter schema has forked from Claudron's.**
`library/resources/frontmatter-schema.md` sits under a pointer banner but restates the schema with divergences:

| Topic | Claudlobby's copy |
|---|---|
| `owner` | required on every doc |
| `expires` | defaults to +90d |
| `supersedes` | a path |
| `slug` | truncated |

Nothing gates this copy against drift.

**5. The vault reconciler is dormant and unsafe when armed.**
- `vault-sync` is dormant by default.
- When armed, it doesn't set `CLAUDRON_SYNC_WORKTREE=1`, so it rebases the live tree that holds fleet config.
- It runs `cd $vault && claudron sync` without `--vault`.

## Test it on yourself

Read-only, on the Pi:

```bash
sqlite3 <plane db> 'select count(*), sum(length(body)) from communications;'   # adjust to schema
du -sh "$BOT_DIR/memory" && ls "$BOT_DIR/memory" | wc -l
git -C "$VAULT" log --since=30.days --format=%s | grep -c '^vault sync: .* straggler'   # door-bypass volume
git -C "$VAULT" log --since=30.days --format=%s | grep -c '^capture('
```

## Proposed fix

1. Plane: keep message hashes and metadata, drop bodies after N days, and add a SQLite backup job.
2. Add a librarian step that captures `reusable` findings via `capture --fleet`.
3. Collect bot memory before purging or removing a bot.
4. Rewrite `/graduate` for vault-wired fleets to use `capture --fleet` and tier promotion. Drop the pointer files.
5. Route edits through `capture --update`.
6. Make the schema file a pure pointer, or a rendered copy with a CI drift gate.
7. Arm the reconciler with worktree mode and `--vault`.
