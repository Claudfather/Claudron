"""The machine-readable contract: what a consumer writes against, as data.

``claudron contract --json`` prints :func:`contract`. A consumer keeps a copy
of it (a rendered copy with a drift gate, boundary spec §10.4) and checks its
own mirrors against that copy in its own CI, with no engine installed. Before
this existed, a consumer's mirror of, say, a home's sections could only be
checked by importing ``claudron.schema``, so the check skipped wherever the
engine wasn't installed.

Every value comes from the module that owns it; nothing is restated here. The
payload carries no engine version: a copy changes when the contract does, not
on every release. ``CONTRACT_VERSION`` changes only when the payload's *shape*
changes (a key removed, renamed or retyped). New keys and new values in a
list are additive.
"""

from __future__ import annotations

from . import CAPABILITIES
from .schema import (HOMES, MATURITY_VALUES, PERSON_DIR, RELATIONS, SOURCE_TYPES, STATUS_VOCAB, TRUST_CLASSES,
                     TYPE_DIRS, TYPES)

CONTRACT_VERSION = 1


def _statuses() -> dict:
    return {t: {"canonical": list(v["canonical"]), "terminal": list(v["terminal"]), "legacy": dict(v["legacy"]),
                "default": v["default"]} for t, v in STATUS_VOCAB.items()}


def contract() -> dict:
    """The contract payload. Pure: no vault, no I/O, the same answer for the same contract."""
    return {
        "contract_version": CONTRACT_VERSION,
        "capabilities": list(CAPABILITIES),
        "types": list(TYPES),
        "type_dirs": dict(TYPE_DIRS),
        "statuses": _statuses(),
        "homes": {home: list(sections) for home, sections in HOMES.items()},
        "relations": list(RELATIONS),
        "maturity": list(MATURITY_VALUES),
        "source_types": list(SOURCE_TYPES),
        "trust_classes": list(TRUST_CLASSES),
        "person_dir": PERSON_DIR,
    }
