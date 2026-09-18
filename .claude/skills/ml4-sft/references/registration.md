# Dataset registration, DataHunter, and the obvious-issues judge

Everything from a cleaned JSONL to the key you put in `recipe_staging.py`.

## 0. Gate the file before registering

Two independent gates. Registration validates with `Conversation`; **training** validates with
the dataloader's set arithmetic. Neither replaces the other.

```bash
<venv>/bin/python /mnt/vast/shared/vincent.pfister/ml4-taskforce/karl/scripts/check_sft_records.py FILE.jsonl
```

- `Conversation.model_validate` **fails open** since #30159: an unresolvable `$ref` in a tool
  schema silently disables the tool-call check
  (`mistral_common/protocol/instruct/response_validation.py:110-112`, `parsed_arguments = None`).
  A dangling `$defs` is the normal result of serialising a nested Pydantic model, so assume
  other envs are affected.
- The dataloader rule is `set(required) <= args.keys() <= all_params`
  (`forge/packages/components/dataloader-mfi/src/dataloader_mfi/samples/utils/instruct.py:126-129`)
  and rejects the **whole conversation** for one bad call — including error-recovery traces.
- `Conversation.model_validate` **mutates the dict in place**. Validate a copy:
  `Conversation.model_validate({**rec, "messages": [dict(m) for m in msgs]})`.

Cleaning script (drops, never repairs): `scratch/vincent.pfister/mint_sft/s7f_clean_ablation_arms.py`.
It exits 1 with a WRONG-SOURCE warning if the file advertises `answer_question` or is majority
tool-ending — **a defect in most of a file is a provenance signal, not a finding**.

Think-chunk contract, asserted before writing any dataset: **exactly one ThinkChunk, at index 0.**
`_extract_think_chunk` (`packages/shared_public/src/shared_public/message.py`) strips only one and
only at index 0, so `[text, think]` and `[think, text, think]` leak `[THINK]…[/THINK]` into the
judged answer.

## 1. Register (Flyte)

```bash
cd ~/workspace/mistral_mint_sft
uv run --frozen --project mistral-flyte python -m run \
  scratch/vincent.pfister/mint_sft/register_karl_us_sft_v1b.yaml
```

Config shape (see the branch `origin/vincent.pfister/mint-sft-tooling` for full files):

```yaml
task: mistral_flyte.workflows.dataset_registration.workflow.dataset_registration_task
remote: true
args:
  input_path: /mnt/vast/shared/.../karl_us_sft_v1b_allpass_260909.jsonl
  original_src_path: /mnt/vast/shared/.../sft_v1b_us_allpass.jsonl
  migrate_to_unified_resources: "yes"      # StrEnum — MUST be quoted or YAML reads it as a bool
  operation_config:
    preset: passthrough
  postprocess_config:                      # REQUIRED, see below
    dedup: none
    n_repeats: 1
    seed: 42
  registry_config:
    dataset_type: instruct
    dataset_name: karl_us_sft_v1b
    domain: finetuning
    registry_name: one_off
    key: "260909_glm53blast_allpass"       # quote it — a numeric key parses as int
    comment: >-
      ...
    overwrite: false
```

| failure | cause | fix |
|---|---|---|
| `AssertionError: Line count mismatch: output has 12305 lines but expected -4` | `postprocess_config` omitted. With `preset: passthrough`, `total_lines_read` stays 0, so `0 - n_discarded` is negative | always set `postprocess_config` |
| dataset trains all-of-one-half-then-the-other | same: `dedupe_shuffle_repeat_task` runs **only** when `postprocess_config` is set. It is the shuffle | same. Do not pre-shuffle the input |
| `1 validation error … registry_config.key … Input should be a valid string` | bare numeric `key:` | quote it |
| `PermissionError: [Errno 13]` | writing into another user's `/mnt/vast/datasets/finetuning/instruct/one_off/<name>/` tree | register under your own `dataset_name`; do not chmod someone else's tree |
| `check_auth` opens a device-flow URL | `check_auth.py` hard-codes `.flyte/config.yaml` (DeviceFlow); the real path uses `config.api.yaml` when `FLYTE_CLIENT_SECRET` is set | **ignore it**; just run `python -m run <yaml>` |

