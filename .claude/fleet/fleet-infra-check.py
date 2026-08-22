#!/usr/bin/env python3
"""Is the laptop-relayed infrastructure up? Definitive answer, no guessing.

    ~/.claude/fleet/fleet-infra-check.py            # human-readable
    ~/.claude/fleet/fleet-infra-check.py --json     # for board.py

Vincent's laptop relays BOTH the cross-cluster SSH tunnels and the forwarded
ssh-agent. When the laptop sleeps or goes offline, both die together — so
`ssh bar` fails AND `git push` fails, and a lane that treats them as two
separate bugs will waste time or, worse, work around them.

Exit 0 = all up. Exit 1 = something down (details on stdout).
"""
import json
import os
import subprocess
import sys

HOSTS = ["bar", "ala0"]


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except Exception as e:  # noqa: BLE001 - diagnostic tool, never raise
        return 1, str(e)


_NOISE = ("warning: permanently added", "warning: identity file",
          "pseudo-terminal", "load pubkey")


def _salient(msg):
    """First line that is an actual error, not ssh's routine chatter.

    Taking msg.splitlines()[0] blindly once made this tool report
    "Warning: Permanently added 'bar-via-tunnel' ... to the list of known
    hosts" as the reason a tunnel was down, burying the real cause two lines
    below. The banner is what lanes act on, so a misleading reason is worse
    than no reason.
    """
    lines = [ln.strip() for ln in (msg or "").splitlines() if ln.strip()]
    for ln in lines:
        if not any(n in ln.lower() for n in _NOISE):
            return ln[:160]
    return lines[0][:160] if lines else "unknown"


def check():
    out = {"tunnels": {}, "ssh_agent": {}, "all_up": True}

    for h in HOSTS:
        rc, msg = run("ssh -o BatchMode=yes -o ConnectTimeout=10 %s true" % h)
        up = rc == 0
        reason, kind = "", ""
        if not up:
            low = msg.lower()
            # Order matters: check for auth failures BEFORE falling back to a
            # generic "tunnel down". A refusing key agent looks nothing like an
            # offline relay and must not be reported as one — telling a lane the
            # tunnel is down makes it park for hours, when the real fix is ten
            # seconds of approving the key on the laptop.
            if "agent refused operation" in low or "signing failed" in low:
                kind = "auth"
                reason = ("TUNNEL IS UP — the key agent refused to SIGN. Not an"
                          " outage: approve/unlock the key on the laptop"
                          " (Secretive) and retry. Parking is the wrong response.")
            elif "permission denied (publickey)" in low:
                kind = "auth"
                reason = ("TUNNEL IS UP — TCP and host key fine, but publickey"
                          " auth was rejected. Key not loaded or not authorised;"
                          " this is credentials, not connectivity.")
            elif "connection refused" in low:
                kind = "down"
                reason = "tunnel down (laptop relay offline or not forwarding)"
            elif "kex_exchange_identification" in low or "timed out" in low:
                kind = "down"
                reason = "tunnel present but not answering (laptop asleep?)"
            elif "could not resolve" in low:
                kind = "config"
                reason = "no ssh config entry / name not resolvable"
            else:
                kind = "unknown"
                reason = _salient(msg)
        out["tunnels"][h] = {"up": up, "reason": reason, "kind": kind}
        if not up:
            out["all_up"] = False

    rc, msg = run("ssh-add -l", timeout=10)
    # rc 0 = keys loaded; 1 = agent reachable but empty; 2 = cannot reach agent.
    # CAVEAT worth stating: rc 0 only proves the agent will LIST keys. It does
    # not prove it will SIGN with them. Secretive on the laptop can list a key
    # and still answer "agent refused operation" when asked to sign, which is
    # why the tunnel probes above classify auth failures themselves rather than
    # trusting this result.
    agent_up = rc == 0
    out["ssh_agent"] = {
        "up": agent_up,
        "sock": os.environ.get("SSH_AUTH_SOCK", "(unset)"),
        "lists_keys_only": agent_up,
        "reason": "" if agent_up else (
            "agent reachable but no keys" if rc == 1
            else "cannot reach agent — forwarded agent died with the laptop"),
    }
    if not agent_up:
        out["all_up"] = False
    return out


def main():
    r = check()
    if "--json" in sys.argv:
        print(json.dumps(r))
        sys.exit(0 if r["all_up"] else 1)

    for h, v in r["tunnels"].items():
        print("tunnel %-5s %s%s" % (h, "UP" if v["up"] else "DOWN",
                                    "" if v["up"] else "  — " + v["reason"]))
    a = r["ssh_agent"]
    print("ssh-agent   %s%s" % ("UP" if a["up"] else "DOWN",
                                "" if a["up"] else "  — " + a["reason"]))
    print("SSH_AUTH_SOCK=%s" % a["sock"])
    auth = [h for h, v in r["tunnels"].items() if v.get("kind") == "auth"]
    if r["all_up"]:
        print("\nAll up. If your command still fails, it is NOT the tunnel.")
    elif auth and all(v.get("kind") == "auth"
                      for v in r["tunnels"].values() if not v["up"]):
        # Distinct from an outage, and the response is the opposite one.
        print("\nThis is an AUTH failure, NOT an outage. The tunnel is up.")
        print("Vincent approves/unlocks the key on the laptop; it then just works.")
        print("DO NOT file BLOCKED-BY-TUNNEL and do not park for hours — say the")
        print("key agent is refusing to sign, and retry once he confirms.")
    else:
        print("\nSomething is down. This is Vincent's laptop relay, NOT your bug.")
        print("DO NOT retry in a loop, work around it, or change approach.")
        print("File a request:  fleet-request.py <your-lane> --kind blocked \\")
        print("    --subject 'BLOCKED-BY-TUNNEL: <what you were doing>' ...")
        print("Then park that work and do something that needs no tunnel.")
    sys.exit(0 if r["all_up"] else 1)


if __name__ == "__main__":
    main()
