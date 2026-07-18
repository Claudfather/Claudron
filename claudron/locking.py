"""Vault write safety: a cross-process advisory lock + atomic file writes.

Two independent hazards on the write path, one home:

- **Lost updates.** ``capture`` / ``append_addendum`` / ``sync`` each do a
  read-modify-write of ``index.json`` (load base → mutate → persist). Two
  overlapping writers load the same base and the last write wins, dropping the
  other's entry — a note on disk, invisible to lookup *and* to dedup (silently
  re-created later as a twin). :func:`vault_write_lock` serializes the whole
  dedup→write→index critical section across processes.
- **Torn files.** A crash mid-``write_text`` leaves a truncated note or index.
  :func:`atomic_write_text` writes a sibling temp then ``os.replace`` (atomic on
  POSIX), so a concurrent reader sees the old file or the new one, never a
  partial — which is what lets readers stay lockless.

``flock`` is kernel-held: a crashed holder releases automatically, so there is
no stale-lock file to clean up and get wrong (this is why flock, not a PID
lockfile). Where ``fcntl`` is unavailable (Windows) the lock degrades to a
no-op — the single-writer assumption the vault already documents — while atomic
writes still apply.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - Windows
    fcntl = None


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically: a sibling temp file then ``os.replace``.

    The temp shares *path*'s directory so the replace stays on one filesystem (a
    cross-device rename is not atomic). A unique temp name means concurrent
    writers never collide on the temp itself, lock or no lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def vault_write_lock(vault) -> Iterator[None]:
    """Serialize the vault's write critical section across processes.

    Every mutator — ``capture``, ``append_addendum``, ``sync`` — holds this
    across its dedup→write→index section so concurrent writers can't clobber the
    index or interleave a note write with a rebase. Blocking (``LOCK_EX``): it
    waits for the current holder, which always releases quickly (local writes)
    or on its own git timeout (sync); a dead holder is released by the kernel,
    so there is no deadlock to recover from. A no-op where ``fcntl`` is
    unavailable.
    """
    if fcntl is None:  # pragma: no cover - Windows
        yield
        return
    lock_dir = Path(vault.root) / ".claudron"
    lock_dir.mkdir(exist_ok=True)
    fh = open(lock_dir / "write.lock", "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
