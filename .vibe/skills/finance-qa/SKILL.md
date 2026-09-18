---
name: finance-qa
description: Finance QA RL training, evaluation, debugging, and standalone episode scripts. Use when the user wants to launch/resume/debug RL training runs, run evals on checkpoints, plot results, compare versions, investigate episode failures, run standalone episodes, or work with the finance_qa orchestral env.
---

# finance-qa

Finance QA RL training, evaluation, debugging, and standalone episode scripts.

## Worktree Layout

| Worktree | Branch | Purpose |
|---|---|---|
| `~/workspace/mistral` | `main` | Pull origin/main here first, then rebase worktrees |
| `~/workspace/mistral_scoring` | `vincent.pfister/finance_qa_rubric_scoring_v2` | **Active** -- PR #19166, new rubric scoring + experiments |
| `~/workspace/mistral_finance_qa` | `vincent.pfister/finance_qa_rl` | **Retired** -- PR #18209 merged. Keep for reference only. |

Launch training from `~/workspace/mistral_scoring`. Env code is on main, scoring refactor is on the branch.

## Key Paths

```
# Env code:
orchestral_package/src/orchestral/envs/finance_qa/

# Data configs:
orchestral_package/configs/finance_qa_*.yaml

# Sweep YAMLs:
sweeps/vincent/finance_qa_rl_24b_v13*.yaml   # current (24B dense, v13 series)
sweeps/vincent/finance_qa_rl_ms41_sft_v*.yaml  # legacy (MS4.1)

# Training data (FinanceQAData format):
/mnt/vast/datasets/finance-task-force/reasoning/rl/
  val_us_rl_qa.jsonl          # 2432 KARL US questions (converted from Thunderdome format)
  karl_eu_rl_260613_fqa.jsonl # 2309 KARL EU questions (converted from SFT conversation format)
  karl_us_391.jsonl           # 391 KARL US questions (old, small set)
  karl_us_195.jsonl           # 195 KARL US questions (subset)
  hec_finance_mh_86.jsonl     # 86 HEC questions
  karl_eu_308.jsonl           # 308 KARL EU questions (old, small set)
/mnt/vast/datasets_raw/hec_finance/processed/
  hec_finance_rl_mh_2026-06-08.jsonl  # 163 HEC questions (native FinanceQAData format)

# Conversion script (Thunderdome/SFT -> FinanceQAData):
~/workspace/mistral_scoring/scripts/convert_to_finance_qa_data.py
#   --format val_us|karl_eu  --input <src> --output <dst> [--dry-run]

# Initial model checkpoints:
# KARL EU+US replay SFT (Lucas, step 1182) -- primary:
/mnt/runs/lucas.mebille/260518_sft_ml4-ms41-vals-us-mix-karl-2ep-replay/.../checkpoint_00001182/consolidated/
# Sheetpedia SFT (Philippe, step 476) -- alternative:
/mnt/runs/alexandre.cahill/260518_sft_ml4-ms41-sheetpedia_v3-replay_r00/.../checkpoint_00000476/consolidated/
# Base MS4.1 SFT -- DO NOT USE for RL (21% malformed tool calls at temp=1.0):
/mnt/solutions/applied-science/models/ms41-sft/checkpoint_00020876/consolidated

# Run dirs pattern:
/mnt/vast/runs/vincent.pfister/finance_qa_rl_ms41_sft_v<N>/finance_qa_rl_ms41_sft_v<N>_run000/
# Eval dirs pattern:
/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v<N>/
```

## Scoring / Verifier (`verifier.py`)

Scoring uses the shared `score_with_rubrics` (`orchestral.core.llm_verifier`), **merged to main in PR #19166 (2026-06-15)**. `_build_rubric_config(rubric, expected_answer)` converts the dataset's verification data into a `RubricConfig` at runtime:

- **Rubric (criterion) path** -- one `RubricDefinition` per criterion, `ScoringType.SCORE_YN`, aggregated with `AggregatorType.WEIGHTED_MEAN` using per-criterion weights. Uses the **shared** `SCORE_YN_JUDGE_USER_PROMPT` + a **finance-specific** `FINANCE_CRITERION_SYSTEM` (adds financial-expert framing + 1% numeric tolerance, asks for `{"rationale","fulfilled"}` JSON). Contradiction items (`operator == "contradiction"`) are inverted in the prompt text.
- **Expected-answer path** (no rubric) -- single `RubricDefinition`, `ScoringType.SCORE_10` (normalizes /10 -> 0-1), with finance-specific `FINANCE_EXPECTED_ANSWER_SYSTEM`/`_USER`. Kept as SCORE_10 **deliberately** (partial credit for near-miss numeric answers).
- `RubricDefinition` built via `RubricDefinition.model_validate({...})` (dicts, not typed kwargs) because the `swestral` extractor classes are import-banned in `orchestral` (`orchestral_package/ruff.toml`).
- **Fault semantics**: if ANY rubric score is `None` (judge unparseable), `WeightedMeanAggregator.aggregate` returns `None` -> `score_with_rubrics` raises `VerifierFaultError` -> episode faults and is **dropped cleanly** (`trajectories.py` skips `not_agents_fault_errors` before aggregation).
- **At `temperature=0.0`** (`_JUDGE_GENERATE_ARGS`), `has_zero_temp_override()` makes `should_retry=False`, so parse-failure retries never fire.

