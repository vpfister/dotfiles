"""Launch the evals Jonas asked for that we had not run.

19 tasks: the aa-index category, the mint_sft_main entries our PR #31253 task string
predates (charxiv_cot, mmmu_cot, harbor_deepswe), and tablebench_dp from finance.

Two checkpoints only -- initial and new (~2ep, step 696). Those are the two the merge
decision turns on; adding baseline and the 3ep pair would triple the queue for columns
nobody is deciding on.

swebench stays out. It is run separately once this succeeds, so a repeat of the lock
collision cannot take the rest of the set down with it.

Groups are split orchestral vs standard because a job group must be homogeneous. None of
these tasks carries a licence, so there is no brave-style third group.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp")
from nonreg_launch import OUT, PY, TOK, W, sh  # noqa: E402

TASKS = json.loads(Path("/tmp/missing_tasks.json").read_text())
GROUPS = {
    "xorch": ",".join(t["task"] for t in TASKS if t["orchestral"]),
    "xstd": ",".join(t["task"] for t in TASKS if not t["orchestral"]),
}
S3 = "s3://consolidated-checkpoints"
RUNS = "/mnt/vast/runs/vincent.pfister"
TARGETS = {
    "INIT": f"{S3}/ala/mint_sft/260901_shrimpy_mid260623_sft260826_code/"
            "260901_shrimpy_mid260623_sft260826_code_run000/checkpoints/"
            "checkpoint_00045374/consolidated",
    "new_2ep": f"{RUNS}/260912_karl_blast_3ep_arm_f/260912_karl_blast_3ep_arm_f_run000"
               "/checkpoints/checkpoint_00000696/consolidated",
}


def main() -> None:
    for grp, tasks in GROUPS.items():
        print(f"{grp}: {len(tasks.split(','))} tasks", flush=True)
    for (name, ckpt), (grp, tasks) in (
        (t, g) for t in TARGETS.items() for g in GROUPS.items()
    ):
        name = f"{name}_{grp}"
        if (OUT / f"{name}.jid").exists():
            print(f"{name}: already submitted", flush=True)
            continue
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        for stale in (d / "jobs").glob("serve_and_evaluate_submission_*.sh"):
            stale.unlink()
        sh(["timeout", "240", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.model.runai_s3_backend", "coreweave",
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
        if sh(["python3", "/tmp/patch_eval.py", str(gen[-1]), str(p), str(PY)]).returncode:
            print(f"{name}: PATCH FAILED", flush=True)
            continue
        j = sh(["sbatch", "--qos=priority-discovery", "--partition=h200",
                "--time=48:00:00", "--parsable", str(p)])
        jid = j.stdout.strip().split(";")[0]
        print(f"{name}: {jid if jid.isdigit() else j.stderr.strip()[:100]}", flush=True)
        if jid.isdigit():
            (OUT / f"{name}.jid").write_text(jid)


if __name__ == "__main__":
    sys.exit(main())
