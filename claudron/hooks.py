"""The hook pack: Claude Code lifecycle glue for the session loop (E2).

The adapter, not the protocol. What the loop promises — the four roles and
their owners, the pull-before-recall ordering, the single-prompt rule, the
budgets, and the composed-settings shape — is normative in
``docs/CLI_CONTRACT.md`` §Session-loop protocol. This module implements the
engine's three of those roles; changes to what they promise PR the contract
first.

Three events, one contract: **hooks fail open**. A hook must never break a
session — on any error it emits nothing (SessionStart stdout is injected
into agent context verbatim), logs to ``.claudron/hooks.log`` (or the
user's temp dir when no vault resolves), and exits 0.

- SessionStart → ``sync --pull`` (hard timeout, offline fail-open) then
  the recall brief on stdout. Pull precedes recall or machine B briefs
  stale.
- PreCompact → block-and-instruct once per session: route the agent to its
  own capture door. Front-end-neutral by construction — the engine never
  asks *who else is here*; a front-end shipping its own prompt defers by
  detecting the engine's registered ``hook pre-compact`` entry.
- SessionEnd → ``sync --push`` (fail open; nothing to inject).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .session import derive_project, recall, render_brief
from .sync import SyncError, sync
from .vault import Vault, detect

SESSION_START_PULL_TIMEOUT = 2.0  # seconds — the SessionStart latency budget
SESSION_END_PUSH_TIMEOUT = 10.0  # bounded teardown — a hang isn't an error,
# so fail-open alone can't save a stalled push


def _log(vault: Vault | None, event: str, message: str) -> None:
    """Append to hooks.log; never raise (logging failures stay silent —
    fail-open applies to the logger too)."""
    try:
        if vault is not None:
            log_dir = vault.root / ".claudron"
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / "hooks.log"
        else:
            log_path = Path(tempfile.gettempdir()) / "claudron-hooks.log"
        stamp = datetime.now().isoformat(timespec="seconds")
        with log_path.open("a") as fh:
            fh.write(f"{stamp} [{event}] {message}\n")
    except OSError:
        pass


def _stdin_payload() -> dict:
    """Claude Code hook input (JSON on stdin); tolerate anything."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def session_start_brief(vault: Vault) -> str:
    """The order-sensitive SessionStart composition: bounded pull, THEN
    recall (pull must precede recall or machine B briefs stale — the
    epic's acceptance-test invariant). The session-layer seam both the
    hook and any future door (E3) call; sync degradation never blocks
    the brief."""
    try:
        result = sync(vault, pull=True, push=False, timeout=SESSION_START_PULL_TIMEOUT)
        if not result.ok:
            _log(vault, "session-start", f"sync --pull degraded: {result.detail}")
        if result.quarantined:
            _log(
                vault, "session-start",
                f"quarantined this pull: {', '.join(result.quarantined)}",
            )
    except SyncError as exc:
        _log(vault, "session-start", f"sync --pull skipped: {exc}")
    # Re-detect after the pull: Vault is a frozen snapshot, and a pull can
    # introduce whole tiers (a project dir first created on another
    # machine) that the pre-pull snapshot — and any index built from it —
    # cannot see. Caught live: machine B's first brief about a project
    # born on machine A came back empty.
    vault = detect(vault.root) or vault
    return render_brief(recall(vault, project=derive_project()))


def hook_session_start(vault: Vault, payload: dict) -> int:
    """Emit the session brief on stdout (fail-open, like every hook)."""
    brief = session_start_brief(vault)
    if brief:
        print(brief)
    return 0


def hook_pre_compact(vault: Vault, payload: dict) -> int:
    """Block the first compaction with the capture prompt; pass afterwards.

    The prompt names no front-end: it routes the agent to *its own* capture
    door, whichever that is, and falls back to the engine's CLI. Which
    participant holds the prompt is settled structurally by the contract's
    claim mechanism, not by this handler looking around: the engine always
    prompts where its hook is installed, and a front-end shipping its own
    prompt defers when it finds that registered ``hook pre-compact`` entry.
    """
    session_id = str(payload.get("session_id") or "unknown")
    marker = Path(tempfile.gettempdir()) / f"claudron-precompact-{session_id}"
    if marker.exists():
        return 0
    try:
        marker.touch()
    except OSError:
        pass
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    "Before compacting: distill this session's durable findings "
                    "through your capture door — your capture skill if you have "
                    "one, otherwise `claudron capture --stdin` (the finding as "
                    "JSON on stdin, never interpolated into --body). Dedup routes "
                    "a near-duplicate to the note that already covers it rather "
                    "than twinning it. Then retry the compaction."
                ),
            }
        )
    )
    return 0


