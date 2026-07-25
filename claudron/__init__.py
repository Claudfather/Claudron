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

from .vault import Vault, detect
from .knowledge import KnowledgeDoc, KnowledgeResult, lookup, resolve_wikilinks

__all__ = [
    "Vault",
    "detect",
    "lookup",
    "resolve_wikilinks",
    "KnowledgeDoc",
    "KnowledgeResult",
    "__version__",
]