Poll and read logs (bare `flyte` fails with `Initialization failed. Pass remote config for CLI.`):

```bash
uv run --frozen --project mistral-flyte flyte --config mistral-flyte/.flyte/config.api.yaml get run  <RUN_ID>
uv run --frozen --project mistral-flyte flyte --config mistral-flyte/.flyte/config.api.yaml get logs <RUN_ID>
```
Phases: `ACTION_PHASE_RUNNING` → `ACTION_PHASE_SUCCEEDED` / `_FAILED`.
Run URL: `https://mistral.eu-west-2.unionai.cloud/v2/domain/development/project/flyte-default/runs/<id>`.
Registration takes ~6-14 min.

## 2. DataHunter (checks + `language_switch`)

Required twice over: it is the guide's filtering step, **and** it writes the `data_quality`
registry block without which the mixture is rejected outright:

```
ValueError: The following instruct datasets are missing required data quality registry metadata:
 - one_off-karl_us_sft_v1b-260909_glm53blast_allpass: missing checks=[...16 names...], missing rubrics=['language_switch']
```

Do **not** use `ALLOW_MISSING_DATA_QUALITY_CHECKS=1` — it would also wave through the dataset
under test. If one frozen `_tcfix` rebuild lost a rubric its predecessor had, except **that one
name** in `datasets_not_data_quality_checked_exceptions`.

```bash
uv run --frozen --project mistral-flyte python -m run \
  scratch/vincent.pfister/mint_sft/datahunter_karl_us_v1b.yaml
```

Checks and rubric are copied verbatim from
`mistral-flyte/mistral_flyte/workflows/data_hunter/configs/sft_datahunter_starter_pack.yaml`:
`double_horizontal_rule, infinite_generation_high_recall, plain_text_tool_call_pattern,
conversation_structure, conversation_validation, chinese_characters, malformed_think_chunk,
invalid_references, thinking_must_be_plain_text, understood, tool_schema_repair_loop,
json_mode_validation, red_flag_keyword, conversation_level_red_flag, nsfw, backtracking_in_text`
plus `rubric_names: [language_switch]`. Keep them identical across arms of one ablation or you
confound the comparison with a data-quality difference.

Other keys: `filter_mode: mask_out`, `cache_version: v2`, `parallelism_mode: flat_batches`,
`max_parallelism: 70`, `batch_config.max_lines_per_batch: 50000`, `enable_registration: true`,
`judge.preset: gemma_4_31b_high_reasoning`. Takes ~24-26 min.

Identical filter config hashes to the same suffix — arms B/C/D all got `dh_mask_967e59b6`. That
is expected, not a bug.

`n_judge_skipped_language_switch = <n_samples>` is the **not-triggered** counter
(`evaluate.py:113`), not a failure.

## 3. Obvious-issues mask judge

Separate pass, separate key. Template:
`mistral-flyte/mistral_flyte/workflows/data_hunter/configs/obvious_issues_mask_judge_starter_pack.yaml`.

```yaml
args:
  registry_datasets:
    - one_off-karl_us_sft_v1b-260909_glm53blast_allpass_dh_mask_967e59b6   # ONE per run
  output_dir: /mnt/vast/shared/vincent.pfister/.../data_hunter/260914_obvious_judge_v1b_us_kimi
  cache_version: v2
  enable_registration: true
  filter_mode: mask_out
  parallelism_mode: flat_batches
  checks: []
  short_circuit_judge: false
  rubric_names: [obvious_issues_mask]
  judge:
    preset: kimi_k2_6_high_reasoning
```

**Smoke first, always**: `debug_max_lines: 100` + `enable_registration: false`. Answers "does the
judge error" for ~25 min instead of hours.

### Rules

- **One dataset per run.** Two parallel discovery tasks both call `git config --global` against a
  shared HOME; the loser exits 255 and Flyte reports `1/2 flat dataset discovery tasks failed`
  (`mistral-flyte/mistral_flyte/tasks/dataset_registry.py:126 _configure_git_credentials`).
  That command also puts a GitHub PAT in plaintext in the Flyte logs.
