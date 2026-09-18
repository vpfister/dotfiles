# Thunderdome evals: launching, repairing, scoring, monitoring

Two eval tracks, both needed for a submission:

1. **Target trajectory** — in-sweep, at each of `num_evals` checkpoints. This is the only way to
   get a curve: `keep_last=1` deletes each checkpoint as the next lands.
2. **Non-regression** — the `mint_sft_main` set, run by hand against a handful of checkpoints.

Three chained Slurm jobs per eval point: **consolidation → generation → scoring**. All three
fail for environment reasons on most runs. Budget for driving them by hand.

## The generated-script patch (applies to every generated job)

Generated consolidation / eval / scoring scripts hard-code
`/mnt/vast/envs/login/mistral_login_*/bin/python`, which is **3.10** (SyntaxError on the PEP 695
generics in `mistral/utils.py`) and has no `thunderdome_tasks`. They also inherit none of the env
the job needs.

```
File ".../mistral/utils.py", line 302
    def timeit[Output, **P](func: Callable[P, Output]) -> Callable[P, Output]:
SyntaxError: invalid syntax
```

Use [`scripts/patch_eval.py`](../scripts/patch_eval.py): substitutes the interpreter for the
worktree `.venv/bin/python`, inserts after the last `#SBATCH` line

```bash
. /etc/shell-config/shell-config.sh >/dev/null 2>&1   # MISTRAL_API_KEY + OIDC S3 creds
export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ulimit -n 1048576
```

and exits non-zero if any `envs/login` reference survives.

Root cause: `build_consolidation_cmd` takes the interpreter from
`cluster.latest_login_env` → `uv_venv_or_legacy_env()`, which returns the **launching process's**
active venv if there is one. Runs launched with a venv active are immune. Symlinking a `.venv`
into the code snapshot does **not** help — the path is resolved at script-generation time.

Other env defects, each surfacing after the previous:

| symptom | fix |
|---|---|
| `PENDING (QOSMaxWallDurationPerJobLimit)` | generated `--time=1440` exceeds `dev`'s 12h MaxWall → pass an explicit `--time` |
| `KeyError: 'LANGUAGE'` in `check_utf8()` | the three locale exports above |
| `OSError: [Errno 24] Too many open files` after ~9 min | `ulimit -n 1048576` (soft default 1024) |
| `ValueError: CoreWeave credentials not configured: ['COREWEAVE_ACCESS_KEY', ...]` | source shell-config **inside** the job. The static keys named in the error are revoked |

## Launching a non-regression set

Working driver: [`scripts/nonreg_launch.py`](../scripts/nonreg_launch.py).

```python
sh(["timeout", "200", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
    "--serving_config", "shrimpstral_fp8_orchestral",
    "--serving_config.model.runai_s3_backend", "coreweave",
    "--serving_config.slurm.qos", "priority-discovery",
    "--serving_config.slurm.partition", "h200",
    "--paths.ckpt_dir", uri,                 # accepts s3:// directly for prod serving types
    "--paths.tokenizer", TOK,                # required whenever ckpt_dir is given
    "--paths.output_dir", str(d),
    "--tasks_str", tasks], cwd=W)
# then patch the script it wrote and submit THAT
sbatch --qos=priority-discovery --partition=h200 --time=48:00:00 --parsable patched_<name>.sh
```

- **`timeout` is load-bearing.** The launcher submits its own job and then **blocks** waiting on
  it, stalling every remaining group for hours. It only needs to write the submission script.
- The job it submits dies in ~1 s (`FAILED 00:00:01 1:0`,
  `ModuleNotFoundError: No module named 'thunderdome_tasks'`). Expect one throwaway per group.
  They accumulate in your queue and can block a real job holding the same output dir — cancel by
  explicit job ID after cross-checking your `.jid` files.
- `--slurm.qos` is rejected; it must be `--serving_config.slurm.qos`.
- `max_concurrent_requests` is an **architectural** field on a registered template and cannot be
  overridden: `differs on architectural fields`.
- Do not wrap `slurm_serve_and_eval` in `sbatch` — it is a launcher, run it on the login pod.

### Task groups must be homogeneous, twice over

