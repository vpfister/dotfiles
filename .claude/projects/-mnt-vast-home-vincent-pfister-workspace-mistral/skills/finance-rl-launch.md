# finance-rl-launch

Launch, monitor, and troubleshoot orchestral RL training runs for financial QA.

## When to activate

When the user wants to launch an RL training run, check on a running job, troubleshoot a crash, resume from a checkpoint, or clean up old runs.

## Launch command

```bash
source .env && export SBATCH_ACCOUNT=ml4_taskforce
IGNORE_DISK_SPACE=1 uv run --frozen python train_online.py sweep \
  --sweep_path sweeps/vincent/<sweep_file>.yaml \
  --exp_name <exp_name> \
  --partition h100 --qos priority-ml4_taskforce --workstream vincent.pfister \
  --env_vars "RAY_CI_LOGGING=1,SEC_EDGAR_API_KEY=${SEC_EDGAR_API_KEY},WANDB_API_KEY=${WANDB_API_KEY},MISTRAL_API_KEY=${MISTRAL_API_KEY},SCIENCE_PRIVATE_ACCESS_ENV_VAR=${SCIENCE_PRIVATE_ACCESS_ENV_VAR}"
```

Must be launched from the worktree that has the `finance_qa` env (currently `~/workspace/mistral_finance_qa`).

## Key pitfalls

- **`orchestral_rl_runner`** (not `orchestral_runner`): required section name. Must have `use_logprobs: true`, `inbox_max_size: 1`.
- **`data_config`** (not `data_config_path`): field was renamed on main (2026-05-26).
- **`reasoning_effort: "high"`**: required in data config after recent main changes. Without it the run crashes silently.
- **`SBATCH_ACCOUNT=ml4_taskforce`**: must be exported as env var, not passed via `--slurm.account` (they conflict).
- **`IGNORE_DISK_SPACE=1`**: required to bypass disk space check.
- **`--env_vars`** (underscore): not `--env-vars` (hyphen). No `--confirm` flag exists.
- **Initial model**: base MS4.1 SFT produces ~21% malformed tool calls at temp=1.0. Always use a tool-use SFT checkpoint.
- **`swestral-rex`**: main occasionally breaks with import errors. Always rebase before launching.

## Resuming from a checkpoint

The trainer auto-resumes from the latest checkpoint in `<run_dir>/checkpoints/` at startup
(`load_latest_checkpoint()` in `mistral/checkpointing/checkpointing_utils.py`).
The key is to **preserve the run dir** when relaunching.

### Safe resume: `relaunch`

```bash
uv run --frozen python train_online.py relaunch --run_dir <run_dir>
```

This preserves checkpoints, reuses the existing code snapshot and args, and submits a new
SLURM job as a dependency of the crashed one. The trainer finds existing checkpoints and
resumes from the latest step.

**If field names changed on main** (e.g. `data_config_path` → `data_config`), relaunch will
fail because it reads the old `args.yaml`. Fix with `--update_args`:

```bash
uv run --frozen python train_online.py relaunch \
  --run_dir <run_dir> \
  --new_code True \
  --update_args '{"orchestral_data_loader.data_config": "orchestral_package/configs/finance_qa_multi.yaml", "orchestral_tokenization.data_config": "orchestral_package/configs/finance_qa_multi.yaml"}'
```

- `--new_code True`: copies fresh code from the worktree (new venv), keeps checkpoints.
- `--update_args`: patches the saved override.yaml with new/renamed fields.

### DANGER: --override_run_dir erases checkpoints

`--override_run_dir True` calls `move_to_trash()` on the **entire experiment directory**
including all checkpoints, generation logs, and code snapshots. It restarts from step 0
with the initial model. There is NO way to recover.

**Before using --override_run_dir**, always:
1. Check for checkpoints: `ls <run_dir>/checkpoints/`
2. Try `relaunch` first (with `--update_args` if needed).
3. Only use `--override_run_dir` if you genuinely want a fresh start.

## Monitoring a running job

```bash
# Job status
squeue -j <JOB_ID> --format="%.10i %.20j %.8T %.10M"

# Episode count
grep -c "Finished instance" <run_dir>/cur_ray_cluster.out

# Train log (empty until first gradient step, ~5-6h after launch)
tail -20 <run_dir>/cur_train.out

# Errors
grep -i "error\|crash\|killed" <run_dir>/cur_ray_cluster.err | grep -iv "wandb\|BrokenPipe\|atexit\|INTENDED"

# Check restart step
cat <run_dir>/restarts/worker_0000.jsonl | tail -1
```

## Common crash causes

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: Please set the field data_config` | `data_config_path` renamed to `data_config` | Update sweep YAML |
| `ExternalLLMClient failed after 5 retries` | Science API model down | Check model availability, switch model, relaunch |
| `recvValue failed` / NCCL errors | Node crash (transient) | Relaunch |
| `PackageNotFoundError: swestral-rex` | Broken import on main | Rebase onto latest main |
| `Reached max_steps=50` (many episodes) | Normal, not an error | — |
| vLLM health check timeouts | Generator startup failure | Check if `reasoning_effort` is set, relaunch |

## Run directories

Pattern: `/mnt/vast/runs/vincent.pfister/<exp_name>/<exp_name>_run000/`

Key subdirs:
- `checkpoints/checkpoint_<step>/` — model weights (sharded, not consolidated)
- `generation_log_dir/<batch>.jsonl` — episode data with rewards
- `evals/eval_<step>/results/` — inline eval results
- `cur_ray_cluster.out` / `cur_train.out` — logs

## Sweep version history

See memory file `finance_qa_rl.md` for the full experiment tracker with all versions, results, and lessons learned.
