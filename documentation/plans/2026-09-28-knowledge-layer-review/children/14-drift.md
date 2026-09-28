TITLE: Claudron-side contract drift: Claudlobby tree sniff, undocumented env, sync --json ok:true on failure, costly capability probe
LABELS: bug,documentation

Part of #{{EPIC}}. Related: #88, #102, #142, #{{release}}.

## Findings

1. **Claudron still recognizes Claudlobby by its directory shape.**
   - `_detect_claudlobby_root` (`claudron/cli.py:121`) still looks for a `library/` + `lib/` tree. #102 removed only the deprecation warning.
   - This contradicts `claudron/CLAUDE.md`: "no Claudlobby directory walks".
   - `migrate` hardcodes `local/<fleet>` and `runtime/bots`. In the vault-IS-`local/` layout, source and destination are the same, so it copies each file onto itself.
2. **Env vars read but not documented.** `CLAUDRON_ACTOR` and `BOT_NAME` are read (`engine.py:359`) but are not in `CLI_CONTRACT.md` §Environment.
3. **`sync --json` reports success on a failed push.** It returns `"ok": true, "errors": []` with `data.detail: "push failed…"` and **exit 1**. This is the same class as #142.
4. **The capability probe is expensive.** It is `status --json`, which reads every note and can rewrite the index (#88). `version --json` has no `capabilities`. clauDNA runs `status --json` before every engine call and on every compaction.

## Test it on yourself

**Read-only.**

```bash
claudron version --json | jq .data            # no capabilities today
cd "$(mktemp -d)" && claudron init v && cd v && git init -q . && echo x > _shared/knowledge/x.md
claudron sync --json; echo "exit=$?"          # no remote → ok:true + exit 1
```

On the Pi, time `claudron status --json` against the live vault.

## Proposed fix

1. Add `capabilities` to `version --json`. It is zero-I/O and needs no vault. Point INTEGRATION.md step 0 at it.
2. Put sync failures into `errors`, so that `ok` matches the exit code.
3. Add `CLAUDRON_ACTOR` to the environment table. Drop `BOT_NAME`, or declare it.
4. Replace the tree sniff with a declared consumer root (`plug --root PATH`), and move `migrate` into Claudlobby.
