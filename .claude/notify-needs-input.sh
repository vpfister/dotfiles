#!/usr/bin/env python3
"""Notification hook: name the session that is waiting for input.

Rings the terminal bell (flags the tmux window) and appends a line to
~/.claude/needs-input.log, which can be tailed from a spare pane.
"""
import glob
import json
import os
import sys
import time

CLAUDE_DIR = os.path.expanduser("~/.claude")
LOG = os.path.join(CLAUDE_DIR, "needs-input.log")
MAX_LOG_BYTES = 512_000


def session_name(session_id):
    for path in glob.glob(os.path.join(CLAUDE_DIR, "sessions", "*.json")):
        try:
            with open(path) as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            continue
        if s.get("sessionId") == session_id:
            return s.get("name") or ""
    return ""


def short(name, limit=52):
    name = name.strip().splitlines()[0].strip() if name.strip() else ""
    return name[: limit - 1] + "…" if len(name) > limit else name


def prune_mode_files():
    """mode-mirror.sh leaves one file per session; drop long-dead ones."""
    cutoff = time.time() - 7 * 86400
    for path in glob.glob(os.path.join(CLAUDE_DIR, "session-mode", "*")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def trim_log():
    if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG_BYTES:
        with open(LOG) as fh:
            tail = fh.readlines()[-200:]
        with open(LOG, "w") as fh:
            fh.writelines(tail)


def main():
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return

    sid = d.get("session_id") or ""
    name = (
        short(session_name(sid))
        or os.path.basename(d.get("cwd") or "")
        or sid[:8]
        or "unknown"
    )

    line = "  ".join(
        [
            time.strftime("%m-%d %H:%M:%S"),
            f"[{name}]",
            d.get("notification_type") or "notification",
            (d.get("message") or "").strip().replace("\n", " "),
        ]
    )

    trim_log()
    prune_mode_files()
    with open(LOG, "a") as fh:
        fh.write(line + "\n")

    try:
        with open("/dev/tty", "w") as tty:
            tty.write("\a")
    except OSError:
        pass


main()
