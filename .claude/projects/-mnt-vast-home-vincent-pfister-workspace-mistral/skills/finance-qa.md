# finance-qa

Finance QA RL training, evaluation, debugging, and standalone episode scripts.

## When to activate

When the user wants to launch/resume/debug RL training runs, run evals on checkpoints, plot results, compare versions, investigate episode failures, run standalone episodes, or work with the finance_qa orchestral env.

## Worktree Layout

| Worktree | Branch | Purpose |
|---|---|---|
| `~/workspace/mistral` | `main` | Pull origin/main here first, then branch new worktrees |
| `~/workspace/mistral_finance_qa` | `vincent.pfister/finance_qa_rl` | **Retired** — PR #18209 merged. Keep for reference only. |

**All finance_qa code is on `main`** as of 2026-06-15: env (PR #17488), hardening + search_backend (#18209), `score_with_rubrics` scoring (#19166). EDGAR cache resilience (#19503) still open.

`mistral_scoring` (branch `finance_qa_rubric_scoring_v2`) was **deleted 2026-06-15** after #19166 merged — its 63 untracked files (configs, sweeps, scripts, notebooks) are archived at `/mnt/vast/shared/vincent.pfister/ml4-taskforce/finance_qa_rl/`.

**For new finance_qa work**: create a fresh worktree off `main` (`git -C ~/workspace/mistral worktree add ~/workspace/mistral_<name> -b vincent.pfister/<branch> origin/main`), then copy needed sweeps/configs/scripts back from the `ml4-taskforce/finance_qa_rl/` archive. Launch training from that new worktree.

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

# Conversion script (Thunderdome/SFT → FinanceQAData) — archived (mistral_scoring deleted):
/mnt/vast/shared/vincent.pfister/ml4-taskforce/finance_qa_rl/scripts/convert_to_finance_qa_data.py
#   --format val_us|karl_eu  --input <src> --output <dst> [--dry-run]

# Initial model checkpoints:
# KARL EU+US replay SFT (Lucas, step 1182) — primary:
/mnt/runs/lucas.mebille/260518_sft_ml4-ms41-vals-us-mix-karl-2ep-replay/.../checkpoint_00001182/consolidated/
# Sheetpedia SFT (Philippe, step 476) — alternative:
/mnt/runs/alexandre.cahill/260518_sft_ml4-ms41-sheetpedia_v3-replay_r00/.../checkpoint_00000476/consolidated/
# Base MS4.1 SFT — DO NOT USE for RL (21% malformed tool calls at temp=1.0):
/mnt/solutions/applied-science/models/ms41-sft/checkpoint_00020876/consolidated

# Run dirs pattern:
/mnt/vast/runs/vincent.pfister/finance_qa_rl_ms41_sft_v<N>/finance_qa_rl_ms41_sft_v<N>_run000/
# Eval dirs pattern:
/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v<N>/
```

## Scoring / Verifier (`verifier.py`)

Scoring uses the shared `score_with_rubrics` (`orchestral.core.llm_verifier`), **merged to main in PR #19166 (2026-06-15)** — this replaced the old bespoke voting-based judge (`_judge_with_voting`, median over k attempts). `_build_rubric_config(rubric, expected_answer)` converts the dataset's verification data into a `RubricConfig` at runtime:

- **Rubric (criterion) path** — one `RubricDefinition` per criterion, `ScoringType.SCORE_YN`, aggregated with `AggregatorType.WEIGHTED_MEAN` using per-criterion weights. Uses the **shared** `SCORE_YN_JUDGE_USER_PROMPT` (from `rl_components...prompts.rubrics_llm_verifier_with_rationale_prompts`) + a **finance-specific** `FINANCE_CRITERION_SYSTEM` (adds financial-expert framing + 1% numeric tolerance, asks for `{"rationale","fulfilled"}` JSON). Contradiction items (`operator == "contradiction"`) are inverted in the prompt text: `"The answer does NOT contradict or conflict with the following: {criterion}"`.
- **Expected-answer path** (no rubric) — single `RubricDefinition`, `ScoringType.SCORE_10` (normalizes /10 → 0–1), with finance-specific `FINANCE_EXPECTED_ANSWER_SYSTEM`/`_USER`. Kept as SCORE_10 **deliberately** (Paul review comment 2): partial credit for near-miss numeric answers; YN would collapse to 0/1. May revisit, but it changes the RL signal so needs testing.
- `RubricDefinition` and its extractors are built via `RubricDefinition.model_validate({...})` (dicts, not typed kwargs) because the `swestral` extractor classes are import-banned in `orchestral` (`orchestral_package/ruff.toml`). `_FINAL_MESSAGE_EXTRACTOR = {"extractor_type": "final_message"}`.
- **Fault semantics**: if ANY rubric score is `None` (judge unparseable), `WeightedMeanAggregator.aggregate` returns `None` → `score_with_rubrics` raises `VerifierFaultError`, which propagates uncaught → the episode faults and is **dropped cleanly** (`trajectories.py` skips `not_agents_fault_errors` before aggregation), not silent batch corruption. Empty response short-circuits to `score=0.0`.
- **At `temperature=0.0`** (`_JUDGE_GENERATE_ARGS`), `has_zero_temp_override()` makes `should_retry=False`, so parse-failure retries never fire — this is why the old `n_retries` field was inert and removed.

⚠️ **Changing a judge prompt changes the RL reward signal** → requires a small-scale validation re-run (template: `v13_mini` config — short, no evals/checkpoints). Note which runs used which prompt wording: v13/v13a/v13c used the *original* per-criterion user prompt; the merged code uses the shared `SCORE_YN_JUDGE_USER_PROMPT`.

### RL runs by scoring method (24B dense)
| Run | Scoring | Dataset | `seq_per_minibatch` |
|-----|---------|---------|--------------------:|
| v12, v12b, v12c, v12d(+_mini) | OLD voting-judge | — | — |
| v13_mini | new `score_with_rubrics` | old (391+308+86) | 16 (smoke) |
| v13 | new `score_with_rubrics` | old (391+308+86) | 1024 |
| v13a | new `score_with_rubrics` | extended (2432+2309+163) | 1024 |
| v13c | new `score_with_rubrics` | extended (2432+2309+163) | 256 |

## Launching Training

```bash
cd ~/workspace/mistral_<finance_qa_worktree>   # mistral_scoring was deleted 2026-06-15; make a fresh worktree off main
set -a && source ~/.env && set +a && export SBATCH_ACCOUNT=ml4_taskforce

IGNORE_DISK_SPACE=1 uv run --frozen python train_online.py sweep \
  --sweep_path sweeps/vincent/<sweep_file>.yaml \
  --override_root_dir /mnt/vast/runs/vincent.pfister/<exp_name> \
  --qos priority-ml4_taskforce
```

### Critical flags

- `SBATCH_ACCOUNT=ml4_taskforce` — must be **exported**, not passed via `--slurm.account` (they conflict)
- `IGNORE_DISK_SPACE=1` — bypasses disk space check
- `--env_vars` (underscore) — `--env-vars` (hyphen) silently fails
- No `--confirm` flag exists
- `--override_root_dir <path>` — sets the run directory. Must `mkdir -p` it first (errors if missing).
- `--override_run_dir True` — **DANGER: wipes entire run dir including checkpoints**. Try `relaunch` first.

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

Warmup constraint: `warmup` must be ≤ `max_steps // 2`, or launch crashes.

### Entropy control

The entropy corridor prevents both entropy collapse (model stops exploring → reward hacking) and entropy explosion (model generates gibberish).

**Recommended for finance_qa**: `target_entropy_min: 0.5, target_entropy_max: 0.6, entropy_constraint_coeff: 0.1` (v13 series).

| Corridor | Result | Run |
|---|---|---|
| 0.25-0.4 | Too tight for 24B, oscillation (natural entropy ~0.45) | v12 |
| 0.75-1.25 | Too wide, entropy exploded to 2.0, gradient spikes to 4.7 | v12b |
| 0.6-0.7 | Stable, 90+ steps, no collapse | v12c |
| **0.5-0.6** | **Current best — used for v13 series** | **v13+** |
| None (0.0 coeff) | Entropy collapse → reward hacking at step 84-133 | v10, v10b |

**Do NOT cap episode length or tool usage** to fight entropy. Curriculum approach instead: first learn to solve correctly, then optimize for efficiency in a second stage.

### `seq_per_minibatch` tuning

`seq_per_minibatch` controls how many episodes are used per gradient step. Larger = more stable gradients but slower steps (generation-bound).

| `seq_per_minibatch` | Step time | LR | Notes | Run |
|---|---|---|---|---|
| 1024 | ~15 min | 6e-7 | Stable but slow (5+ days for 500 steps) | v13, v13a |
| 256 | ~4 min | 2e-7 | 4x faster, conservative LR for noisy rewards | v13c |

LR scaling rule: when reducing `seq_per_minibatch` by N×, scale LR by ~1/N to 1/sqrt(N). Linear (1/N) is conservative, sqrt (1/sqrt(N)) is standard. v13c uses ~linear (6e-7 → 2e-7 for 4x reduction).

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
            library_collection: "hec_finance"  # NEVER use "creator" — causes OOM
  hec_finance:
    sampling_weight: 0.20  # ~3x upsampling (163/2432 * 3 ≈ 0.20)
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

**CRITICAL:** `library_collection: "creator"` (the default) causes OOM → `httpcore.ReadError` crashes. Always use `"hec_finance"`.

## Resuming from a Checkpoint

### Safe resume: `relaunch`

```bash
uv run --frozen python train_online.py relaunch --run_dir <run_dir>
```

Preserves checkpoints AND optimizer state, reuses existing code snapshot, submits new SLURM job. Resumes from the **latest** checkpoint in the run dir.

If field names changed on main (e.g. `data_config_path` → `data_config`), use `--update_args`:

```bash
uv run --frozen python train_online.py relaunch \
  --run_dir <run_dir> \
  --new_code True \
  --update_args '{"orchestral_data_loader.data_config": "orchestral_package/configs/finance_qa_multi.yaml"}'
```

- `--new_code True` — copies fresh code from worktree, keeps checkpoints
- `--update_args` — patches saved override.yaml with new/renamed fields
- `--job_id <ID>` — required if relaunch can't auto-detect the last job (e.g. copied run dir)

### Relaunch pitfalls (learned the hard way)

- **`relaunch` always resumes from the LATEST checkpoint**. To resume from an earlier one, delete or rename later checkpoints first.
- **`relaunch` needs a job directory** (`job<ID>-000/`) in the run dir. If missing (e.g. copied run dir), pass `--job_id` explicitly.
- **Run dir paths in override.yaml**: `relaunch` reads these but may not update them all. If you copied the run dir, the paths still point to the original. The `stool_args.yaml` and `ray_cluster_args.yaml` also contain paths — `relaunch` may reference the old location for vllm_logs, barriers, etc.
- **Checkpoint sync barrier**: `load_latest_checkpoint` runs `assert_saved_dataloader_states_in_sync` which creates barrier files keyed by checkpoint step AND job ID. If the run dir has checkpoints from a different job, the barrier looks for files in the wrong path → `TimeoutError` after 600s.
- **Preferred approach for parameter changes**: use `relaunch --update_args` on the original run dir rather than copying. Copying run dirs causes path mismatches throughout the config.
- **TODO**: investigate the proper way to relaunch with different resource allocations (more nodes/generators). Need to check stool docs, slack discussions, or ask orchestral team.

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

# Check restart step
cat <run_dir>/restarts/worker_0000.jsonl | tail -1
```

Run dir structure:
```
<run_dir>/
  checkpoints/checkpoint_<step>/   # model weights (sharded, not consolidated)
  generation_log_dir/<batch>.jsonl  # episode data with rewards
  evals/eval_<step>/results/       # inline eval results
  cur_ray_cluster.out/.err         # Ray logs
  cur_train.out/.err               # training logs
```

## Crash Diagnosis

| Pattern | Log signature | Cause | Fix |
|---|---|---|---|
| Science-library OOM | `httpcore.ReadError: Connection reset` | `library_collection: "creator"` (too large) | Use `library_collection: "hec_finance"` |
| Event loop saturation | `httpx.RemoteProtocolError: peer closed` + `efficiency: 0%` | Too many concurrent MCP sessions | Known infra issue. Limit httpx connections. |
| Data worker timeout | `TimeoutError: Data worker is hanging!` | Science API + EDGAR rate limiting | Check judge endpoint, switch model |
| required_services mismatch | `pools not built` | Missing service in ClassVar | Add to `required_services` + `_ENVS_WITH_SERVICE_SPEC_MISMATCH` |
| Web search client closed | `client has been closed` | PR #16588 `StatelessSingletonPool` teardown bug | Workaround: `httpx.Limits(max_connections=10)` |
| Ray N-1/N stuck | Ray node never joins | Bad SLURM node | Cancel and relaunch |
| Stale file handle | `OSError: Errno 116` | Transient Vast NFS issue | Relaunch |
| EDGAR cache disk quota | `OSError: [Errno 122] Disk quota exceeded: .../finance-task-force/cache/edgar_search/...` | `/mnt/vast/datasets` is a **separate Vast volume that is 100% full** (capacity, not inodes); the cache is the victim, not the cause. Also read-only on other clusters. | Fixed in `cache.py` (graceful degradation, see below). Pre-fix workaround: free space on the datasets volume. |
| vLLM health timeout | Health check never passes | Missing `reasoning_effort` in data config | Add `reasoning_effort: "high"` |
| NCCL errors | `recvValue failed` | Node crash (transient) | Relaunch |
| swestral-rex import | `PackageNotFoundError: swestral-rex` | Broken import on main | Rebase onto latest main |

## EDGAR / data cache (`cache.py`)

`PersistentCache` (`orchestral_package/src/orchestral/envs/finance_qa/cache.py`) is a one-file-per-entry JSON cache for EDGAR search + price history, default path `/mnt/vast/datasets/finance-task-force/cache` (set via `FinanceQAToolConfig.cache_dir`; standalone `run_episode.py` hardcodes it).

- **The cache volume is fragile**: `/mnt/vast/datasets` (Vast PVC `100.121.37.190`) is a *different* volume from `/mnt/vast/runs` + home (`100.121.37.100`). It runs at ~100% capacity and is **read-only on other clusters**. Don't assume free space there.
- **Graceful degradation (PR 2026-06-12, branch `finance_qa_rubric_scoring_v2`)**: `cache.py` probes writability at init and degrades to **read-only mode** on EDQUOT/ENOSPC/EROFS instead of crashing — `put()` catches `OSError`, logs once, disables further writes, and skips (a miss just re-requests from the server); `get()` reads **without the lock file** when writes are disabled (lock file can't be created on a read-only/full volume; atomic writes make lockless reads safe). So a pre-populated cache still serves reads on read-only clusters.
- Per-entry lock files (`<bucket>/.locks/<hash>.json.fcntl.v2.lock`, from `shared.file_utils.lock_file`) are **never deleted** — they roughly double the inode count. Not the cause of the v13 crash (that was capacity), but worth knowing.

## Evaluation

### Batch eval launcher

```bash
cd ~/workspace/mistral_finance_qa && source .env && export SBATCH_ACCOUNT=ml4_taskforce && export SEC_EDGAR_API_KEY

uv run --frozen python sweeps/vincent/eval_rl_batch.py \
  --run-dir /mnt/vast/runs/vincent.pfister/<exp>/<exp>_run000 \
  --eval-dir /mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_<version> \
  --baseline-ckpt "/mnt/runs/lucas.mebille/.../checkpoint_00001182/consolidated" \
  --code-dir ~/workspace/mistral_finance_qa \
  --chain  # sequential (avoids saturating science API)
```

Key flags:
- `--code-dir` — overrides auto-detected code snapshot
- `--chain` — dependency chain (one eval at a time)
- `--exclude 25 50` — skip specific steps
- `--dry-run` — preview without submitting

Parallel chains (2 concurrent, 16 GPU limit for dev QoS): run batch script twice with complementary `--exclude` lists.

### ⚠️ Container ABI mismatch — batch worker is broken for v13 snapshots

`eval_rl_array_worker.sh` hardcodes container `gpu_1a0c8a4d.sqsh`, whose compiled vLLM (`/lib-vllm/_C.abi3.so`) is **ABI-incompatible** with the v13 code snapshot. Symptoms (vLLM serve dies in <2 min, harmattan health check never passes, eval aborts with no results):
- bare `python` (worktree venv, torch ≥2.12): `AttributeError: type object 'GraphCaptureOutput' has no attribute 'get_runtime_env'` (snapshot `env_override.py` expects torch <2.12)
- `$CODE_DIR/.venv/bin/python` (snapshot venv): `ImportError: /lib-vllm/_C.abi3.so: undefined symbol: ...c10::cuda...` (container `_C` vs snapshot torch)

The 3-way coupling (vLLM source ↔ venv torch ↔ container compiled `_C`) must all match. **Working recipe = reuse the training harness's own serve+evaluate script**, which uses container `gpu_0c78140a.sqsh` + container `python` + `PYTHONPATH=$CODE_DIR` for vLLM serve, and `$CODE_DIR/.venv/bin/python` for the thunderdome eval.

**Reusable one-off eval (proven 2026-06-13, step 50 = 0.615):**
```bash
SRC=<run_dir>/evals/eval_00000025/jobs/serve_and_evaluate_submission_*.sh
sed -e 's/checkpoint_00000025/checkpoint_000000<STEP>/g' \
    -e 's#/evals/eval_00000025#/evals/eval_000000<STEP>_rerun#g' "$SRC" > ~/tmp/eval_step.sh
cd ~/workspace/mistral_scoring && set -a && source .env && set +a && export SBATCH_ACCOUNT=ml4_taskforce
sbatch ~/tmp/eval_step.sh   # result → <run_dir>/evals/eval_000000<STEP>_rerun/results/vals_finance_agent_v2--<hash>.json
```
The consolidate step inside the script is a no-op if already consolidated (`--no-raise-if-consolidated`). The eval client runs on the host (not in a container), so export secrets before sbatch. Find the actual container a snapshot needs by grepping `--container-image` in that snapshot's inline-eval submission script. **TODO**: fix `eval_rl_batch.py`/worker to derive the container from the snapshot instead of hardcoding.

### Worker script

`sweeps/vincent/eval_rl_array_worker.sh` — QoS `priority-ml4_taskforce`. `eval_rl_batch.py` auto-resolves `CODE_DIR` (latest code snapshot in the run's `code/` dir) and passes it via `--export`, so no manual `CODE_DIR` edit is needed. **Note the container-mismatch caveat above — this worker currently fails for v13.**

**Worker config for 24B/v15 models (corrected 2026-06-12):**
- `TOKENIZER=/mnt/vast/tokenizers/v15_none_high_response_format.tekken.json` (was v14 — must match the model's training tokenizer)
- vals task string: `vals_finance_agent_v2[judge_model=kimi-k2.6-eval-judge-only|temperature=1.0|max_gen_toks=100000|reasoning_effort=high]` — k2.6 not k2.5 (k2.5 is legacy); temp/max_gen_toks match the inline-eval config so batch scores are comparable to the inline curve.
- Earlier batch evals (v8–v12c) used k2.5 judge + v14 tokenizer (hash `32407f6f`); k2.6 produces a different hash and is NOT comparable to that track.

**`reasoning_effort` semantics in `vals_finance_agent_v2`** (`vals_finance_agent.py`): the task-string `reasoning_effort` applies to the **policy model under test** (→ `FinanceAgentArgs.reasoning_effort`, line ~513), NOT the judge. The judge (`ValsFinanceRubricScorer`) is constructed without passing `reasoning_effort`, so it always runs at `None` (the correct setting for a YES/NO rubric judge). Use `reasoning_effort=high` to match how v13+ reasoning models were trained.

### Eval tasks

- `vals_finance_agent_v2` — legacy finance QA, closest to the official benchmark. Use for tracking progress. Can be noisy, but NOT broken. This is the preferred inline eval during training.
- `vals_finance_qa_v11` — alternative eval using FinanceQAEnv (PR #16209). Used for batch evals.
- `new_mmlu_5shot_instruct` — general knowledge non-regression
- `aime25_instruct_v2_maj@16` — math reasoning non-regression
- `livecodebench_cot_instruct_only_v6_4k_pass@1` — code non-regression

### Inline eval judge model

**IMPORTANT**: The sweep's `train.eval.tasks_str` must use `judge_model=kimi-k2.6-eval-judge-only` (NOT `kimi-k2.6-rubrics-cube-online-training`). The inline eval scoring runs as a separate SLURM job on CPU nodes. Thunderdome's `JudgeForScoring` resolves the judge URL via `get_server_url()` in `inference/api/external/__init__.py`, which looks up the model in `SCIENCE_MISTRAL_MODEL` (`inference/api/harmattan.py:83`). Only `kimi-k2.6-eval-judge-only` is in that list — `rubrics-cube` is not, so scoring fails with 100% missing scores.

The `rubrics-cube` endpoint is for RL training only (configured with explicit `server_url` in the data config YAML under `models.judge`).

### Symlink hack for scoring with a different judge model

When inline eval generations were produced with judge_model=A but you need to score with judge_model=B (because A is not in the URL mapping), use this procedure:

1. **Compute both hashes**:
```bash
uv run --frozen python -c "
from thunderdome.core.results_structure import hash_kwargs
old = hash_kwargs({'judge_model': 'kimi-k2.6-rubrics-cube-online-training', 'max_gen_toks': '131072', 'reasoning_effort': 'high', 'temperature': '1.0'})
new = hash_kwargs({'judge_model': 'kimi-k2.6-eval-judge-only', 'max_gen_toks': '131072', 'reasoning_effort': 'high', 'temperature': '1.0'})
print(f'old={old} new={new}')
"
# Result: old=f2ba7fc8 new=e2e8ff96
```

2. **Create proper directories** (NOT symlinks — Thunderdome reads `hash_to_name.json` from inside):
```bash
for step in 25 50 75 100 125; do
  eval_dir="<run_dir>/evals/eval_00000$(printf '%03d' $step)/results/vals_finance_agent_v2"
  results_dir="<run_dir>/evals/eval_00000$(printf '%03d' $step)/results"
  
  # Create real directory with correct hash_to_name.json
  mkdir -p "$eval_dir/<NEW_HASH>"
  cat > "$eval_dir/<NEW_HASH>/hash_to_name.json" << 'EOF'
{"vals_finance_agent_v2--<NEW_HASH>": {"judge_model": "kimi-k2.6-eval-judge-only", "max_gen_toks": "131072", "reasoning_effort": "high", "temperature": "1.0"}}
EOF
  
  # Symlink ONLY the responses file
  ln -s ../<OLD_HASH>/responses.jsonl "$eval_dir/<NEW_HASH>/responses.jsonl"
  
  # Symlink the top-level generation.json
  ln -s "vals_finance_agent_v2--<OLD_HASH>.generation.json" \
       "$results_dir/vals_finance_agent_v2--<NEW_HASH>.generation.json"
done
```

3. **Run scoring** with the new judge model and `SLURM_JOB_USER` set:
```bash
export SLURM_JOB_USER=vincent.pfister
uv run --frozen python -u -m thunderdome.main run-scoring \
  --tasks_str "vals_finance_agent_v2[judge_model=kimi-k2.6-eval-judge-only|max_gen_toks=131072|reasoning_effort=high|temperature=1.0]" \
  --output_path "<run_dir>/evals/eval_00000025"
```

**Key pitfalls**:
- Do NOT symlink the entire hash directory — `hash_to_name.json` inside must match the new params, or Thunderdome asserts on hash collision.
- Do NOT forget `export SLURM_JOB_USER=vincent.pfister` — the science API requires the `x-slurm-job-user` header (mandatory since 2026-06-03).

### Check eval progress

```bash
uv run --frozen python sweeps/vincent/eval_progress.py <eval_dir1> [<eval_dir2>]
```

Quick score extraction:
```bash
for dir in <eval_dir>/*/; do
    name=$(basename "$dir")
    result=$(find "$dir" -name "vals_finance_qa_v11--*.json" ! -name "*.generation.json" 2>/dev/null | head -1)
    if [ -n "$result" ]; then
        score=$(python3 -c "import json; print(json.load(open('$result')).get('rubric_score_MeanScore', 'n/a'))")
        echo "$name: $score"
    else
        echo "$name: pending"
    fi
done
```

### Stale lock cleanup (after cancelled jobs)

```bash
for d in <eval_dir>/step_*/results/vals_finance_qa_v11; do
  rm -rf "$d" 2>/dev/null || { chmod -R u+w "$d" && rm -rf "$d"; }
done
```

Remove SLURM dependency to unblock a chained job:
```bash
scontrol update JobId=<JOBID> Dependency=
```

## Plotting

```bash
# Single version (chart + markdown table)
uv run --frozen python sweeps/vincent/plot_eval_single.py <eval_dir>
uv run --frozen python sweeps/vincent/plot_eval_single.py <eval_dir> --baseline <other_dir>

# Compare versions (overlay chart)
uv run --frozen python sweeps/vincent/plot_eval_compare.py v8d=<dir> v9b=<dir> --output <png>

# Multi-run chart (all versions)
python /mnt/vast/shared/vincent.pfister/ml4_rl/plot_evals.py
```

Output: PNG at `<eval_dir>/evals.png` + markdown table to stdout.

## Episode Analysis / Debugging

### Score distribution from generation logs

```python
import json
from collections import Counter

scores = []
with open("<run_dir>/generation_log_dir/<batch>.jsonl") as f:
    for line in f:
        data = json.loads(line)
        for gk, episodes in data["group"].items():
            for ep in episodes:
                for conv in ep.get("conversations", []):
                    for m in reversed(conv.get("messages", [])):
                        if m.get("role") == "assistant":
                            score = m.get("score")
                            if score is not None:
                                scores.append(score)
                            break

fault = sum(1 for s in scores if s <= -1.0)
zero = sum(1 for s in scores if s == 0.0)
pos = sum(1 for s in scores if s > 0)
print(f"Fault: {fault} ({100*fault/len(scores):.1f}%)")
print(f"Zero: {zero} ({100*zero/len(scores):.1f}%)")
print(f"Positive: {pos} ({100*pos/len(scores):.1f}%)")
```

### Common failure patterns

- **Malformed tool calls (score -1.1)**: model outputs tool names as plain text. Caused by non-tool-use SFT init.
- **Submit spam (score -1.1 or 0.0)**: model calls `submit_final_result` with garbage. First submit ends episode.
- **Reward hacking**: model submits without research for partial rubric credit. Diagnosis: check 3-message episode ratio.

**Note:** `conv.meta.verifier` always shows `"function_check_verifier"` — this is hardcoded dummy label. Look at `last_assistant_message.score` for the real reward.

## Standalone Scripts

```bash
# Serve a checkpoint (run from repo root)
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

`serve_checkpoint` uses `vllm_only_server` (not `vllm_harmattan_prod`). Runs `python` directly in container (not `uv run`). Must launch from repo root.

`run_episode` redirects stdout→stderr to protect JSONL pipe from library `print()` calls.

## Science API

```
URL: https://quota-science-api-prod-swe.mistralai.com/v1
Headers: MISTRAL_API_KEY + SCIENCE_PRIVATE_ACCESS_ENV_VAR
Mandatory since 2026-06-03: x-slurm-job-user header (PR #16923)
```

Check availability:
```bash
source .env && curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "x-private-access: $SCIENCE_PRIVATE_ACCESS_ENV_VAR" \
  https://quota-science-api-prod-swe.mistralai.com/v1/models
```

### Key models

| Model | Role | Notes |
|---|---|---|
| `kimi-k2.6-rubrics-cube-online-training` | RL judge (dedicated, autoscaling 5-30) | Use for training |
| `kimi-k2.6-eval-judge-only` | Eval judge | Use for evals |
| `kimi-k2.6-internal` | Fallback judge / retriever | Higher latency (~3s) |
| `mistral-medium-3.5-internal` | Retriever | Fast (~0.7s) |

## API Migration Notes (after rebase on main)

These are recurring issues when rebasing the finance_qa branch:

- `data_config_path` → `data_config` (renamed 2026-05-26)
- `get_doclib_provider()` removed → use `MCPToolProvider(service)` directly
- `ConnectorWebSearchProvider` deleted → use `WebSearchProvider` (service-based)
- `player_id=None` required on all `runtime.generate()` calls
- `reasoning_effort` required in data config and on `runtime.generate()` for non-default models
- `image_preprocess_args: {}` required in sweep
- `Verifier.__call__()` needs `verified_model_name`, `verified_player_id`
- `FinanceQAEnv` must be in `_ENVS_WITH_SERVICE_SPEC_MISMATCH` in `env_unit_test.py`

### Rebase procedure

```bash
cd ~/workspace/mistral && git pull origin main
cd ~/workspace/mistral_finance_qa && git rebase origin/main
# MCP doclib conflicts: --ours = main in rebase context
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

- `#eng-indexed-connectors` — MCP document library team
- `#orchestral-backroom` — orchestral/online-training team
- `#llm-magenta-search` — web search issues
- Grafana (science-library pods): filter service=`science-library-prod`
