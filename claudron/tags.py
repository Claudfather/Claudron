"""The tag registry (#200 §3): one git-tracked file says which tags exist and what they mean.

``_shared/TAGS.yaml`` (a non-note file: never indexed, ranked or validated as
a note)::

    version: 1
    facets: [domain, tech, repo, fleet, team]     # closed: what a registered tag's prefix may be
    tags:
      tech:python:
        description: The Python language and its tooling
        aliases: [lang:python, py]
      tech:py2:
        status: deprecated
        merged_into: tech:python

Tags are open: a note may carry any tag, registered or not. The registry
names the canonical ones, and :func:`canonical` maps an alias or a merged tag
to its canonical form. Usage counts come from the derived index and are never
stored here. Subjects have no enum (#200 §3): a subject exists because its
note does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .schema import _as_str_list
from .vault import Vault

REGISTRY = "TAGS.yaml"
FACETS = ("domain", "tech", "repo", "fleet", "team")
STATUSES = ("active", "proposed", "deprecated")


@dataclass
class Tag:
    name: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    status: str = "active"
    merged_into: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Registry:
    """The parsed registry: its tags by name, every name and alias folded, and what is wrong with the file."""

    path: Path
    facets: tuple[str, ...] = FACETS
    tags: dict[str, Tag] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)  #: folded name → the registry's spelling
    aliases: dict[str, str] = field(default_factory=dict)  #: folded alias → its tag
    problems: list[str] = field(default_factory=list)

    def _chain(self, name: str) -> tuple[str, bool]:
        """Follow ``merged_into`` from a registered ``name`` (deprecated tags only): ``(end, looped)``."""
        seen: set[str] = set()
        while name in self.tags and self.tags[name].status == "deprecated" and self.tags[name].merged_into:
            if name in seen:
                return name, True
            seen.add(name)
            name = self.tags[name].merged_into
        return name, False

    def canonical(self, tag: str) -> str:
        """``tag``'s canonical form, case-insensitively: a registered name in the registry's spelling, an
        alias as its tag, a deprecated tag along ``merged_into``. A tag the registry doesn't know comes
        back stripped, as written."""
        text = tag.strip()
        folded = text.lower()
        name = self.names.get(folded) or self.aliases.get(folded)
        return self._chain(name)[0] if name else text


def registry_path(vault: Vault) -> Path:
    return vault.shared / REGISTRY


def load(vault: Vault) -> Registry | None:
    """The vault's registry, or ``None`` when it has none. A malformed file loads what it can and says why."""
    path = registry_path(vault)
    if not path.is_file():
        return None
    reg = Registry(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        reg.problems.append(f"unreadable: {str(exc).splitlines()[0][:160]}")
        return reg
    if not isinstance(data, dict):
        reg.problems.append("the file is not a mapping")
        return reg
    if "facets" in data and not isinstance(data["facets"], list):
        reg.problems.append("`facets` is not a list")
    facets = _as_str_list(data.get("facets")) or list(FACETS)
    if unknown := [f for f in facets if f not in FACETS]:
        reg.problems.append(f"facets outside the closed set {list(FACETS)}: {unknown}")
    reg.facets = tuple(f for f in facets if f in FACETS)
    raw = data.get("tags") or {}
    if not isinstance(raw, dict):
        reg.problems.append("`tags` is not a mapping")
        raw = {}
    for name, spec in raw.items():
        name = str(name).strip()
        spec = spec if isinstance(spec, dict) else {}
        facet = name.split(":", 1)[0].lower() if ":" in name else ""
        if facet not in reg.facets:
            reg.problems.append(f"{name}: not `facet:value` with a facet in {list(reg.facets)}")
            continue
        if name.lower() in reg.names:
            reg.problems.append(f"{name}: the same tag as {reg.names[name.lower()]} (tags are case-insensitive)")
            continue
        aliases = []
        for alias in spec.get("aliases") if isinstance(spec.get("aliases"), list) else _as_str_list(spec.get("aliases")):
            if not isinstance(alias, str):
                reg.problems.append(f"{name}: alias {alias!r} is not a string (quote it: YAML reads yes/no/1 as values)")
            elif alias.strip():
                aliases.append(alias.strip())
        tag = Tag(name, str(spec.get("description") or ""), aliases, str(spec.get("status") or "active"),
                  str(spec.get("merged_into") or "").strip())
        if tag.status not in STATUSES:
            reg.problems.append(f"{name}: status {tag.status!r} is not one of {list(STATUSES)}")
        if tag.status == "deprecated" and not tag.merged_into:
            reg.problems.append(f"{name}: deprecated without `merged_into`")
        if tag.merged_into and tag.status != "deprecated":
            reg.problems.append(f"{name}: `merged_into` on a tag that isn't deprecated (ignored)")
        reg.tags[name] = tag
        reg.names[name.lower()] = name
    for tag in reg.tags.values():
        if tag.status == "deprecated" and tag.merged_into and tag.merged_into not in reg.tags:
            reg.problems.append(f"{tag.name}: merged_into {tag.merged_into!r} is not a registered tag")
        for alias in tag.aliases:
            folded = alias.lower()
            if folded == tag.name.lower():
                reg.problems.append(f"{tag.name}: alias {alias!r} is the tag's own name")
            elif folded in reg.names:
                reg.problems.append(f"{tag.name}: alias {alias!r} is the registered tag {reg.names[folded]}")
            elif reg.aliases.get(folded, tag.name) != tag.name:
                reg.problems.append(f"{tag.name}: alias {alias!r} is already an alias of {reg.aliases[folded]}")
            else:
                reg.aliases[folded] = tag.name
    for name in reg.tags:
        end, looped = reg._chain(name)
        if looped and end == name:
            reg.problems.append(f"{name}: merged_into loops back to it")
    return reg


def canonicalize(vault: Vault, tags: list[str]) -> list[str]:
    """``tags`` with each alias and merged tag replaced by its canonical form, order kept, duplicates dropped."""
    reg = load(vault)
    if reg is None:
        return list(tags)
    return list(dict.fromkeys(reg.canonical(t) for t in tags))


def report(vault: Vault, usage: dict[str, int]) -> dict:
    """``tags --json``: the registry's tags with their usage, and what notes use that it doesn't cover.

    ``usage`` is ``{tag: notes carrying it}`` from the index. ``unregistered`` lists tags in use under
    a registered facet that the registry doesn't name (the ones worth adding or mapping); tags outside
    every facet (a consumer's own namespaces) are counted in ``other`` only.
    """
    reg = load(vault)
    if reg is None:
        return {"registry": None, "tags": [], "unregistered": [], "noncanonical_in_use": [], "other": len(usage),
                "problems": []}
    faceted = {t for t in usage if t.split(":", 1)[0].lower() in reg.facets}
    return {
        "registry": str(reg.path.relative_to(vault.root)),
        "tags": [{**t.as_dict(), "count": usage.get(t.name, 0)} for t in sorted(reg.tags.values(), key=lambda t: t.name)],
        "unregistered": sorted(({"tag": t, "count": usage[t]} for t in faceted if reg.canonical(t) == t
                                and t not in reg.tags), key=lambda d: (-d["count"], d["tag"])),
        "noncanonical_in_use": sorted(({"tag": t, "count": usage[t], "canonical": reg.canonical(t)} for t in usage
                                     if reg.canonical(t) != t), key=lambda d: (-d["count"], d["tag"])),
        "other": len(set(usage) - faceted),
        "problems": reg.problems,
    }