Changing a judge prompt changes the RL reward signal -- requires a small-scale validation re-run (template: `v13_mini` config).

### RL runs by scoring method (24B dense)
| Run | Scoring | Dataset | `seq_per_minibatch` |
|-----|---------|---------|--------------------:|
| v12, v12b, v12c, v12d(+_mini) | OLD voting-judge | -- | -- |
| v13_mini | new `score_with_rubrics` | old (391+308+86) | 16 (smoke) |
| v13 | new `score_with_rubrics` | old (391+308+86) | 1024 |
| v13a | new `score_with_rubrics` | extended (2432+2309+163) | 1024 |
| v13c | new `score_with_rubrics` | extended (2432+2309+163) | 256 |

## Launching Training

```bash
cd ~/workspace/mistral_scoring
set -a && source .env && set +a && export SBATCH_ACCOUNT=ml4_taskforce

IGNORE_DISK_SPACE=1 uv run --frozen python train_online.py sweep \
  --sweep_path sweeps/vincent/<sweep_file>.yaml \
  --override_root_dir /mnt/vast/runs/vincent.pfister/<exp_name> \
  --qos priority-ml4_taskforce
```

### Critical flags

- `SBATCH_ACCOUNT=ml4_taskforce` -- must be **exported**, not passed via `--slurm.account` (they conflict)
- `IGNORE_DISK_SPACE=1` -- bypasses disk space check
- `--env_vars` (underscore) -- `--env-vars` (hyphen) silently fails
- No `--confirm` flag exists
- `--override_root_dir <path>` -- sets the run directory. Must `mkdir -p` it first.
- `--override_run_dir True` -- **DANGER: wipes entire run dir including checkpoints**. Try `relaunch` first.

### Sweep file requirements

Runner section must be named **`orchestral_rl_runner`** (not `orchestral_runner`):
```yaml
orchestral_rl_runner:
  use_logprobs: true
  inbox_max_size: 1
```

Data config must include:
```yaml
reasoning_effort: "high"     # or "none" for no-thinking. MUST be present.
image_preprocess_args: {}    # required after recent main changes
```

Warmup constraint: `warmup` must be <= `max_steps // 2`, or launch crashes.

### Entropy control

**Recommended for finance_qa**: `target_entropy_min: 0.5, target_entropy_max: 0.6, entropy_constraint_coeff: 0.1` (v13 series).

| Corridor | Result | Run |
|---|---|---|
| 0.25-0.4 | Too tight for 24B, oscillation | v12 |
| 0.75-1.25 | Too wide, entropy exploded to 2.0 | v12b |
| 0.6-0.7 | Stable, 90+ steps, no collapse | v12c |
| **0.5-0.6** | **Current best** | **v13+** |
| None (0.0 coeff) | Entropy collapse -> reward hacking | v10, v10b |

**Do NOT cap episode length or tool usage** to fight entropy. Curriculum approach instead.

### `seq_per_minibatch` tuning

| `seq_per_minibatch` | Step time | LR | Notes | Run |
|---|---|---|---|---|
| 1024 | ~15 min | 6e-7 | Stable but slow | v13, v13a |
| 256 | ~4 min | 2e-7 | 4x faster, conservative LR | v13c |

LR scaling rule: when reducing `seq_per_minibatch` by Nx, scale LR by ~1/N to 1/sqrt(N).

### Multi-submixture data config

```yaml
# Example: orchestral_package/configs/finance_qa_v13a.yaml (extended dataset)
submixtures:
  karl_us:
    sampling_weight: 1.0
    group_size: 16
    datasets:
      - name: "val_us_rl_qa"
        path: "/mnt/vast/datasets/finance-task-force/reasoning/rl/val_us_rl_qa.jsonl"
        env_type: "finance_qa"
        env_args:
          tool_config:
            edgar_search: true
            web_search: true
  karl_eu:
    sampling_weight: 0.95  # equalizes epochs with karl_us
    group_size: 16
    datasets:
      - name: "karl_eu_rl_260613"
        path: "/mnt/vast/datasets/finance-task-force/reasoning/rl/karl_eu_rl_260613_fqa.jsonl"
        env_type: "finance_qa"
        env_args:
          tool_config:
            web_search: true
            library_search: true
            library_collection: "hec_finance"  # NEVER use "creator" -- causes OOM
  hec_finance:
    sampling_weight: 0.20  # ~3x upsampling
    group_size: 16
    datasets:
      - name: "hec_finance_rl_260608"
        path: "/mnt/vast/datasets_raw/hec_finance/processed/hec_finance_rl_mh_2026-06-08.jsonl"
        env_type: "finance_qa"
        env_args:
          tool_config:
            edgar_search: true
            library_search: true
            library_collection: "hec_finance"
            calculator: true
```