def hook_session_end(vault: Vault, payload: dict) -> int:
    """Push the session's vault changes; fail open (nothing to inject)."""
    try:
        result = sync(vault, pull=False, push=True, timeout=SESSION_END_PUSH_TIMEOUT)
        if not result.ok:
            _log(vault, "session-end", f"sync --push degraded: {result.detail}")
    # Deliberate, not a residual guard the boundary makes redundant: a
    # vault without a working git setup raises SyncError on every push, so
    # this is the expected-degradation logger ("skipped", symmetric with the
    # pull side's catch in session_start_brief) — the boundary's "failed
    # open" line stays reserved for genuinely unanticipated failures.
    except SyncError as exc:
        _log(vault, "session-end", f"sync --push skipped: {exc}")
    return 0


def run_hook(event: str, vault: Vault | None) -> int:
    """THE fail-open boundary: whatever goes wrong inside a handler —
    including exception classes the inner guards never anticipated — a
    hook exits 0 with nothing on stdout. One guard at the boundary
    instead of per-call try blocks of mismatched breadth (a PermissionError
    from the git layer escaped the narrow SyncError catch and would have
    broken the session). The boundary also owns the wire prologue every
    handler used to repeat: drain the stdin payload, then no-op (exit 0)
    when no vault resolved."""
    try:
        payload = _stdin_payload()
        if vault is None:
            _log(None, event, "no vault resolvable — nothing to do")
            return 0
        return _HOOK_HANDLERS[event](vault, payload)
    except Exception as exc:
        _log(vault, event, f"hook failed open: {exc!r}")
        return 0


_HOOK_HANDLERS = {
    "session-start": hook_session_start,
    "pre-compact": hook_pre_compact,
    "session-end": hook_session_end,
}

HOOK_EVENTS = tuple(sorted(_HOOK_HANDLERS))


def settings_snippet(executable: str) -> dict:
    """The Claude Code settings.json hooks block, absolute-path commands
    (venv/pipx installs survive hook context, where PATH may not)."""

    def entry(event_cmd: str) -> list[dict]:
        return [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": f"{executable} hook {event_cmd}"}],
            }
        ]

    return {
        "hooks": {
            "SessionStart": entry("session-start"),
            "PreCompact": entry("pre-compact"),
            "SessionEnd": entry("session-end"),
        }
    }


def _is_claudron_hook(entry: dict, event_cmd: str) -> bool:
    """A claudron hook's identity is (event, ours) — NOT the literal
    command string. Keying on the full path made a moved venv/pipx path
    append a duplicate entry instead of replacing the stale one (the
    exact portability scenario absolute paths exist for)."""
    return any(
        str(h.get("command", "")).endswith(f"hook {event_cmd}")
        for h in (entry.get("hooks") or [])
    )


def merge_settings(settings: dict, snippet: dict) -> dict:
    """Merge the snippet's hook entries into existing settings without
    touching anything else. Idempotent, and self-replacing: a prior
    claudron entry for the same event is replaced (stale executable
    paths don't accumulate); foreign entries are never touched."""
    merged = dict(settings)
    hooks = dict(merged.get("hooks") or {})
    event_cmds = {
        "SessionStart": "session-start",
        "PreCompact": "pre-compact",
        "SessionEnd": "session-end",
    }
    for event, entries in snippet["hooks"].items():
        event_cmd = event_cmds[event]
        kept = [
            e for e in (hooks.get(event) or [])
            if not _is_claudron_hook(e, event_cmd)
        ]
        hooks[event] = kept + entries
    merged["hooks"] = hooks
    return merged


def resolve_executable() -> str:
    """Absolute claudron invocation for hook commands: the console script
    beside the interpreter when present, else `python -m claudron.cli`."""
    exe_dir = Path(sys.executable).parent
    script = exe_dir / "claudron"
    if script.is_file() and os.access(script, os.X_OK):
        return str(script)
    return f"{sys.executable} -m claudron.cli"
