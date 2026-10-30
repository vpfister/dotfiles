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
import shlex
import sys

MERGE = re.compile(r"/merge\b|mergePullRequest|PullRequestAutoMerge|enqueuePullRequest|merge-queue", re.I)
ASSIGNMENT = re.compile(r"(?:^|[\s;&|(])([A-Za-z_]\w*)=('[^']*'|\"[^\"]*\"|[^\s;&|)]+)")
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n", "{", "}", "$("}
FLAGS_WITH_VALUE = {
    "-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header", "-q", "--jq",
    "-t", "--template", "--input", "--hostname", "--cache", "-p", "--preview",
}
FIELD_FLAGS = {"-f", "--raw-field", "-F", "--field"}

# An id is a number or a shell variable (`$1` in a helper function, `$c` from a lookup).
# A variable can't smuggle in a merge: MERGE is checked on the whole command text.
ID = r"(?:\d+|\$\w+|\$\{\w+\})"
ALLOWED_REST = [
    rf"pulls/{ID}/comments/{ID}/replies",
    rf"pulls/comments/{ID}(?:/reactions)?",
    rf"issues/{ID}/comments",
    rf"issues/comments/{ID}(?:/reactions)?",
    rf"issues/{ID}/labels(?:/[^/]+)?",
    rf"pulls/{ID}",
    rf"actions/runs/{ID}/(?:rerun|rerun-failed-jobs)",
    rf"actions/jobs/{ID}/rerun",
    rf"check-runs/{ID}/rerequest",
    rf"check-suites/{ID}/rerequest",
]
REPO_PREFIX = r"/?repos/[^/]+/[^/]+/"
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


def expand_assignments(command: str) -> str:
    """Substitute `NAME=value` assignments made earlier in the same command."""
    for name, value in ASSIGNMENT.findall(command):
        value = value.strip("'\"")
        command = re.sub(rf"\$(?:{name}\b|\{{{name}\}})", lambda _: value, command)
    return command


def gh_api_calls(command: str) -> list[list[str]]:
    """Split a shell command into simple commands and return the args of each `gh api` call."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.wordchars += "$@%+,:^!#{}[]"
    lexer.commenters = ""
    calls, current = [], []
    for tok in lexer:
        if tok in SEPARATORS or tok.endswith("$") and tok != "$":
            current = []
            continue
        current.append(tok)
        if current[:2] == ["gh", "api"]:
            calls.append(current)
    return calls


def needs_prompt(args: list[str]) -> bool:
    method, endpoint, fields, skip = None, None, {}, None
    for tok in args[2:]:
        if skip:
            if skip in ("-X", "--method"):
                method = tok.upper()
            elif skip in FIELD_FLAGS:
                key, _, value = tok.partition("=")
                fields[key] = value
            elif skip == "--input":
                return True  # body not visible on the command line
            skip = None
        elif tok in FLAGS_WITH_VALUE:
            skip = tok
        elif not tok.startswith("-") and endpoint is None:
            endpoint = tok
    if endpoint == "graphql":
        query = fields.get("query", "")
        if query.startswith("@"):
            return True
        if "mutation" not in query:
            return False
        names = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", query)) - GRAPHQL_KEYWORDS
        return not names or not names <= ALLOWED_MUTATIONS
    if method in (None, "GET") and not fields:
        return False
    if method == "GET":
        return False
    path = re.sub(REPO_PREFIX, "", (endpoint or "").split("?")[0], count=1)
    return not any(re.fullmatch(p, path) for p in ALLOWED_REST)


def main() -> None:
    data = json.load(sys.stdin)
    command = expand_assignments(data.get("tool_input", {}).get("command", ""))
    try:
        calls = gh_api_calls(command)
    except ValueError:
        calls = None  # unbalanced quotes: can't tell what runs
    if calls is None or MERGE.search(command) or any(needs_prompt(c) for c in calls):
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
