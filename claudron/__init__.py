"""Claudron — standalone knowledge engine for Claude Code.

Public API::

    from claudron import detect, lookup, resolve_wikilinks

    vault = detect()                        # walk up from CWD
    results = lookup("auth", vault=vault)   # search vault knowledge
    resolved = resolve_wikilinks(text, vault=vault)  # Phase 4
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("claudron")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from .vault import Vault, detect
from .knowledge import KnowledgeDoc, KnowledgeResult, lookup


def resolve_wikilinks(text: str, vault: Vault) -> dict[str, dict]:
    """Resolve ``[[wikilinks]]`` in *text*.

    Returns a mapping of ``{"[[topic]]": {"path": ..., "title": ..., "tier": ...}}``.

    .. note:: Stub for Phase 4. Returns an empty dict.
    """
    return {}
