"""Replay #178 through the installed hook commands on disposable local vaults.

Run from the checkout with: python -m claudron.tests.replay_session_start
The output measures hook stdout. Native runtime context retention is a
separate observation. No native sessions or provider requests are created.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from claudron.vault import init

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("fixtures") / "codex"
SID = "00000000-0000-4000-8000-000000000001"
FORK_SID = "00000000-0000-4000-8000-000000000002"
WEB_BODY = "WEB_BODY_CANARY: the synthetic web text is still under review."
SESSION_BODY = "SESSION_BODY_CANARY: the synthetic transcript text is still under review."
AUTHORED_BODY = "AUTHORED_BODY_CANARY: the synthetic plan is still under review."
REVIEWED_BODY = "REVIEWED_BODY_CANARY: résumé validation runs before import."
UPDATED_BODY = "REVIEWED_UPDATE_CANARY: résumé validation now runs after import."
CAPTURE_PREFIX = b"After compaction: "


def run(argv: list[str], cwd: Path, env: dict[str, str], stdin: bytes = b"") -> bytes:
    result = subprocess.run(argv, cwd=cwd, env=env, input=stdin,
                            capture_output=True, timeout=20, check=False)
    if result.returncode:
        raise RuntimeError(f"{argv!r} exited {result.returncode}: {result.stderr.decode()}")
    if "hook" in argv and result.stderr:
        raise RuntimeError(f"Unexpected hook stderr: {result.stderr.decode()}")
    return result.stdout


def git(cwd: Path, env: dict[str, str], *args: str) -> bytes:
    return run(["git", *args], cwd, env)


def note(path: Path, title: str, body: str, maturity: str, source_type: str, source_url: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    provenance = f"source_url: {source_url}\n" if source_url else ""
    path.write_text(
        f"---\ntitle: {title}\ntype: knowledge\nstatus: current\nowner: replay\n"
        f"created: 2026-11-21\nupdated: 2026-11-21\ntags: [import]\n"
        f"maturity: {maturity}\nsource_type: {source_type}\n{provenance}---\n\n"
        f"# {title}\n\n{body}\n", encoding="utf-8"
    )


def payload(agent: str, event: str, source: str, work: Path) -> tuple[bytes, str]:
    fixtures = sorted(FIXTURES.glob(f"{event.lower()}-{source}-*.json"))
    captured = agent == "codex" and bool(fixtures)
    data = json.loads(fixtures[0].read_bytes()) if captured else {}
    data.update(
        cwd=str(work),
        session_id=FORK_SID if source == "fork" else SID,
        transcript_path=str(work / "synthetic-transcript.jsonl"),
        hook_event_name=event,
        model="synthetic",
    )
    data.setdefault("permission_mode", "default")
    if event == "PreCompact":
        data["trigger"] = source
    else:
        data["source"] = source
    provenance = "captured shape" if captured else "documented shape"
    return json.dumps(data).encode(), provenance


def sections(brief: bytes) -> dict[bytes, bytes]:
    starts = list(re.finditer(rb"^## .+$", brief, flags=re.MULTILINE))
    ends = [match.start() for match in starts[1:]] + [len(brief)]
    return {
        match[0]: brief[match.start():end].rstrip(b"\n")
        for match, end in zip(starts, ends)
    }


def replay(agent: str, base: Path) -> None:
    work = base / "import-demo"
    home = base / "home"
    tmp = base / "tmp"
    for directory in (work, home, tmp):
        directory.mkdir(parents=True)
    env = {
        "PATH": os.defpath + os.pathsep + str(Path(sys.executable).parent),
        "HOME": str(home), "TMPDIR": str(tmp), "LC_ALL": "C",
        "PYTHONUTF8": "1", "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_ALLOW_PROTOCOL": "file",
        "GIT_AUTHOR_NAME": "Replay", "GIT_AUTHOR_EMAIL": "replay@example.invalid",
        "GIT_COMMITTER_NAME": "Replay", "GIT_COMMITTER_EMAIL": "replay@example.invalid",
    }
    seed = init(base / "seed")
    (seed / "_shared" / "CONVENTIONS.md").write_text(
        "---\nmaturity: verified\n---\n\n"
        "# Conventions\n\nValidate each import with a synthetic record.\n",
        encoding="utf-8",
    )
    project = seed / "projects" / work.name
    reviewed = project / "reviewed.md"
    note(reviewed, "Reviewed import rule", REVIEWED_BODY, "verified", "inline")
    note(project / "web.md", "Unreviewed web import", WEB_BODY, "draft", "url",
         "https://example.invalid/import")
    note(project / "session.md", "Unreviewed transcript import", SESSION_BODY, "draft", "session",
         "session:synthetic:1")
    git(seed, env, "init", "-qb", "main")
    git(seed, env, "add", ".")
    git(seed, env, "commit", "-qm", "Synthetic seed")
    remote = base / "origin.git"
    git(base, env, "clone", "-q", "--bare", str(seed), str(remote))
    vault = base / "vault"
    git(base, env, "clone", "-q", str(remote), str(vault))
    cli = [sys.executable, "-m", "claudron.cli", "--vault", str(vault)]
    snippet = json.loads(run(cli + ["hooks", "install", "--agent-cli", agent], work, env))
    commands = {
        event: shlex.split(groups[0]["hooks"][0]["command"])
        for event, groups in snippet["hooks"].items()
    }

    previous: dict[bytes, bytes] = {}

    def arm(event: str, source: str, case: str, *, updated: bool = False, capture: bool = False) -> bytes:
        nonlocal previous
        stdin, provenance = payload(agent, event, source, work)
        stdout = run(commands[event], work, env, stdin)
        brief, separator, _ = stdout.partition(CAPTURE_PREFIX)
        current = sections(brief)
        repeated = [name.decode().removeprefix("## ") for name in current
                    if current[name] == previous.get(name)]
        if event == "PreCompact":
            assert not stdout, (agent, case, stdout)
        else:
            assert len(current) == 3, (agent, case, stdout)
            assert (UPDATED_BODY if updated else REVIEWED_BODY).encode() in brief
            assert b"Unreviewed web import" in brief and b"Unreviewed transcript import" in brief
            assert b"WEB_BODY_CANARY" not in stdout and b"SESSION_BODY_CANARY" not in stdout
            assert bool(separator) == capture, (agent, case, stdout)
            previous = current
        print(f"| {agent} | {case} ({source}) | {provenance} | {len(brief)} | "
              f"{len(stdout) - len(brief)} | {', '.join(repeated) or '—'} |")
        return brief

    original = arm("SessionStart", "startup", "Fresh start")
    assert arm("SessionStart", "resume", "Unchanged resume") == original
    arm("PreCompact", "manual", "Before compaction")
    assert arm("SessionStart", "compact", "After compaction", capture=True) == original
    assert arm("SessionStart", "compact", "Second compaction") == original
    assert arm("SessionStart", "clear", "Clear") == original
    assert arm("SessionStart", "fork", "Fork") == original

    note(reviewed, "Reviewed import rule", UPDATED_BODY, "verified", "inline")
    git(seed, env, "add", str(reviewed))
    git(seed, env, "commit", "-qm", "Revise reviewed rule")
    git(seed, env, "push", "-q", str(remote), "main")
    assert UPDATED_BODY.encode() not in (vault / reviewed.relative_to(seed)).read_bytes()
    changed = arm("SessionStart", "resume", "Reviewed update from upstream", updated=True)
    assert changed != original and REVIEWED_BODY.encode() not in changed
    assert git(vault, env, "rev-parse", "HEAD") == git(seed, env, "rev-parse", "HEAD")

    note(vault / "projects" / work.name / "authored.md",
         "Unreviewed authored import", AUTHORED_BODY, "draft", "inline")
    authored = arm("SessionStart", "resume", "Authored draft control", updated=True)
    assert b"Unreviewed authored import" in sections(authored)[b"## Unverified (not yet reviewed)"]
    assert b"AUTHORED_BODY_CANARY" not in authored


def main() -> None:
    print("| Adapter | Event | Payload provenance | Brief B | Capture B | Repeated brief sections |")
    print("| --- | --- | --- | ---: | ---: | --- |")
    with tempfile.TemporaryDirectory(prefix="claudron-178-") as directory:
        for agent in ("claude", "codex"):
            replay(agent, Path(directory) / agent)


if __name__ == "__main__":
    main()
