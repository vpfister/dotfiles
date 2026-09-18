"""What Jonas asked for, versus what we have scored.

Resolves the three eval categories he named from the registry, then diffs against the
task names already present in our non-regression output dirs.
"""

import glob
import json
import os
import re
from collections import defaultdict

from mistral.conf_store.eval.prod import get_evals_registry

WANT = ("mint_sft_main", "finance", "artificial_analysis_index_4_1_1")

by_cat: dict[str, list[str]] = defaultdict(list)
for e in get_evals_registry():
    cats = [str(c).split(".")[-1] for c in (getattr(e, "eval_categories", None) or [])]
    ws = getattr(e, "workstream", None)
    if ws is not None:
        cats.append(str(ws).split(".")[-1])
    for c in set(cats):
        by_cat[c].append(getattr(e, "name", None) or str(e))

for c in WANT:
    print(f"{c}: {len(by_cat.get(c, []))} entries")

# What we already have, by bare task name.
ROOT = "/mnt/vast/runs/vincent.pfister/nonreg_mint_sft_main"
have: set[str] = set()
for f in glob.glob(f"{ROOT}/*/evals.json"):
    try:
        for k in json.load(open(f)).get("results", {}):
            have.add(re.sub(r"\[.*", "", k))
    except Exception:
        pass
print(f"\nscored task names in our dirs: {len(have)}")
for c in WANT:
    names = {re.sub(r"\[.*", "", n) for n in by_cat.get(c, [])}
    missing = sorted(names - have)
    print(f"\n--- {c}: {len(names) - len(missing)}/{len(names)} covered")
    for m in missing[:25]:
        print(f"    MISSING {m}")
