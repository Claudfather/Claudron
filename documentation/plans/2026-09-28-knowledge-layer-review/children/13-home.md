TITLE: Walk-up vault detection binds $HOME when ~/shared exists; hooks install doesn't persist the vault address
LABELS: bug,priority:medium

Part of #{{EPIC}}. Related: #{{claudna}}.

## Finding

Two independent problems combine here.

**1. Walk-up detection binds `$HOME`.**

- `detect()` (`claudron/vault.py:250`) binds the first ancestor that contains a dir named exactly `shared` or `_shared`.
- clauDNA `init-project` defaults its raw-tree location to **`~/shared`** (claudna `skills/init-project/SKILL.md:181`).
- With no `CLAUDRON_VAULT_PATH` set, every repo under your home directory therefore resolves **`$HOME` as the vault**. What follows:
  - the `other:` catch-all tier makes every top-level home directory searchable;
  - captures land in `~/shared/…`, and `--project X` captures land in `~/projects/X/`;
  - the index goes into `~/.claudron/`;
  - if `$HOME` is a git repo (a dotfiles setup), the SessionEnd safety net would `git add -A` inside it.

**2. `hooks install` doesn't record which vault to use.**

- The hook command is `<exe> hook <event>`, with no `--vault`.
- `init --personal` lists `export CLAUDRON_VAULT_PATH=…` only as step 4.
- Miss that step, or launch Claude from a GUI that doesn't source your shell profile, and the loop silently does nothing. With `~/shared` present, it binds `$HOME` instead.

## Evidence (reproduced)

From `~/code/myrepo`, with `~/shared/` present:

- `status` resolved `$HOME` as the vault root;
- `lookup taxes` returned `Documents/taxes-2025.md`.

## Test it on yourself

**Read-only, on the Pi, in each user account that runs Claude:**

```bash
ls -d ~/shared ~/_shared 2>/dev/null
cd ~ && env -u CLAUDRON_VAULT_PATH claudron status --json 2>/dev/null | jq -r .data.root
grep -n CLAUDRON_VAULT_PATH ~/.claude/settings*.json ~/.profile ~/.bashrc 2>/dev/null
```

## Proposed fix

1. Walk-up binds only `_shared/`, or `shared/` plus a positive marker (`CONVENTIONS.md` or `.claudron/`).
2. Walk-up never binds `$HOME` or `/`.
3. `hooks install --write` records the vault address. Either:
   - `"env": {"CLAUDRON_VAULT_PATH": …}` in the same settings file; or
   - `--vault` in the command. The identity suffix `hook <event>` is preserved either way.
4. clauDNA: change the raw-tree default away from `~/shared`, e.g. `~/shared-docs`. See #{{claudna}}.
