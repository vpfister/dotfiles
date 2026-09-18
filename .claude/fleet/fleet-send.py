#!/usr/bin/env python3
"""Append a message to a lane's fleet inbox. Atomic, never clobbers.

  fleet-send.py <lane> --from "pr-review #28292" --subject "3 blocking" \
      --body "short text"
  ... | fleet-send.py <lane> --from X --subject Y        # body on stdin

Always appends under an exclusive lock, so concurrent senders cannot destroy
each other's messages. Refuses unknown lanes so a typo does not silently create
an inbox nobody reads.

Queueing alone does not wake an idle recipient — the delivery hook only fires on
Stop/UserPromptSubmit/SessionStart, none of which an idle lane produces. So this
prints the SendMessage call to make next, which the sender must actually issue.
"""
import argparse
import fcntl
import json
import os
import sys

FLEET = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(FLEET, "inbox")
LANES = os.path.join(FLEET, "lanes.json")

sys.path.insert(0, FLEET)
try:
    import fleet_sessions
except ImportError:                       # resolution is optional, queueing is not
    fleet_sessions = None


def detect_authority():
    """'supervisor' only when SUPER is demonstrably the caller, else 'peer'.

    Failure direction matters: an undetectable caller under-claims authority
    rather than letting any lane's message render as a supervisor directive.
    """
    if fleet_sessions is None:
        return "peer", None
    try:
        me = fleet_sessions.calling_session()
    except Exception:
        return "peer", None
    if not me:
        return "peer", None
    name = (me.get("name") or "").strip()
    return ("supervisor" if name.upper() == "SUPER" else "peer"), name


def print_ping(lane, sender, subject):
    """Tell the caller exactly how to wake the recipient, or why it cannot."""
    if fleet_sessions is None:
        return
    try:
        targets = fleet_sessions.sessions_for_lane(lane)
    except Exception:
        return
    inbox = "~/.claude/fleet/inbox/%s.md" % lane
    if not targets:
        # A live session can be missing from ~/.claude/sessions (seen once), so this
        # is "cannot resolve", not "definitely dead" — hence ListAgents as the check.
        print("\nNOT WAKEABLE: no session file maps to lane %r." % lane)
        print("The message stays queued and is delivered if that lane starts again.")
        print("Before assuming it is dead, check ListAgents: if the lane is listed")
        print("there, SendMessage it by that name and tell it to drain %s." % inbox)
        return
    if len(targets) > 1:
        print("\nAmbiguous: %d live sessions map to lane %r (%s)."
              % (len(targets), lane, ", ".join(repr(t.get("name")) for t in targets)))
        print("Run ListAgents and SendMessage the right one.")
        return
    t = targets[0]
    print("\nWAKE THE RECIPIENT — call the SendMessage tool now:")
    print('  to:      %r' % (t.get("name") or ""))
    # The ping itself fires the recipient's UserPromptSubmit hook, which delivers and
    # deletes the inbox file in the same turn — so pointing at the file is a fallback,
    # not the instruction. Verified 2026-09-08 against the kgtool lane.
    print('  message: fleet mail from %s: %s — your delivery hook hands it to you with'
          ' this ping; if no PEER/SUPERVISOR block appears, read %s'
          % (sender, subject, inbox))
    print("Send exactly that one line. The content stays in the envelope the hook")
    print("renders, so the recipient is not derailed by the ping itself.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lane")
    ap.add_argument("--from", dest="sender", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", default=None)
    ap.add_argument("--as", dest="authority", choices=("supervisor", "peer"),
                    default=None, help="override sender authority (detected by default)")
    a = ap.parse_args()

    try:
        known = set(json.load(open(LANES)).values())
    except (OSError, ValueError):
        known = set()
    if known and a.lane not in known:
        sys.exit("unknown lane %r. Known lanes: %s" % (a.lane, ", ".join(sorted(known))))

    body = a.body if a.body is not None else sys.stdin.read()
    body = body.strip()
    if not body:
        sys.exit("refusing to send an empty message")
    if "--- MESSAGE ---" in body or "--- END ---" in body:
        sys.exit("body must not contain the message delimiters")

    detected, caller = detect_authority()
    authority = a.authority or detected

    block = ("--- MESSAGE ---\nfrom: %s\nauthority: %s\nsubject: %s\n%s\n--- END ---\n"
             % (a.sender, authority, a.subject, body))
    os.makedirs(INBOX, exist_ok=True)
    path = os.path.join(INBOX, "%s.md" % a.lane)
    with open(path, "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(block)
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    n = open(path).read().count("--- MESSAGE ---")
    print("queued for %s (%d message(s) now pending): %s" % (a.lane, n, a.subject))
    print("authority: %s%s" % (authority, " (caller: %s)" % caller if caller else ""))
    print_ping(a.lane, a.sender, a.subject)


if __name__ == "__main__":
    main()
