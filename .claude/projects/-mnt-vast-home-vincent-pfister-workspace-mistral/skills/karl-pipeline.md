# karl-pipeline

KARL data synthesis pipeline (synthesize → solve → judge → filter → check → export).

## When to activate

When the user wants to run the KARL pipeline, work with KARL data, export SFT/RL traces, run data_hunter checks, or analyze KARL experiment results.

## Branch & Environment

- Branch: `vincent.pfister/karl` — PR [#12602](https://github.com/mistralai/mistral/pull/12602)
- Run with `--extra karl`: `uv run --project zephyr --extra karl -m zephyr.datasets.karl.process ...`
- JupyterLab: `uv run --project zephyr --frozen --extra karl --with jupyterlab jupyter lab <notebook> --ServerApp.token=mistral2026 --no-browser --port=18888 --ServerApp.ip=0.0.0.0`

## Pipeline Stages

1. **synthesize** — generate question candidates from ChromaDB corpus
2. **solve** — run solvers (configurable per-solver `max_steps`, default 15)
3. **judge** — evaluate solver traces against rubrics
4. **filter** — difficulty filter + quality check + dedup
5. **check** — strong-model answer verification (Claude Opus via OpenRouter)
6. **export_traces** — 3 modes: default/full/compressed-steps, thinking support

Config: `KarlConfig` in `config.py`, loaded from `karl.yaml` files per experiment.

## Key Modules

```
zephyr/datasets/karl/
  agent.py          # BaseSearchAgent, AsyncBaseSearchAgent, SolverAgent
  validate.py       # solve + judge orchestration
  filter.py         # difficulty filter + quality check + dedup
  check.py          # strong-model answer verification
  export_traces.py  # 3 export modes, thinking support
  config.py         # KarlConfig dataclass
  reporting/        # unified CLI for eval extraction + charts
```

## Solver Config

```yaml
solvers:
  - model: deepseek-v4-pro
    reasoning_effort: high
    max_steps: 30
  - model: glm-5.1-internal
    reasoning_effort: high
    max_steps: 30
```

- `repeat_original_question: true` — merges question into compressed summary as single user message (avoids user-user sequence)
- Filter quality model uses `synthesize.endpoint` — config must have `synthesize:` section pointing to a valid science endpoint model

## Exploration Seeds

Two methods for generating exploration angles that steer synthesis toward diverse topics:

- **`examples`** (default) — LLM imagines angles from seed benchmark CSV examples. Fast, not corpus-grounded.
- **`corpus`** — samples random pages from ChromaDB, extracts angles from real document excerpts. Better diversity for under-represented sectors.

```yaml
synthesize:
  exploration_seeds:
    seed_method: corpus          # "examples" or "corpus"
    corpus_sample_pages: 300     # pages to sample (corpus mode only)
    batches_per_type: 5
    angles_per_batch: 10
```

Config: `ExplorationSeedsConfig` in `config.py`, `SeedMethod = Literal["examples", "corpus"]`.
Implementation: `_generate_exploration_seeds()` (examples) and `_generate_corpus_seeds()` (corpus) in `synthesize.py`.

## Target-Aware Filtering & Split Mode

`_classify_target_aware()` in `filter.py` splits solvers into reference (strong) and target (model being trained). Three-way classification:
- **RL**: `ref_mean >= ref_min AND target_mean <= target_max` — valid questions the target struggles with
- **SFT**: `ref_mean >= ref_min AND target_mean > target_max` — valid questions the target can solve
- **discard**: `ref_mean < ref_min` — bad/ambiguous questions

### Split mode (`--split`)

Writes `output_rl.jsonl` and `output_sft.jsonl` separately. SFT bucket skips rubric generation (rubrics are only for RL reward functions). Without `--split`, legacy behavior: only RL bucket, writes to `output.jsonl`.

### Cross-experiment dedup (`--dedup-anchors`)

Comma-separated list of output files from previous experiments to use as dedup anchors:
```bash
uv run --project zephyr --frozen --extra karl -m zephyr.datasets.karl.process \
  filter --config experiments/eu_opus_1k/config.yaml \
  --data-dir /mnt/vast/datasets_raw/val_eur/karl_eu_opus_1k \
  --split --workers 8 \
  --dedup-anchors "/path/to/exp1/output_rl.jsonl,/path/to/exp1/output_sft.jsonl"
```

**Important**: `--dedup-anchors` takes a single comma-separated string (Fire doesn't support list args). The SFT bucket also uses the current experiment's RL questions as additional anchors.

### Dry run (`--dry-run`)

Prints split counts per question type without running quality/dedup/rubric (no API calls):
```bash
... filter --config ... --data-dir ... --dry-run
```

### Dashboard

`generate_dashboard.py` — interactive HTML with Plotly charts and threshold sliders.

```bash
uv run --project zephyr --frozen --extra karl python \
  zephyr/datasets/karl/generate_dashboard.py <data_dir> \
  --ref deepseek-v4-pro-thinking-high glm-5.1-internal-thinking-high \
  --target 24b-sft-v15
```

## Thinking Chunks

- `AgentResult` has 4 message lists: `messages`, `full_messages`, `messages_with_thinking`, `full_messages_with_thinking`
- Uses `extract_openai_reasoning` from `mistral_common` + `ThinkChunk.from_openai()`
- `warnings=False` on `model_dump()` for GLM/DeepSeek thinking content (list instead of str)
- Export: `--include-thinking` CLI flag

## Context Compression

- Threshold: 80K chars → `_compress_messages()` keeps last 4 messages + summary
- With `--repeat-original-question`: `[system, "question\n\n[COMPRESSED HISTORY...]", ...tail]`
- Without: `[system, original_question, compressed_summary, ...tail]` (user-user problem)

## SFT Trace Mixer

Creates balanced SFT datasets from multiple sources:
```bash
uv run --project zephyr --extra karl -m zephyr.datasets.karl.mix_traces mix --config mix.yaml
uv run --project zephyr --extra karl -m zephyr.datasets.karl.mix_traces mix-stats --input-file out.jsonl
```

Configurable weights for sources, difficulty buckets, question types.

## Export Tool Validation

`_has_invalid_tool_calls()` filters traces where tool calls don't match `available_tools`. The training data loader (`Conversation` in mistral_common) validates tool names — mismatches cause `InvalidFunctionCallException`.

## Data Hunter

Run from `~/workspace/mistral` (main worktree):
```bash
uv run --project mistral-flyte --frozen python -m mistral_flyte.workflows.data_hunter.hunt
```

Or use the `/data-hunter` skill.

Known false positives:
- Language switch flags: ~90% are intermediate reasoning in English with correct final answer
- conversation_structure flags on compressed-steps: expected (segments start with compressed summary)

## Eval Reporting

```bash
uv run --project zephyr --frozen -m zephyr.datasets.karl.reporting --config eval_sources.yaml
```

Flags: `--format {terminal,markdown,charts,all}`, `--configs`, `--metrics`, `--output-dir`

YAML config reference: `eval_sources_example.yaml`. Key: `metrics` order matters (first = primary with delta column).

## Check Step & Rescue

The check step verifies reference answers for low-pass-rate items using a strong model. When it finds a wrong answer, it corrects it and re-judges all solver results.

### Rescuing discarded items for RL

Items discarded by the difficulty filter (ref < ref_min) may have wrong reference answers, not invalid questions. Run check on these to correct answers and rescue valid-but-hard questions:

```bash
uv run --project zephyr --frozen --extra karl -m zephyr.datasets.karl.process \
  check --config experiments/eu_gpt55_1k/config.yaml \
  --data-dir /mnt/vast/datasets_raw/val_eur/karl_eu_gpt55_1k \
  --threshold 0.20 --workers 4
```

**Rescue criterion**: after correction, if ANY reference solver got it right at least once (not ref_mean >= 0.20). Rationale: hard-but-valid questions are valuable for late-stage RL where the model needs harder signal. Only items where ALL ref solvers score 0 after correction are truly unsolvable.

After rescue, patch corrected answers and generate rubrics using `rescue_rubrics`:
```bash
uv run --project zephyr --frozen --extra karl python \
  -m zephyr.datasets.karl.rescue_rubrics \
  --config experiments/eu_gpt55_1k/config.yaml \
  --data-dir /mnt/vast/datasets_raw/val_eur/karl_eu_gpt55_1k \
  --workers 8
```

This tool: (1) patches corrected answers in existing `output_rl.jsonl` items, (2) generates rubrics for rescued items, (3) appends them. Use `--dry-run` to preview.

**Important**: run `rescue_rubrics` AFTER check, because `output_rl.jsonl` was written by filter BEFORE check corrected answers. Without rescue_rubrics, corrected answers won't propagate to the RL output.

**Files modified by check**: `candidates.jsonl` (checked/corrected flags), `results.jsonl` (re-judged), `validated.jsonl` (recomputed rates). Back up before running.

## 24B Local Solver (vLLM)

Serve the 24B SFT checkpoint for use as a target solver:
```bash
SBATCH_ACCOUNT=ml4_taskforce sbatch --qos=priority-ml4_taskforce \
  zephyr/datasets/karl/experiments/eu_gpt55_1k/serve_24b.sh
```

- **Container**: `gpu_bc0fe89c.sqsh` with frozen code snapshot (main has moved ahead)
- **Code dir**: `/mnt/vast/runs/vincent.pfister/finance_qa_rl_24b_v12c/code/260605_083442`
- **Critical flags**: `--tool-call-parser mistral --enable-auto-tool-choice` (without these, tool calls are plain text)
- **IP**: check output file for `IP:` line, update experiment config before solving
- **Wall time**: 12h on dev QoS — plan solve jobs accordingly
- ChromaDB symlink: do NOT change `.chromadb` symlink while solve is running. For synthesis, use `--chromadb-dir /tmp/...` instead.

## SLURM for KARL

CPU-only jobs (API calls). `dev` or `priority-ml4_taskforce` QoS (needs `SBATCH_ACCOUNT=ml4_taskforce`):
- Env vars not inherited — source `.env` from script with absolute path
- `$(dirname "$0")` resolves to SLURM spool dir, not original script path

## Data Locations

```
# EU corpus & experiments:
/mnt/vast/datasets_raw/val_eur/karl/              # iter 3 (original)
/mnt/vast/datasets_raw/val_eur/karl_eu_glm_1k/    # GLM 1k experiment
/mnt/vast/datasets_raw/val_eur/karl_eu_opus_1k/   # Opus 1k experiment
/mnt/vast/datasets_raw/val_eur/karl_eu_gpt55_1k/  # GPT-5.5 2k experiment (corpus seeds)
/mnt/vast/datasets_raw/val_eur/karl_eu_glm_2k/    # GLM 2k experiment (corpus seeds)

# ChromaDB (single copy, symlinked from all experiments):
/mnt/vast/datasets_raw/val_eur/karl/.chromadb      # 103GB, the canonical copy

# Production SFT datasets:
/mnt/vast/datasets/finance-task-force/reasoning/sft/karl_eu_glm_1k/
  mix_plain.jsonl      # 1,101 traces (GLM only)
  mix_plain_mm.jsonl   # same + multimodal_document: null
/mnt/vast/datasets/finance-task-force/reasoning/sft/karl_eu_combined/
  mix_plain.jsonl      # 1,970 traces (GLM + Opus)
  mix_plain_mm.jsonl   # same + multimodal_document: null

# RL samples (converted from KARL format):
/mnt/vast/datasets/finance-task-force/reasoning/rl/karl_us_391.jsonl
/mnt/vast/datasets/finance-task-force/reasoning/rl/karl_eu_308.jsonl
```

## SFT Ablation Launch

Shrimp-scale SFT ablation with replay:

1. **Prepare traces**: export + mix + data hunter → `filtered.jsonl`
2. **Strip trailing tool messages**: KARL traces end with tool result — strip before registration
3. **Register** (optional, for confstore): place in `/mnt/vast/datasets/finetuning/instruct/one_off/<name>/raw.jsonl`, process with `instruct_default_all_langs_one_off`
4. **Write sweep YAML**: use `instruct:-1` path with raw file paths for both finance data and replay sources
5. **Key replay sources** (by raw path, no confstore needed):
   - Alignment: `kimi_k2p5_oss_all_{no_,}reasoning`
   - Safety: `safety_parlai_jailbreaks_rs_glm5_kimi2p5_v2_no_reasoning`
   - Reasoning: `magistral_sft_kimik25_open_thoughts_3`
   - FC: `fc_parlai_free_tier_regen_last_bot_glm5_nojsonmd_tokv15p_fixed_only_last`
6. **Launch**: `IGNORE_DISK_SPACE=1 SBATCH_ACCOUNT=ml4_taskforce uv run --frozen python -m train sweep ...`

Model config for shrimp (MS4.1): `shrimpstral_mla` with `override_parameters_str: ["moe.expert_capacity_factor,moe.topk_first,attention_type"]`. Do NOT use `multimodal_24B_410M` — wrong architecture.

## KARL → FinanceQAData Conversion

```python
converted = {
    "type": "finance_qa",
    "id": raw["uid"],
    "question": raw["data"]["question"],
    "verification_data": {
        "expected_answer": raw["data"]["expected_answer"],
        "rubric": [
            {"criteria": r["criteria"], "weight": 1.0, "operator": r["operator"]}
            for r in raw["data"]["rubric"]
        ],
    },
}
```
