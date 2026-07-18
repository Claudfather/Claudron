"""Tests for the vault write-lock + atomic writes (PR-H, Juncture A).

Regression guard for the lost-update race the re-ironclad found: demoting E3
(the write-lock's original home) while the CLI/fleet write path is live left
concurrent captures able to clobber each other's index entry — a note on disk,
invisible to lookup and dedup. These pin the fix.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from claudron.knowledge import index_divergence
from claudron.locking import atomic_write_text, vault_write_lock
from claudron.vault import detect


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path: Path):
    target = tmp_path / "sub" / "f.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    assert [p.name for p in target.parent.iterdir()] == ["f.txt"]  # no .tmp litter
    atomic_write_text(target, "world")  # overwrite existing
    assert target.read_text() == "world"
    assert [p.name for p in target.parent.iterdir()] == ["f.txt"]


def test_write_lock_is_exclusive(vault_dir: Path):
    """vault_write_lock serializes across holders (flock LOCK_EX): a second
    non-blocking acquire on the same lock file fails while the first is held."""
    fcntl = pytest.importorskip("fcntl")
    vault = detect(vault_dir)
    with vault_write_lock(vault):
        probe = open(vault_dir / ".claudron" / "write.lock", "w")
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            probe.close()


def _capture_proc(vault: Path, n: int) -> subprocess.Popen:
    code = "import sys; from claudron.cli import main; sys.exit(main(sys.argv[1:]))"
    return subprocess.Popen(
        [sys.executable, "-c", code, "--vault", str(vault), "capture",
         "--type", "knowledge", "--title", f"Concurrent Note {n}",
         "--body", f"finding number {n}", "--owner", "t"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def test_concurrent_captures_all_land_in_index(vault_dir: Path):
    """The lost-update regression: N processes capturing distinct notes at once
    must ALL appear in index.json. Without the lock the read-modify-write of
    index.json is last-writer-wins and drops entries."""
    pytest.importorskip("fcntl")  # the lock is a no-op without it; skip there
    n = 8
    procs = [_capture_proc(vault_dir, i) for i in range(n)]
    for p in procs:
        assert p.wait(timeout=30) == 0

    index = json.loads((vault_dir / ".claudron" / "index.json").read_text())
    titles = {e["title"] for e in index["entries"]}
    for i in range(n):
        assert f"Concurrent Note {i}" in titles, f"note {i} dropped from the index"

    # And no drift between disk and index after the concurrent burst.
    div = index_divergence(detect(vault_dir))
    assert div["missing"] == 0 and div["ghost"] == 0
