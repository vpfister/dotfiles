# Source from shell startup files; the credential stays in the untracked ~/.env.
if [ -z "${LITELLM_API_KEY:-}" ] && [ -r "$HOME/.env" ]; then
  LITELLM_API_KEY="$(python3 - <<'PY'
from pathlib import Path
import re
import shlex

for line in (Path.home() / ".env").read_text().splitlines():
    match = re.match(r"^\s*(?:export\s+)?LITELLM_API_KEY\s*=\s*(.*)$", line)
    if match:
        values = shlex.split(match[1], comments=True)
        if len(values) == 1:
            print(values[0])
            break
PY
)"
fi
export LITELLM_API_KEY
export ANTHROPIC_FOUNDRY_API_KEY="${LITELLM_API_KEY:-}"
export ANTHROPIC_FOUNDRY_BASE_URL='https://internal-ai-gateway.mistralai.com'
export CLAUDE_CODE_USE_FOUNDRY=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
export ENABLE_TOOL_SEARCH=true
export ANTHROPIC_MODEL='vertex_ai/claude-opus-5-5'
export ANTHROPIC_DEFAULT_OPUS_MODEL='vertex_ai/claude-opus-5-5'
export ANTHROPIC_DEFAULT_SONNET_MODEL='azure_ai/claude-sonnet-5-5'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='azure_ai/claude-haiku-5-5'
export ANTHROPIC_SMALL_FAST_MODEL='azure_ai/claude-haiku-5-5'
unset CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS USE_TOOL_SEARCH ANTHROPIC_CUSTOM_HEADERS