- **Read `n_flagged_judge_error_*` against `n_flagged_*` in `summary.json` before trusting any
  count.** A judge error is treated as a discard. In June this deleted 95.5% of KARL SFT tokens
  (11,959 errors vs 23 real flags) and the residue shipped as `_dh_mask_0f112f61`.
- `filter_mode: mask_out`, not `drop` — a flagged trainable message loses its signal, the
  conversation is kept.
- **Use `judge.preset`, not a manual model config.** `JUDGE_PRESET_EXECUTION_DEFAULTS` is keyed on
  `judge.preset` (`hunt.py:659`), so a manual config inherits **no** fanout tuning and the fanout
  is undefined. A manual config also fails validation unless you supply all four of
  `model_name`, `model_url`, `temperature`, `max_tokens`:
  `Value error, Manual judge config requires model_name, model_url, temperature, and max_tokens.`
  and you must then set `max_concurrent` yourself (32 ≈ 2k global; the preset shape is
  64 batch tasks × 240 = 15,360).

### The gemma outage (2026-09-14) and the kimi fallback

`gemma-4-31b-data-hunter-judge` ran on a **single replica** and returned no response at all under
load — a 24-way concurrent probe got HTTP 000 on all 24. The judge surfaces that as:

```
data_quality.judges.truncate_long_judge_prompts.PromptTokenCountUnavailableError:
Judge tokenizer is unavailable; refusing to send an unverified prompt
```

because it **fails closed** when it cannot get an exact token count. `1536 sub-exceptions` = the
batch size, not 1536 distinct problems.

Fix: `judge.preset: kimi_k2_6_high_reasoning` — the fallback the starter pack names. Slower, a
different deployment, larger context. Switch back once gemma is scaled.

Two dead ends tried first, recorded so they are not retried: repointing `model_name` at
`gemma-4-31b-finance-rl` (same failure — it is provisioned `completion_chat: false`), and lowering
fanout alone (reduced errors 96% but did not eliminate them).

Also note: the **generic** `gemma_4_31b_high_reasoning` preset is capped at 131k client-side; only
the dedicated `gemma_4_31b_data_hunter_judge_high_reasoning` was raised to 262,144 (237,568 prompt
budget) in #32772. Long KARL traces are why the 260909 run errored rather than flagged.

Clean result for reference (US/EU v1b, 2026-09-14): US 11,110 judged 100%, 275 masked (2.5%), 2
discarded, 0 errors. EU 6,348, 194 masked (3.1%), 2 discarded, 0 errors.

## 4. Find the registered key — read it, do not compute it

The post-judge suffix is **not derivable from the config**. `hunt.py` builds it from an
`evaluation_identity.digest(8)`; a local reconstruction produced `dh_mask_590f4175` while the
registry held `dh_mask_798b846a`, and the recipe failed with:

```
AssertionError: Cannot find version registered with key='..._dh_mask_967e59b6_dh_mask_590f4175'
in registry for dataset_name='karl_us_sft_v1b'
```

```bash
cd ~/workspace/mistral_mint_sft
uv run --frozen python -c "
from shared_public.registry import get_registry
r = get_registry('instruct', 'one_off')       # both args are required
raw = r._load_raw()
for n in ('karl_us_sft_v1b', 'karl_eu_sft_v1b'):
    print(n, list(raw.get(n, {})))
"
```

## 5. The registry is a git repo, per cluster

`/mnt/vast/shared/registry` — and BAR's clone does **not** sync automatically. A key registered
from RNO is invisible to a BAR sweep until you pull:

```bash
ssh bar 'export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock; git -C /mnt/vast/shared/registry pull --ff-only'
```

Symptom: `AssertionError: Dataset <name> not found in registry /mnt/vast/shared/registry/instruct/one_off.json`
(`shared_public/registry.py:504`). `DatasetId.from_sweep_str(..., allow_git_pull=False)` means the
code will not self-update. Never hand-edit the shared JSON, never copy the file across clusters.

Registry `n_tokens` is **not comparable across entries** — use `composite_token_count`
(see [ablations.md](ablations.md)).
