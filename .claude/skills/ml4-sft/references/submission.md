# MINT SFT submission

Guide: Notion **"Workstream contributor guide"**, `843bbdaa-7d3e-476d-bca0-e058fbdb4964`
(MINT - Model Integration team / Mint Cycles / MINT Recipe submissions - SFT). Re-read it each
cycle; it changes.

## The checklist (verbatim)

### Dataset filtering, registration, and validation
- [ ] registered your raw / initial dataset;
- [ ] optionally run mixture validation on the raw dataset or a small temporary recipe for early feedback;
- [ ] checked tokenizer-v16 compatibility if your data uses websearch, references, or tool results;
- [ ] run required Data Hunter checks and registered the filtered dataset key;
- [ ] eyeballed kept and trashed samples;
- [ ] run obvious Data Hunter judge filtering and registered the filtered dataset key;
- [ ] eyeballed kept and trashed samples;
- [ ] decided which final filtered dataset key(s) should be submitted;
- [ ] added only the final dataset key(s) to `recipe_staging.py`;
- [ ] updated the changelog above your recipe update in `recipe_staging.py`;
- [ ] run final mixture validation on the submitted recipe change and saved `report.html`;

### Dataset SFT ablation
- [ ] run an SFT ablation or provided an accepted fallback;
- [ ] checked target workstream evals and important global evals;

### Submission PR
- [ ] opened a PR with all required links and evidence.
- [ ] asked for a review on `#mint-submissions-sft`

Eyeballing kept/trashed samples is the submitter's responsibility. The guide has an escape hatch:
*"If you believe obvious judge filtering hurts your data, say so explicitly and provide examples."*

## Deadlines

Freezes are announced in **#llm-model-integration-fyi** (`C09FB7B0T70`) and live only in Slack —
not in Notion. Cadence "at least once a month"; late submissions explicitly not accepted. The
15 Sep 2026 freeze ran noon internal review / soft 17:00 / hard midnight. Sharing the PR counts;
it need not be merged.

## What the PR carries

Keep it to recipe + ablation configs + report. Move tooling to a separate branch/PR.
The 2026-09 submission (PR #34338) was 15 files:

```
mistral/conf_store/model_integration/sft/recipe_staging.py        the only mixture change
mistral/conf_store/experiments/base.py                            ConfStore keys
mistral/conf_store/experiments/sft/recipe_260908_karl_us_mix_ablation.py
sweeps/vpfister/karl_us_mix/*.yaml                                one per arm
scratch/vincent.pfister/mint_sft/SUBMISSION.md
scratch/vincent.pfister/mint_sft/APPENDIX.md                      exploratory arms
scratch/vincent.pfister/mint_sft/report.html                      mixture validation
scratch/vincent.pfister/mint_sft/{fab_main,fab_all_arms,nonreg_bars}.png
```

Explicitly **removed** before opening: the local-only `consolidation_qos` patch
(`packages/inference/src/inference/args.py`,
`packages/thunderdome_tasks/.../scheduling/{eval_utils,serve_and_eval}.py`) and the
`deprecated_fields.py` mixture-validation fix. Local-only patches must not reach main, **including
via sweep YAMLs** — a YAML referencing `consolidation_qos` would not parse against main.

Template for `SUBMISSION.md`: `scratch/vincent.pfister/mint_sft/SUBMISSION.md` on
`origin/vincent.pfister/mint-sft-tooling`. Structure that worked:

1. **What we are submitting** — a removed/added table of dataset keys with epoch weights.
2. **The judge pass** — samples / judged / masked / discarded, and which judge preset and why.
3. **The eval we track** — name it explicitly (FABv11 = `vals_finance_agent_v2`, fixed variant
   `_mk2`), judge, question count, metrics reported.
4. **"Read this before the numbers: the eval instrument changed"** — any harness change goes
   **up front**, not in the caveats.
5. **Ablation design** — the four configurations with the internal→external name mapping stated
   once, plus every deviation from the guide's preferred design declared explicitly.
6. **Results at matched token budget** — with the measured uncertainty and what counts as a gap.
7. **Non-regression** on `mint_sft_main`.
8. **Caveats and accepted risks.**
9. **Artifacts** — recipe change, `report.html`, run dirs, sweeps, appendix.

Two deviations worth declaring when they apply:

- The guide asks for *baseline vs baseline + your data*. A **replacement** makes the meaningful
  comparison **old vs new**; the rehearsal-only control is what makes that rigorous. Say so.
- The guide's preferred ablation is full-mixture. A **tail-patch from an end-of-SFT checkpoint is
  the explicit fallback**: *"weaker evidence than a full-mixture ablation. MINT may ask for more
  evidence if the data is risky or the signal is ambiguous."*

## Naming: external vs internal

| external | internal |
|---|---|
| **initial** | the shared init checkpoint |
| **baseline** | arm Z, rehearsal only |
| **old** | arm A, the recipe being replaced |
| **new** | arm F, the submitted data |

Internal arm letters belong in exactly two places: one mapping line in `SUBMISSION.md` and the
mapping table in `APPENDIX.md`. A reviewer reading "arm_z" guessed it meant "baseline with the old
karl finance sources" — that is arm A. Anywhere else, use the external names.

## Review

Post the PR in **#mint-submissions-sft** (`C0BJB8W4L80`) and ask for review. Reviewers ask for:
no regressions across other workstreams (standing requirement, every submission), an ETA for the
experiment plus evals, and the specific eval categories they care about — in Sep 2026 that was
`mint_sft_main`, `finance`, and `artificial_analysis_index_4_1_1`.

`gh` cannot attach files; drag `report.html` into the GitHub editor.

**Never regenerate a PR description wholesale** — Vincent hand-edits it. Read it back
(`gh pr view <n> --json body -q .body`), patch exact anchored strings, assert each anchor matched.

## Notion

Mirror the outcome on the Discovery Finance page for the cycle (2026-09:
"FinanceQA: SFT ablation Sep 2026", `3d56ba59-a7fe-815b-a0c0-f56d5afe0c23`, under Discovery
Finance `3186ba59-a7fe-80e7-9350-d9db12edf5bb`).

## Reporting to Vincent

Progress goes to Slack **#vp-model-train** (`C0B667J12FM`, private). Standing authorisation to
post unattended status updates there. Slack has no tables and no `#` headers — lead with the
point, bold the names/dates/numbers, 1-3 short paragraphs.

Report facts, not hypotheses. A gap is a finding; say "I don't know" rather than inferring. And
re-probe flapping transients (ssh signing, tunnel, push state) at send time rather than relaying a
stale status line.
