"""Health monitor for the non-regression evals.

Reports a compact line per poll and, separately, explicit PROBLEM lines. It watches for the
failure modes this lane has actually hit rather than only job exit codes:

  DEAD        job ended TIMEOUT/FAILED/CANCELLED -- a partial generation nobody should score
  EMPTY       job COMPLETED but produced no responses (the 20:45 lock collision looked
              exactly like this: COMPLETED, zero tasks, scoring then reported "10 failed")
  STALLED     RUNNING but total response rows have not moved in STALL_MIN minutes
  UNSCORED    generation COMPLETED with responses, but evals.json still has no results and
              no scoring job is in flight

Read-only: it never cancels or resubmits. Deciding what to do is the operator's call.
"""

import json
import subprocess
import time
from pathlib import Path

OUT = Path("/mnt/vast/runs/vincent.pfister/nonreg_mint_sft_main")
POLL = 300
STALL_MIN = 45
DEAD = ("FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF", "PREEMPTED")


def sh(c):
    return subprocess.run(c, capture_output=True, text=True).stdout


def jstate(jid):
    o = sh(["sacct", "-j", str(jid), "-n", "--format=State", "-X"])
    return o.splitlines()[0].strip() if o.strip() else ""


def rows(d: Path) -> int:
    n = 0
    for f in d.glob("results/*/*/responses.jsonl"):
        try:
            with f.open("rb") as fh:
                n += sum(1 for _ in fh)
        except OSError:
            pass
    return n


def scored(d: Path) -> bool:
    f = d / "evals.json"
    try:
        return bool(json.loads(f.read_text()).get("results"))
    except Exception:
        return False


def main() -> None:
    last: dict[str, tuple[int, float]] = {}
    while True:
        now = time.time()
        problems, live, done = [], 0, 0
        for j in sorted(OUT.glob("*.jid")):
            name = j.stem
            d = OUT / name
            st = jstate(j.read_text().strip())
            r = rows(d)
            ok = scored(d)
            if ok:
                done += 1
                last.pop(name, None)
                continue
            if st.startswith(DEAD):
                problems.append(f"DEAD     {name}: job ended {st}, {r} response rows")
            elif st.startswith("COMPLETED"):
                if r == 0:
                    problems.append(f"EMPTY    {name}: COMPLETED but produced no responses")
                else:
                    sj = OUT / f"{name}.score_jid"
                    sst = jstate(sj.read_text().strip()) if sj.exists() else ""
                    if not sst or sst.startswith(DEAD) or sst.startswith("COMPLETED"):
                        problems.append(
                            f"UNSCORED {name}: generation done ({r} rows), no scoring in flight"
                        )
            else:
                live += 1
                prev = last.get(name)
                if prev and prev[0] == r and (now - prev[1]) > STALL_MIN * 60:
                    mins = int((now - prev[1]) / 60)
                    problems.append(f"STALLED  {name}: {r} rows unchanged for {mins} min")
                elif not prev or prev[0] != r:
                    last[name] = (r, now)
        ts = time.strftime("%H:%M:%S")
        print(f"{ts} scored={done} running={live} problems={len(problems)}", flush=True)
        for p in problems:
            print(f"{ts} {p}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