**CRITICAL:** `library_collection: "creator"` (the default) causes OOM. Always use `"hec_finance"`.

## Resuming from a Checkpoint

### Safe resume: `relaunch`

```bash
uv run --frozen python train_online.py relaunch --run_dir <run_dir>
```

Preserves checkpoints AND optimizer state, reuses existing code snapshot.

With field renames:
```bash
uv run --frozen python train_online.py relaunch \
  --run_dir <run_dir> \
  --new_code True \
  --update_args '{"orchestral_data_loader.data_config": "orchestral_package/configs/finance_qa_multi.yaml"}'
```

### Relaunch pitfalls

- **`relaunch` always resumes from the LATEST checkpoint**. To resume from an earlier one, delete or rename later checkpoints first.
- **`relaunch` needs a job directory** (`job<ID>-000/`) in the run dir. If missing, pass `--job_id` explicitly.
- **Checkpoint sync barrier**: `load_latest_checkpoint` runs `assert_saved_dataloader_states_in_sync` which creates barrier files keyed by checkpoint step AND job ID. If the run dir has checkpoints from a different job, the barrier times out.
- **Preferred approach for parameter changes**: use `relaunch --update_args` on the original run dir rather than copying.

## Monitoring a Running Job

```bash
# Job status
squeue -j <JOB_ID> --format="%.10i %.20j %.8T %.10M"

# Episode count
grep -c "Finished instance" <run_dir>/cur_ray_cluster.out

# Train log (empty until first gradient step, ~5-6h after launch)
tail -20 <run_dir>/cur_train.out

# Errors (filter noise)
grep -i "error\|crash\|killed" <run_dir>/cur_ray_cluster.err | grep -iv "wandb\|BrokenPipe\|atexit\|INTENDED"
```

## Crash Diagnosis

| Pattern | Log signature | Cause | Fix |
|---|---|---|---|
| Science-library OOM | `httpcore.ReadError: Connection reset` | `library_collection: "creator"` | Use `"hec_finance"` |
| Event loop saturation | `httpx.RemoteProtocolError: peer closed` | Too many concurrent MCP sessions | Known infra issue |
| Data worker timeout | `TimeoutError: Data worker is hanging!` | Science API + EDGAR rate limiting | Check judge endpoint |
| Web search client closed | `client has been closed` | `StatelessSingletonPool` teardown bug | `httpx.Limits(max_connections=10)` |
| EDGAR cache disk quota | `OSError: [Errno 122] Disk quota exceeded` | `/mnt/vast/datasets` is full | Fixed in `cache.py` (graceful degradation) |
| vLLM health timeout | Health check never passes | Missing `reasoning_effort` in data config | Add `reasoning_effort: "high"` |
| NCCL errors | `recvValue failed` | Node crash | Relaunch |

## EDGAR / data cache (`cache.py`)

`PersistentCache` is a one-file-per-entry JSON cache for EDGAR search + price history, default path `/mnt/vast/datasets/finance-task-force/cache`.

- **The cache volume is fragile**: `/mnt/vast/datasets` is a separate Vast PVC at ~100% capacity and read-only on other clusters.
- **Graceful degradation**: `cache.py` probes writability at init and degrades to read-only mode on EDQUOT/ENOSPC/EROFS. `get()` reads without the lock file when writes are disabled.

## Evaluation

### Batch eval launcher

```bash
cd ~/workspace/mistral_finance_qa && source .env && export SBATCH_ACCOUNT=ml4_taskforce && export SEC_EDGAR_API_KEY

uv run --frozen python sweeps/vincent/eval_rl_batch.py \
  --run-dir /mnt/vast/runs/vincent.pfister/<exp>/<exp>_run000 \
  --eval-dir /mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_<version> \
  --baseline-ckpt "/mnt/runs/lucas.mebille/.../checkpoint_00001182/consolidated" \
  --code-dir ~/workspace/mistral_finance_qa \
  --chain
```

### Container ABI mismatch -- batch worker is broken for v13 snapshots

`eval_rl_array_worker.sh` hardcodes container `gpu_1a0c8a4d.sqsh`, whose compiled vLLM is ABI-incompatible with v13 code snapshots.

