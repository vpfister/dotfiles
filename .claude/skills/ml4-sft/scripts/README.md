# Working scripts from the 2026-09-15 finance freeze

Copied verbatim from BAR `/tmp` (which is volatile) on 2026-09-15. They carry the run dirs,
checkpoints and task strings of **that** cycle — edit the constants at the top, do not assume the
paths still exist. The comments in them are the point; several encode failures that cost hours.

They assume `PY = ~/workspace/mistral_fabv3_pinned/.venv/bin/python` (a detached worktree pinned
at the eval SHA) and `sys.path.insert(0, "/tmp")` for cross-imports, so keep them together.

| script | what it does | the lesson it encodes |
|---|---|---|
| `patch_eval.py` | rewrites a generated thunderdome script: worktree python + shell-config + locale + `ulimit`, exits 1 on any residual `envs/login` | the generated interpreter is 3.10 and has no `thunderdome_tasks` |
| `nonreg_launch.py` | launches `mint_sft_main` across 3 checkpoints × 3 task groups | `timeout` the launcher; three groups by licence AND orchestral-ness, taken from the launcher's own error |
| `nonreg_orch_redo.py` | rebuilds and resubmits only the orchestral groups | task strings are baked into the submission script, so a changed group must be regenerated; `--time=48:00:00`, not 12h |
| `nonreg_2ep.py` | same tasks at the epoch actually being submitted (step 696 = 1.80ep) | measure at the submitted config, not only at the final checkpoint |
| `nonreg_old.py` | adds the `old` arm so the set compares new against the current recipe, not just against a no-finance control | that is the comparison a reviewer cares about most |
| `nonreg_extra.py` | the 19 extra tasks a reviewer asked for, 2 checkpoints only | do not triple the queue for columns nobody is deciding on |
| `nonreg_score.py` | polls, refuses to score a non-`COMPLETED` generation, requires **full** task coverage before calling a group scored | eval jobs score judge-free tasks inline; "any results" marks a half-scored group done |
| `nonreg_health.py` | read-only monitor: `DEAD` / `EMPTY` / `STALLED` / `UNSCORED` | it never cancels or resubmits — that is the operator's call |
| `nonreg_table.py` | one headline metric per task, markdown with external column names | never collapse two epoch counts into one column |
| `eval_gap.py` | diffs the eval categories a reviewer named against what is already scored | resolve categories from the registry at launch time; pinned task strings drift |
| `mk2_sweep.py` | FAB re-run across 35 ablation checkpoints, straight from S3 | one pinned checkout for all 35, or they are not mutually comparable; stagger submissions (35 × 238 GB from S3) |
| `mk2_batch.py` | keeps 8 evals in flight and scores each itself | the auto-submitted scoring jobs target the drained `cpu` partition and never run; refuse scoring below 200 responses |
