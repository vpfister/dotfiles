#!/usr/bin/env python3
"""PreToolUse guard for `gh api` writes.

`gh api:*` is allowed so reads run unprompted. This hook forces a prompt for
any `gh api` write except routine PR-thread work (comment replies, thread
resolution, labels, PR title/body, ready-for-review, CI reruns, COMMENT reviews). Merge
endpoints are also `ask` rules in settings.json. This hook never returns
"allow"; uninspectable review-file commands are denied with retry instructions.
"""

import json
from pathlib import Path
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


class ReviewPayloadNotReady(Exception):
    """The review file must be prepared before the submission tool call."""


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


def review_input_cwd(command: str, cwd: str) -> Path | None:
    """Inspect files only for a standalone request, optionally preceded by cd."""
    if any(char in command for char in "$`"):
        return None  # shell expansion could change the request or its payload
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    tokens = list(lexer)
    directory = Path(cwd)
    if len(tokens) >= 4 and tokens[0] == "cd" and tokens[2] in {";", "&&"}:
        if any(char in tokens[1] for char in "$`~"):
            return None
        directory /= tokens[1]
        tokens = tokens[3:]
    if tokens[:2] != ["gh", "api"]:
        return None
    if any(tok and all(char in ";&|()<>\n" for char in tok) for tok in tokens):
        return None
    return directory


def needs_prompt(args: list[str], input_cwd: Path | None = None) -> bool:
    method, endpoint, fields, input_file = None, None, {}, None
    tokens = iter(args[2:])
    for tok in tokens:
        flag, equals, value = tok.partition("=")
        if flag in FLAGS_WITH_VALUE and equals:
            pass
        elif tok[:2] in {"-X", "-f", "-F"} and len(tok) > 2:
            flag, value = tok[:2], tok[2:]
        elif tok in FLAGS_WITH_VALUE:
            flag, value = tok, next(tokens, None)
            if value is None:
                return True
        else:
            flag = None
        if flag:
            if flag in ("-X", "--method"):
                method = value.upper()
            elif flag in FIELD_FLAGS:
                key, _, value = value.partition("=")
                fields[key] = value
            elif flag == "--input":
                input_file = value
        elif not tok.startswith("-") and endpoint is None:
            endpoint = tok
    path = re.sub(REPO_PREFIX, "", (endpoint or "").split("?")[0], count=1)
    effective_method = method or ("POST" if fields or input_file is not None else "GET")
    if effective_method == "POST" and re.fullmatch(rf"pulls/{ID}/reviews", path):
        if input_file is None:
            return fields.get("event") != "COMMENT"
        # The file must exist before this tool call, not be generated by it.
        if fields:
            return True
        if input_cwd is None or input_file == "-" or any(c in input_file for c in "$`~"):
            raise ReviewPayloadNotReady
        try:
            payload_path = input_cwd / input_file
            if not payload_path.is_file():
                raise ReviewPayloadNotReady
            payload = json.loads(payload_path.read_text())
        except (OSError, ValueError):
            return True
        return not isinstance(payload, dict) or payload.get("event") != "COMMENT"
    if input_file is not None:
        return True  # other file-backed writes remain outside this allowance
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
    return not any(re.fullmatch(p, path) for p in ALLOWED_REST)


def main() -> None:
    data = json.load(sys.stdin)
    command = expand_assignments(data.get("tool_input", {}).get("command", ""))
    try:
        calls = gh_api_calls(command)
        input_cwd = review_input_cwd(command, data.get("cwd") or str(Path.cwd()))
    except ValueError:
        calls = None  # unbalanced quotes: can't tell what runs
    decision = None
    reason = "gh api write outside routine PR-thread endpoints"
    try:
        if calls is None or MERGE.search(command) or any(needs_prompt(c, input_cwd) for c in calls):
            decision = "ask"
    except ReviewPayloadNotReady:
        decision = "deny"
        reason = (
            "Prepare the PR review JSON in a separate tool call, then retry a standalone "
            "gh api request with literal arguments and --input /absolute/path.json. COMMENT reviews pass without "
            "confirmation once the payload is inspectable; other review events still require approval."
        )
    if decision:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
