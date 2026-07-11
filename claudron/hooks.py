"""The hook pack: Claude Code lifecycle glue for the session loop (E2).

Three events, one contract: **hooks fail open**. A hook must never break a
session — on any error it emits nothing (SessionStart stdout is injected
into agent context verbatim), logs to ``.claudron/hooks.log`` (or the
user's temp dir when no vault resolves), and exits 0.

- SessionStart → ``sync --pull`` (hard timeout, offline fail-open) then
  the recall brief on stdout. Pull precedes recall or machine B briefs
  stale.
- PreCompact → block-and-instruct once per session: prompt the agent to
  distill durable findings through ``claudron capture``. When clauDNA is
  installed it owns the PreCompact capture prompt (a bare ``/claudna:capture``
  distills the session), so this hook defers — one prompt per event.
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
# so fail-open alone can't save a stalled push (gauntlet finding)


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
    # Bounded: marketplace/plugin layout is one level deep, and the dir
    # itself is the signal (a `**/claudna/*` glob walked the whole cache
    # on the miss path and missed empty dirs — gauntlet finding).
    plugins = Path.home() / ".claude" / "plugins"
    if not plugins.is_dir():
        return False
    return any(plugins.glob("*/claudna")) or any(plugins.glob("*/*/claudna"))


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


def hook_session_start(vault: Vault | None) -> int:
    """Emit the session brief on stdout (fail-open, like every hook)."""
    _stdin_payload()  # drain stdin per the hook protocol
    if vault is None:
        _log(None, "session-start", "no vault resolvable — nothing injected")
        return 0
    brief = session_start_brief(vault)
    if brief:
        print(brief)
    return 0


def hook_pre_compact(vault: Vault | None) -> int:
    """Block the first compaction with the capture prompt; pass afterwards.

    Defer when clauDNA is installed: its PreCompact hook owns the single
    capture prompt (a bare ``/claudna:capture`` distills the session), and two
    block-prompts on one event would double up. Claudron-only installs keep
    the prompt.
    """
    payload = _stdin_payload()
    if vault is None:
        return 0
    if _claudna_installed():
        return 0
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
                    "into the vault. For each durable finding, run `claudron capture "
                    "--type knowledge --title \"...\" --body \"...\"` (dedup will route "
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
        result = sync(vault, pull=False, push=True, timeout=SESSION_END_PUSH_TIMEOUT)
        if not result.ok:
            _log(vault, "session-end", f"sync --push degraded: {result.detail}")
    except SyncError as exc:
        _log(vault, "session-end", f"sync --push skipped: {exc}")
    return 0


def run_hook(event: str, vault: Vault | None) -> int:
    """THE fail-open boundary: whatever goes wrong inside a handler —
    including exception classes the inner guards never anticipated — a
    hook exits 0 with nothing on stdout. One guard at the boundary
    instead of per-call try blocks of mismatched breadth (gauntlet
    finding: a PermissionError from the git layer escaped the narrow
    SyncError catch and would have broken the session)."""
    try:
        return _HOOK_HANDLERS[event](vault)
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
    append a duplicate entry instead of replacing the stale one (gauntlet
    finding: the exact portability scenario absolute paths exist for)."""
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
