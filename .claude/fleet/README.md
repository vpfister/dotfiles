# Fleet coordination

The protocol lives in the **`fleet` skill** — single source of truth:

    ~/.claude/skills/fleet/SKILL.md

Lanes: run `/fleet` to onboard, or read that file directly.

| Path | What |
|---|---|
| `plan.yaml`        | Declared plan (source of truth). SUPER writes, lanes read. |
| `BOARD.md`         | Live view: plan + observed fleet state. Generated, never hand-edited. |
| `board.py`         | Board generator. |
| `hook-deliver.py`  | Delivers supervisor messages at a lane's turn end. Fail-open. |
| `inbox/<lane>.md`  | Queued messages for a lane; consumed on delivery. |
| `requests/<lane>.md` | Lanes append plan-change requests here; SUPER triages. |
| `archive/<lane>.log` | Audit log of every delivery. |

Kill switch: `touch ~/.claude/fleet/DISABLED` — makes delivery inert instantly.

## Naming note

Delivery uses Claude Code's **`Stop` hook**. Despite the name, this does *not*
stop a lane. `Stop` is the event "this session has finished its turn and is about
to go idle" — the safe boundary at which we hand it any waiting mail. Nothing
interrupts a lane mid-task; the mid-task mechanism (`PreToolUse`) was deliberately
removed. Vincent handles anything genuinely urgent by hand.
