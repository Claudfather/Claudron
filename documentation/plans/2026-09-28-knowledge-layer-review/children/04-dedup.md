TITLE: Capture dedup only catches exact twins — paraphrased re-captures create duplicates
LABELS: enhancement,priority:medium

Part of #{{EPIC}}. Related: #{{index}}, #{{reduce}}.

## Finding

`engine.find_duplicate` (`claudron/engine.py:186`) routes a capture to `suggest_update` only on exact matches:

- a lowercased exact **title, alias or slug** match; or
- a **byte-identical** body fingerprint.

LLM agents rarely repeat a title exactly. The dominant duplicate source is therefore paraphrase at every compaction.

The PreCompact prompt still tells agents that "Dedup routes a near-duplicate to the note that already covers it" (`hooks.py:148`). That claim is not true.

## Evidence (reproduced)

| Existing note | Re-capture | Result |
|---|---|---|
| "JWT validation gotchas" | "Gotchas when validating JWTs", near-identical body | `created` (twin) |
| "Token rotation schedule" | "Token rotation cadence", paraphrased body | `created` (twin) |
| "Token rotation schedule" | "token rotation schedule" (case change only) | `suggest_update` (works) |

## Test it on yourself

Scratch vault.

```bash
V=$(mktemp -d)/v && claudron init "$V" && (cd "$V" && git init -q .)
c(){ printf '%s' "$1" | claudron --vault "$V" capture --stdin --json | jq -r '.data.action+" "+.data.path'; }
c '{"type":"knowledge","title":"JWT validation gotchas","body":"Always pin the alg header; never accept none. Clock skew tolerance is 60s."}'
c '{"type":"knowledge","title":"Gotchas when validating JWTs","body":"Always pin the alg header and never accept alg none. Allow 60s clock skew."}'
```

**Also, read-only on the live vault:** list title pairs with high word overlap. Report how many are real duplicates:

```bash
claudron index --json >/dev/null
jq -r '.entries[].title' "$VAULT/.claudron/index.json"
```

## Proposed fix

1. Store a small similarity signature per index entry: token set, or 3-shingle MinHash over title + tags + body.
2. When similarity is above a threshold, return `suggest_update` naming the closest note. Continue to route rather than reject.
3. Tune the threshold on a labelled sample from the live vault.
4. Fix the PreCompact prompt wording until this ships.
