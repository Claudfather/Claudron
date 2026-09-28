TITLE: Recall/lookup substring matching lets unrelated notes into briefs and suppresses the full-text fallback
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #143, #144, #{{scope}}, #{{budget}}.

## Finding

`claudron/knowledge.py:353` (`_score_term`) matches each query token with an unanchored substring test, `term in title`. It has no word boundaries and no stopword list, so:

- one title hit scores 80 (`W_TITLE_SUBSTR`), or 50 per token;
- the recall abstention floor is only 50 (`claudron/session.py:43`);
- any junk hit scoring 50 or more skips Tier B entirely (`knowledge.py:525`), so a note that matches only on its body is never found.

This is the root cause behind #143. Normalizing by query length (the fix proposed there) is necessary but not sufficient: substring matching breaks 1–3-token queries too.

## Evidence (reproduced 2026-09-26)

| Case | What happened |
|---|---|
| Repo named `api` | SessionStart brief injects "Rapid prototyping playbook", score 110 (`r-api-d`) |
| Repo named `app` | Brief injects "Happy path bias in reviews", score 110 |
| `lookup how to deploy` | Returns two notes matched only on "to" ("pro**to**typing", "**to**ken"). **Misses** "Rollback procedure", whose body mentions deploy twice |
| Reference vault eval | Recall@5 = 95%, but 11 of the 21 results that clear the floor are the wrong note |
| Off-topic query "setting up a python virtualenv" | 5 unrelated notes pass the floor at score 120 |

Tier A also re-reads every *matching* note from disk before truncating to `limit`, so broad tokens turn it into a full vault read: about 1.9 s at 5k notes on a fresh index.

## Test it on yourself

Scratch vault only.

```bash
V=$(mktemp -d)/v && claudron init "$V" && cd "$V" && git init -q .
cap(){ printf '%s' "$1" | claudron --vault "$V" capture --stdin --json | jq -r '.data.action'; }
cap '{"type":"knowledge","title":"Rapid prototyping playbook","body":"Timebox spikes.","tags":["process"]}'
cap '{"type":"knowledge","title":"Token rotation schedule","body":"Rotate every 30 days.","tags":["security"]}'
cap '{"type":"runbook","title":"Rollback procedure","body":"To deploy a rollback, run the release job with the previous tag; deploy takes 4 minutes.","tags":["ops"]}'
claudron --vault "$V" lookup how to deploy --json | jq '.data.results[] | {title, score}'
mkdir -p /tmp/api && cd /tmp/api && git init -q . && claudron --vault "$V" recall
```

**Expected if confirmed:**

- `lookup` returns the two junk titles and omits "Rollback procedure".
- `recall` from `/tmp/api` lists "Rapid prototyping playbook".

**Also run, read-only, on the live vault:** 5 real queries your fleet used this week. Report how many results are off-topic.

## Proposed fix

1. Match whole words (`\b` boundaries) and drop stopwords and tokens shorter than 3 characters.
2. Weight tokens by rarity (IDF / BM25-lite over title, tags and body; pure Python, no new dependency).
3. Normalize per query term so scores cannot saturate at `SCORE_CAP`.
4. Rank from the index, then parse only the top `limit × 2` docs.
5. Decide Tier B escalation on the best *normalized* Tier A score.
6. Update the INTEGRATION.md "recall abstains" claim once it is true.
