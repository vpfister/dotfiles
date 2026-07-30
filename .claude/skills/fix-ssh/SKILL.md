---
name: fix-ssh
description: Use when the forwarded SSH agent on a login pod / remote host has gone stale — "fix the stale ssh", /fix-ssh, git/ssh suddenly asks for a password or key, `ssh-add -l` says "Error connecting to agent", or `~/.ssh/agent.sock` is a dangling symlink because the agent died. Not for cluster-to-cluster tunnels (see cluster-tunnels).
---

# Fix stale SSH agent forwarding

The forwarded SSH agent died and the stable symlink `~/.ssh/agent.sock` now dangles. Shells (tmux, etc.) keep `SSH_AUTH_SOCK=~/.ssh/agent.sock`, so once it points at a dead socket, every `git`/`ssh` op loses agent auth until the link is refreshed.

**Background:** `.bashrc` pins `SSH_AUTH_SOCK` to `~/.ssh/agent.sock` and, on each Linux login, relinks it to the newest `/tmp/ssh-*/agent.*` forwarded socket. The relink only fires on a **fresh login shell with live agent forwarding** — so the cure needs a genuine reconnect from the laptop, not just a new tmux pane.

## The fix

Two halves — I do the pod side, the user does the laptop side.

**1. On the pod (I do this):** remove the dangling symlink.
```bash
rm -f ~/.ssh/agent.sock
```

**2. On the laptop (user does this):**
- Disconnect **all** SSH sessions to this pod (close every terminal / detach every connection — a lingering old connection keeps the dead forward alive).
- Reconnect with agent forwarding (`ssh -A …` or the caffeinated wrapper).

On reconnect the `.bashrc` login hook recreates `~/.ssh/agent.sock` → the new `/tmp/ssh-*/agent.*`. Existing tmux shells follow the symlink automatically.

## Verify

```bash
ssh-add -l        # should LIST keys, not "Error connecting to agent"
readlink -f ~/.ssh/agent.sock   # should resolve to a live /tmp/ssh-*/agent.* socket
```

## Diagnose first (optional)

```bash
readlink -f ~/.ssh/agent.sock                       # empty => dangling
SSH_AUTH_SOCK=~/.ssh/agent.sock ssh-add -l          # "No such file or directory" => dead
find /tmp/ssh-* -name 'agent.*' -user "$USER" 2>/dev/null   # empty => no live forward on this host
```

If a live `/tmp/ssh-*/agent.*` **does** exist but the symlink points elsewhere, just relink instead of forcing a reconnect:
```bash
ln -sf "$(find /tmp/ssh-* -name 'agent.*' -user "$USER" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2)" ~/.ssh/agent.sock
```
But if no forwarded socket exists at all (the usual case — the agent itself died), the relink can't help; the reconnect from the laptop is required.

## What I can and can't do

- ✅ Remove the symlink, diagnose, relink to an existing live socket, verify afterward.
- ❌ Reconnect the laptop's SSH — that's a manual user action. State it clearly and stop there.
