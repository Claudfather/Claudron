TITLE: SessionStart pull blocks on the vault flock with no deadline — a concurrent sync stalls every session start and compaction
LABELS: bug

Part of #{{EPIC}}. Related: #{{sessionend}}, #43, #167.

## Finding

- `pull_ff_only` takes `vault_write_lock` (`claudron/sync.py:1134`).
- That lock is a blocking `fcntl.flock(LOCK_EX)` with **no timeout** (`claudron/locking.py:121`).
- `SESSION_START_PULL_TIMEOUT = 2.0` bounds the git calls, not the wait for the lock.

So if another process holds the lock, SessionStart waits for as long as it is held. Candidates:

- Claudlobby's `vault-sync` job, which runs `claudron sync --timeout 300`, i.e. 300 s per git op;
- a manual `claudron sync`.

Claude's first response waits for SessionStart hooks, and SessionStart also fires after every compaction.

## Test it on yourself

Scratch vault, two shells.

```bash
V=$(mktemp -d)/v && claudron init "$V" && (cd "$V" && git init -q .)
# shell 1: hold the lock for 20 s
python3 -c "
from claudron.vault import detect; from claudron.locking import vault_write_lock; import time
with vault_write_lock(detect('$V')): time.sleep(20)"
# shell 2, within the 20 s:
time (echo '{}' | CLAUDRON_VAULT_PATH="$V" claudron hook session-start >/dev/null)
```

**Expected if confirmed:** about 20 s, not about 2 s.

**On the Pi:** check whether `vault-sync` is armed, and whether bot boot times correlate with its runs.

## Proposed fix

In the hook path:

1. Take the lock with `LOCK_NB` and poll until the event budget expires.
2. On expiry, skip the pull and brief from local state, which is already fail-open semantics.
3. Add a lock-wait bound to the contract's HOOK_TIMEOUTS table.
