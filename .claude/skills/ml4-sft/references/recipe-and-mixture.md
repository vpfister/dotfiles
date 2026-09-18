# `recipe_staging.py` and mixture validation

## The contribution rule (verbatim from the file header)

> When adding, removing, or updating datasets in a workstream, copy the ENTIRE data string for
> that workstream into a new `*_STAGING` variable below, then make your modifications on the copy.
> Do NOT import and mutate a frozen variable — always work on a full inline copy so reviewers can
> diff your changes against the frozen baseline.
>
> When a workstream has no pending changes, it uses the frozen variable directly (no `_STAGING`
> copy needed).

So for finance: copy the whole `FINANCE_DATA_260826_CODE_TCFIX` literal into a new
`FINANCE_DATA_STAGING`, edit only your lines, swap it into the `INSTRUCT_TEXT_DATA_STAGING` list,
and **remove the now-unused import** or ruff fails CI.

Main restructures this file periodically. In September it moved onto `recipe_260826_code_tcfix`
and deleted every per-workstream `*_STAGING` copy. On a rebase conflict, take main's side
wholesale and then re-apply the rule to a fresh copy.

## Changelog block (immediately above your variable)

```python
# Added dataset : finance:one_off-karl_us_sft_v1b-260909_glm53blast_allpass_dh_mask_967e59b6_dh_mask_798b846a:2.0ep
# Added dataset : finance:one_off-karl_eu_sft_v1b-260911_glm53blast_allpass_dh_mask_967e59b6_dh_mask_798b846a:2.0ep
# Removed dataset : finance:one_off-karl_us_sft_v1-260815_strict_valid_dh_mask_c8c45d75:1.0ep
# Removed dataset : finance:one_off-karl_eu_sft_v1-260815_strict_valid_dh_mask_c8c45d75:1.0ep
# workstream: finance
# Author: Vincent Pfister
# ablations: BAR:/mnt/vast/runs/vincent.pfister/260912_karl_blast_3ep_arm_f (new, 3ep)
#            BAR:/mnt/vast/runs/vincent.pfister/260912_rehearsal_only_arm_z (no-finance control)
# rational: <two or three lines: what changed, and the headline measured delta>
# PR #34338
FINANCE_DATA_STAGING = """finance:one_off-...:1.0ep,
    finance:one_off-...:1.5ep,
    ..."""
```

House convention for `ablations:` is a **pointer** (run dir, PR, Notion URL, Slack permalink), not
a results table. Ref format is `finance:one_off-<name>-<key>:<N>ep`.

## Verify before committing

```bash
cd ~/workspace/mistral_mint_sft
uvx ruff format mistral/conf_store/model_integration/sft/recipe_staging.py
uvx ruff check  mistral/conf_store/model_integration/sft/recipe_staging.py

# the mixture must resolve — this fails fast on an unknown or misspelled key
uv run --frozen python -c "
from mistral.conf_store.base import ConfStore
d = ConfStore['sft_staging_data']
print('resolves:', type(d).__name__)
"
```

Filter the noise: `| grep -viE 'hardlink|intentional|different filesys|INFO:'`.

Diff two mixtures before trusting an ablation's arms:

```bash
uv run --frozen python -m tools.mint.compare_mix compare_two_confstores \
    sft_260908_karl_us_mix_arm_a sft_260908_karl_us_mix_arm_b     # ~1m45s
```

Commit hooks: `ruff format` rewrites files on commit, so the commit **fails silently** and you
must `git add -A` and redo it. `flake8 J001` requires `json.dumps(..., ensure_ascii=False)`.
Never truncate hook output — capture it:
`git commit -m "..." > /tmp/commit_out.txt 2>&1; echo "exit=$?"`.

## Mixture validation

`--mixture` takes a **ConfStore mixture name** (`sft_staging_data`), not a dataset key. Run it on
the edited recipe, not before.

