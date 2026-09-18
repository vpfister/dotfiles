"""Non-regression at the epoch we actually submit.

The first pass ran `new` at its 3-epoch final. We submit 2 epochs, so a regression measured
at 3ep overstates it. Step 696 is 1.80 epochs -- the last checkpoint below 2ep -- and the
closest measurable proxy for the submitted config.

`baseline` is taken at step 696 too (1.46B tokens for both runs), so the two are compared at
a matched token budget rather than at their respective finals.

Checkpoints are still on BAR local disk here, so no S3 round-trip.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp")
from nonreg_launch import OUT, PY, TASK_GROUPS, TOK, W, sh  # noqa: E402

RUNS = "/mnt/vast/runs/vincent.pfister"
TARGETS = {
    "new_2ep": f"{RUNS}/260912_karl_blast_3ep_arm_f/260912_karl_blast_3ep_arm_f_run000"
               "/checkpoints/checkpoint_00000696/consolidated",
    "baseline_2ep": f"{RUNS}/260912_rehearsal_only_arm_z/260912_rehearsal_only_arm_z_run000"
                    "/checkpoints/checkpoint_00000696/consolidated",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for (name, ckpt), (grp, tasks) in (
        (t, g) for t in TARGETS.items() for g in TASK_GROUPS.items()
    ):
        name = f"{name}_{grp}"
        if (OUT / f"{name}.jid").exists():
            print(f"{name}: already submitted", flush=True)
            continue
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        # timeout: the launcher submits then blocks waiting on its own job, stalling the
        # rest. We only need the generated submission script.
        sh(["timeout", "200", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.slurm.qos", "priority-discovery",
            "--serving_config.slurm.partition", "h200",
            "--paths.ckpt_dir", ckpt,
            "--paths.tokenizer", TOK,
            "--paths.output_dir", str(d),
            "--tasks_str", tasks], cwd=W)
        gen = sorted((d / "jobs").glob("serve_and_evaluate_submission_*.sh"))
        if not gen:
            print(f"{name}: NO SCRIPT GENERATED", flush=True)
            continue
        p = OUT / f"patched_{name}.sh"
        r = sh(["python3", "/tmp/patch_eval.py", str(gen[-1]), str(p), str(PY)])
        if r.returncode != 0:
            print(f"{name}: PATCH FAILED {r.stdout.strip()[:80]}", flush=True)
            continue
        j = sh(["sbatch", "--qos=priority-discovery", "--partition=h200",
                "--time=12:00:00", "--parsable", str(p)])
        jid = j.stdout.strip().split(";")[0]
        print(f"{name}: {jid if jid.isdigit() else j.stderr.strip()[:100]}", flush=True)
        if jid.isdigit():
            (OUT / f"{name}.jid").write_text(jid)


if __name__ == "__main__":
    sys.exit(main())
