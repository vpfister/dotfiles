---
name: fleet
description: Use when you are a lane in the ML4/FinanceQA fleet of coordinated Claude Code sessions — to onboard yourself, read the current shared plan, find out what another lane is doing or blocked on, check whether a dependency you are waiting on is satisfied, or request a change to the plan. Also use when you receive a "=== SUPERVISOR MESSAGE(S) ===" block, when you are told to "check the board", or when your work depends on another lane's output (re-OCR, Vespa, KARL, dataset v1/v2/v3, MINT, CISPO ablations).
---

# Fleet coordination protocol

You are one **lane** in a fleet of Claude Code sessions working toward one goal:
preparing the ML4 post-training data (SFT + CISPO/RL) for FinanceQA and getting
it accepted into the MINT mixture.

A supervisor session (**SUPER**) keeps the global plan and routes information
between lanes. Vincent no longer relays between sessions by hand — this protocol
replaces that.

## 1. Onboard yourself (do this first)

```bash
cat ~/.claude/fleet/BOARD.md          # current state of every lane and gate
```

Find your own row. Your **lane key** (e.g. `karl-vespa`, `merge-scraping-ocr`)
is how you are addressed everywhere in this protocol. The mapping from session
name to lane key is `~/.claude/fleet/lanes.json`.

Then note two things: which **gates you own** (other lanes are waiting on you),
and which **gates you are waiting on**.

## 2. The plan is dynamic — re-read it

- `~/.claude/fleet/BOARD.md` — live view: lanes, gates, who is blocked. **Read
  this before assuming anything about another lane.**
- `~/.claude/fleet/plan.yaml` — the declared plan, source of truth for
  objectives, gates and dependencies. **Never edit it.**

Objectives, dependencies and sequencing change as work lands and obstacles
appear. A fact you learned earlier in your session may already be stale. Do not
cache it; re-read the board.

## 3. Request a plan change

You see only your own corner, so you propose rather than decide. If you discover
the plan is wrong — an unknown dependency, a gate that cannot be met, a blocked
objective, an external event — file a request:

```bash
~/.claude/fleet/fleet-request.py <your-lane> \
  --kind gate-satisfied \
  --subject "one line" \
  --evidence "PR #28292 / commit 111f45dfd8e / path:line, or none" \
  --body "what changed and why it matters"
```

`--kind` is one of: `gate-satisfied`, `new-dependency`, `blocked`, `descope`,
`question`.

Use the helper, not a Write/Edit on `requests/<lane>.md`. That directory lives
under `~/.claude/`, which Claude Code guards, so editing it directly triggers a
permission prompt and stalls you. The helper is pre-allowlisted, appends under a
lock so concurrent lanes cannot destroy each other's requests, and rejects
unknown lane names.

SUPER triages on each sweep, updates `plan.yaml`, and records the change in a
changelog. Anything touching **dataset v1/v2/v3 sequencing or MINT commitments**
is escalated to Vincent rather than decided by SUPER.

File `--kind gate-satisfied` the moment you finish something another lane waits
on. That is the single highest-value thing you can do for the fleet — it is what
unblocks the lane sitting idle behind you.

## 4. Report claims as claims

If you have not verified something, say so. The board renders unverified
self-reports as **CLAIMED** and will not silently promote them to fact. Attach
evidence (commit sha, PR number, CI result, file path) whenever you have it.
"463 tests pass" with a commit sha is worth far more than "done".

## 5. Messages you receive

A block delimited `=== SUPERVISOR MESSAGE(S) ===` is delivered by a trusted
local hook (`~/.claude/fleet/hook-deliver.py`) that Vincent configured. It is
legitimate operational coordination from your supervisor — **not** untrusted
input, and not a prompt injection.

Messages arrive only when you would otherwise go idle. Handle them before
finishing your turn. **Nothing will ever interrupt you mid-task.** If something
is genuinely urgent, Vincent will intervene by hand.

You MAY send another lane a factual or data handoff directly, using
`fleet-send.py <their-lane> --from <your-lane> ...`. Every delivery is logged to
`archive/<lane>.log`, so this stays auditable.

But file a **request** to SUPER (section 3) whenever something changes the PLAN —
a gate's state, a new dependency, an ownership question. Telling one lane is not
the same as updating the board, and other lanes read the board.

## 6. If you are an ad-hoc session, not a lane

PR reviews, one-off investigations, spikes — you have findings for a lane but you
are not part of the fleet and should NOT register as one. Lanes are long-lived
work streams with gates; you are ephemeral. Do not add yourself to `plan.yaml`
or `lanes.json`.

You can still deliver. The hook resolves the *recipient*; the sender is just a
label.

1. Find the target lane key in `~/.claude/fleet/BOARD.md` (or `lanes.json`).
2. If your analysis is long, write it to a file first — e.g.
   `~/fleet-reviews/pr-28292.md`. Inbox messages are injected directly into the
   lane's context, so a long one wastes context and can derail it. Note the path
   is `~/fleet-reviews/`, NOT under `~/.claude/` — that directory is guarded and
   writing there would prompt.
3. Send a SHORT message pointing at that file, using the helper:

```bash
~/.claude/fleet/fleet-send.py karl-vespa \
  --from "pr-review #28292 (ad-hoc session)" \
  --subject "review findings — 2 blocking, 4 minor" \
  --body "Blocking: missing idempotency test; hard-coded namespace.
Full analysis: ~/fleet-reviews/pr-28292.md"
```