```bash
cat > /tmp/mixval.sh <<'EOF'
#!/bin/bash
#SBATCH --job-name=mixval
#SBATCH --partition=cpu
#SBATCH --qos=dev
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=32
#SBATCH --mem=900G
#SBATCH --output=/mnt/vast/home/vincent.pfister/workspace/mistral_mint_sft/scratch/vincent.pfister/mint_sft/mixval.out
#SBATCH --error=/mnt/vast/home/vincent.pfister/workspace/mistral_mint_sft/scratch/vincent.pfister/mint_sft/mixval.err
. /etc/shell-config/shell-config.sh >/dev/null 2>&1
export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ulimit -n 1048576
cd /mnt/vast/home/vincent.pfister/workspace/mistral_mint_sft
# 32 workers, not 64: the 64-worker run peaked at MaxRSS 268G against a 256G request.
# Peak memory scales with max_parallel over a 12.2M-sample mixture.
.venv/bin/python -m tools.mint.mixture_validation.cli \
  --mixture sft_staging_data --max_parallel 32 \
  --output scratch/vincent.pfister/mint_sft/report.html
EOF
sbatch --account=discovery --parsable /tmp/mixval.sh
```

Sizing and scheduling, all learned the hard way:

| | value | why |
|---|---|---|
| `--max_parallel` | **32** | 64 OOM'd: `MaxRSS 268428748K` vs `ReqMem 256G`, FAILED `120:0` after 13m19 |
| `--mem` | **900G** | nodes carry ~1.4 TB (`sinfo -p cpu -h -o "%m"` → `1478656+`), so 900G is schedulable |
| `--qos` | **`dev`** | with **no** `--qos` the job lands on a preemptible default: elapsed went *backwards*, `scontrol show job` → `Requeue=1 Restarts=1`, all progress lost |
| `--time` | **12:00:00** | `dev`'s MaxWall. Successful run took `02:02:19` on 12.2M samples |
| partition | `cpu` if healthy | BAR's `cpu` was drained for days (`squeue` estimated start **12 November**). Check `sinfo -p cpu -N -o "%n %t %C %m"` and read the **Idle** column of `A/I/O/T`, not the aggregate. If dead, `--partition=h200 --qos=priority-discovery` works |

Progress polling (tqdm writes `\r`):

```bash
tr '\r' '\n' < mixval.out | grep -oE 'Validating: +[0-9]+%' | tail -1
```

**Exit code 1 is expected when the mixture has any errors.** Read the attribution, not the exit
code: a run that flags 6 forbidden-tool samples in someone else's `parlai` dataset has passed for
your purposes. Grep the log for your own keys to confirm zero errors attributed to them.

Sample counts are a useful cross-check: 12,207,634 before the obvious-issues judge and 12,207,630
after, i.e. exactly the 4 samples the judge discarded.

### Known tool bug, still on main

```
AttributeError: 'MistralSystemMessage' object has no attribute 'keys'
  tools/mint/mixture_validation/rules/deprecated_fields.py:57   found = _ALL_DEPRECATED & msg.keys()
```

`extract_conversations()` can return already-parsed pydantic messages. Added by
`e77dc2cb505 feat(validation): warn on deprecated fields in mixture data (#31529)`. It takes down
the whole run. One-line guard (`if not isinstance(msg, dict): continue`) — keep it as a separate
commit / separate PR, not in the submission. It did not fire on the final successful run.

### If the full mix hangs

Historically it stalls near 98%. Fallback the guide permits: validate finance-only with a helper
that builds `DataArgs` from just the target refs — template
`/mnt/vast/shared/philippe.pinel/validate_finance_only.py`.

### Attaching `report.html` to the PR

`gh` cannot attach files. Drag the HTML into the GitHub editor; it becomes
`https://github.com/user-attachments/files/...`. Do not commit it and do not paste a cluster path.
(The 2026-09 submission committed it into `scratch/` as well, at 43 KB — either is acceptable, a
cluster path is not.)
