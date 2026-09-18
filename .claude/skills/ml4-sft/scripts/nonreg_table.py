"""Emit mint_sft_main non-regression as one headline metric per task.

Columns use the submission's external names: initial / baseline / new.
Writes markdown to stdout so it can be pasted straight into SUBMISSION.md.
"""

import glob
import json
import os
import re
import sys

ROOT = "/mnt/vast/runs/vincent.pfister/nonreg_mint_sft_main"
# new is reported at two epoch counts: ~2ep (step 696 = 1.80 epochs, the last checkpoint
# below the submitted 2ep) and the 3ep final the first pass used.
# baseline and new are each reported at both epoch counts. Collapsing the two baselines
# into one column silently let whichever scored last win, which changed published numbers.
LABEL = {
    "INIT": "initial",
    "baseline_2ep": "base2",
    "Z_final": "base3",
    "new_2ep": "new2",
    "F_final": "new3",
}
COLS = ("initial", "base2", "new2", "base3", "new3")
HEADER = ("initial", "baseline (~2ep)", "new (~2ep)", "baseline (3ep)", "new (3ep)")

# One headline metric per task family. First match wins; anything unmatched falls back to
# the shortest plain metric name, which is reliably the aggregate rather than a @k variant.
PREFERRED = (
    "browsecomp_score", "aime_maj_vote_match", "collie_match", "rubric_score_MeanScore",
    "surge_bench_score", "verbosity_score", "sysbench_score", "omniscience_score",
    "arxivmath_match", "swebench_resolved", "octobench_score", "tau3_reward",
    "gdpval_pairwise_weighted_average", "jobbench_score", "apex_score", "cybergym_score",
    "entropy",
)
SKIP_PREFIX = ("length_", "reasoning_", "engine_", "by_tag")
SKIP_SUBSTR = ("NumTotal", "NumNaN", "num_datapoints", "duration", "_n_gram", "avg_turns",
               "avg_discard", "errors", "pct_submitted")


def headline(metrics: dict) -> str | None:
    names = [
        m for m, v in metrics.items()
        if isinstance(v, (int, float))
        and not m.startswith(SKIP_PREFIX)
        and not any(s in m for s in SKIP_SUBSTR)
    ]
    if not names:
        return None
    for p in PREFERRED:
        if p in names:
            return p
    # Drop @k / gap variants before falling back.
    plain = [m for m in names if not re.search(r"@\d+|gap", m)] or names
    return min(plain, key=len)


data: dict[str, dict[str, float]] = {}
metric_of: dict[str, str] = {}
for f in sorted(glob.glob(f"{ROOT}/*/evals.json")):
    name = os.path.basename(os.path.dirname(f))
    label = LABEL.get(name.rsplit("_", 1)[0])
    if label is None:
        continue
    try:
        res = json.load(open(f)).get("results", {})
    except Exception:
        continue
    for task, metrics in res.items():
        m = headline(metrics)
        if m is None:
            continue
        short = re.sub(r"\[.*?\]", "", task)
        reasoning = "reasoning_effort=high" in task
        key = f"{short}{' (high)' if reasoning else ''}"
        metric_of[key] = m
        data.setdefault(key, {})[label] = metrics[m]

if "--json" in sys.argv:
    json.dump({"data": data, "metric_of": metric_of, "cols": list(COLS),
               "header": list(HEADER)}, sys.stdout, ensure_ascii=False)
    raise SystemExit

print("| eval | metric | " + " | ".join(HEADER) + " |")
print("|" + "---|" * (len(HEADER) + 2))
for k in sorted(data):
    r = data[k]
    cells = " | ".join(f"{r[c]:.4f}" if c in r else "—" for c in COLS)
    print(f"| {k} | `{metric_of[k]}` | {cells} |")
print(f"\n{len(data)} tasks scored so far.")
