# User Instructions

## Dotfiles

- At the start of every session, read `$HOME/DOTFILES.md` to understand how dotfiles are managed on this system.

## Commit messages & documentation

- Never add co-author lines (e.g. `Co-Authored-By: Claude`) to commit messages.
- Never mention Claude authorship or AI assistance in PR titles, PR bodies, code comments, READMEs, or any other documentation.

## Worktree conventions

The mistral monorepo uses git worktrees for parallel branch development:

- **`~/workspace/mistral/`** -- always on `main`. Used for training, evals, and as the fetch/pull target for `origin/main`.
- **`~/workspace/mistral_<name>/`** -- worktrees for feature branches. The `<name>` is a short identifier for the branch (e.g. `finance_qa`, `karl`).

When working in a worktree:
- The worktree's remote is shared with the main repo. To fetch latest main: `cd ~/workspace/mistral && git pull origin main`, then rebase in the worktree.
- SSH keys may not work from the cluster -- if `git fetch` fails with SSH errors, pull from the main worktree first.
- Each worktree has its own `.venv`. Always use `uv run --frozen` to avoid dependency resolution delays.
- Training must be launched from the worktree that has the env code (not from `~/workspace/mistral/` if the env isn't merged to main yet).

## Personal Skills

When working on the following topics, load the corresponding skill **before** starting work:

- **Finance QA RL** (training, evals, plotting, debugging, sweep configs, standalone scripts): load skill `finance-qa`
- **KARL pipeline** (synthesize, solve, judge, filter, export, data hunter, SFT traces): load skill `karl-pipeline`
- **PDF scraping sources** (adding new sources to fetch_pdfs): load skill `add-pdf-source`

## Active Experiment State (updated 2026-06-16)

### KARL pipeline

- Branch: `vincent.pfister/karl` -- PR [#12602](https://github.com/mistralai/mistral/pull/12602)
- **ML4 SFT/RL campaign** (2026-06-13, ongoing): 3 experiments, split filter, cross-experiment dedup

### Finance QA RL

- **Merged to main**: PR [#17488](https://github.com/mistralai/mistral/pull/17488) (env code), PR [#18209](https://github.com/mistralai/mistral/pull/18209) (hardening + search_backend fix), PR [#19166](https://github.com/mistralai/mistral/pull/19166) (score_with_rubrics migration, squash commit `0f4a5b55893`).
- **EDGAR cache fix**: PR [#19503](https://github.com/mistralai/mistral/pull/19503), draft, branch `vincent.pfister/finance_qa_edgar_cache_resilience`, worktree `~/workspace/mistral_edgar_cache`.
- **v12c** (completed step 121): 24B dense, entropy 0.6-0.7.
- **v13** (completed step 72): new `score_with_rubrics` scoring. Crashed from EDGAR cache disk quota. Step 25 = **0.635 MeanScore**, step 50 = **0.615 MeanScore**.
- **v13a** (stopped at step 37): extended dataset, `seq_per_minibatch=1024`, `lr=6e-7`. Step 25 = **0.611 MeanScore**. Stopped because ~15 min/step was too slow.
- **v13c** (completed successfully 2026-06-15): extended dataset + `seq_per_minibatch=256` + `lr=2e-7`. ~4 min/step (4x faster than v13a).
- **Shared configs**: `/mnt/vast/shared/vincent.pfister/finance_qa_rl/v13/`

### Worktree setup (updated 2026-06-12)

- `~/workspace/mistral` -- on `main`
- `~/workspace/mistral_finance_qa` -- branch `vincent.pfister/finance_qa_rl` (PR merged, **retired**)
- `~/workspace/mistral_scoring` -- branch `vincent.pfister/finance_qa_rubric_scoring_v2` (PR #19166 **MERGED 2026-06-15**)

### SFT Ablation (completed 2026-05-18)

- **Best config**: `us-ue-replay-v31` -- vals_finance **+69%** (0.258 -> 0.435), no regressions
- **Production dataset**: `/mnt/vast/datasets/finance-task-force/reasoning/sft/karl_eu_glm_1k/`

### Competitor evals

- **Eval dir**: `/mnt/vast/runs/vincent.pfister/finance_qa_rl_evals_competitors/`
- **Science API models** (running): `deepseek-v4-pro`, `kimi-k2.6-internal`, `glm-5.1-internal`
- **OpenRouter models** (blocked): needs PR #16976 for thinking chunk support

### RNO cluster QoS

- `dev`: priority 9900, 16 GPU limit, 12h wall time
- `scavengers`: no limits, priority 0, heavily preempted
- `priority-ml4_taskforce`: needs `SBATCH_ACCOUNT=ml4_taskforce`, priority 1000, no wall time limit
- `unpreemptible`: priority 10000, best if available

### ML4 task-force work collection

- **Location**: `/mnt/vast/shared/vincent.pfister/ml4-taskforce/` -- durable collection of ML4 artifacts.
- **Convention**: live worktrees -> copy here + replace original with a symlink; retired worktrees -> copy here directly.

### Active plans

- Small-scale validation re-run for the merged criterion-prompt change (#19166)
- EDGAR cache fix PR [#19503](https://github.com/mistralai/mistral/pull/19503)
- Update KARL export pipeline to produce FinanceQAData format directly

### Feedback notes

- `vals_finance_agent_v2` is the preferred eval for tracking finance QA progress, NOT broken.
- Inline eval judge: must use `kimi-k2.6-eval-judge-only` in sweep tasks_str, not rubrics-cube.

### Science API

```
URL: https://quota-science-api-prod-swe.mistralai.com/v1
Mandatory since 2026-06-03: x-slurm-job-user header (PR #16923)
```
