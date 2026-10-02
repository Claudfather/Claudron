"""The operations log (#200 §5): what the engine did, per run and per session.

Under the vault's ``.claudron/`` (gitignored, so local and never synced), one
JSONL file per run and per session::

    .claudron/runs/<run_id>/ops.jsonl        writes tagged with a run (harvest), refusals, a revert
    .claudron/sessions/<session_id>/ops.jsonl what a session's hooks did: recall served, push outcome

Every line shares one envelope, named to line up with clauDNA's store and the
Claudlobby plane where they overlap: ``v``, ``ts``, ``kind``, ``session_id``,
``run_id``, ``emitter``, ``event_id``, then the kind's own fields.

**Best-effort by construction**, like the sync journal: a write that can't be
logged still succeeds, so :func:`record` never raises. Ids become directory
names, so one that isn't a safe path segment is not logged at all. Each of
``runs/`` and ``sessions/`` keeps its newest :data:`KEEP` logs.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .vault import Vault, missing_gitignore_rules

OPS_VERSION = 1
EMITTER = "claudron"
KEEP = 200  #: run or session directories kept per kind; the oldest go first
#: A safe directory name: what a run id already is (runs.RUN_ID_RE), and what a Claude Code session id is.
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _dir(vault: Vault, *, run_id: object, session_id: object) -> Path | None:
    ident, kind = (run_id, "runs") if run_id else (session_id, "sessions")
    if not isinstance(ident, str) or not _ID_RE.fullmatch(ident):
        return None
    return vault.root / ".claudron" / kind / ident


def _ignored(vault: Vault) -> bool:
    """Is ``.claudron/`` kept out of git? In a git vault without the rule (an unmigrated one), `sync`'s
    straggler net would commit and push the logs — session ids, note paths, refusal reasons — so none is written."""
    return not (vault.root / ".git").exists() or ".claudron/" not in missing_gitignore_rules(vault.root)


def _prune(parent: Path) -> None:
    """Keep the newest :data:`KEEP` logs under ``parent``, by when each was last appended to.

    Only ever removes what :func:`record` made: a directory's ``ops.jsonl``, then the directory if
    that leaves it empty. Never a symlinked directory, never anything else in it.
    """
    logs = [d / "ops.jsonl" for d in parent.iterdir() if not d.is_symlink() and (d / "ops.jsonl").is_file()]
    logs.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for old in logs[KEEP:]:
        old.unlink()
        try:
            old.parent.rmdir()
        except OSError:
            pass  # something else lives there: not ours to delete


def _short(value: object) -> object:
    return value[:200] if isinstance(value, str) else value


def record(vault: Vault, kind: str, *, run_id: str | None = None, session_id: str | None = None,
           **fields: object) -> None:
    """Append one event to the run's log (``run_id``) or else the session's; never raises.

    String fields are cut to 200 characters. Nothing is written in a git vault whose ``.gitignore``
    doesn't keep ``.claudron/`` out of commits (``claudron doctor --fix`` adds the rule).
    """
    try:
        where = _dir(vault, run_id=run_id, session_id=session_id)
        if where is None or not _ignored(vault):
            return
        log = where / "ops.jsonl"
        fresh = not log.exists()
        where.mkdir(parents=True, exist_ok=True)
        line = {"v": OPS_VERSION, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "kind": kind, "session_id": session_id, "run_id": run_id, "emitter": EMITTER,
                "event_id": os.urandom(8).hex(), **{k: _short(v) for k, v in fields.items()}}
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
        if fresh:
            _prune(where.parent)
    except Exception:  # noqa: BLE001 — a log must never fail the write (or the hook) it records
        return


def _first_ts(path: Path) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            first = json.loads(fh.readline() or "{}")
    except (OSError, ValueError):
        return ""
    return str(first.get("ts") or "") if isinstance(first, dict) else ""


def _events(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


#: Events that mean a run's write did not land as asked: refused, or written but not committed.
FAILURES = ("write.refused", "write.uncommitted")


def runs_summary(vault: Vault) -> dict:
    """``status``'s view of the runs: the newest run, when one last applied cleanly, and the last failure.

    ``{"last_run": {run_id, at, writes, failures, reverted} | None, "last_ok_at": ts | None,
    "last_failure": {run_id, at, kind, reason} | None}``. Runs are ordered by when they started (a
    later ``revert-run`` doesn't make an old run the newest), and a run's ``at`` is its last write.
    A run applied cleanly when it wrote and nothing in it failed. Never raises.
    """
    summary: dict = {"last_run": None, "last_ok_at": None, "last_failure": None}
    try:
        logs = list((vault.root / ".claudron" / "runs").glob("*/ops.jsonl"))
    except OSError:
        return summary
    # Ordered by each log's first line (when the run started); a whole log is read only when reached.
    for _, log in sorted(((_first_ts(log), log) for log in logs), reverse=True):
        run_id, events = log.parent.name, _events(log)
        if not events:
            continue
        writes = [e for e in events if e.get("kind") in ("write", *FAILURES, "write.routed")]
        failed = [e for e in events if e.get("kind") in FAILURES]
        at = str((writes or events)[-1].get("ts") or "")
        if summary["last_run"] is None:
            summary["last_run"] = {"run_id": run_id, "at": at,
                                   "writes": sum(e.get("kind") == "write" for e in events),
                                   "failures": len(failed),
                                   "reverted": any(e.get("kind") == "run.reverted" for e in events)}
        if summary["last_ok_at"] is None and not failed and any(e.get("kind") == "write" for e in events):
            summary["last_ok_at"] = at
        if summary["last_failure"] is None and failed:
            last = failed[-1]
            summary["last_failure"] = {"run_id": run_id, "at": str(last.get("ts") or ""), "kind": last.get("kind"),
                                       "reason": str(last.get("reason") or "")[:200]}
        if summary["last_ok_at"] and summary["last_failure"]:
            break
    return summary
