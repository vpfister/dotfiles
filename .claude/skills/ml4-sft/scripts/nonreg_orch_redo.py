"""Rebuild and resubmit the orchestral non-regression groups without swebench.

The previous orch jobs had the 14-task string baked into their submission scripts, so they
have to be regenerated rather than resubmitted. swebench is dropped (see nonreg_launch).

Wall time is 48h, not 12h: priority-discovery has no MaxWall and h200 is MaxTime=UNLIMITED,
so the earlier 12h cap was carried over from the dev QoS for no reason and killed two jobs
at exactly 12:00.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp")
from nonreg_launch import OUT, PY, TASK_GROUPS, TOK, W, sh  # noqa: E402

S3 = "s3://consolidated-checkpoints"
RUNS = "/mnt/vast/runs/vincent.pfister"
TARGETS = {
    "INIT": f"{S3}/ala/mint_sft/260901_shrimpy_mid260623_sft260826_code/"
            "260901_shrimpy_mid260623_sft260826_code_run000/checkpoints/"
            "checkpoint_00045374/consolidated",
    "Z_final": f"{S3}/bar/vincent.pfister/260912_rehearsal_only_arm_z/"
               "260912_rehearsal_only_arm_z_run000/checkpoints/checkpoint_00001147/consolidated",
    "F_final": f"{S3}/bar/vincent.pfister/260912_karl_blast_3ep_arm_f/"
               "260912_karl_blast_3ep_arm_f_run000/checkpoints/checkpoint_00001159/consolidated",
    "new_2ep": f"{RUNS}/260912_karl_blast_3ep_arm_f/260912_karl_blast_3ep_arm_f_run000"
               "/checkpoints/checkpoint_00000696/consolidated",
    "baseline_2ep": f"{RUNS}/260912_rehearsal_only_arm_z/260912_rehearsal_only_arm_z_run000"
                    "/checkpoints/checkpoint_00000696/consolidated",
}
TASKS = TASK_GROUPS["orch"]


def main() -> None:
    print(f"orch group is now {len(TASKS.split(','))} tasks", flush=True)
    for name, ckpt in TARGETS.items():
        name = f"{name}_orch"
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        # Clear stale submission scripts so the newest glob is definitely ours.
        for old in (d / "jobs").glob("serve_and_evaluate_submission_*.sh"):
            old.unlink()
        sh(["timeout", "200", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.model.runai_s3_backend", "coreweave",
            "--serving_config.slurm.qos", "priority-discovery",
            "--serving_config.slurm.partition", "h200",
            "--paths.ckpt_dir", ckpt,
            "--paths.tokenizer", TOK,
            "--paths.output_dir", str(d),
            "--tasks_str", TASKS], cwd=W)
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
                "--time=48:00:00", "--parsable", str(p)])
        jid = j.stdout.strip().split(";")[0]
        print(f"{name}: {jid if jid.isdigit() else j.stderr.strip()[:100]}", flush=True)
        if jid.isdigit():
            (OUT / f"{name}.jid").write_text(jid)


if __name__ == "__main__":
    sys.exit(main())
