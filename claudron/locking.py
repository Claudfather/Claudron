"""Vault write safety: a cross-process advisory lock + atomic file writes.

Two independent hazards on the write path, one home:

- **Lost updates.** ``capture`` / ``append_addendum`` / ``sync`` — and the
  *read-path* index rebuild (``build_index`` / ``load_index`` prune) — each do a
  read-modify-write of ``index.json``. Two overlapping writers (or a rebuild
  racing a capture) load the same base and the last write wins, dropping the
  other's entry — a note on disk, invisible to lookup *and* to dedup.
  :func:`vault_write_lock` serializes those critical sections across processes.
  It is **re-entrant per thread**, so a mutator that already holds it (capture
  holding the lock while calling ``ensure_index`` → ``build_index``) does not
  self-deadlock.
- **Torn files.** A crash mid-``write_text`` leaves a truncated note or index.
  :func:`atomic_write_text` writes a sibling temp then ``os.replace`` (atomic on
  POSIX), so a concurrent reader sees the old file or the new one, never a
  partial — which is what lets fresh-index readers stay lockless.

``flock`` is kernel-held: a crashed holder releases automatically, so there is
no stale-lock file to clean up. **Limits, stated honestly:** the lock is a no-op
where ``fcntl`` is unavailable (Windows), and ``flock`` can be a silent per-host
no-op on some network filesystems (NFS without lockd, SMB/CIFS) — on such a
mount two hosts are *not* serialized; a git-synced vault should live on a local
filesystem (the Claudlobby deployment's ``local/`` is). :func:`atomic_write_text`
guarantees reader-atomicity, not crash-durability (no fsync) — acceptable
because the vault is git-backed.
"""

from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - Windows
    fcntl = None

# Per-thread set of lock keys this thread already holds, for re-entrancy. Per
# thread (not per process) so two threads still exclude each other via flock on
# their separate file descriptions, while the *same* thread re-entering is a
# no-op. Claudron's write path is single-threaded; this is belt-and-suspenders.
_reentry = threading.local()


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically: a sibling temp file then ``os.replace``.

    The temp shares *path*'s directory so the replace stays on one filesystem (a
    cross-device rename is not atomic). A unique temp name means concurrent
    writers never collide on the temp itself, lock or no lock. Permissions are
    preserved: ``mkstemp`` creates the temp 0600, so without this every rewrite
    would silently narrow an existing note/index to owner-only (breaking
    cross-UID reads on a shared-host fleet) — we copy the target's prior mode, or
    fall back to the process umask for a new file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        prior_mode = path.stat().st_mode & 0o777  # preserve an existing file's mode
    except OSError:
        umask = os.umask(0)  # read-and-restore: no portable read-only accessor
        os.umask(umask)
        prior_mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, prior_mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def vault_write_lock(vault) -> Iterator[None]:
    """Serialize the vault's write critical section across processes (re-entrant
    per thread).

    Every mutator holds this across its read-modify-write of the index (and sync
    across its git ops) so concurrent writers can't clobber the index. Blocking
    (``LOCK_EX``); a dead holder is released by the kernel. Re-entrant: if this
    thread already holds the lock (capture → ``ensure_index`` → ``build_index``),
    the inner acquisition is a no-op instead of a self-deadlock. A no-op where
    ``fcntl`` is unavailable.

    Callers that also run slow/blocking work under the lock (sync's git ops)
    MUST bound that work with a timeout — the lock cannot be reclaimed from a
    process wedged (not crashed) while holding it.
    """
    if fcntl is None:  # pragma: no cover - Windows
        yield
        return
    held = getattr(_reentry, "held", None)
    if held is None:
        held = _reentry.held = set()
    lock_dir = Path(vault.root) / ".claudron"
    lock_path = lock_dir / "write.lock"
    key = str(lock_path.resolve())
    if key in held:
        yield  # this thread already holds it — re-entrant no-op
        return
    try:
        lock_dir.mkdir(exist_ok=True)
        fh = open(lock_path, "w")
    except OSError:
        # Can't create the lock file (e.g. an unwritable .claudron). Degrade to
        # a no-op rather than raise: the index is disposable and the actual write
        # fails-and-warns on its own, so locking must never turn a warn-path into
        # a crash-path.
        yield
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        held.add(key)
        yield
    finally:
        held.discard(key)
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
