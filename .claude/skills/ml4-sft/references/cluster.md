# Cluster, QoS, licences, S3, cross-cluster

## Environment for every non-interactive BAR command

`ssh bar 'cmd'` lands in `$HOME`, sources nothing, and sets none of this.

```bash
export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock                 # git / registry pulls; composite_token_count does an internal git fetch
ssh bar '. /etc/shell-config/shell-config.sh >/dev/null 2>&1;
  export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock;
  export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8;
  export REGION=BAR SBATCH_ACCOUNT=discovery IGNORE_DISK_SPACE=1;
  cd /mnt/vast/home/vincent.pfister/workspace/mistral_mint_sft && <cmd>'
```

| missing | symptom |
|---|---|
| `LANGUAGE`/`LANG`/`LC_ALL` | `KeyError: 'LANGUAGE'` from `check_utf8()` at `mistral/__init__.py` import |
| `REGION` | `cluster.get_cluster()` falls back to `CI`, whose partitions are `{cpu, h100}` → `AssertionError: ('b200', {'cpu','h100'})` or h200 rejected |
| `SBATCH_ACCOUNT` | `{'priority-discovery'} are not in available_qos={'scavengers'} (account='root')`, or `sbatch: error: Job submission blocked for root account` |
| shell-config | `MISTRAL_API_KEY` / OIDC S3 creds absent → `{"message":"Forbidden"}`, `CoreWeave credentials not configured` |
| `SSH_AUTH_SOCK` | `Permission denied (publickey)` from a tool doing an internal `git fetch` |

Never pass `--account` **and** have `SBATCH_ACCOUNT` set:
`Only one of SBATCH_ACCOUNT and --account should be specified`. And remember the precedence —
`~/.bashrc:81-82` exports `SBATCH_ACCOUNT=discovery`, and **argv > environment > `#SBATCH`
directives**, so a `#SBATCH --account=...` line in a job script is silently ignored. Verify what
actually ran: `sacct -j <id> --format=JobID,Account,QOS,State -X`.

Heredocs through `ssh bar 'bash -s'` mangle quoting and f-strings and have silently produced no
output twice. Write a helper locally, `cat >` it to the remote, run it.

## QoS

| qos | priority | MaxWall | limits |
|---|---|---|---|
| `urgent` | 99999 | | |
| `unpreemptible` / `priority-ci` | 10000 | | |
| `dev` | 9900 | **12:00:00** | `cpu=256, gres/gpu=16` per user, MaxJobsPerUser 5 |
| team `priority-*` | 1000 | none | `priority-discovery` GrpTRES `gres/gpu=768`, no per-user cap |
| `research` | 100 | none | preempted by every `priority-*`, `dev`, `priority-ci` |
| `scavengers` | lowest | | where an unspecified QoS lands you |

- **An unspecified QoS is preemptible.** A mixture-validation job with no `--qos` was requeued
  mid-run (elapsed went *backwards*; `scontrol show job` → `Requeue=1 Restarts=1`) and lost all
  progress. Long CPU jobs go on `dev` (and then `--time` must be ≤ 12h) or `unpreemptible`.
- `priority-ml4_taskforce` and `priority-mint` are **capped at `gres/gpu=0`** — priority 1000 with
  zero allocation. Jobs there sit at `QOSGrpGRES` forever. Their CPU-only use is fine.
- `QOSGrpGRES` **at submit time rejects rather than queues**: two arms sat "PENDING" for a week and
  had actually `FAILED` at `00:00:07` with `ExitCode 0:53, Reason QOSGrpGRES`. Re-verify with
  `sacct`, never a remembered `squeue`.
- `priority-discovery` **preempts `research`**, so evals parked on `research` are preemptible by
  your own training.

Diagnostics:

```bash
squeue -u $USER -h -o "%i %T %r %P %q %l"           # %r = pending reason
squeue -j <jid> -o "%T %r %S" -h                    # reason + estimated start
sacct -j <ids> -n --format=JobID%10,State%12,Elapsed,ExitCode -X
sacct -j <id> --format=JobID%14,State,ExitCode,MaxRSS,ReqMem,Elapsed
sacctmgr -nP show qos priority-discovery format=Name,MaxWall,GrpTRES%25,Priority,Preempt
sacctmgr -nP show assoc account=discovery user=$USER format=account,user,qos
scontrol show partition h200 | grep -oE "MaxTime=[^ ]+"
sinfo -p cpu -N -o "%n %t %C %m"                    # read the Idle column of A/I/O/T, not the aggregate
sinfo -R -o "%n %E"                                 # drain reasons
```

A partition can bleed to zero schedulable cores while aggregate `sinfo` still looks busy — cores
move to "Other" (cordoned) as jobs finish. BAR's `cpu` partition was effectively dead for days
(`k8s: pod scheduled for deletion: rolling update`), with `squeue` estimating a start two months
out. That silently blocks every auto-submitted scoring job.

## Licences

`Reason=None` on a PENDING job is often an **exhausted remote licence**, not a scheduling wait —
Slurm does not say `Licenses`.

```bash
scontrol show licenses | head -8
scontrol show job <jid> | grep -oE "Licenses=[^ ]+|Reason=[^ ]+"
```

```
LicenseName=brave_eval@slurmdb
  Total=10  Used=0  Free=0  Reserved=0  Remote=yes
  LastConsumed=10  LastDeficit=10
```

`Used=0` with `Free=0` is remote-licence accounting: consumption is tracked cluster-wide in
`slurmdb`, not by your jobs. Nothing to fix locally — it starts when someone releases one.
`browsecomp_v3` needs `brave_eval@slurmdb:1`, which is also why it must be its own task group.