```
AssertionError: Task group has heterogeneous license requirements
ValueError: Cannot mix orchestral and non-orchestral tasks in one job group
  (orchestral: [...], standard: [...]). Split them into separate task groups.
```

Two independent constraints: **licence** and **orchestral-vs-standard**. For `mint_sft_main` that
is three groups — `brave` (1 task: `browsecomp_v3`, needs `brave_eval@slurmdb`), `orch` (14),
`std` (14). **Read the split from the launcher's own error message rather than guessing**; the
first attempt assumed two groups and every checkpoint returned `NO SCRIPT GENERATED`.

Symptom of a bad group: `NO SCRIPT GENERATED`, silently.

Orchestral prefixes in the 2026-09 list: `swebench_vibe_v1`, `swebench_pro_orchestral_v1`,
`octobench_vibe_v2`, `tau3_bench_telecom`, `gdpval_v5`, `jobbench_v1`, `apex_agents`,
`cybergym_orchestral_v2`, `swebench_verified_orchestral_v2`.

### Wall time

`priority-discovery` has **no MaxWall** and `h200` is `MaxTime=UNLIMITED`. A 12h `--time` carried
over from `dev` killed two orchestral jobs at exactly `12:00:07`. Use `--time=48:00:00` for
orchestral groups; std runs 9-10 min, brave 6 min.

swebench alone starved the rest: in 12h an orchestral group produced output for 3 of 14 tasks,
all swebench. Dropping the three swebench entries is a declared deviation in `SUBMISSION.md`.

### Never resubmit into a live output dir

```
TimeoutError: Could not acquire lock on .../responses.jsonl after 0.1 seconds:
another process is currently holding it
```

Jobs then report `COMPLETED` while scoring logs `Generation watch complete: 0 ready, 10 failed`.
All 10 tasks lost, invisibly. Wait for the predecessor to fully die, and clear stale
`serve_and_evaluate_submission_*.sh` so the newest glob is definitely yours.

## Recovering the final checkpoint

Training dies in teardown after the last step, so the final checkpoint gets **no generated
consolidation or eval script**. Retarget the previous step's and verify zero residuals:

```bash
S=$(find $R/evals/eval_00000592 -name 'consolidation_job_*.sh' | head -1)
sed -e "s|00000592|00000722|g" \
    -e "s|/mnt/vast/envs/login/mistral_login_[^/]*/bin/python|$PY|g" "$S" > "$P"
grep -c 00000592 "$P"   # want 0
mkdir -p $R/evals/eval_00000722/jobs
sbatch --partition=cpu --qos=unpreemptible --parsable "$P"
```

**Resubmitting a failed consolidation breaks the chain.** Eval jobs are `afterok` on the
*original* consolidation; when it fails they are dropped, and a standalone resubmit fires nothing
downstream. Recovering one stage commits you to driving all three. Checking for `evals/eval_<step>/`
is not enough — it is created regardless. Check for `results/<task>/<hash>/responses.jsonl`.

Write literal absolute paths into batch scripts. A `$W` that reached a script unexpanded produced
`/.venv/bin/python: No such file or directory`.

## Scoring

**Judge-free tasks are scored inline by the eval job; judge-based tasks are not.** So a group can
be *partially* scored and look finished.

```python
def scored(name, grp) -> bool:
    """True only when EVERY task in the group has a result.

    Any-results-is-done was wrong: a group showed 7 of 14 and was treated as finished;
    the 7 judge-based tasks were never scored and the gap was invisible.
    """
    got = set(json.loads((OUT/name/"evals.json").read_text()).get("results", {}))
    return all(t in got for t in TASK_GROUPS[grp].split(",") if t)
```

Standalone scoring job:

```bash
$PY -m thunderdome.main run-scoring \
    --tasks_str '<the group's full task string>' \
    --output_path '<eval_dir>/' \
    --overwrite_scoring_only True
```

on `--partition=h200 --qos=priority-discovery --time=06:00:00 --cpus-per-task=16 --mem=128G`
(or `--partition=cpu --qos=unpreemptible` when `cpu` is healthy). Working watcher:
[`scripts/nonreg_score.py`](../scripts/nonreg_score.py).

