# SFT ablations: design, sizing, launching

## Design

**One variable per arm.** Move the US half or the EU half, never both, or the delta is not
attributable. The 2026-09 set:

| arm | external name | what moves | epochs |
|---|---|---|---|
| A | **old** | shipping US + shipping EU (the recipe being replaced) | 1.0 / 1.0 |
| B | — | US → solver+blast mix | 1.0 / 1.0 |
| C | — | US → blast only | 1.23 / 1.0 |
| D | — | EU → blast only | 1.0 / 1.0 |
| E | — | both halves blast | 1.23 / 1.0 |
| F | **new** | both halves blast, 3 epochs | 3.0 / 3.0 |
| Z | **baseline** | rehearsal only, **no finance data at all** | — |

### Why arm Z is mandatory

The init checkpoint (`260901_shrimpy_mid260623_sft260826_code`) was itself trained on the 260826
mixture, which **already contains** `karl_us_sft_v1` and `karl_eu_sft_v1` at 1.0ep. So step 0 is
"one epoch of shipping KARL", not "no finance data", and arm A is a *second pass over data the
model has seen*. Without a rehearsal-only control, **no arm-vs-baseline delta in the ablation is
interpretable.**

Build it by removing the finance entries from the rehearsal half only:

```python
REHEARSAL_TEXT_DATA = _remove_sources(MINT_TEXT_DATA_TCFIX, (KARL_US_SHIPPING, KARL_EU))
ARM_Z_TARGET_TOKENS = 2_430_000_000          # sized to arm F, the longest run
REHEARSAL_SCALE_Z   = ARM_Z_TARGET_TOKENS / MINT_TEXT_TOKENS_AT_1X
```

Size the control to the **longest** arm so one run controls all of them: at `num_evals=5` its 60%
point lands at 1.46B, between arm E (1.39B) and arm A (1.51B).

### Iso-token, and the axis you report on

Runs do not share a token budget. **Index every comparison by `tokens_seen`, never by % of
training and never by epochs.** Plotting arm A (1.51B) against arms F/Z (2.43B) on a %-axis
stretched A across the full width and inflated the headline from +2.1 to +4.5 points.

Read `tokens_seen` out of `metrics.train.jsonl`:

```python
for line in open(f"{run}/metrics.train.jsonl"):
    d = json.loads(line)
    if "tokens_seen" in d: tok[d["step"]] = d["tokens_seen"]
```

Note `metrics.train.jsonl` has no `loss` key — it is `ce_loss_AVG` / `_MAX` / `_MIN`.

## Sizing epoch weights: `composite_token_count`, not raw tokens

```bash
cd ~/workspace/mistral_mint_sft
.venv/bin/python -m tools.mint.composite_token_count from_confstore \
    sft_260908_karl_us_mix_arm_c \
    -t /mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json
```

`total_tokens = seq_len * tokenized_n_sequences * epoch * limit_data_size` — **packed sequence
slots**, not raw tokens. Under binpacking at `seq_len 262144`, trace *count* dominates per-trace
length, so raw-token estimates are wrong in both directions:

