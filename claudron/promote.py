"""Maturity promotion — move a note along the trust ladder (E5, PR1).

The curation half of the graph slice: a note's ``maturity`` (the D11 trust axis,
distinct from the activity ``status``) rises draft → verified → canonical as a
human vouches for it, and can be demoted the same way. Every transition stamps
provenance (``promoted_by`` / ``promoted_at``) so the git history and the
frontmatter both record who trusted what, when.

v1 is human-triggered by construction (a CLI verb) — the human running it *is*
the gate the plan reserves for ``canonical``; automated N-bot/LLM promotion is a
deferred non-goal. Mirrors ``engine.append_addendum``'s write path exactly:
containment guard → vault write-lock over read→write→index → lenient revalidate
(a promote that would corrupt the note is reported and not written) → atomic
write → index refresh (maturity feeds ranking + the ``status`` lifecycle metric).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .engine import ScopeError
from .knowledge import ensure_index, write_index
from .locking import atomic_write_text, vault_write_lock
from .schema import (
    MATURITY_VALUES,
    Finding,
    ladder_index,
    parse_note,
    set_frontmatter_field,
    validate_note,
)
from .vault import Vault, is_within_root


@dataclass
class PromoteResult:
    """Outcome of a maturity transition. ``action``:
    ``promoted`` | ``demoted`` | ``unchanged`` | ``rejected``."""

    action: str
    path: str
    from_maturity: str
    to_maturity: str
    promoted_by: str = ""
    promoted_at: str = ""
    errors: list[Finding] = field(default_factory=list)

    @property
    def written(self) -> bool:
        """True iff the note changed on disk. The shared success-signal (mirrors
        ``engine.WriteResult.written``, PR-H) so a CLI/MCP door branches on this,
        not on the ``action`` string — ``unchanged`` and ``rejected`` wrote
        nothing."""
        return self.action in ("promoted", "demoted")

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "path": self.path,
            "from": self.from_maturity,
            "to": self.to_maturity,
            "promoted_by": self.promoted_by,
            "promoted_at": self.promoted_at,
            "written": self.written,
            "errors": [f.to_dict() for f in self.errors],
        }


def promote(
    vault: Vault, note_path: Path, *, to_maturity: str, actor: str
) -> PromoteResult:
    """Set *note_path*'s ``maturity`` to *to_maturity*, stamping ``promoted_by``
    / ``promoted_at``. Direction (promoted vs demoted) is derived from the ladder;
    a no-op (already at *to_maturity*) returns ``unchanged`` without a write.

    *to_maturity* must be a value in ``MATURITY_VALUES`` (the CLI enforces this
    via argparse choices). Caller resolves the note reference to a path — same
    contract as ``append_addendum``."""
    if to_maturity not in MATURITY_VALUES:
        raise ValueError(
            f"maturity must be one of {MATURITY_VALUES}, not {to_maturity!r}"
        )
    if not is_within_root(note_path, vault.root):
        raise ScopeError(f"path {str(note_path)!r} escapes the vault root")
    note_path = note_path.resolve()
    rel = str(note_path.relative_to(vault.root))
    today = date.today().isoformat()

    # One lock over read→write→index (same critical section as capture/append):
    # a concurrent writer must not stale the index between our read and rewrite.
    # This mirrors engine.append_addendum's guarded-mutate skeleton;
    # extract a shared engine._guarded_mutate(mutate, refresh) when a 3rd
    # in-place note-mutator lands (rule of three).
    with vault_write_lock(vault):
        original = note_path.read_text()
        fm_before, _body, _err = parse_note(original)
        current = str(fm_before.get("maturity", ""))

        if current == to_maturity:  # no-op: skip the index load entirely
            return PromoteResult(
                action="unchanged", path=rel,
                from_maturity=current, to_maturity=to_maturity,
            )

        index = ensure_index(vault)  # fresh BEFORE the write (append_addendum note)
        text = set_frontmatter_field(original, "maturity", to_maturity)
        text = set_frontmatter_field(text, "promoted_by", actor)
        text = set_frontmatter_field(text, "promoted_at", today)

        fm, note_body, err = parse_note(text)
        findings = validate_note(
            fm, note_body, strict=False, path=rel, raw=text, parse_error=err
        )
        errors = [f for f in findings if f.severity == "error"]
        if errors:
            return PromoteResult(
                action="rejected", path=rel,
                from_maturity=current, to_maturity=to_maturity, errors=errors,
            )

        atomic_write_text(note_path, text)

        # Refresh the entry's maturity so ranking + the status metric see it
        # without a full rebuild (write index.json last — mtime ≥ the note's).
        for entry in index.get("entries", []):
            if entry.get("path") == rel:
                entry["maturity"] = to_maturity
                break
        write_index(vault, index)

    action = (
        "promoted" if ladder_index(to_maturity) > ladder_index(current) else "demoted"
    )
    return PromoteResult(
        action=action, path=rel, from_maturity=current, to_maturity=to_maturity,
        promoted_by=actor, promoted_at=today,
    )
