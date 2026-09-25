---
name: finance-qa
description: Work on Finance QA RL training, scoring, checkpoint evaluation, and episode debugging in the mistral repository. Use for Finance QA runs, evals, and orchestral environment work.
---

# Finance QA

When available, read [the RNO Finance QA reference](references/finance-qa.md)
for the relevant workflow. It records dated experiment state, so check the
current repository and run configuration before acting. Without that local
reference, inspect `orchestral_package/src/orchestral/envs/finance_qa/` and the
current sweep or eval configuration in the active worktree. Launch from the
worktree containing the environment code, using `uv run --frozen`.
