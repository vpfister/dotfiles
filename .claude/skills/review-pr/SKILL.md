---
name: review-pr
description: Review someone else's pull request and post the feedback — propose small self-contained changes as one-click GitHub suggestion blocks rather than prose, batched into a single review. Use when commenting on, reviewing, or suggesting changes to a PR you do not own.
---

# Reviewing someone else's PR

For preparing your *own* PR for review, use `self-review` instead.

## The rule

**If a change is small and self-contained, post it as an applicable `suggestion` block.**
The author clicks Apply. Prose ("add `foo=BAR` after line 181") makes them retype it,
re-derive the line number, and risk a transcription error.

Prose is right when the change is not mechanical: a design question, something needing a
decision, or an edit spanning files. Do not dress those as suggestions — a suggestion says
"this is correct, apply it", so only use it when you believe that.

## Mechanics

```jsonc
// POST /repos/{owner}/{repo}/pulls/{n}/comments
{
  "commit_id": "<PR head sha>",              // gh pr view N --json headRefOid
  "path": "path/to/file.py",
  "start_line": 178, "line": 182,            // omit start_line for a single line
  "side": "RIGHT", "start_side": "RIGHT",
  "body": "why this change\n\n```suggestion\n<replacement for the WHOLE range>\n```"
}
```

- **The block replaces exactly the commented range.** A pure insertion anchored on one line
  means repeating that line plus the new one.
- **Prefer a range covering the whole call or block**, even when one line changes. The
  author sees a coherent unit instead of a fragment.
- Anchor lines must lie **inside a diff hunk**. Context lines within a hunk are fine.
- **Batch into one review** (`POST .../reviews` with a `comments[]` array and
  `"event": "COMMENT"`) so the author gets a single notification, with the summary and any
  table in the review `body`.
- Suggestions bind to `commit_id`. Once the author pushes, they go outdated and the Apply
  button disappears, so post close to when they will be read.

## Before posting

- **Verify the claim against the code**, especially when relaying a bot or another person's
  report. Read the file, and reproduce the failure if one is claimed. Posting a wrong
  suggestion costs the author more than saying nothing.
- **Check what the config actually resolves to**, not what it appears to say. A preset or
  factory can invert the obvious reading, and a `None` default may not mean "off".
- Resolve a `…#diff-<hash>` permalink to a path with `sha256(path)` over
  `gh pr view N --json files --jq '.files[].path'`.
- Rehearse unfamiliar formatting on a PR of your own and delete it:
  `gh api -X DELETE repos/{owner}/{repo}/pulls/comments/{id}`.

## Tone

State the constraint and the consequence, not the process that found it. Say which
suggestions you would actually take and which are optional — a reviewer who flags six things
without ranking them has moved the triage work onto the author.

Replying to a finding on your own PR, the same rule cuts two habits:

- **No self-narration.** "so my assumption was wrong", "I had thought X" — your internal
  history is not the reviewer's business. Say what the code does now.
- **No praise formula.** "Good catch" is filler. If a finding reproduced, say it reproduced
  and how; that is the actual acknowledgement.

Say what changed and what you verified. Anything else gets edited out.
