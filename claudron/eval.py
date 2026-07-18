"""Retrieval eval harness — measure recall@k of ``lookup`` on a fixed query set.

The **G1/F2 instrument**: the re-scope defers E4's SQLite/FTS5 scale tier behind a
named trigger (D6/F2 — "paraphrase-miss rate crosses a threshold, or the vault
passes ~1k notes"). This makes the paraphrase-miss half of that trigger
*measurable* instead of assumed. Run it against the reference vault; if
heuristic ``lookup`` already misses too many paraphrases, the scale bet is
warranted — otherwise the deferral is evidence-based.

Stdlib + the existing ``lookup`` only; no new dependency. When E4's ranking
lands, the same harness scores the before/after the roadmap promises to publish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .knowledge import lookup
from .vault import Vault

SEED_PATH = Path(__file__).parent / "tests" / "eval" / "queries.json"


@dataclass
class EvalResult:
    total: int
    hits: int  # expected note in top-k
    by_kind: dict[str, tuple[int, int]]  # kind -> (hits, total)
    misses: list[dict]  # the queries that missed, for inspection

    @property
    def recall(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def kind_recall(self, kind: str) -> float:
        hits, total = self.by_kind.get(kind, (0, 0))
        return hits / total if total else 0.0


def load_seed(path: Path | None = None) -> dict:
    return json.loads((path or SEED_PATH).read_text())


def run_eval(vault: Vault, seed: dict | None = None) -> EvalResult:
    """Score every seed query: is its ``expects`` path in ``lookup``'s top-k?"""
    seed = seed or load_seed()
    k = int(seed.get("k", 5))
    by_kind: dict[str, list[int]] = {}
    misses: list[dict] = []
    hits = 0
    for q in seed["queries"]:
        results = lookup(q["query"], vault, limit=k)
        got = [str(r.doc.source_path.relative_to(vault.root)) for r in results]
        hit = q["expects"] in got
        hits += hit
        kind = q.get("kind", "literal")
        bucket = by_kind.setdefault(kind, [0, 0])
        bucket[0] += int(hit)
        bucket[1] += 1
        if not hit:
            misses.append({"query": q["query"], "kind": kind,
                           "expects": q["expects"], "got": got})
    return EvalResult(
        total=len(seed["queries"]),
        hits=hits,
        by_kind={kind: (h, t) for kind, (h, t) in by_kind.items()},
        misses=misses,
    )


def format_report(result: EvalResult) -> str:
    lines = [
        f"retrieval eval: recall@k = {result.recall:.0%} "
        f"({result.hits}/{result.total})",
    ]
    for kind in sorted(result.by_kind):
        h, t = result.by_kind[kind]
        lines.append(f"  {kind:<10s} {h}/{t}  ({h / t:.0%})")
    if result.misses:
        lines.append("  misses:")
        for m in result.misses:
            lines.append(f"    [{m['kind']}] {m['query']!r} → wanted {m['expects']}")
    return "\n".join(lines)
