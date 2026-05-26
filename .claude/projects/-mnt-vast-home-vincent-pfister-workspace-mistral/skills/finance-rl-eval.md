# finance-rl-eval

Run evals on RL checkpoints, visualize results, and compare training versions.

## When to activate

When the user wants to evaluate checkpoints, plot eval results, compare versions, or check inline eval progress.

## Eval script

`sweeps/vincent/eval_rl_checkpoints.sh` — spins up vLLM + Harmattan on a single 8-GPU node and runs thunderdome tasks.

**Before use**: update `CODE_DIR` and `#SBATCH --chdir` to point to the latest code snapshot:
```
<run_dir>/code/<timestamp>/
```

## Launch evals

```bash
source .env && export SBATCH_ACCOUNT=ml4_taskforce

# Single checkpoint
CKPT=/path/to/checkpoint/consolidated \
  OUTPUT_DIR=/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_<version>/<name> \
  SEC_EDGAR_API_KEY=$SEC_EDGAR_API_KEY \
  sbatch sweeps/vincent/eval_rl_checkpoints.sh

# Batch: all checkpoints from a run
RUN=/mnt/vast/runs/vincent.pfister/<exp_name>/<exp_name>_run000
EVAL_DIR=/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_<version>

# Baseline
CKPT=/path/to/sft/consolidated OUTPUT_DIR=$EVAL_DIR/baseline \
  SEC_EDGAR_API_KEY=$SEC_EDGAR_API_KEY sbatch sweeps/vincent/eval_rl_checkpoints.sh

# RL checkpoints
for step in 25 50 75 100 125; do
  CKPT=$RUN/checkpoints/checkpoint_$(printf '%08d' $step)/consolidated \
    OUTPUT_DIR=$EVAL_DIR/step_$step SEC_EDGAR_API_KEY=$SEC_EDGAR_API_KEY \
    sbatch sweeps/vincent/eval_rl_checkpoints.sh
done
```

## Eval tasks

Default tasks (configurable via `TASKS` in the script):
- `vals_finance_agent_v2` — finance QA benchmark (target metric: `rubric_score_MeanScore`)
- `new_mmlu_5shot_instruct` — general knowledge non-regression
- `aime25_instruct_v2_maj@16` — math reasoning non-regression
- `livecodebench_cot_instruct_only_v6_4k_pass@1` — code non-regression

## Finding results

### Standalone evals
```
/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v{3,4,5,6}/
├── baseline/results/*.json
├── step_25/results/*.json
└── ...
```

### Inline evals (during training)
```
<run_dir>/evals/eval_<step>/results/vals_finance_agent_v2--*.json
```

Note: inline evals use the `finance_agent` env (thunderdome task), which has a `str.format()` bug causing some eval failures. The `vals_finance_qa_v11` task (PR #16209) fixes this.

### Eval job logs
```
<code_dir>/rl-eval-job<JOBID>.{out,err}
```

## Plotting results

### Single version (chart + markdown table)
```bash
uv run --frozen python sweeps/vincent/plot_eval_single.py <eval_dir>

# With external baseline (when eval_dir has no baseline/ subdir)
uv run --frozen python sweeps/vincent/plot_eval_single.py <eval_dir> \
  --baseline /mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v3/baseline
```

Output: PNG chart at `<eval_dir>/evals.png` + markdown table to stdout.

### Compare versions
```bash
uv run --frozen python sweeps/vincent/plot_eval_compare.py \
  v3=/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v3 \
  v5=/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_v5 \
  --output /tmp/compare.png
```

Output: overlay chart (one line per version) + comparison table with best score and delta vs baseline.

## Quick check: are eval results ready?

```bash
for dir in /mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_<version>/*/; do
    name=$(basename "$dir")
    result=$(find "$dir" -name "vals_finance_agent_v2--*.json" ! -name "*.generation.json" 2>/dev/null | head -1)
    if [ -n "$result" ]; then
        score=$(python3 -c "import json; print(json.load(open('$result')).get('rubric_score_MeanScore', 'n/a'))")
        echo "$name: $score"
    else
        echo "$name: pending"
    fi
done
```
