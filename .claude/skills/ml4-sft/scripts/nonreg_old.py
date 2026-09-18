"""Non-regression for `old` -- the recipe this submission replaces.

The first passes covered initial / baseline / new only, so the set showed new against a
no-finance control but never against the current recipe. That is the comparison a reviewer
cares about most: replacing old with new should not regress anything.

old's final is step 722 = 1.51B tokens, closest in budget to the ~2ep column (1.46B), so it
pairs with baseline (~2ep) and new (~2ep). Checkpoint is still on BAR local disk.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tmp")
from nonreg_launch import OUT, PY, TASK_GROUPS, TOK, W, sh  # noqa: E402

CKPT = ("/mnt/vast/runs/vincent.pfister/260908_karl_us_mix_ablation/"
        "260908_karl_us_mix_ablation_run000__data_0/checkpoints/checkpoint_00000722/consolidated")


def main() -> None:
    for grp, tasks in TASK_GROUPS.items():
        name = f"old_{grp}"
        if (OUT / f"{name}.jid").exists():
            print(f"{name}: already submitted", flush=True)
            continue
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        for old in (d / "jobs").glob("serve_and_evaluate_submission_*.sh"):
            old.unlink()
        sh(["timeout", "200", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.slurm.qos", "priority-discovery",
            "--serving_config.slurm.partition", "h200",
            "--paths.ckpt_dir", CKPT,
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
