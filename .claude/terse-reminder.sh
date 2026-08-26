#!/usr/bin/env bash
# Injected into every turn so the "Be terse" rules in ~/.claude/CLAUDE.md stay in recent
# context rather than buried at the top of a long session. Deliberately specific and
# checkable: "be terse" alone gets tuned out, a word budget does not.
# Always exits 0 — a reminder must never block a turn.
cat <<'EOF'
BREVITY CHECK — applies to the reply you are about to write (~/.claude/CLAUDE.md "Be terse"):
- Cut the story: what you tried, what broke, how you got there. The result is the deliverable.
- Keep the constraint: gotchas, non-obvious decisions, why the code is this way.
- Do not restate the diff, or explain what the reader already knows.
- PR body ~200 words. Commit message scales to the change. Comments say what a dev needs in 6 months.
- Human prose (Slack, Notion, email): no dashes as punctuation, no throat-clearing, no padding.
EOF
exit 0
