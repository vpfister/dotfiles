#!/usr/bin/env python3
"""Render BOARD.md = declared plan (plan.yaml) + observed fleet state.

Observed state is DERIVED and disposable: it is re-read from the live fleet on
every run and never hand-edited. The declared plan is the source of truth for
objectives/gates and is only changed deliberately (see README.md).

Lane self-reports are rendered as CLAIMS, never silently promoted to fact.
"""
import glob
import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
FLEET = os.path.join(HOME, ".claude", "fleet")
JOBS = os.path.join(HOME, ".claude", "jobs")

CONF_MARK = {"verified": "verified", "claimed": "CLAIMED (unverified)",
             "stated": "stated (unverified)"}


def observed():
    """Live fleet state, keyed by session name."""
    out = {}
    try:
        raw = subprocess.run(["claude", "agents", "--json"], capture_output=True,
                             text=True, timeout=90).stdout
        # Resolve names from ~/.claude/sessions/*.json — the SAME source
        # hook-deliver.lane_for() reads. `claude agents --json` names are not
        # stable (auto-titling rewrites them mid-session), so keying on them
        # let the health check and the delivery path disagree silently.
        canon = {}
        for f in glob.glob(os.path.join(HOME, ".claude", "sessions", "*.json")):
            try:
                with open(f) as fh:
                    sj = json.load(fh)
            except (OSError, ValueError):
                continue
            nm = (sj.get("name") or "").strip().splitlines()
            if sj.get("sessionId"):
                canon[sj["sessionId"]] = nm[0].strip() if nm else ""
        for a in json.loads(raw):
            nm = canon.get(a.get("sessionId"))
            if nm is None:
                nm = (a.get("name") or "").strip().splitlines()
                nm = nm[0].strip() if nm else ""
            out[nm] = a
    except Exception:
        pass
    for name, a in out.items():
        p = os.path.join(JOBS, a.get("id", ""), "state.json")
        try:
            with open(p) as fh:
                s = json.load(fh)
            a["detail"] = s.get("detail")
            a["result"] = (s.get("output") or {}).get("result")
            a["mtime"] = os.path.getmtime(p)
        except (OSError, ValueError, AttributeError):
            pass
    return out


