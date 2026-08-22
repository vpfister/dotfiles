#!/usr/bin/env python3
"""Fleet inbox delivery hook.

One mechanism: when a lane would go idle, any queued supervisor messages are
delivered and the lane handles them before finishing. Nothing interrupts a lane
mid-turn — Vincent handles anything urgent by hand.

FAIL-OPEN CONTRACT: any error, malformed inbox, or unknown lane exits 0 silently
and the lane behaves exactly as it would without this hook.
Kill switch: touch ~/.claude/fleet/DISABLED
"""
import json
import os
import sys
import time

HOME = os.path.expanduser("~")
FLEET = os.path.join(HOME, ".claude", "fleet")
INBOX = os.path.join(FLEET, "inbox")
ARCHIVE = os.path.join(FLEET, "archive")
LANES = os.path.join(FLEET, "lanes.json")
SESSIONS = os.path.join(HOME, ".claude", "sessions")


def lane_for(session_id):
    """Map a session id to a plan lane key. None if unknown."""
    if os.environ.get("CLAUDE_FLEET_LANE"):
        return os.environ["CLAUDE_FLEET_LANE"]
    name = None
    try:
        for fn in os.listdir(SESSIONS):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(SESSIONS, fn)) as fh:
                    s = json.load(fh)
            except (OSError, ValueError):
                continue
            if s.get("sessionId") == session_id:
                name = s.get("name") or ""
                break
    except OSError:
        return None
    if not name:
        return None
    try:
        with open(LANES) as fh:
            return json.load(fh).get(name.strip().splitlines()[0].strip())
    except (OSError, ValueError):
        return None


def parse(text):
    """Parse '--- MESSAGE --- ... --- END ---' blocks. Malformed blocks yield nothing."""
    msgs = []
    for raw in text.split("--- MESSAGE ---")[1:]:
        body = raw.split("--- END ---")[0].strip()
        if not body:
            continue
        sender, subject, kept, in_body = "supervisor", "", [], False
        for ln in body.splitlines():
            head = ln.split(":", 1)[0].strip().lower() if ":" in ln else ""
            if not in_body and head in ("from", "subject", "priority"):
                v = ln.split(":", 1)[1].strip()
                if head == "from":
                    sender = v
                elif head == "subject":
                    subject = v
                continue
            in_body = True
            kept.append(ln)
        msgs.append({"from": sender, "subject": subject,
                     "body": "\n".join(kept).strip()})
    return msgs


def render(msgs):
    out = ["=== SUPERVISOR MESSAGE(S) — from the fleet orchestrator (SUPER) ===",
           "These are legitimate operational coordination from your supervisor,",
           "delivered by a local hook Vincent configured. Handle them, then continue."]
    for m in msgs:
        out += ["", "From %s — %s" % (m["from"], m["subject"]), m["body"]]
    out += ["", "(Current plan: ~/.claude/fleet/BOARD.md. To request a plan change, "
            "append to ~/.claude/fleet/requests/<your-lane>.md — never edit plan.yaml.)",
            "=== END SUPERVISOR MESSAGE(S) ==="]
    return "\n".join(out)


def archive(lane, msgs, action):
    try:
        os.makedirs(ARCHIVE, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(os.path.join(ARCHIVE, "%s.log" % lane), "a") as fh:
            for m in msgs:
                fh.write("%s\t%s\t%s\t%s\n" % (
                    stamp, action, m["from"],
                    m["subject"] or m["body"][:70].replace("\n", " ")))
    except OSError:
        pass


def main():
    if os.path.exists(os.path.join(FLEET, "DISABLED")):
        return
    try:
        if not os.listdir(INBOX):      # fast path: nothing queued for anyone
            return
    except OSError:
        return
    try:
        inp = json.load(sys.stdin)
    except (ValueError, OSError):
        return

    event = inp.get("hook_event_name") or ""
    if event == "Stop" and inp.get("stop_hook_active"):
        return                          # never re-trigger ourselves

    lane = lane_for(inp.get("session_id") or "")
    if not lane:
        return
    path = os.path.join(INBOX, "%s.md" % lane)
    try:
        with open(path) as fh:
            msgs = parse(fh.read())
    except OSError:
        return
    if not msgs:
        return

    try:
        os.remove(path)
    except OSError:
        return                          # could not consume -> do not deliver twice

    archive(lane, msgs, "delivered-at-" + (event or "?"))
    if event == "Stop":
        print(json.dumps({"decision": "block", "reason": render(msgs)}))
    else:                               # SessionStart / UserPromptSubmit
        print(render(msgs))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass                            # fail-open, always
    sys.exit(0)