- arm C: raw-token derivation said 1.6 epochs; packed said **1.23** (414.65M vs arm A's 413.40M).
  A **30% overshoot**. Confirmed independently: both arms ran 722 steps.
- arm D: raw v16 put EU v1b at 23.9M, **9.3x below** its packed cost of 223.08M, because ~3.8k-token
  traces fill ~11% of a 262,144-token sequence. Raw said "14 epochs to match"; packed said 1.57.

Two gotchas:
- The tool defaults to `/mnt/vast/tokenizers/v14.tekken_mm.json`. **The cache key includes the
  tokenizer** — always pass the v16 one the sweep trains with, or it misses.
- ConfStore keys are lowercase (`sft_260908_karl_us_mix_arm_a`), and `ConfStoreExperiments[...]`
  returns a `DataArgs`, not a factory — do not call it.

Registry `n_tokens` is not comparable across entries and must not be used for sizing.

`REHEARSAL_SCALE` is likewise measured, not chosen:
`KARL_ONE_EPOCH_TOKENS / MINT_TEXT_TOKENS_AT_1X`. Use **one** value for every arm — the rehearsal
half must be identical or the arms are not comparable. (Arms A/B differed by 1.4%; the mean was
used.) When rendering scaled weights, emit positional notation and never let a weight render as
`"1."` or `"9.4759e-05ep"` — `get_source_names_and_check_format` rejects both.

## Finite cache — build it or training hard-fails at startup

```
AssertionError: Finite-data cache is incomplete: 374/375 sources found for seq_len=262144,
tokenizer=/mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json, ...
```

```bash
uv run --frozen python -m tools.finetuning.finite.build_cache scan_missing --confstore_key <key>
uv run --frozen python -m tools.finetuning.finite.build_cache from_confstore \
    --confstore_key sft_260908_karl_us_mix_arm_c --seq_len 262144 \
    --tokenizer /mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json
```

Run `scan_missing` first — a warm cache builds in ~3 min, a cold one takes >17 min (run detached).
The error text in older docs names `tools.finetuning.load_finite`; that module does not exist.

## Launch

```bash
ssh bar
export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock
. /etc/shell-config/shell-config.sh >/dev/null 2>&1
set -a; . $HOME/.env; set +a                       # WANDB_API_KEY, and it must exist ON BAR
export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export REGION=BAR                                  # unset resolves to CI, whose partitions exclude h200
export SBATCH_ACCOUNT=discovery                    # else the account resolves to root, whose only qos is scavengers
export IGNORE_DISK_SPACE=1                         # the code tests == "1"; the Notion page's "true" is silently ignored
cd /mnt/vast/home/vincent.pfister/workspace/mistral_mint_sft

yes y | uv run --frozen python -m train sweep \
    --sweep_path sweeps/vpfister/karl_us_mix/260912_karl_blast_3ep_arm_f.yaml \
    --qos priority-discovery --partition h200 --preview 1
```

Drop `--preview 1` to launch.

- **`--qos` is a CLI flag on `train sweep`, not a sweep-file key.** Omit it and training lands
  silently on `scavengers` even though the sweep header comment says otherwise. Verify after
  launch: `scontrol show job <id> | grep -oE 'QOS=[^ ]+'`.
- `yes y |` answers stool's `One of you experiment uses no disk space, are you sure? [y/N]`
  (an `EOFError` with stdin on /dev/null).
- Paired arms: use `SUBSWEEP_data:` with named keys so run dirs are `..._run000__data_arm_a_shipping`
  rather than anonymous `run000`/`run001`.
- Run dir already exists → `AssertionError: Folder ... already exists.` **Never use
  `--override_run_dir`; it destroys progress.** Verify there is none (`find ... -name 'checkpoint_*'`,
  `metrics.train.jsonl`), then `mv` the dir to `TRASH_<name>` or `<name>_cancelled`.

## Sweep keys that matter

Full worked example: `sweeps/vpfister/karl_us_mix/260912_karl_blast_3ep_arm_f.yaml` on
`origin/vincent.pfister/mint-sft-tooling`.

```yaml
initial_model_path: [s3://consolidated-checkpoints/ala/mint_sft/260901_shrimpy_mid260623_sft260826_code/260901_shrimpy_mid260623_sft260826_code_run000/checkpoints/checkpoint_00045374/consolidated]
tokenizer: [/mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json]

# Finite data: cadence is num_*, and the *_freq keys MUST be null.
ckpt_freq: [null]; eval_freq: [null]; super_eval_freq: [null]
num_ckpts: [20]; num_evals: [5]; num_super_evals: [1]

keep_last: [1]                       # asserted to 1 for instruct training
keep_only_if_last_or_not_consolidated: [true]
delete_old_optim_states: [true]
retention_policy: [POSTRAINING_ABLATION]   # mandatory, and must match keep_last=1
s3_consolidation: [true]             # the ONLY reason anything but the final checkpoint survives

seq_len: [262_144]; world_size: [128]
model.model_parallel: [4]; model.context_parallel: [4]; model.moe.expert_parallel: [8]
model.attention_type: [FLASH_ATTN_4]
model.cust_bwd: [false]              # QAT/fp8 asserts "QAT doesn't support custom backward yet"
optim.lr: [1.0e-5]
wandb_project: [financeqa-2609]
data: [sft_260908_karl_us_mix_arm_f]
```

- Half the baseline's `world_size`/`model_parallel` is allowed by the MINT guide. DP replicas =
  `world_size / (mp * cp)`; ws256 + mp8 keeps the same 8 replicas and the same 2,097,152 global
  batch as ws128 + mp4.
- `yarn`, `llama_4_scaling`, `rope_theta`, quantization are **frozen from the init checkpoint's
  `params.json`** — do not let them drift.
- `FLASH_ATTN_4` runs fine on BAR h200 (job 2168177 completed). The August note claiming FA4 is
  Blackwell-only is stale.

## The failure ladder when a stale config meets current main

Each surfaces only after the previous is fixed. Budget several `--preview 1` rounds.

| error | fix |
|---|---|
| `resolve_path` ValueError naming deprecated datasets ("Use instead: `<name>_tcfix`") | map through the live table: `from mistral.data.config.finetuning.deprecated_datasets import deprecated_data_entries_dict`, not a hardcoded list |
| the same, but from the image-transform builder | `_build_260806_per_source_image_transforms()` resolves the **unmapped** list internally; write your own over the mapped one |
| `missing rubrics=['language_switch']` on one `_tcfix` rebuild | except that **one name**, never `ALLOW_MISSING_DATA_QUALITY_CHECKS=1` |
| `shared_public.args.Migrated: Got keys that have been migrated` | `eval.tasks_str` → `eval.tasks.tasks_str`; `eval.slurm.*` → `eval.serving.slurm.*`; apply to `eval`, `eval_long`, `eval_orchestral` |
| `AssertionError: retention_policy is mandatory` | `POSTRAINING_ABLATION` (matches `keep_last=1`) |
| `Dataset <name> not found in registry` | `git -C /mnt/vast/shared/registry pull --ff-only` **on the cluster you launch from** |
| `missing checks=[...16...], missing rubrics=['language_switch']` on the new key | run DataHunter; point the recipe at the `_dh_mask_*` key |
| `ValueError: Cannot mix orchestral and non-orchestral tasks in one job group` | move `bfcl`, `tau3_bench_*` into `eval_orchestral.tasks.super_tasks_str` |
| `RuntimeError: task='finance_bench_v5': Task ... is not defined in the registry` | `finance_bench_v6`; `web_search_complex_prompts_v4_web` → `surge_bench_web_search_v3[judge_model=...]` (not a rename, no successor) |
| `S3 backend requires environment variables ['COREWEAVE_ACCESS_KEY', ...]` | a shell problem, not infra. `. /etc/shell-config/shell-config.sh`; the static keys named in the error are **revoked** |
| `DiskSpaceException: Clean your colleagues' shit in /mnt/vast/runs` | `IGNORE_DISK_SPACE=1` (guard floor is 200 TB and blocks every job regardless of size) |

## While it runs

- `slurm.log` is the srun wrapper and stops after task startup — it looks like a hang. Read
  `<run_dir>/job<JOBID>-000/0000.out`.
- `args.yaml` is written at submission, so a run dir looks live with zero steps. Check `sacct`
  elapsed and the step count in `metrics.train.jsonl`.
- **`sacct` state is not the training outcome.** Every arm reported `FAILED 15:0` at 99-100% from
  an NCCL/TCPStore teardown race (`Failed to check the "should dump" flag on TCPStore ... Broken
  pipe`). The weights are fine, but **the final checkpoint gets no generated consolidation or
  eval script** — retarget the previous step's (see [evals.md](evals.md)).
- Two arms died at ~23% when a **rehearsal** record tripped #30159 tool-call validation at
  dataload (`tool_bad_args_schema` on `format_final_json_response`). That record is in the 260806
  mixture. Build on 260826. Do not reintroduce a 260806 base.
