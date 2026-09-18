#!/usr/bin/env python3
"""Resolve fleet lane keys to live Claude Code sessions.

Shared by fleet-send.py and fleet-request.py. Reads ~/.claude/sessions/*.json,
which every running session maintains (name, status, messagingSocketPath).

Everything here fails soft: an unreadable or stale session file yields no match
rather than an error, because the caller only uses this to decide whether it can
wake a recipient immediately or must leave the message queued.
"""
import json
import os

HOME = os.path.expanduser("~")
SESSIONS = os.path.join(HOME, ".claude", "sessions")
LANES = os.path.join(HOME, ".claude", "fleet", "lanes.json")


def _proc_starttime(pid):
    """Field 22 of /proc/<pid>/stat. None if the pid is gone."""
    try:
        with open("/proc/%d/stat" % pid) as fh:
            data = fh.read()
    except OSError:
        return None
    # comm may contain spaces and parens, so split after the last ')'
    tail = data[data.rfind(")") + 2:].split()
    try:
        return tail[19]
    except IndexError:
        return None


def live_sessions():
    """Every session whose process is still running. [{pid,name,status,...}]"""
    out = []
    try:
        names = os.listdir(SESSIONS)
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(SESSIONS, fn)) as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            continue
        pid = s.get("pid")
        if not isinstance(pid, int):
            continue
        start = _proc_starttime(pid)
        if start is None:
            continue
        # guard against pid reuse: a recycled pid has a different start time
        if s.get("procStart") and str(s["procStart"]) != start:
            continue
        sock = s.get("messagingSocketPath")
        if sock and not os.path.exists(sock):
            continue
        out.append(s)
    return out


def lane_map():
    try:
        with open(LANES) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def lane_of_name(name, lanes=None):
    if not name:
        return None
    lanes = lane_map() if lanes is None else lanes
    return lanes.get(name.strip().splitlines()[0].strip())


def sessions_for_lane(lane):
    """Live sessions registered to a lane key. Usually 0 or 1."""
    lanes = lane_map()
    return [s for s in live_sessions() if lane_of_name(s.get("name"), lanes) == lane]


def sessions_named(name):
    """Live sessions with this exact session name (SUPER is not a lane key)."""
    want = name.strip().lower()
    return [s for s in live_sessions()
            if (s.get("name") or "").strip().lower() == want]


def calling_session():
    """The session whose Bash tool invoked us, by walking the parent pid chain.

    Returns None when the chain cannot be read, which callers must treat as
    "unknown sender" rather than guessing.
    """
    pid = os.getpid()
    for _ in range(12):
        path = os.path.join(SESSIONS, "%d.json" % pid)
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return None
        try:
            with open("/proc/%d/stat" % pid) as fh:
                data = fh.read()
        except OSError:
            return None
        tail = data[data.rfind(")") + 2:].split()
        try:
            pid = int(tail[1])
        except (IndexError, ValueError):
            return None
        if pid <= 1:
            return None
    return None
