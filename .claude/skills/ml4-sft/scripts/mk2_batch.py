"""Keep up to MAX_INFLIGHT mk2 evals running until all 35 checkpoints are scored.

Runs on the BAR login pod (setsid nohup), so it survives the ssh relay dropping.

Submits evals, then scores each one itself: the auto-submitted scoring jobs target the
drained `cpu` partition and never run. Scoring is refused below 200 responses — a partial
generation scores to a silently wrong number.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/tmp")
from mk2_sweep import ARMS, ENV, FAB, OUT, PY, TASK, W, ckpt_uri, outdir, patch, tag  # noqa: E402

MAX_INFLIGHT = 8
N_EXPECT = 200
POLL = 240
DEAD = ("FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF")
MAX_TRIES = 2


def sh(c, **kw):
    return subprocess.run(c, capture_output=True, text=True, **kw)


def jstate(jid):
    o = sh(["sacct", "-j", str(jid), "-n", "--format=State", "-X"]).stdout
    return o.splitlines()[0].strip() if o.strip() else ""


def scored(d: Path) -> bool:
    f = d / "evals.json"
    if not f.exists():
        return False
    try:
        return any(k.startswith("vals_finance_agent")
                   for k in json.loads(f.read_text()).get("results", {}))
    except Exception:
        return False


def nresp(d: Path) -> int:
    f = d / FAB / "responses.jsonl"
    return sum(1 for _ in f.open()) if f.exists() else 0


def meta(t: str) -> dict:
    p = OUT / f"{t}.meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def setmeta(t: str, **kw):
    p = OUT / f"{t}.meta.json"
    d = meta(t)
    d.update(kw)
    p.write_text(json.dumps(d))


def submit_eval(arm, step):
    t = tag(arm, step)
    d = outdir(arm, step)
    d.mkdir(parents=True, exist_ok=True)
    sh([str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
        "--serving_config", "shrimpstral_fp8_orchestral",
        "--serving_config.model.runai_s3_backend", "coreweave",
        "--serving_config.slurm.qos", "priority-discovery",
        "--serving_config.slurm.partition", "h200",
        "--paths.ckpt_dir", ckpt_uri(arm, step),
        "--paths.tokenizer", "/mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json",
        "--paths.output_dir", str(d),
        "--tasks_str", TASK], cwd=W)
    gen = sorted((d / "jobs").glob("serve_and_evaluate_submission_*.sh"))
    if not gen:
        print(f"  {t}: NO SCRIPT", flush=True)
        return None
    p = OUT / f"patched_{t}.sh"
    if not patch(gen[-1], p):
        print(f"  {t}: PATCH FAILED", flush=True)
        return None
    r = sh(["sbatch", "--qos=priority-discovery", "--partition=h200",
            "--time=08:00:00", "--parsable", str(p)])
    jid = r.stdout.strip().split(";")[0]
    if not jid.isdigit():
        print(f"  {t}: SUBMIT FAILED {r.stderr.strip()[:80]}", flush=True)
        return None
    setmeta(t, eval_jid=jid, eval_tries=meta(t).get("eval_tries", 0) + 1)
    print(f"  eval {t} -> {jid}", flush=True)
    return jid


def submit_score(arm, step):
    t = tag(arm, step)
    d = outdir(arm, step)
    p = OUT / f"score_{t}.sh"
    p.write_text(
        f"#!/bin/bash\n#SBATCH --job-name=sc_{t}\n"
        "#SBATCH --partition=h200\n#SBATCH --qos=dev\n#SBATCH --time=04:00:00\n"
        "#SBATCH --cpus-per-task=8\n#SBATCH --mem=64G\n"
        f"#SBATCH --output={OUT}/score_{t}.out\n#SBATCH --error={OUT}/score_{t}.err\n"
        f"{ENV}cd {W}\n"
        f"{PY} -m thunderdome.main run-scoring --tasks_str '{TASK}' "
        f"--output_path '{d}/' --overwrite_scoring_only True\n")
    r = sh(["sbatch", "--parsable", str(p)])
    jid = r.stdout.strip().split(";")[0]
    if jid.isdigit():
        setmeta(t, score_jid=jid, score_tries=meta(t).get("score_tries", 0) + 1)
        print(f"  score {t} -> {jid}", flush=True)


def main():
    units = [(a, s) for a, (_, _, steps) in ARMS.items() for s in steps]
    # Z/A/F carry the submission; B/C/D/E are appendix. Order matters because the
    # concurrency cap means the tail may not finish before the deadline.
    prio = {"I": 0, "I2": 0, "I3": 0, "Z": 1, "A": 2, "F": 3}
    units.sort(key=lambda u: (prio.get(u[0], 9), u[0], u[1]))
    for _ in range(400):
        inflight = 0
        pending = []
        for arm, step in units:
            t, d = tag(arm, step), outdir(arm, step)
            if scored(d):
                continue
            m = meta(t)
            n = nresp(d)

            if n >= N_EXPECT:
                sj = m.get("score_jid")
                if sj and not jstate(sj).startswith(DEAD) and jstate(sj) != "COMPLETED":
                    inflight += 1
                elif not scored(d) and m.get("score_tries", 0) < MAX_TRIES:
                    submit_score(arm, step)
                    inflight += 1
                continue

            ej = m.get("eval_jid")
            st = jstate(ej) if ej else None
            if ej and (st == "" or not st.startswith(DEAD)) and st != "COMPLETED":
                inflight += 1
            elif m.get("eval_tries", 0) < MAX_TRIES:
                pending.append((arm, step))

        for arm, step in pending:
            if inflight >= MAX_INFLIGHT:
                break
            if submit_eval(arm, step):
                inflight += 1
                time.sleep(5)

        done = sum(1 for a, s in units if scored(outdir(a, s)))
        print(f"{time.strftime('%H:%M:%S')} scored={done}/{len(units)} inflight={inflight}", flush=True)
        if done == len(units):
            print("ALL SCORED", flush=True)
            break
        time.sleep(POLL)


if __name__ == "__main__":
    main()
