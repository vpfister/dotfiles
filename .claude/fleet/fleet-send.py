#!/usr/bin/env python3
"""Append a message to a lane's fleet inbox. Atomic, never clobbers.

  fleet-send.py <lane> --from "pr-review #28292" --subject "3 blocking" \
      --body "short text"
  ... | fleet-send.py <lane> --from X --subject Y        # body on stdin

Always appends under an exclusive lock, so concurrent senders cannot destroy
each other's messages. Refuses unknown lanes so a typo does not silently create
an inbox nobody reads.
"""
import argparse
import fcntl
import json
import os
import sys

FLEET = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(FLEET, "inbox")
LANES = os.path.join(FLEET, "lanes.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lane")
    ap.add_argument("--from", dest="sender", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", default=None)
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

    block = ("--- MESSAGE ---\nfrom: %s\nsubject: %s\n%s\n--- END ---\n"
             % (a.sender, a.subject, body))
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


if __name__ == "__main__":
    main()
