#!/usr/bin/env python3
"""PreToolUse guard: prompt for `git push` that lands on a default/protected branch.

`git push:*` is allowed and settings rules only see command text, so a bare
`git push` while on main, or `git -C dir push origin main`, would not prompt.
This hook resolves the repo dir (`cd X &&`, `git -C X`, hook cwd) and the
target branch, and returns "ask" when it is main, master, or origin's HEAD.
"""

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "master"}
SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
FLAGS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def protected_branches(cwd: str) -> set[str]:
    head = git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return PROTECTED | ({head.split("/", 1)[1]} if head and "/" in head else set())


def push_targets(tokens: list[str], cwd: str) -> list[str] | None:
    positional, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
        elif tok in FLAGS_WITH_VALUE:
            skip = True
        elif not tok.startswith("-"):
            positional.append(tok)
    current = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if current is None:
        return None  # not a repo; the push fails on its own
    if len(positional) <= 1:
        return [current]
    targets = []
    for spec in positional[1:]:
        src, _, dst = spec.lstrip("+").partition(":")
        dst = dst or src
        dst = current if dst == "HEAD" else dst
        targets.append(dst.removeprefix("refs/heads/"))
    return targets


def needs_prompt(command: str, cwd: str) -> bool:
    for segment in SEPARATORS.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        if tokens[0] == "cd" and len(tokens) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(tokens[1]))
            continue
        if tokens[0] != "git":
            continue
        rest, repo = tokens[1:], cwd
        while rest[:1] == ["-C"] and len(rest) > 1:
            repo = os.path.join(repo, os.path.expanduser(rest[1]))
            rest = rest[2:]
        if rest[:1] != ["push"]:
            continue
        targets = push_targets(rest[1:], repo)
        if targets and set(targets) & protected_branches(repo):
            return True
    return False


def main() -> None:
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    if needs_prompt(command, data.get("cwd") or os.getcwd()):
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": "git push targets a default/protected branch",
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
