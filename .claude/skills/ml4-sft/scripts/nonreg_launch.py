"""Non-regression evals: mint_sft_main on the shared init plus arms Z and F finals.

Task string is Jonas Amar's verbatim `mint_sft_main` from PR #31253 — 31 evals. Kept
character-for-character, judge models included (k2.5, not the k2.6 we use for FAB), so our
numbers stay comparable to every other workstream's.

Three checkpoints: the shared init both arms start from, arm Z's final (rehearsal-only
control) and arm F's final. Start-and-end only; the trajectory is FAB's job.

Checkpoints are read from S3 — keep_last=1 pruned every local copy.
"""

import subprocess
import sys
from pathlib import Path

W = Path("/mnt/vast/home/vincent.pfister/workspace/mistral_fabv3_pinned")
PY = W / ".venv/bin/python"
OUT = Path("/mnt/vast/runs/vincent.pfister/nonreg_mint_sft_main")
TOK = "/mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json"
S3 = "s3://consolidated-checkpoints"
_ALL = [t for t in Path("/tmp/mint_sft_main_tasks.txt").read_text().strip().split(",") if t]
# Three groups, forced by two separate constraints the launcher enforces:
#   - browsecomp_v3 needs the brave_eval@slurmdb licence and the rest need none; a group
#     must be licence-homogeneous
#   - orchestral tasks (sandboxed) cannot share a job group with standard ones
# Names taken from the launcher's own error message rather than guessed.
_ORCH = (
    "swebench_vibe_v1", "swebench_pro_orchestral_v1", "octobench_vibe_v2",
    "tau3_bench_telecom", "gdpval_v5", "jobbench_v1", "apex_agents",
    "cybergym_orchestral_v2", "swebench_verified_orchestral_v2",
)
# swebench is dropped: it is a code-agent benchmark with no bearing on a finance data
# change, and it is by far the slowest thing here -- a 12h orchestral job produced output
# for only 3 of 14 tasks, all swebench. Deviation from the verbatim mint_sft_main list is
# declared in SUBMISSION.md.
_DROP = ("swebench_vibe_v1", "swebench_pro_orchestral_v1", "swebench_verified_orchestral_v2")
_ALL = [t for t in _ALL if not t.startswith(_DROP)]

TASK_GROUPS = {
    "brave": ",".join(t for t in _ALL if t.startswith("browsecomp_v3")),
    "orch": ",".join(t for t in _ALL if t.startswith(_ORCH)),
    "std": ",".join(
        t for t in _ALL if not t.startswith(_ORCH) and not t.startswith("browsecomp_v3")
    ),
}

TARGETS = {
    "INIT": f"{S3}/ala/mint_sft/260901_shrimpy_mid260623_sft260826_code/"
            "260901_shrimpy_mid260623_sft260826_code_run000/checkpoints/"
            "checkpoint_00045374/consolidated",
    "Z_final": f"{S3}/bar/vincent.pfister/260912_rehearsal_only_arm_z/"
               "260912_rehearsal_only_arm_z_run000/checkpoints/checkpoint_00001147/consolidated",
    "F_final": f"{S3}/bar/vincent.pfister/260912_karl_blast_3ep_arm_f/"
               "260912_karl_blast_3ep_arm_f_run000/checkpoints/checkpoint_00001159/consolidated",
}


def sh(c, **kw):
    return subprocess.run(c, capture_output=True, text=True, **kw)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(_ALL)} tasks x {len(TARGETS)} checkpoints x {len(TASK_GROUPS)} groups", flush=True)

    for (name, uri), (grp, tasks) in ((t, g) for t in TARGETS.items() for g in TASK_GROUPS.items()):
        name = f"{name}_{grp}"
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        # timeout: the launcher SUBMITS then BLOCKS waiting for its own job, which stalls
        # the remaining groups for hours. We only need it to write the submission script;
        # we patch and submit that ourselves.
        sh(["timeout", "200", str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.model.runai_s3_backend", "coreweave",
            "--serving_config.slurm.qos", "priority-discovery",
            "--serving_config.slurm.partition", "h200",
            "--paths.ckpt_dir", uri,
            "--paths.tokenizer", TOK,
            "--paths.output_dir", str(d),
            "--tasks_str", tasks], cwd=W)

        gen = sorted((d / "jobs").glob("serve_and_evaluate_submission_*.sh"))
        if not gen:
            print(f"{name}: NO SCRIPT GENERATED", flush=True)
            continue
        # Generated scripts hard-code the login python, which lacks thunderdome_tasks.
        p = OUT / f"patched_{name}.sh"
        r = sh(["python3", "/tmp/patch_eval.py", str(gen[-1]), str(p), str(PY)])
        if r.returncode != 0:
            print(f"{name}: PATCH FAILED {r.stdout.strip()}", flush=True)
            continue
        j = sh(["sbatch", "--qos=priority-discovery", "--partition=h200",
                "--time=12:00:00", "--parsable", str(p)])
        jid = j.stdout.strip().split(";")[0]
        print(f"{name}: {jid if jid.isdigit() else j.stderr.strip()[:100]}", flush=True)
        if jid.isdigit():
            (OUT / f"{name}.jid").write_text(jid)


if __name__ == "__main__":
    sys.exit(main())
