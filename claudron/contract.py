"""The machine-readable contract: what a consumer writes against, as data.

``claudron contract --json`` prints :func:`contract`. A consumer keeps a copy
of it (a rendered copy with a drift gate, boundary spec §10.4) and checks its
own mirrors against that copy in its own CI, with no engine installed. Before
this existed, a consumer's mirror of, say, a home's sections could only be
checked by importing ``claudron.schema``, so the check skipped wherever the
engine wasn't installed.

Every value comes from the module that owns it; nothing is restated here.
``CONTRACT_VERSION`` changes only when this payload's *shape* changes (a key
removed, renamed or retyped). New keys and new values in a list are additive.
"""

from __future__ import annotations

from . import CAPABILITIES, __version__
from .schema import HOMES, MATURITY_VALUES, PERSON_DIR, RELATIONS, SOURCE_TYPES, TRUST_CLASSES, TYPES

CONTRACT_VERSION = 1


def contract() -> dict:
    """The contract payload. Pure: no vault, no I/O, same answer for the same engine."""
    return {
        "contract_version": CONTRACT_VERSION,
        "engine_version": __version__,
        "capabilities": list(CAPABILITIES),
        "types": list(TYPES),
        "homes": {home: list(sections) for home, sections in HOMES.items()},
        "relations": list(RELATIONS),
        "maturity": list(MATURITY_VALUES),
        "source_types": list(SOURCE_TYPES),
        "trust_classes": list(TRUST_CLASSES),
        "person_dir": PERSON_DIR,
    }