**The auto-submitted scoring jobs target the `cpu` partition.** When `cpu` is drained they sit
`JobHeldUser` / `PENDING` forever (estimated start two months out) and nothing ever scores. Score
it yourself.

### Never score a partial generation

A partial score looks valid, is wrong, and writing `evals.json` makes the done-check true so it is
never redone. Two independent guards:

- refuse unless the generation job state starts with `COMPLETED` — `TIMEOUT`/`FAILED`/`CANCELLED`
  leave a partial `responses.jsonl` behind, and two orchestral jobs hit the 12h wall for real;
- refuse unless `wc -l responses.jsonl` equals the expected count (200 for FAB,
  **150 for `finance_bench_v6`** — a bare `find -name responses.jsonl | head -1` picks the wrong
  file).

A job can report `COMPLETED  ExitCode 0:0` while its steps were killed
(`*** STEP ... CANCELLED ... DUE TO SIGNAL Killed ***`), leaving 135/200. Retry those, but **park
the partial first** (`mv responses.jsonl responses.jsonl.partial_$TS`,
`mv eval.err eval.err.old_$TS`) — generation resumes from `responses.jsonl`, so a short file caps
the retry at the same count, and a stale `eval.err` makes scoring refuse.

The built-in refusal is correct and should not be overridden blindly:

```
ERROR: Parent generation job 2195405 is FAILED and grace cycle exhausted; abandoning 1 pending task(s)
WARNING: Generation failed for vals_finance_agent_v2[...], skipping scoring (error file: .../eval.err)
```

Twice this cycle the generation had genuinely crashed part-way (intermittent `parse_html_page` in
the finance_agent tool) leaving 97 and 106 of 200 responses.

### The 0.5% missing-score threshold

```
RuntimeError: 1 metric(s) failed: rubric_score
  -> results/errors/<task>--<hash>_scoring.err:
     ValueError: Too many missing scores (1.0000% > 0.5000%)
```

2 of 200 judge scores missing breaches a hard 0.5% tolerance
(`thunderdome/metrics/metric_runners.py:112 check_score_fraction`). Points that lost 1 score
passed. It is transient, so retry — but the retry fails identically unless you reset the
watcher's counter (`score_tries: 0`, drop `score_jid` from the point's `.meta.json`). The exit
code is `0:0`; the real cause is at line ~16 of the `_scoring.err` file, not in the job log.

## Monitoring

[`scripts/nonreg_health.py`](../scripts/nonreg_health.py) — **read-only by design**. It never
cancels or resubmits; deciding what to do is the operator's call. Polls every 300 s and alarms on
exactly the four modes this lane has hit:

| state | meaning |
|---|---|
| `DEAD` | job ended `TIMEOUT`/`FAILED`/`CANCELLED`/`NODE_FAIL`/`PREEMPTED` — a partial generation nobody should score |
| `EMPTY` | job `COMPLETED` but produced **zero** responses (what the lock collision looked like) |
| `STALLED` | `RUNNING` but total response rows unchanged for `STALL_MIN = 45` minutes |
| `UNSCORED` | generation `COMPLETED` with responses, `evals.json` empty, no scoring job in flight |

Two watcher bugs worth not repeating:

- **Re-discover targets inside the poll loop**, not once at start — targets get added while it runs.
- **Dedup on in-flight state, not on end state**, and treat empty `sacct` output as *alive*. A
  dedup on "already consolidated" produced 4 duplicate consolidations; a dedup on a truncated
  Slurm job name produced 4 duplicate evals and 12 scoring jobs.
- `cat *.jid | sort -u` is broken — the files have **no trailing newline**, so everything merges
  into one string and every running job looks untracked. This nearly got live jobs cancelled. Use
  `for f in $O/*.jid; do printf "%s %s\n" "$(cat "$f")" "$(basename "$f" .jid)"; done`.

Run the watcher detached on the login pod, not as a Slurm job — queueing a 2-CPU polling loop
behind a 322-deep queue so it can submit into that same queue cost 2.5 hours:

```bash
ssh -f bar '. /etc/shell-config/shell-config.sh >/dev/null 2>&1;
  export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock SBATCH_ACCOUNT=discovery REGION=BAR \
         LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8;
  cd /tmp && setsid nohup $HOME/workspace/mistral_fabv3_pinned/.venv/bin/python /tmp/nonreg_score.py \
    > /mnt/vast/runs/vincent.pfister/nonreg_score.log 2>&1 < /dev/null'
```

Verify it actually detached: `ps -o pid=,ppid=,sid=,tty=,args= -p <pid>` — safe only when
`sid == pid` and `tty` is `?`. And verify a restart took: kill and restart in **separate**
commands, then confirm the log advances.

## Reading results

`evals.json` is `{start, end, time, results}` — iterate `d["results"]`, not `d`. Task keys embed
the judge, so an exact lookup on `vals_finance_agent_v2` finds nothing:

```python
fab = next((v for k, v in d["results"].items() if k.startswith("vals_finance_agent")), None)
```

FAB metrics are namespaced: `rubric_score_MeanScore`, `rubric_score_NaiveAccuracy`,
`rubric_score_CorrectnessScore`, `rubric_score_ContradictionScore`,
`rubric_score_ClassBalancedAccuracy`, `rubric_score_CompletionRate`, `rubric_score_NumTotal`,
`rubric_score_NumNaN`. A loose key filter once returned the prefix-cache `hit_rate` as a score.

A judge parse failure poisons a row to NaN and `rubric_score_NumNaN` still reports 0.0 — compare
`NumTotal` against `num_datapoints`.

Table generator for the submission: [`scripts/nonreg_table.py`](../scripts/nonreg_table.py). It
picks one headline metric per task family and emits markdown with the **external** column names
(initial / base2 / new2 / base3 / new3). Do not collapse two epoch counts into one column —
whichever scored last silently won, and published numbers changed.

Gap check against what a reviewer asked for: [`scripts/eval_gap.py`](../scripts/eval_gap.py)
resolves eval categories from `mistral.conf_store.eval.prod.get_evals_registry()` and diffs
against the task names already in your output dirs. Resolve categories **at launch time** — the
`mint_sft_main` list in PR #31253 had already drifted (`charxiv_cot`, `mmmu_cot`,
`harbor_deepswe` added since).

## Noise floor — measure it, do not borrow it

Evaluate the **initial** checkpoint three times on the exact same eval, judge and question set.
2026-09: 0.8085 / 0.8082 / 0.7897 MeanScore and 0.6231 / 0.6150 / 0.6080 NaiveAccuracy
→ sd 1.08 and 0.75 points. The bar for comparing two runs is the sd of their *difference*:
**1.53 points on MeanScore, 1.07 on NaiveAccuracy**. State in the report that an sd from 3 samples
is loosely pinned (~±50%).

Superseded figures still floating around: the VALS `observed_duplicate_run_range` of **3.32
points** (a range, not a dispersion — it overstates the bar) and a 2.04-point mean-difference sd.

## Judge model constraints

- Use `*-eval-judge-only` endpoints. `kimi-k2.6-finance-rl` is **absent from
  `SCIENCE_MISTRAL_MODEL`** (`packages/inference/src/inference/api/harmattan.py`), so thunderdome
  cannot resolve a server URL and scoring fails **after** generation. The preview only *logs*
  `ERROR - No default server URL for model: kimi-k2.6-finance-rl` and still exits 0.
- Never use `*-do-not-use-ml4-release-run` models.
- Run `mint_sft_main` **verbatim including its judge models** (k2.5, not the k2.6 used for FAB) so
  the numbers stay comparable to every other workstream's.
- `vals_finance_agent_v2` is FAB **v1.1**, not FAB v2. The `_mk2` variant is the fixed FABv11.

## Serving configs

| config | max_model_len | max_concurrent_requests |
|---|---|---|
| `shrimpstral_fp8_classic` | 131,072 | 512 |
| `shrimpstral_fp8_orchestral` | 262,144 | 64 |
| `shrimpstral_bf16_classic` | — | use for a checkpoint with no fp8 qscales, at `model_parallel 4` |

Orchestral tasks assert `max_model_len >= 131_072`. An eval job is 2 GPUs, not 8.

Concurrent evals on one node collide: `OSError: [Errno 98] Address already in use` — submit with
`--exclusive`, or stagger.