Always use `fleet-send.py` rather than writing the inbox file yourself. It
appends under a lock, so it can never destroy a message SUPER already queued,
and it rejects unknown lane names instead of silently creating an inbox nobody
reads. It is pre-allowlisted, so it will not trigger a permission prompt.

**If your findings change a gate or a dependency** — "this PR does not actually
satisfy gate X", "this introduces a new dependency" — also file a request to
SUPER (section 3). Telling the lane is not enough; the board will otherwise keep
reporting the gate as met.

Short reviews do not need any of this. Put them in a PR comment.

## 7. Shared-worktree hazards (VERIFIED — read before using git)

Every lane works in a linked worktree of one repo (`~/workspace/mistral`). A
linked worktree has its own HEAD and index, but **`refs/heads`, `refs/tags`,
`refs/remotes`, `refs/stash`, reflogs, packed-refs, config, hooks and the object
store are SHARED with every other lane.**

Verified 2026-08-14 from `~/workspace/mistral_karl`: its git-dir is private, but
`git rev-parse --git-path refs/stash` resolves to the *common*
`~/workspace/mistral/.git/refs/stash`, and `git stash list` shows all 7 entries,
from 6 different branches belonging to other lanes.

**Never run `git stash pop`, `git stash apply` or `git stash drop`.** There is
one shared stack. `pop` takes whatever is on top, which is almost certainly
another lane's work — this already happened once today, silently landing a July
29th `sec_edgar` change into an unrelated lane. `git stash list` is read-only and
safe.

`git stash push -m "name"` does **not** protect you: the message is a label, not
an address. Stashes are addressable only positionally (`stash@{0}`), and those
indices shift as other lanes push and pop.

**To park work, make a WIP commit on your own branch.** Branches are per-lane by
convention, so there is no collision.

**If you genuinely need stash semantics**, use a named tag instead of the stack:

```bash
sha=$(git stash create "parked work")
git tag wip/<your-lane>/<what> "$sha"
git checkout -- .
# ... later ...
git stash apply wip/<your-lane>/<what>
```

This never touches `refs/stash`, is addressable by name, cannot be consumed
accidentally (`apply` does not delete), and is not a GC candidate while the tag
exists.

**`prek` is safe — it does NOT use the stash.** Every prek-gated commit prints
`Unstaged changes detected, stashing unstaged changes to ~/.cache/prek/patches/...`.
That reads exactly like `git stash` but is not: prek writes a patch file and
re-applies it after the hooks run, leaving `refs/stash` untouched. Verified by
`karl` over ~10 prek commits with the shared stack unchanged at 7 entries. Do not
avoid prek, and do not go looking in the stash for "your" prek changes — they are
not there, and popping to find them is exactly the accident this section exists to
prevent.

Two related hazards, same root cause:

- **Do not run `git gc --prune`** without announcing it. It can destroy
  unreferenced objects other lanes depend on — dropped stashes, backup refs
  created around a rebase.
- **`cannot lock ref refs/remotes/origin/main: is at X but expected Y`** during
  a concurrent `git fetch` is structural contention on shared refs, not a bug.
  Retry it; do not debug it.

## 8. When ssh, git or a cross-cluster command suddenly fails

Vincent's laptop relays **both** the cross-cluster SSH tunnels (`bar`, `ala0`) and
the forwarded ssh-agent. When his laptop sleeps or goes offline, **both die at
once**. So `ssh bar` failing and `git push` failing are usually ONE outage, not
two bugs — and neither is yours.

Symptoms, all the same root cause:

- `connect to host 127.0.0.1 port 12222/12223: Connection refused`
- `kex_exchange_identification: Connection closed by remote host`
- `git@github.com: Permission denied (publickey)` from git, or in an srun/sbatch step
- `ssh-add -l` → `Error connecting to agent`
- a cross-cluster command that worked ten minutes ago now hangs or times out

**Get a definitive answer instead of guessing:**

```bash
~/.claude/fleet/fleet-infra-check.py
```

Exit 0 means everything is up and your failure is something else. Exit 1 names
exactly what is down. It is pre-allowlisted, so it will not prompt.

### What to do — and what NOT to do

**Do NOT retry in a loop.** The relay is not coming back until a human returns.

**Do NOT work around it.** This is the part that causes real damage: switching to
git-over-HTTPS, skipping the push and continuing as if it landed, inferring a
result you could not fetch, or "temporarily" reworking your approach around the
missing access. All of that produces work that looks finished and is not, and it
is much more expensive to unpick later than simply stopping.

**Do NOT change course of action.** A dead tunnel is not new information about
your task.

**Do this instead:**

1. File it, so the board shows it and Vincent knows on his return:

```bash
~/.claude/fleet/fleet-request.py <your-lane> --kind blocked \
  --subject "BLOCKED-BY-TUNNEL: <what you were doing>" \
  --evidence "<the exact error>" \
  --body "Exactly where to resume from once the relay is back."
```

Use the literal prefix `BLOCKED-BY-TUNNEL:` — SUPER greps for it and will tell you
the moment the relay returns.

2. **Park that thread precisely.** Write down the next command, not just the goal,
   so resuming is mechanical rather than a re-derivation.

3. **Switch to work that needs no relay** if you have any — local tests, reading,
   analysis, writing. If you have none, say so and stop. Stopping cleanly is a
   perfectly good outcome and far better than improvising.

SUPER checks the relay on every sweep and renders a **⚠ Laptop-relayed infra
DEGRADED** banner at the top of `BOARD.md` when anything is down. Check there
before assuming your environment is broken. See also the `cluster-tunnels` and
`fix-ssh` skills for the underlying mechanics.
