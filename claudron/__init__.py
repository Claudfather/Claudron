"""Claudron — standalone knowledge engine for Claude Code.

Public API::

    from claudron import detect, lookup, resolve_wikilinks

    vault = detect()                        # walk up from CWD
    results = lookup("auth", vault=vault)   # search vault knowledge
    resolved = resolve_wikilinks(text, vault=vault)  # [[wikilink]] → note refs

Types: `Vault`, `KnowledgeDoc`, `KnowledgeResult` (return types).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claudron")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

#: What this engine SHIPS, declared rather than inferred — `docs/CLI_CONTRACT.md`
#: register rule R5, "capability is declared to the owner, never inferred", and
#: `docs/CLAUDE.md`'s "capabilities are declared to the engine".
#:
#: It exists because the three obvious ways to infer this all fail, measured:
#:
#: * A VERSION FLOOR cannot be expressed. `engine_version` is `0.5.0.dev0` on a
#:   build of the branch that ships a feature and `0.4.0` on the last release,
#:   and PEP 440 sorts a dev release BEFORE its release — so the `>= 0.5.0` a
#:   CHANGELOG naturally invites is satisfied by neither, and the gate can never
#:   pass. Claudlobby's own compat table says the same thing from its side:
#:   release numbers are ordinal, so a row is met "when the capability answers,
#:   not when a version string compares".
#: * A VERB probe (`claudron <verb> --help`, exit 2 on an unknown verb) cannot
#:   see a new FLAG on a verb that already exists.
#: * A FLAG probe (`claudron index --navigation --help`) cannot fail: argparse
#:   fires `--help` as a parse action and exits 0 before it reports unknown
#:   arguments, so it returns 0 on an engine with no such flag.
#:
#: A name here is a CONTRACT: add one when a capability ships, and never remove
#: or rename one without a breaking-change entry.
CAPABILITIES: tuple[str, ...] = (
    "navigation",   # `index --navigation` regenerates INDEX.md from the index
)

from .vault import Vault, detect
from .knowledge import KnowledgeDoc, KnowledgeResult, lookup, resolve_wikilinks

__all__ = [
    "Vault",
    "detect",
    "lookup",
    "resolve_wikilinks",
    "KnowledgeDoc",
    "KnowledgeResult",
    "CAPABILITIES",
    "__version__",
]
