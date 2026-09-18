"""Score the non-regression evals on h200.

The scoring jobs thunderdome auto-submits land on the `cpu` partition, which is drained --
they were estimated to start in November. Nothing scores non-regression otherwise, so the
generations would have sat complete and unscored indefinitely.

Waits for each group's eval job to leave the queue before scoring: scoring a partial
generation produces a number that looks valid and is wrong.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/tmp")
from nonreg_launch import OUT, PY, TASK_GROUPS, W  # noqa: E402

ENV = (
    "\n. /etc/shell-config/shell-config.sh >/dev/null 2>&1\n"
    "export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8\n"
    "ulimit -n 1048576\n"
)
POLL = 240
DEAD_OR_DONE = ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF")


def sh(c, **kw):
    return subprocess.run(c, capture_output=True, text=True, **kw)


def jstate(jid: str) -> str:
    o = sh(["sacct", "-j", str(jid), "-n", "--format=State", "-X"]).stdout
    return o.splitlines()[0].strip() if o.strip() else ""


def submit(name: str, tasks: str) -> str | None:
    d = OUT / name
    p = OUT / f"score_{name}.sh"
    p.write_text(
        f"#!/bin/bash\n#SBATCH --job-name=nrs_{name}\n"
        "#SBATCH --partition=h200\n#SBATCH --qos=priority-discovery\n"
        "#SBATCH --time=06:00:00\n#SBATCH --cpus-per-task=16\n#SBATCH --mem=128G\n"
        f"#SBATCH --output={OUT}/score_{name}.out\n#SBATCH --error={OUT}/score_{name}.err\n"
        f"{ENV}cd {W}\n"
        f"{PY} -m thunderdome.main run-scoring --tasks_str '{tasks}' "
        f"--output_path '{d}/' --overwrite_scoring_only True\n"
    )
    r = sh(["sbatch", "--parsable", str(p)])
    jid = r.stdout.strip().split(";")[0]
    if not jid.isdigit():
        print(f"  {name}: SUBMIT FAILED {r.stderr.strip()[:100]}", flush=True)
        return None
    (OUT / f"{name}.score_jid").write_text(jid)
    print(f"  score {name} -> {jid}", flush=True)
    return jid


def scored(name: str, grp: str) -> bool:
    """True only when every task in the group has a result.

    Any-results-is-done was wrong: eval jobs score the judge-free tasks inline, so a group
    could show 7 of 14 and be treated as finished. The judge-based tasks were then never
    scored and the gap was invisible.
    """
    f = OUT / name / "evals.json"
    if not f.exists():
        return False
    try:
        got = set(json.loads(f.read_text()).get("results", {}))
    except Exception:
        return False
    return all(t in got for t in TASK_GROUPS[grp].split(",") if t)


def main() -> None:
    for _ in range(300):
        # Re-discover every pass, not once at start: targets get added while this runs
        # (the 1.8-epoch pair was launched after the watcher).
        units = [
            (j.stem, j.stem.rsplit("_", 1)[-1])
            for j in sorted(OUT.glob("*.jid"))
            if j.stem.rsplit("_", 1)[-1] in TASK_GROUPS
        ]
        left = 0
        for name, grp in units:
            if scored(name, grp):
                continue
            left += 1
            sj = OUT / f"{name}.score_jid"
            if sj.exists():
                st = jstate(sj.read_text().strip())
                if st == "" or not st.startswith(DEAD_OR_DONE):
                    continue  # scoring in flight
                if st.startswith("COMPLETED"):
                    continue  # completed but unscored: leave it, do not loop-resubmit
            ej = OUT / f"{name}.jid"
            if not ej.exists():
                continue
            st = jstate(ej.read_text().strip())
            if not st.startswith(DEAD_OR_DONE):
                continue  # generation still running
            if not st.startswith("COMPLETED"):
                # TIMEOUT / FAILED / CANCELLED leave a partial generation behind. Scoring it
                # produces a number that looks valid and is wrong, and writing evals.json
                # would make scored() true so it never gets redone. Two orch jobs already
                # hit the 12h wall, so this is not hypothetical.
                print(f"  {name}: generation ended {st}, refusing to score", flush=True)
                continue
            submit(name, TASK_GROUPS[grp])
        print(f"{time.strftime('%H:%M:%S')} unscored={left}/{len(units)}", flush=True)
        if left == 0:
            print("ALL SCORED", flush=True)
            break
        time.sleep(POLL)


if __name__ == "__main__":
    main()
