#!/usr/bin/env python3
"""PreToolUse guard for `gh api` writes.

`gh api:*` is allowed so reads run unprompted. This hook forces a prompt for
any `gh api` write except routine PR-thread work (comment replies, thread
resolution, labels, PR title/body, ready-for-review, CI reruns). Merge
endpoints are also `ask` rules in settings.json; a hook "allow" cannot
override those, so this hook only ever returns "ask" or nothing.
"""

import json
import re
import sys

WRITE_FLAG = re.compile(r"(?:^|\s)(?:-X|--method|-f|-F|--field|--raw-field|--input)(?:[\s=]|$)")
READ_METHOD = re.compile(r"(?:-X|--method)[\s=]*['\"]?GET\b", re.I)
MERGE = re.compile(r"/merge\b|mergePullRequest|PullRequestAutoMerge|enqueuePullRequest|merge-queue", re.I)

ALLOWED_REST = [
    r"pulls/\d+/comments/\d+/replies",
    r"pulls/comments/\d+(?:/reactions)?\b",
    r"issues/\d+/comments\b",
    r"issues/comments/\d+(?:/reactions)?\b",
    r"issues/\d+/labels\b",
    r"pulls/\d+(?=['\"\s]|$)",
    r"actions/runs/\d+/(?:rerun|rerun-failed-jobs)\b",
    r"actions/jobs/\d+/rerun\b",
    r"check-runs/\d+/rerequest\b",
    r"check-suites/\d+/rerequest\b",
]
ALLOWED_MUTATIONS = {
    "resolveReviewThread",
    "unresolveReviewThread",
    "addPullRequestReviewThreadReply",
    "addComment",
    "updateIssueComment",
    "updatePullRequestReviewComment",
    "updatePullRequest",
    "markPullRequestReadyForReview",
    "addLabelsToLabelable",
    "removeLabelsFromLabelable",
    "addReaction",
}
GRAPHQL_KEYWORDS = {"mutation", "query"}


def needs_prompt(segment: str) -> bool:
    if MERGE.search(segment):
        return True
    if "--input" in segment or re.search(r"query=@", segment):
        return True  # body not visible on the command line
    if re.match(r"gh api\s+graphql\b", segment):
        if "mutation" not in segment:
            return False
        fields = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", segment)) - GRAPHQL_KEYWORDS
        return not fields or not fields <= ALLOWED_MUTATIONS
    if not WRITE_FLAG.search(segment) or READ_METHOD.search(segment):
        return False
    return not any(re.search(p, segment) for p in ALLOWED_REST)


def main() -> None:
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    segments = ["gh api" + s for s in command.split("gh api")[1:]]
    if any(needs_prompt(s) for s in segments):
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "gh api write outside routine PR-thread endpoints",
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
