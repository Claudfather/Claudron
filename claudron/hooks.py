"""The hook pack: Claude Code lifecycle glue for the session loop (E2).

Three events, one contract: **hooks fail open**. A hook must never break a
session — on any error it emits nothing (SessionStart stdout is injected
into agent context verbatim), logs to ``.claudron/hooks.log`` (or the
user's temp dir when no vault resolves), and exits 0.

- SessionStart → ``sync --pull`` (hard timeout, offline fail-open) then
  the recall brief on stdout. Pull precedes recall or machine B briefs
  stale.
- PreCompact → block-and-instruct once per session: prompt the agent to
  distill durable findings through ``claudron capture`` (clauDNA's
  precompact-reflect is the pattern; when claudna is installed the prompt
  folds capture into its reflect step instead of double-prompting).
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


def _claudna_installed() -> bool:
    plugins = Path.home() / ".claude" / "plugins"
    return any(plugins.glob("**/claudna/*")) if plugins.is_dir() else False


def hook_session_start(vault: Vault | None) -> int:
    """Pull (bounded, fail-open) then emit the recall brief on stdout."""
    _stdin_payload()  # drain stdin per the hook protocol
    if vault is None:
        _log(None, "session-start", "no vault resolvable — nothing injected")
        return 0
    try:
        result = sync(vault, pull=True, push=False, timeout=SESSION_START_PULL_TIMEOUT)
        if not result.ok:
            _log(vault, "session-start", f"sync --pull degraded: {result.detail}")
    except SyncError as exc:
        _log(vault, "session-start", f"sync --pull skipped: {exc}")
    try:
        data = recall(vault, project=derive_project())
        brief = render_brief(data)
        if brief:
            print(brief)
    except Exception as exc:  # fail open — a brief is optional, a session is not
        _log(vault, "session-start", f"recall failed: {exc!r}")
    return 0


def hook_pre_compact(vault: Vault | None) -> int:
    """Block the first compaction with the capture prompt; pass afterwards."""
    payload = _stdin_payload()
    if vault is None:
        return 0
    session_id = str(payload.get("session_id") or "unknown")
    marker = Path(tempfile.gettempdir()) / f"claudron-precompact-{session_id}"
    if marker.exists():
        return 0
    try:
        marker.touch()
    except OSError:
        pass
    combined = (
        " Fold this into the /reflect pass: for each durable finding, run"
        if _claudna_installed()
        else " For each durable finding, run"
    )
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    "Before compacting: distill this session's durable findings "
                    "into the vault." + combined + " `claudron capture --type "
                    "knowledge --title \"...\" --body \"...\"` (dedup will route "
                    "updates to existing notes). Then retry the compaction."
                ),
            }
        )
    )
    return 0


def hook_session_end(vault: Vault | None) -> int:
    """Push the session's vault changes; fail open (nothing to inject)."""
    _stdin_payload()
    if vault is None:
        return 0
    try:
        result = sync(vault, pull=False, push=True)
        if not result.ok:
            _log(vault, "session-end", f"sync --push degraded: {result.detail}")
    except SyncError as exc:
        _log(vault, "session-end", f"sync --push skipped: {exc}")
    return 0


HOOK_HANDLERS = {
    "session-start": hook_session_start,
    "pre-compact": hook_pre_compact,
    "session-end": hook_session_end,
}


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


def merge_settings(settings: dict, snippet: dict) -> dict:
    """Merge the snippet's hook entries into existing settings without
    touching anything else. Idempotent: an entry whose command already
    exists for the event is not re-added."""
    merged = dict(settings)
    hooks = dict(merged.get("hooks") or {})
    for event, entries in snippet["hooks"].items():
        existing = list(hooks.get(event) or [])
        known = {
            h.get("command")
            for e in existing
            for h in (e.get("hooks") or [])
        }
        for entry in entries:
            cmd = entry["hooks"][0]["command"]
            if cmd not in known:
                existing.append(entry)
        hooks[event] = existing
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
