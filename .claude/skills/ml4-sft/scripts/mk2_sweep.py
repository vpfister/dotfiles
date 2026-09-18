"""Re-run FAB on every ablation checkpoint with the mk2 scaffold.

All 35 checkpoints live only on S3 — keep_last=1 pruned every local consolidated copy — so
each eval reads its checkpoint straight from the bucket.

Everything runs from ONE checkout (mk2 @ 907a14c0d13) so the 35 results are mutually
comparable. They are NOT comparable to our historical v2 numbers: those came from a branch
571 commits behind, and mk2 additionally swaps the retrieval backend and raises the open_url
cap. Treat the new set as a fresh ablation, not a correction of the old one.

Two things the generated scripts always get wrong, both patched here:
  - they hard-code /mnt/vast/envs/login/mistral_login_*/bin/python, which lacks
    thunderdome_tasks and is 3.10 (SyntaxError on PEP 695 generics)
  - they inherit none of the env the job needs (API key, OIDC S3 creds, locale, ulimit)

Usage:  mk2_sweep.py launch [N]   submit N checkpoints (default all)
        mk2_sweep.py status       progress table
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

W = Path("/mnt/vast/home/vincent.pfister/workspace/mistral_fabv3_pinned")
PY = W / ".venv/bin/python"
OUT = Path("/mnt/vast/runs/vincent.pfister/fab_mk2_rerun")
TOK = "/mnt/vast/tokenizers/v16_none_high_response_format.tekken_mm.json"
TASK = "vals_finance_agent_v2_mk2[judge_model=kimi-k2.6-eval-judge-only]"
# shrimpstral_fp8_orchestral (262,144 ctx), NOT classic (131,072). mk2 raises the
# open_url cap to 500k, so observations overflow the classic context: the first attempt
# logged 6,008 MaxPendingTokensError in 15 min (149,790 pending vs 131,072 max) and
# produced 14 responses. Orchestral is also the right group for an agentic task.
S3 = "s3://consolidated-checkpoints/bar/vincent.pfister"
FAB = "results/vals_finance_agent_v2_mk2/default"
N_EXPECT = 200

# arm -> (run dir name, run subdir, [checkpoint steps])
ARMS = {
    "A": ("260908_karl_us_mix_ablation", "260908_karl_us_mix_ablation_run000__data_0",
          [148, 296, 444, 592, 722]),
    "B": ("260908_karl_us_mix_ablation", "260908_karl_us_mix_ablation_run001__data_1",
          [144, 288, 432, 576, 717]),
    "C": ("260909_karl_us_v1b_arm_c", "260909_karl_us_v1b_arm_c_run000",
          [148, 296, 444, 592, 722]),
    "D": ("260911_karl_eu_v1b_arm_d", "260911_karl_eu_v1b_arm_d_run000",
          [136, 272, 408, 544, 661]),
    "E": ("260911_karl_blast_only_arm_e", "260911_karl_blast_only_arm_e_run000",
          [136, 272, 408, 544, 662]),
    "F": ("260912_karl_blast_3ep_arm_f", "260912_karl_blast_3ep_arm_f_run000",
          [232, 464, 696, 928, 1159]),
    "Z": ("260912_rehearsal_only_arm_z", "260912_rehearsal_only_arm_z_run000",
          [232, 464, 696, 928, 1147]),
    # The shared init every arm resumes from: the step-0 baseline. Lives under ala/mint_sft,
    # not our bar/vincent.pfister prefix, so ckpt_uri special-cases it.
    "I": ("260901_shrimpy_mid260623_sft260826_code",
          "260901_shrimpy_mid260623_sft260826_code_run000", [45374]),
    # Same checkpoint as I, evaluated again. The spread across I/I2/I3 is our uncertainty
    # estimate: same eval, same judge, same 200 questions, so it captures the variability
    # that actually applies to these numbers.
    "I2": ("260901_shrimpy_mid260623_sft260826_code",
           "260901_shrimpy_mid260623_sft260826_code_run000", [45374]),
    "I3": ("260901_shrimpy_mid260623_sft260826_code",
           "260901_shrimpy_mid260623_sft260826_code_run000", [45374]),
}
INIT_S3 = "s3://consolidated-checkpoints/ala/mint_sft"

ENV = (
    "\n. /etc/shell-config/shell-config.sh >/dev/null 2>&1\n"
    "export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8\n"
    "ulimit -n 1048576\n"
)


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def tag(arm: str, step: int) -> str:
    return f"{arm}_{step:08d}"


def outdir(arm: str, step: int) -> Path:
    return OUT / tag(arm, step)


def ckpt_uri(arm: str, step: int) -> str:
    run, sub, _ = ARMS[arm]
    root = INIT_S3 if arm.startswith("I") else S3
    return f"{root}/{run}/{sub}/checkpoints/checkpoint_{step:08d}/consolidated"


def patch(src: Path, dst: Path) -> bool:
    text = re.sub(r"/mnt/vast/envs/login/mistral_login_[^/]*/bin/python", str(PY), src.read_text())
    lines = text.splitlines(True)
    if not any("shell-config.sh" in ln for ln in lines):
        i = max(i for i, ln in enumerate(lines) if ln.startswith("#SBATCH")) + 1
        lines.insert(i, ENV)
    dst.write_text("".join(lines))
    return "envs/login" not in dst.read_text()


def launch_one(arm: str, step: int) -> str:
    d = outdir(arm, step)
    d.mkdir(parents=True, exist_ok=True)
    if (d / "evals.json").exists():
        return "already has evals.json"

    # The launcher writes a submission script then submits it with the wrong interpreter.
    # Let it write, ignore its failed submit, then patch and submit ourselves.
    sh(
        [
            str(PY), "-m", "thunderdome.run", "slurm_serve_and_eval",
            "--serving_config", "shrimpstral_fp8_orchestral",
            "--serving_config.model.runai_s3_backend", "coreweave",
            "--serving_config.slurm.qos", "priority-discovery",
            "--serving_config.slurm.partition", "h200",
            "--paths.ckpt_dir", ckpt_uri(arm, step),
            "--paths.tokenizer", TOK,
            "--paths.output_dir", str(d),
            "--tasks_str", TASK,
        ],
        cwd=W,
    )
    gen = sorted((d / "jobs").glob("serve_and_evaluate_submission_*.sh"))
    if not gen:
        return "NO SCRIPT GENERATED"
    p = OUT / f"patched_{tag(arm, step)}.sh"
    if not patch(gen[-1], p):
        return "PATCH FAILED"
    r = sh(["sbatch", "--qos=priority-discovery", "--partition=h200",
            "--time=08:00:00", "--parsable", str(p)])
    jid = r.stdout.strip().split(";")[0]
    if not jid.isdigit():
        return f"SUBMIT FAILED {r.stderr.strip()[:80]}"
    (OUT / f"{tag(arm, step)}.jid").write_text(jid)
    return jid


def status() -> None:
    print(f"{'arm':>4} " + "".join(f"{i:>9}" for i in range(1, 6)))
    for arm, (_, _, steps) in ARMS.items():
        cells = []
        for s in steps:
            d = outdir(arm, s)
            f = d / "evals.json"
            done = False
            if f.exists():
                try:
                    done = any(k.startswith("vals_finance_agent")
                               for k in json.loads(f.read_text()).get("results", {}))
                except Exception:
                    pass
            if done:
                cells.append("scored")
            else:
                rf = d / FAB / "responses.jsonl"
                n = sum(1 for _ in rf.open()) if rf.exists() else 0
                cells.append(f"{n}/200" if n else ("." if (OUT / f"{tag(arm,s)}.jid").exists() else "-"))
        print(f"{arm:>4} " + "".join(f"{c:>9}" for c in cells))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "status":
        status()
    else:
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 999
        n = 0
        for arm, (_, _, steps) in ARMS.items():
            for s in steps:
                if n >= limit:
                    break
                if (OUT / f"{tag(arm, s)}.jid").exists():
                    continue
                print(f"{arm} step {s}: {launch_one(arm, s)}", flush=True)
                n += 1
                time.sleep(3)  # stagger: 35 servers pulling 238GB each from S3 at once
