#!/usr/bin/env python3
"""What does committing a capture cost? (#157)

NOT A TEST — a benchmark that spends real seconds and needs a real disk, so it
is never collected (the `eval_harness.py` precedent: no `test_` prefix). Run it
by hand:

    ./.venv/bin/python -m claudron.tests.bench_capture_commit --reps 14

**This exists because a number that justifies a design decision must travel with
its repro.** #157 landed on "median +16 ms, tail +899 ms" — figures that decide
whether git-per-capture is acceptable on SD storage. An uncommitted harness makes
that justification expire the moment someone doubts it, with no way to re-run.

**THE CONTROL IS `--no-commit`, ON THE SAME BINARY, INTERLEAVED.** That is the
whole method and it is not a detail:

  * A sequential before/after across the code change is confounded. Measured on
    the reference host: load rose 3.24 -> 4.66 between the arms, so the +14 ms it
    reported was partly ambient. Only the paired form is evidence.
  * `--no-commit` skips exactly `_commit_written` and nothing else, so the
    difference between arms IS the commit.
  * Reps outer, arms inner, so both arms share the same minutes of load.

**Report the median AND the tail, never the mean alone.** On the reference host
the mean (+101 ms) is dragged by a single +899 ms rep: a git commit on a loaded
SD card occasionally takes about a second. A mean overstates the typical cost; a
median alone hides the tail. Both, or the number misleads in one direction or the
other.

Bounds this cannot escape: one host, one storage device, whatever load happens to
be running. It answers "what does it cost HERE", never "what does it cost".
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _run(args: list[str]) -> None:
    subprocess.run(args, capture_output=True, text=True, check=False)


def _git(root: Path, *args: str) -> None:
    _run(["git", "-C", str(root), *args])


def _new_vault(base: Path) -> Path:
    vault = base / "vault"
    _run([sys.executable, "-m", "claudron", "init", str(vault)])
    if not vault.exists():                     # module entry differs by install
        _run(["claudron", "init", str(vault)])
    _git(vault, "init", "-q", "-b", "main")
    _git(vault, "config", "user.email", "bench@bench.invalid")
    _git(vault, "config", "user.name", "bench")
    _git(vault, "add", "-A")
    _git(vault, "commit", "-qm", "seed")
    return vault


def _capture_ms(claudron: str, vault: Path, title: str, *, commit: bool) -> int:
    """One capture, wall-clock ms. The body is derived from the title so
    successive captures are not deduped into `suggest_update` — which writes
    nothing and would silently measure the dedup path instead."""
    argv = [claudron, "--vault", str(vault), "capture", "--type", "knowledge",
            "--title", title, "--body", f"bench body for {title}, distinct",
            "--owner", "bench"]
    if not commit:
        argv.append("--no-commit")
    t0 = time.monotonic_ns()
    _run(argv)
    return (time.monotonic_ns() - t0) // 1_000_000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=14)
    ap.add_argument("--claudron", default=str(Path(sys.executable).parent / "claudron"))
    ap.add_argument("--keep", action="store_true", help="leave the vault for inspection")
    a = ap.parse_args(argv)

    base = Path(tempfile.mkdtemp(prefix="bench-capture-"))
    try:
        vault = _new_vault(base)
        device = subprocess.run(["findmnt", "-no", "SOURCE", "--target", str(vault)],
                                capture_output=True, text=True).stdout.strip()
        load_before = Path("/proc/loadavg").read_text().split()[0] \
            if Path("/proc/loadavg").exists() else "n/a"

        control: list[int] = []
        treatment: list[int] = []
        for i in range(1, a.reps + 1):
            # INTERLEAVED: both arms see the same minute of load.
            control.append(_capture_ms(a.claudron, vault, f"Ctl {i}", commit=False))
            # The control leaves its note uncommitted; commit it so the next
            # treatment rep starts from a clean tree like the control did.
            _git(vault, "add", "-A")
            _git(vault, "commit", "-qm", f"stage ctl {i}")
            treatment.append(_capture_ms(a.claudron, vault, f"Trt {i}", commit=True))

        load_after = Path("/proc/loadavg").read_text().split()[0] \
            if Path("/proc/loadavg").exists() else "n/a"
        pairs = [t - c for c, t in zip(control, treatment)]
        cs, ts, ps = sorted(control), sorted(treatment), sorted(pairs)

        def p90(v: list[int]) -> int:
            return v[max(0, int(len(v) * 0.9) - 1)]

        print(f"storage : {device or 'unknown'}")
        print(f"load    : {load_before} -> {load_after}   reps={a.reps}")
        print()
        print(f"  --no-commit (control) : median={statistics.median(cs):.0f} "
              f"p90={p90(cs)} max={cs[-1]}  (ms)")
        print(f"  commits     (treat)   : median={statistics.median(ts):.0f} "
              f"p90={p90(ts)} max={ts[-1]}  (ms)")
        print()
        print(f"  PAIRED delta : median +{statistics.median(ps):.0f}ms   "
              f"p90 gap +{p90(ts) - p90(cs)}ms   "
              f"range {ps[0]:+d}..{ps[-1]:+d}ms   mean +{statistics.mean(ps):.0f}ms")
        print(f"  as a fraction of a capture: "
              f"{100 * statistics.median(ps) / statistics.median(cs):.0f}%")
        print()
        print("  Read the median as the typical cost and the range's high end as")
        print("  the tail. The mean is reported only to show what the tail does to")
        print("  it -- on the reference host a single +899ms rep pulled the mean to")
        print("  +101ms against a +16ms median.")
        if a.keep:
            print(f"\nkept: {vault}")
        return 0
    finally:
        if not a.keep:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
