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

ASSIGNMENT = re.compile(r"(?:^|[\s;&|(])([A-Za-z_]\w*)=('[^']*'|\"[^\"]*\"|[^\s;&|)]+)")
# A numeric id, or a positional parameter in a helper like `reply() { gh api "$R/$1/replies" ...; }`.
# A positional value can't smuggle in a merge: MERGE is checked on the whole command text.
ID = r"(?:\d+|\$\d|\$\{\d\})"
ALLOWED_REST = [
    rf"pulls/{ID}/comments/{ID}/replies",
    rf"pulls/comments/{ID}(?:/reactions)?\b",
    rf"issues/{ID}/comments\b",
    rf"issues/comments/{ID}(?:/reactions)?\b",
    rf"issues/{ID}/labels\b",
    rf"pulls/{ID}(?=['\"\s]|$)",
    rf"actions/runs/{ID}/(?:rerun|rerun-failed-jobs)\b",
    rf"actions/jobs/{ID}/rerun\b",
    rf"check-runs/{ID}/rerequest\b",
    rf"check-suites/{ID}/rerequest\b",
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


def expand_assignments(command: str) -> str:
    """Substitute `NAME=value` assignments made earlier in the same command."""
    for name, value in ASSIGNMENT.findall(command):
        value = value.strip("'\"")
        command = re.sub(rf"\$(?:{name}\b|\{{{name}\}})", lambda _: value, command)
    return command


def main() -> None:
    data = json.load(sys.stdin)
    command = expand_assignments(data.get("tool_input", {}).get("command", ""))
    segments = ["gh api" + s for s in command.split("gh api")[1:]]
    if MERGE.search(command) or any(needs_prompt(s) for s in segments):
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
