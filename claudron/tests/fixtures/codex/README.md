# Native Codex lifecycle fixtures

Captured from actual Codex CLI 0.162.0-alpha.17.2 hook stdin, not reconstructed from vendor source. The instrumentation parsed stdin only in memory and replaced identifiers, filesystem paths and content strings before writing these files. Key ordering, nesting, scalar types and protocol enums are retained. The fake session UUID and /tmp paths are placeholders.

`manifest.json` records the exact transformer hash, actual raw-input hash/length and sanitized-file hash for each capture. Private raw payloads were not persisted. The independent P0 canary retains the instrumentation/provenance; its canonical evidence is the 2026-10-16 continuation of Claudfather/Claudlobby#2145's runtime-neutral run log. These five observed lifecycle shapes ground this owner adapter; no unobserved event support or universal transcript-path nullability is inferred.