## Cross-cluster: RNO and BAR have SEPARATE `/mnt/vast`

Same paths, different filesystems, different content, different credentials. This has cost
repeated hours. Concretely, on BAR:

| path | present on BAR? |
|---|---|
| `/mnt/vast/datasets/finetuning/...` | yes |
| `/mnt/vast/shared/registry/instruct/one_off.json` | yes, but a **separate git clone** that goes stale |
| `/mnt/vast/shared/vincent.pfister/ml4-taskforce/...` | **no** |
| `/mnt/vast/shared/vincent.pfister/karl_v2/...` | **no** |
| `~/.env` | a different file — BAR's had an empty `MISTRAL_API_KEY` |
| the worktree at the same path | a **separate clone** at a different commit |

Which cluster am I on:

```bash
echo "$REGION"
python -c "from cluster.cluster import get_cluster; print(get_cluster().value)"   # rno / bar / ci
```

`get_cluster()` returning `ci` means `REGION` is unset — it is also the tell that you are in a
non-interactive shell that sourced nothing.

**Move code by pushing and pulling a branch, never by assuming a shared checkout.** Two mixture
validations "failed on a tool bug" while also silently validating the *old* recipe, because the
edits were on RNO and the job ran on BAR:

```bash
# RNO
git commit -am "..." && git push origin HEAD
# BAR
git pull --ff-only origin vincent.pfister/finance-qa-sft-run-260908
find $W/tools/mint -name __pycache__ -type d -exec rm -rf {} +
```

Also on BAR: `git -C /mnt/vast/shared/registry pull --ff-only` before any sweep referencing a
newly registered dataset.

Do **not** copy `.env` across clusters — it carries seven other secrets, and cross-cluster
credential copying caused REINF-3004.

## S3 (CoreWeave / CAIOS)

Credentials are **OIDC pod identity**, already in the env after sourcing shell-config. The static
`COREWEAVE_ACCESS_KEY` / `COREWEAVE_SECRET_KEY` are **revoked** — setting them shadows OIDC and
produces `InvalidAccessKeyId`.

```bash
. /etc/shell-config/shell-config.sh >/dev/null 2>&1
printf '[default]\ns3 =\n    addressing_style = virtual\n' > ~/.aws-virtual-config
export AWS_CONFIG_FILE=$HOME/.aws-virtual-config     # shell-config's own aws-config omits this
aws s3 ls --endpoint-url "$COREWEAVE_ENDPOINT" s3://consolidated-checkpoints/ala/
```

Without the endpoint → `InvalidAccessKeyId`. Without virtual addressing →
`PathStyleRequestNotAllowed`. Writes need `--endpoint-url https://cwobject.com`; the default
`cwlota.com` is a read cache and writing through it **succeeds silently**.

- **ALA checkpoints are mirrored to `s3://consolidated-checkpoints/ala/`** — that is how to reach
  them when the ALA tunnel is down, and `--paths.ckpt_dir` accepts an `s3://` URI directly for
  prod serving types.
- A consolidated checkpoint is ~238.8 GB. 35 of them is ~8.3 TB. With `keep_last=1` and
  `s3_consolidation: true`, S3 is the **only** copy.
- Non-recursive `aws s3 ls | grep -c "PRE checkpoint_"` returns 0 for every arm — use
  `aws s3 ls --recursive ... | grep -c consolidated.safetensors`.
- Transient 400 `invalid request sent to auth endpoint` = OIDC token rotation (10 min lifetime).
  Re-run; `sync` is resumable.
- `s3://data-transfers` deletes every object after 7 days. Staging, not storage.
- Outage seen 2026-09-11: `ListMultipartUploads: AccessDenied` on `consolidated-checkpoints`.
  Small `cp` passed, 238 GB multipart uploads failed. A CAIOS auth incident; the status bot's
  "Resolved" ran ~3h ahead of reality. Isolate with
  `aws s3api list-multipart-uploads --endpoint-url $COREWEAVE_ENDPOINT --bucket consolidated-checkpoints`.
  Fallback: strip `--s3 --s3-bucket ... --s3-backend coreweave` from the generated consolidation
  script for a local-only `consolidated/`, which is all the eval needs (cost: no durable copy).

## Checkpoint retention

`retention_policy` is mandatory at launch and must match `keep_last`: 1 → `BENCH` or
`POSTRAINING_ABLATION`; 2 → `MINT_SFT`; 3 → `MINT_RL`; 5 → `BIG_RUN_PRETRAIN`. Instruct training
asserts `keep_last == 1`, so a MINT SFT ablation cannot use `MINT_SFT` — use
`POSTRAINING_ABLATION`. `BENCH` is `ttl=0` and deletes everything.

## Git hygiene in this repo

- **Never `git stash` / `stash pop`** — `refs/stash` is shared across all worktrees and you will
  steal another lane's work. Park as a WIP commit or a temporary branch.
- `fatal: Unable to create '.../worktrees/<name>/index.lock': File exists` — check age and
  `ps -u $USER -o pid=,etime=,args= | grep "[g]it "` before `rm -f`. The lock is worktree-scoped,
  not the shared index.
- `cannot lock ref refs/remotes/origin/main: is at X but expected Y` is structural contention
  between worktrees — retry, do not debug.
- Long `git worktree add` (52,553 files) exceeds the 2-minute Bash timeout and leaves a broken
  partial: `git worktree prune && rm -rf <dir> && git branch -D <branch>`. Run it backgrounded.
- Buildkite is the source of truth for CI, not `gh pr view --json statusCheckRollup`, which lags:
  `bk build view <n> -p mistralai/mistral` (org-qualified slug; `-p mistral` fails).
- An empty `git ls-remote` is usually an auth failure — check rc and stderr.
