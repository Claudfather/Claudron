TITLE: Brief token budget undercounts real tokens ~2.7x (whitespace-word proxy; path-heavy lines)
LABELS: bug

Part of #{{EPIC}}. Related: #{{retrieval}}.

## Finding

`schema.count_tokens` is `len(text.split())` (`claudron/schema.py:278`). It is the proxy for:

- `BRIEF_TOKEN_BUDGET = 900` (`session.py:26`);
- the CONVENTIONS budget.

Each brief line ends in a backticked vault path. That path counts as 1 "token" but costs ~15–25 real tokens.

## Evidence (reproduced)

- A 10-note project brief measured **305 proxy tokens against 3,260 chars**, which is ~815 tokens at chars/4. That is a **2.67× undercount**.
- Worst case: a brief saturated to the 900-word cap is ~11K chars, about **2.8K real tokens**.
- Summaries are cut at 140 chars mid-word, with no ellipsis (`session.py:64`).
- The per-tier limit leaks:
  - The shared relevance pass is not tier-filtered, so it re-selects the same project's notes.
  - One project filled all 10 slots.

## Test it on yourself

Scratch vault.

```bash
V=$(mktemp -d)/v && claudron init "$V" && (cd "$V" && git init -q .)
for i in $(seq 1 12); do printf '{"type":"knowledge","title":"Payments reconciliation edge case %s","body":"Nightly job in payments-service/src/reconcile/ledger_diff.py double-counts refunds within 30s of settlement."}' $i \
  | claudron --vault "$V" capture --stdin --project payments-service >/dev/null; done
mkdir -p /tmp/payments-service && cd /tmp/payments-service && git init -q .
claudron --vault "$V" recall > /tmp/brief.txt
python3 -c "t=open('/tmp/brief.txt').read(); print('words',len(t.split()),'chars',len(t),'~tok',len(t)//4)"
```

**Also, read-only on the live vault:** run the same measurement on a real bot's SessionStart brief (`claudron recall` from the bot dir).

## Proposed fix

1. Use a chars/4 proxy, or chars/3.5, in `count_tokens`.
2. Shorten brief lines. Drop the path; agents can `lookup` by title.
3. Use the note's `description:` frontmatter as the summary when present. The index already carries it for INDEX.md.
4. Trim summaries at a word boundary.
5. Exclude already-selected project-tier notes from the shared pass, or apply the limit per tier as documented.
