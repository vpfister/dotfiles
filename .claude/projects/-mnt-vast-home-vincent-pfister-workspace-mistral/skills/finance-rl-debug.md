# finance-rl-debug

Analyze RL training episodes, diagnose quality issues, and investigate failure patterns.

## When to activate

When the user wants to understand why a training run has low pass rate, investigate episode failures, check tool call patterns, or eyeball generation data.

## Generation log structure

Episodes are in `<run_dir>/generation_log_dir/<batch>.jsonl`. Each line:
```
{"src": "submixture/dataset_name", "group": {"['default', None]": [episodes...]}}
```

Each episode:
```
episode.conversations[0].messages  — list of messages (system, user, assistant, tool)
episode.conversations[0].meta      — {"verifier": "function_check_verifier", ...}  (dummy, ignore)
last_assistant_message.score        — the actual reward (-1.1 = fault, 0.0 = wrong, >0 = correct)
```

## Score distribution analysis

```python
import json
from collections import Counter

scores = []
with open("<run_dir>/generation_log_dir/<batch>.jsonl") as f:
    for line in f:
        data = json.loads(line)
        for gk, episodes in data["group"].items():
            for ep in episodes:
                for conv in ep.get("conversations", []):
                    for m in reversed(conv.get("messages", [])):
                        if m.get("role") == "assistant":
                            score = m.get("score")
                            if score is not None:
                                scores.append(score)
                            break

fault = sum(1 for s in scores if s <= -1.0)
zero = sum(1 for s in scores if s == 0.0)
pos = sum(1 for s in scores if s > 0)
print(f"Fault: {fault} ({100*fault/len(scores):.1f}%)")
print(f"Zero: {zero} ({100*zero/len(scores):.1f}%)")
print(f"Positive: {pos} ({100*pos/len(scores):.1f}%)")
```

## Common failure patterns

### Malformed tool calls (score -1.1)
The model outputs tool names as plain text (`"edgar_search"`, `"submit"`) instead of proper tool calls. Caused by:
- Base model not SFT'd on tool-use data
- High temperature (1.0) degrading format compliance
- `early_stop_on_format_error: true` killing these instantly

**Diagnosis**: check 3-message episodes with no tool calls:
```python
# Count plain-text tool name outputs
for m in msgs:
    if m.get("role") == "assistant":
        content = m.get("content", "")
        if isinstance(content, str) and content.strip() in ("edgar_search", "submit", "submit_final_result"):
            plain_text_count += 1
```

### Submit spam (score -1.1 or 0.0)
The model calls `submit_final_result` repeatedly with garbage like "Waiting...", "Working on it...", "HODL". First submit ends the episode.

### Science API failures
`ExternalLLMClient` retries exhausted → runner actor crashes → episode faulted. Check model availability:
```bash
source .env && curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
  -H "x-api-key: $MISTRAL_API_KEY" -H "x-private-access: $SCIENCE_PRIVATE_ACCESS_ENV_VAR" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-k2.6-internal","messages":[{"role":"user","content":"test"}],"max_tokens":5}' \
  https://quota-science-api-prod-swe.mistralai.com/v1/chat/completions
```

### Verifier meta is misleading
`conv.meta.verifier` always shows `"function_check_verifier"` — this is a dummy label hardcoded in `episode.py:414`. The actual reward comes from the verifier called during the episode. Look at `last_assistant_message.score` for the real reward.

## EDGAR API cache check

```bash
# Count cached entries
find /mnt/vast/datasets/finance-task-force/cache/edgar_search/ -name "*.json" -type f | wc -l

# Check if new entries are being added
find /mnt/vast/datasets/finance-task-force/cache/edgar_search/ -name "*.json" -newer <run_dir>/sweep.yaml | wc -l
```

## Comparing runs

To compare episode quality between two runs (e.g. v4 with malformed tool calls vs Philippe's clean run):
```python
# Check Philippe's reference run
gen_log = "/mnt/vast/runs/philippe.pinel/train_hec_finance_ms41_must_have_g32_v3/.../generation_log_dir/000.jsonl"
# Same analysis as above — compare fault/zero/positive distribution
```

## Eyeballing data

For JSONL files with conversations, always suggest:
```
eye /absolute/path/to/file.jsonl
```