def ago(ts):
    if not ts:
        return "?"
    m = int((time.time() - ts) / 60)
    if m < 60:
        return "%dm" % m
    if m < 1440:
        return "%dh%02dm" % (m // 60, m % 60)
    return "%dd" % (m // 1440)


def pending():
    """Undelivered inbox messages and unprocessed lane requests."""
    inb, req = {}, {}
    for p in glob.glob(os.path.join(FLEET, "inbox", "*.md")):
        inb[os.path.basename(p)[:-3]] = open(p).read().count("--- MESSAGE ---")
    for p in glob.glob(os.path.join(FLEET, "requests", "*.md")):
        if os.path.getsize(p):
            req[os.path.basename(p)[:-3]] = os.path.getsize(p)
    return inb, req


def main():
    import yaml
    plan = yaml.safe_load(open(os.path.join(FLEET, "plan.yaml")))
    obs = observed()
    inb, req = pending()
    L = []
    a = L.append
    a("# ML4 / FinanceQA — Fleet Board")
    a("")
    a("*Generated %s by SUPER. Plan rev %s. Do not hand-edit — edit `plan.yaml`.*"
      % (time.strftime("%Y-%m-%d %H:%M"), plan.get("plan_revision")))
    a("")
    a("**Mission.** %s" % plan.get("mission", "").strip())
    a("")

    # Laptop-relayed infra: tunnels + forwarded ssh-agent die together when the
    # laptop sleeps. Surface it once, centrally, so ten lanes do not each
    # rediscover it as "my ssh is broken".
    try:
        raw = subprocess.run([os.path.join(FLEET, "fleet-infra-check.py"), "--json"],
                             capture_output=True, text=True, timeout=90).stdout
        infra = json.loads(raw)
    except Exception:
        infra = None
    if infra and not infra.get("all_up"):
        # Stamp the probe time INSIDE the banner. The board is regenerated only
        # once per sweep, and the relay flaps on a shorter timescale than that,
        # so a lane reading this file cannot otherwise tell whether it is looking
        # at live state or at a snapshot from twenty minutes ago. karl-vespa hit
        # exactly this and reported the banner as stale when it was merely old.
        a("## \u26a0 Laptop-relayed infra DEGRADED \u2014 as probed at %s"
          % time.strftime("%Y-%m-%d %H:%M:%S %Z"))
        a("")
        a("*This is a point-in-time probe, not a live indicator, and the relay"
          " flaps. If it matters right now, re-run"
          " `~/.claude/fleet/fleet-infra-check.py` yourself \u2014 it is"
          " pre-allowlisted and takes seconds. Trust it over this banner.*")
        a("")
        for h, v in infra.get("tunnels", {}).items():
            if not v["up"]:
                # Label by CAUSE, not by a flat DOWN: an auth failure printed as
                # "DOWN — TUNNEL IS UP" is self-contradictory and a reader will
                # believe the first two words.
                label = ("**AUTH FAILING** (tunnel reachable)"
                         if v.get("kind") == "auth" else "**DOWN**")
                a("- tunnel `%s` %s — %s" % (h, label, v["reason"]))
        ag = infra.get("ssh_agent", {})
        if not ag.get("up"):
            a("- **ssh-agent DOWN** — %s (git push/fetch will fail)" % ag.get("reason"))
        a("")
        # An auth failure and an outage look similar on this board but call for
        # OPPOSITE responses: park for hours vs wait ten seconds for a keypress.
        # Conflating them is what makes a lane sit idle on a solved problem.
        down = infra.get("tunnels", {})
        kinds = {v.get("kind") for v in down.values() if not v["up"]}
        if kinds and kinds <= {"auth"}:
            a("**This is an AUTH failure, not an outage — the tunnel is UP.** The key"
              " agent on the laptop is refusing to sign. Vincent approves/unlocks it"
              " and work resumes immediately. Do NOT file `BLOCKED-BY-TUNNEL` and do"
              " NOT park for hours; report that the key agent is refusing to sign and"
              " retry once he confirms.")
        else:
            a("This is Vincent's laptop relay, not a lane bug. Lanes: do NOT retry in a"
              " loop or work around it — file `BLOCKED-BY-TUNNEL` and park that work.")
        a("Run `~/.claude/fleet/fleet-infra-check.py` for a definitive answer; it"
          " distinguishes the two cases.")
        a("")

    blocked = [n for n, x in obs.items() if x.get("status") == "waiting"]
    if blocked:
        a("## Needs Vincent now")
        a("")
        for n in blocked:
            a("- **%s** — %s (idle %s)" % (n, obs[n].get("waitingFor", "?"),
                                           ago(obs[n].get("mtime"))))
        a("")

    # Registration health: a lane whose session_name matches no live session can
    # never receive mail (lane_for returns None and delivery silently no-ops).
    live = set(obs)
    unresolved = []
    for key, ln in plan["lanes"].items():
        names = [ln["session_name"]] + list(ln.get("session_name_aliases") or [])
        if not any(n in live for n in names):
            unresolved.append((key, ln["session_name"]))
    if unresolved:
        a("## \u26a0 Registration mismatch — these lanes cannot receive mail")
        a("")
        for key, nm in unresolved:
            a("- `%s` expects a session named **%s**, which is not live. Mail to it"
              " will silently vanish. Rename the session or fix lanes.json." % (key, nm))
        a("")

    a("## Lanes")
    a("")
    a("| Lane | Live | Last %s | Objective |" % "signal")
    a("|---|---|---|---|")
    for key, ln in plan["lanes"].items():
        o = obs.get(ln["session_name"], {})
        st = o.get("status", "—")
        icon = {"idle": "idle", "busy": "working", "waiting": "**BLOCKED**"}.get(st, st)
        det = (o.get("result") or o.get("detail") or "—")
        det = str(det).replace("\n", " ")[:90]
        a("| `%s` | %s | %s | %s |" % (key, icon, det, ln["objective"].strip()[:70]))
    a("")

    a("## Gates")
    a("")
    a("| Gate | Owner | State | Confidence | Confirmed | Waiting on it |")
    a("|---|---|---|---|---|---|")
    for g, d in plan.get("gates", {}).items():
        a("| `%s` | %s | %s | %s | %s | %s |" % (
            g, d.get("owner", "?"), d.get("state", "?"),
            CONF_MARK.get(d.get("confidence"), d.get("confidence")),
            d.get("last_confirmed") or "never",
            ", ".join(d.get("consumers", []) or ["—"])))
    a("")

    unver = [g for g, d in plan.get("gates", {}).items()
             if d.get("confidence") in ("claimed", "stated")]
    if unver:
        a("> **%d of %d gates are unverified.** SUPER has not independently"
          " cross-checked these against git/CI/disk; they are assertions only:"
          " %s" % (len(unver), len(plan.get("gates", {})),
                   ", ".join("`%s`" % g for g in unver)))
        a("")

    # Undeliverable-by-construction: an inbox whose lane maps to no live session.
    # Independent of plan.yaml, so it catches session renames the plan has not
    # caught up with — the failure that left hec-dataset unreachable for 2h.
    try:
        with open(os.path.join(FLEET, "lanes.json")) as fh:
            name2lane = json.load(fh)
    except (OSError, ValueError):
        name2lane = {}
    reachable = {name2lane[n] for n in obs if n in name2lane}
    orphaned = [k for k in inb if k not in reachable]
    if orphaned:
        a("## \u26a0 Mail queued for lanes that CANNOT be reached")
        a("")
        for k in orphaned:
            a("- `%s`: %d message(s) queued, but no live session resolves to this lane."
              " Delivery will silently no-op. Check lanes.json against the live session"
              " name." % (k, inb[k]))
        a("")

    if inb or req:
        a("## Traffic")
        a("")
        # A lane that is ALREADY idle will not fire Stop again, so queued mail sits
        # undelivered until someone types in that session. Surface it loudly.
        name_of = {v.get("id"): k for k, v in obs.items()}
        lane_status = {}
        for lname, o in obs.items():
            for key, ln in plan["lanes"].items():
                if ln["session_name"] == lname:
                    lane_status[key] = o.get("status")
        for k, v in inb.items():
            st = lane_status.get(k)
            if st == "idle":
                a("- inbox `%s`: %d message(s) queued — **WILL NOT DELIVER, lane is"
                  " idle.** Type anything in that session to release it." % (k, v))
            elif st is None:
                a("- inbox `%s`: %d message(s) queued — lane not live; will deliver"
                  " on next session start" % (k, v))
            else:
                a("- inbox `%s`: %d message(s) queued, delivers at next turn end"
                  " (lane is %s)" % (k, v, st))
        for k in req:
            a("- request from `%s`: **awaiting SUPER triage**" % k)
        a("")

    oq = plan.get("open_questions") or []
    if oq:
        a("## Open questions for Vincent")
        a("")
        for q in oq:
            a("- **%s** %s" % (q["id"], q["q"]))
        a("")

    a("## Escalation boundary")
    a("")
    a("SUPER will not decide these alone:")
    for e in plan.get("escalate_to_human", []):
        a("- %s" % e)
    a("")
    txt = "\n".join(L) + "\n"
    open(os.path.join(FLEET, "BOARD.md"), "w").write(txt)
    sys.stderr.write("wrote BOARD.md (%d bytes)\n" % len(txt))


if __name__ == "__main__":
    main()