**Working recipe = reuse the training harness's own serve+evaluate script**:
```bash
SRC=<run_dir>/evals/eval_00000025/jobs/serve_and_evaluate_submission_*.sh
sed -e 's/checkpoint_00000025/checkpoint_000000<STEP>/g' \
    -e 's#/evals/eval_00000025#/evals/eval_000000<STEP>_rerun#g' "$SRC" > ~/tmp/eval_step.sh
cd ~/workspace/mistral_scoring && set -a && source .env && set +a && export SBATCH_ACCOUNT=ml4_taskforce
sbatch ~/tmp/eval_step.sh
```

### Inline eval judge model

**IMPORTANT**: The sweep's `train.eval.tasks_str` must use `judge_model=kimi-k2.6-eval-judge-only` (NOT `kimi-k2.6-rubrics-cube-online-training`). Only `kimi-k2.6-eval-judge-only` is in the URL mapping.

**`reasoning_effort` semantics in `vals_finance_agent_v2`**: the task-string `reasoning_effort` applies to the **policy model under test**, NOT the judge. The judge always runs at `None`.

### Eval tasks

- `vals_finance_agent_v2` -- preferred inline eval during training
- `vals_finance_qa_v11` -- alternative eval using FinanceQAEnv
- `new_mmlu_5shot_instruct` -- general knowledge non-regression
- `aime25_instruct_v2_maj@16` -- math reasoning non-regression
- `livecodebench_cot_instruct_only_v6_4k_pass@1` -- code non-regression

### Check eval progress

```bash
uv run --frozen python sweeps/vincent/eval_progress.py <eval_dir1> [<eval_dir2>]
```

## Plotting

```bash
uv run --frozen python sweeps/vincent/plot_eval_single.py <eval_dir>
uv run --frozen python sweeps/vincent/plot_eval_compare.py v8d=<dir> v9b=<dir> --output <png>
```

## Standalone Scripts

```bash
# Serve a checkpoint
cd ~/workspace/mistral_finance_qa
uv run --frozen python -m orchestral.envs.finance_qa.serve_checkpoint karl-sft --wait

# Run episodes and pipe to eye
head -3 /mnt/vast/datasets/finance-task-force/reasoning/rl/karl_us_391.jsonl | \
  uv run --frozen python -m orchestral.envs.finance_qa.run_episode \
    --server-url http://slurm-<node>:<port>/v1 | eye

# Against science API (no checkpoint needed)
uv run --frozen python -m orchestral.envs.finance_qa.run_episode \
    --in questions.jsonl \
    --server-url https://quota-science-api-prod-swe.mistralai.com/v1 \
    --model mistral-medium-3.5-internal | eye
```

## Science API

```
URL: https://quota-science-api-prod-swe.mistralai.com/v1
Headers: MISTRAL_API_KEY + SCIENCE_PRIVATE_ACCESS_ENV_VAR
Mandatory since 2026-06-03: x-slurm-job-user header (PR #16923)
```

### Key models

| Model | Role | Notes |
|---|---|---|
| `kimi-k2.6-rubrics-cube-online-training` | RL judge (dedicated, autoscaling 5-30) | Use for training |
| `kimi-k2.6-eval-judge-only` | Eval judge | Use for evals |
| `kimi-k2.6-internal` | Fallback judge / retriever | Higher latency (~3s) |
| `mistral-medium-3.5-internal` | Retriever | Fast (~0.7s) |

## API Migration Notes (after rebase on main)

- `data_config_path` -> `data_config` (renamed 2026-05-26)
- `get_doclib_provider()` removed -> use `MCPToolProvider(service)` directly
- `ConnectorWebSearchProvider` deleted -> use `WebSearchProvider` (service-based)
- `player_id=None` required on all `runtime.generate()` calls
- `reasoning_effort` required in data config and on `runtime.generate()` for non-default models
- `image_preprocess_args: {}` required in sweep
- `Verifier.__call__()` needs `verified_model_name`, `verified_player_id`
- `FinanceQAEnv` must be in `_ENVS_WITH_SERVICE_SPEC_MISMATCH` in `env_unit_test.py`

### Rebase procedure

```bash
cd ~/workspace/mistral && git pull origin main
cd ~/workspace/mistral_finance_qa && git rebase origin/main
git checkout --ours orchestral/envs/document_library/env.py
git add <files> && git rebase --continue
git push --force origin vincent.pfister/finance_qa
```

### Tests after rebase

```bash
uv run --frozen pytest orchestral_package/src/orchestral/envs/finance_qa/ -x -q
uv run --frozen pytest orchestral_package/src/orchestral/env_unit_test.py -k FinanceQAEnv -x -q
uvx prek run --all-files
```

## Key Contacts / Channels

- `#eng-indexed-connectors` -- MCP document library team
- `#orchestral-backroom` -- orchestral/online-training team
- `#llm-magenta-search` -- web search issues
