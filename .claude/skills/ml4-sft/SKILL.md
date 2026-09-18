---
name: ml4-sft
description: Run the ML4 FinanceQA SFT workflow end to end — register SFT datasets and run DataHunter / the obvious-issues mask judge, validate a MINT mixture, launch and size SFT ablation sweeps, launch repair score and monitor thunderdome evals, and prepare a MINT SFT recipe-freeze submission PR. Use for any of: dataset registration, `recipe_staging.py`, mixture validation, `slurm_serve_and_eval`, `run-scoring`, non-regression evals, FAB/FABv11, or #mint-submissions-sft.
---

# ML4 FinanceQA SFT

Runbook for one MINT SFT cycle. Written from the 2026-09-15 finance freeze (PR #34338); every
number and error string here was observed, not inferred.

**Rule zero: never read a working tree to support a code claim.** Every worktree on this
machine is hundreds to thousands of commits behind. `git fetch origin main -q && git grep -n
'<pattern>' origin/main -- <path>`, and cite the SHA.

## The pipeline

| # | Stage | Where it runs | Reference |
|---|---|---|---|
| 1 | Build + clean the JSONL, pass both validation gates | login pod | [registration.md](references/registration.md) |
| 2 | Register via Flyte (`dataset_registration_task`) | Flyte remote | [registration.md](references/registration.md) |
| 3 | DataHunter checks + `language_switch` → `_dh_mask_<hash>` | Flyte remote | [registration.md](references/registration.md) |
| 4 | Obvious-issues mask judge → second `_dh_mask_<hash>` | Flyte remote | [registration.md](references/registration.md) |
| 5 | Read the final key **out of the registry** | login pod | [registration.md](references/registration.md) |
| 6 | Edit `recipe_staging.py`, resolve the ConfStore key | login pod | [recipe-and-mixture.md](references/recipe-and-mixture.md) |
| 7 | Mixture validation → `report.html` | Slurm, `cpu`, `qos=dev` | [recipe-and-mixture.md](references/recipe-and-mixture.md) |
| 8 | SFT ablation sweeps (arms + rehearsal-only control) | Slurm, BAR, 128 GPU | [ablations.md](references/ablations.md) |
| 9 | Target eval trajectory (in-sweep) + non-regression (by hand) | Slurm, BAR, h200 | [evals.md](references/evals.md) |
| 10 | Score, monitor, tabulate | Slurm + login pod | [evals.md](references/evals.md) |
| 11 | Submission PR + review request | GitHub + Slack | [submission.md](references/submission.md) |

Cluster/QoS/licence/S3 facts that apply to every stage: [cluster.md](references/cluster.md).
Working scripts from the last cycle: [scripts/](scripts/) (see [scripts/README.md](scripts/README.md)).

## Order that is not negotiable

- **v16 / unified-resources migration before anything expensive.** It runs inside registration
  (`migrate_to_unified_resources: "yes"`). A prior orchestral set lost 76% of conversations to
  `legacy_json_dump` at this step. Smoke it on a few hundred traces first.
- **DataHunter before the recipe.** The mixture gate rejects any dataset without the
  `data_quality` registry block that DataHunter writes. Not bypassable for a new SFT dataset.
- **Mixture validation after the recipe edit**, on the edited `sft_staging_data`, not before.
- **In-sweep evals are the only eval trajectory you get.** `keep_last` is asserted to 1 for
  instruct training, so every checkpoint is deleted as the next lands. Set `num_evals` up
  front, and set `s3_consolidation: true` or only the final checkpoint survives.

## The traps that cost the most time

| Trap | What you do instead |
|---|---|
| The post-judge registry key is **not derivable from the config** — a computed digest was wrong once (`dh_mask_590f4175` vs the real `dh_mask_798b846a`) | `get_registry('instruct','one_off')._load_raw()` |
| Omitting `postprocess_config` in a `preset: passthrough` registration | Always set it. Otherwise `total_lines_read` stays 0 → `AssertionError: Line count mismatch: output has 12305 lines but expected -4`, **and the dataset never gets shuffled** |
| `slurm_serve_and_eval` submits its own job which dies in ~1s (login python has no `thunderdome_tasks`, and is 3.10) | `timeout 200` the launcher, then patch and `sbatch` the script it generated ([patch_eval.py](scripts/patch_eval.py)) |
| The launcher then **blocks** waiting on that job | the same `timeout` wrapper |
| Scoring a generation whose job ended `TIMEOUT`/`FAILED`/`CANCELLED` | refuse unless `COMPLETED`. A partial score looks valid, is wrong, and writing `evals.json` makes it permanent |
| "any results in `evals.json`" as a done-check | require **every** task in the group. Eval jobs score judge-free tasks inline and leave the judge-based ones |
| Eval task groups mixed by licence or orchestral-ness | three groups: `brave` / `orch` / `std`. Take the split from the launcher's own `AssertionError`, do not guess |
| Sizing epoch weights from raw tokens | `tools.mint.composite_token_count` (packed slots). Raw overshot by 30% one way and 9.3x the other |
| An ablation with no rehearsal-only control | add arm Z. The init checkpoint already contains the shipping finance data, so "arm vs init" is not "with vs without" |
| `SBATCH_ACCOUNT=discovery` in `~/.bashrc` beating `#SBATCH --account` | pass account and qos on argv |
| RNO and BAR `/mnt/vast` being the same path | they are different filesystems. `/mnt/vast/shared/vincent.pfister/...` does not exist on BAR |

## Where the last cycle's artifacts are

Branch **`origin/vincent.pfister/mint-sft-tooling`** (tip `92adfd79376`) carries the full worked
example under `scratch/vincent.pfister/mint_sft/` — `SUBMISSION.md`, `APPENDIX.md`, `README.md`,
`RESULTS.md`, the registration / DataHunter / obvious-judge YAMLs, `s7f_clean_ablation_arms.py`,
`plot_fab.py`, `report.html` — plus `sweeps/vpfister/karl_us_mix/*.yaml` (one per arm) and
`mistral/conf_store/experiments/sft/recipe_260908_karl_us_mix_ablation.py`.

```bash
git fetch origin vincent.pfister/mint-sft-tooling -q
git show origin/vincent.pfister/mint-sft-tooling:scratch/vincent.pfister/mint_sft/SUBMISSION.md
```

Submission PR: **#34338**. Run dirs (BAR): `/mnt/vast/runs/vincent.pfister/260912_*_arm_{f,z}`,
`260908_karl_us_mix_ablation`. Non-regression outputs:
`/mnt/vast/runs/vincent.pfister/nonreg_mint_sft_main/`.

## Naming discipline

Keep two vocabularies apart and never mix them in one document.

| external (submission, Slack, MINT) | internal (run dirs, sweeps, recipe) |
|---|---|
| **initial** | the shared init checkpoint |
| **baseline** | arm Z — rehearsal only, no finance data |
| **old** | arm A — the recipe being replaced |
| **new** | arm F — the data being submitted |

A reviewer reading "arm_z" guesses wrong — a MINT reviewer read it as "baseline with the old KARL
sources", which is arm A. State the mapping once, in the submission, then use external names only.

## Reporting

Post progress to Slack **#vp-model-train** (`C0B667J12FM`, private) — Vincent has granted standing
authorisation for unattended status posts there. Review requests go to **#mint-submissions-sft**
(`C0BJB8W4L80`).
