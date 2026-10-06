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
import re
import os
import shlex
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import ops
from .session import derive_project, recall, render_brief
from .sync import SyncError, pull_ff_only, sync
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


#: The path a brief line ends with (an Unverified line adds `` · from <source>`` after it).
_RENDERED_PATH = re.compile(r"`([^`]+)`(?: · from .*)?$")


def _session_id(payload: dict) -> str | None:
    """The hook payload's ``session_id``, when it is a string (the ops log keys a directory on it)."""
    sid = payload.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def _stdin_payload() -> dict:
    """Claude Code hook input (JSON on stdin); tolerate anything."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def session_start_brief(vault: Vault, session_id: str | None = None) -> str:
    """The order-sensitive SessionStart composition: bounded pull, THEN
    recall (pull must precede recall or machine B briefs stale — the
    epic's acceptance-test invariant). The session-layer seam both the
    hook and any future door (E3) call; sync degradation never blocks
    the brief."""
    try:
        # FAST-FORWARD ONLY, never `sync(pull=True)` (#156). That call commits
        # whatever is on disk and then rebases in the live tree, on THIS budget
        # -- and SessionStart fires on startup, resume, clear AND compaction, so
        # a long-running bot rewrote its own vault at an unpredictable moment
        # mid-session. A 2 s budget has exactly two outcomes against a rebase:
        # nothing to do, or killed part-way with HEAD detached. `fetch` writes
        # only under `.git/` and `merge --ff-only` is one ref-and-tree update,
        # so the same budget is honest here.
        result = pull_ff_only(vault, timeout=SESSION_START_PULL_TIMEOUT)
        if not result.ok:
            _log(vault, "session-start", f"pull --ff-only degraded: {result.detail}")
        elif result.local_ahead:
            # NOT a degradation: an ahead clone is a legitimate state that the
            # scheduled reconciliation door resolves. Logged so the operator of
            # a fleet that has not armed that door can SEE the divergence
            # accumulating rather than only find it later.
            _log(
                vault, "session-start",
                f"not fast-forwardable: {result.local_ahead} local commit(s) await "
                "reconciliation (a scheduled door resolves this; the tree was "
                "not rewritten)",
            )
        if result.quarantined:
            _log(
                vault, "session-start",
                f"quarantined this pull: {', '.join(result.quarantined)}",
            )
    except SyncError as exc:
        _log(vault, "session-start", f"pull --ff-only skipped: {exc}")
    # Re-detect after the pull: Vault is a frozen snapshot, and a pull can
    # introduce whole tiers (a project dir first created on another
    # machine) that the pre-pull snapshot — and any index built from it —
    # cannot see. Caught live: machine B's first brief about a project
    # born on machine A came back empty.
    vault = detect(vault.root) or vault
    data = recall(vault, project=derive_project())
    brief = render_brief(data)
    # The session's ops log (#200 §5): what this session was shown, trusted apart from unreviewed. Only
    # what the brief kept: the budget drops notes, and each rendered line ends with its `path`.
    # Each rendered note line ENDS with its backticked path; a path quoted in a summary doesn't count.
    rendered = {m.group(1) for line in brief.splitlines() if (m := _RENDERED_PATH.search(line))}

    def shown(entries: list[dict], trust: str | None = None) -> list[str]:
        return [e["path"] for e in entries if (trust is None or e.get("trust") == trust) and e["path"] in rendered]

    notes = data.get("notes") or []
    ops.record(vault, "recall.served", session_id=session_id, project=data.get("project"),
               trusted=shown(notes, "trusted"), drafts=shown(notes, "draft"),
               unverified=shown(data.get("unverified") or []))
    return brief


def hook_session_start(vault: Vault, payload: dict) -> int:
    """Emit the session brief on stdout (fail-open, like every hook)."""
    brief = session_start_brief(vault, _session_id(payload))
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
        ops.record(vault, "sync.push", session_id=_session_id(payload), ok=result.ok, detail=str(result.detail or ""))
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


#: Claude Code event -> the engine's `hook <event>` dispatch verb, in the
#: snippet's order. `settings_snippet` renders from it, `merge_settings` keys
#: its replace-not-append rule on it, and doctor's hook checks (#204) walk it,
#: so all three agree on which events the loop needs.
SNIPPET_EVENTS = {
    "SessionStart": "session-start",
    "PreCompact": "pre-compact",
    "SessionEnd": "session-end",
}


def settings_snippet(executable: str, vault_root: str) -> dict:
    """The Claude Code settings.json hooks block.

    Absolute-path commands (venv/pipx installs survive hook context, where
    PATH may not), each naming its vault with the global ``--vault`` (#183):
    walk-up binds only a directory carrying ``.claudron-vault``, so a session
    started outside the vault finds it only by an address. ``--vault`` goes
    before ``hook <event>``, the identity suffix ``merge_settings`` keys on.
    The vault root is shell-quoted when it needs it, because Claude Code runs
    the command through a shell. The executable is NOT quoted: it is a command
    prefix, and :func:`resolve_executable` falls back to the multi-word
    ``<python> -m claudron.cli``, which quoting would turn into one word."""
    prefix = f"{executable} --vault {shlex.quote(vault_root)}"

    def entry(event_cmd: str) -> list[dict]:
        return [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": f"{prefix} hook {event_cmd}"}],
            }
        ]

    return {"hooks": {event: entry(cmd) for event, cmd in SNIPPET_EVENTS.items()}}


def default_settings_path() -> Path:
    """The settings file `hooks install --write` writes when not given
    `--settings`, and so the one `doctor` checks by default (#204)."""
    return Path.home() / ".claude" / "settings.json"


def settings_shape_error(data: object) -> str | None:
    """Why `merge_settings` cannot merge into *data*, or None when it can.

    It checks only what the merge reads: a JSON object, its `hooks` (when
    present) an object, and each event in `SNIPPET_EVENTS` (when
    present) a list of objects whose own `hooks` is a list of objects. Other
    events are never touched, so their shape is not the install's to refuse."""
    if not isinstance(data, dict):
        return "not a JSON object"
    if "hooks" not in data:
        return None
    hooks = data["hooks"]
    if not isinstance(hooks, dict):
        return "its `hooks` is not an object"
    for event in SNIPPET_EVENTS:
        if event not in hooks:
            continue
        groups = hooks[event]
        if not isinstance(groups, list):
            return f"its `hooks.{event}` is not a list"
        for group in groups:
            if not isinstance(group, dict):
                return f"`hooks.{event}` holds an entry that is not an object"
            inner = group.get("hooks", [])
            if not isinstance(inner, list) or not all(isinstance(h, dict) for h in inner):
                return f"`hooks.{event}` holds an entry whose `hooks` is not a list of objects"
    return None


def read_settings(path: Path) -> tuple[dict | None, str | None]:
    """A settings file as `merge_settings` can use it: (settings, None), or
    (None, why) when it cannot, and ({}, None) when there is no file yet.

    `hooks install --write` refuses every file this cannot use, and `doctor`
    calls exactly those files unparseable (D009), through this one reader, so
    the remedy either one names is true of the other (#205)."""
    if not path.exists():
        return {}, None
    if not path.is_file():
        return None, "not a regular file"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, str(exc)
    why = settings_shape_error(data)
    return (None, why) if why else (data, None)


@dataclass(frozen=True)
class HookCommand:
    """A claudron hook command read back into its parts (#204)."""

    prefix: str  # the executable, as written: a command prefix
    vault: str | None  # the recorded `--vault` address, or None if it names none
    canonical: bool  # `settings_snippet` renders exactly this command from them


def parse_hook_command(command: str, event_cmd: str) -> HookCommand | None:
    """Read a hook command back into its executable prefix and `--vault`
    address, or return None when it is not a claudron hook for *event_cmd*.

    It is one when it ends in ``hook <event_cmd>``, the identity rule
    `merge_settings` keys on. It is *canonical* when `settings_snippet` would
    render exactly this string from the parts read. Anything else (an entry
    from before #183, `--vault=PATH`, stray spacing) is read best-effort from
    its shell words, so doctor can say what it found."""
    suffix = f"hook {event_cmd}"
    if not command.endswith(suffix):
        return None
    marker, start = " --vault ", 0
    while (i := command.find(marker, start)) != -1:
        start = i + 1
        prefix, rest = command[:i], command[i + len(marker):]
        if not prefix or prefix != prefix.strip() or not rest.endswith(" " + suffix):
            continue
        try:
            words = shlex.split(rest[: -len(suffix) - 1])
        except ValueError:
            continue
        if (len(words) == 1
                and f"{prefix} --vault {shlex.quote(words[0])} {suffix}" == command):
            return HookCommand(prefix, words[0], True)
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    vault, at = None, len(words) - 2
    for k, word in enumerate(words):
        if word == "--vault" and k + 1 < len(words):
            vault, at = words[k + 1], k
            break
        if word.startswith("--vault="):
            vault, at = word[len("--vault="):], k
            break
    return HookCommand(" ".join(words[:at]), vault, False)


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
    for event, entries in snippet["hooks"].items():
        event_cmd = SNIPPET_EVENTS[event]  # the one event map: the snippet was rendered from it
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
