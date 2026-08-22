---
name: fix-ssh
description: Use when SSH-agent auth fails on a login pod / cluster. Two cases. (1) Stale agent — "fix the stale ssh", /fix-ssh, git/ssh suddenly asks for a password or key, `ssh-add -l` says "Error connecting to agent", `~/.ssh/agent.sock` dangles. (2) Agent alive but `SSH_AUTH_SOCK` unset — `git@github.com: Permission denied (publickey)` from a non-interactive `ssh host 'cmd'`, an srun/sbatch step, or registry-touching tooling (composite_token_count, dataset registration) while interactive shells work fine; also covers why `ssh -A` and gh-over-HTTPS do not work for mistralai repos. Not for cluster-to-cluster tunnels (see cluster-tunnels).
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

---

# Different failure: agent is ALIVE but `SSH_AUTH_SOCK` isn't set

Do not confuse this with the dangling-symlink case above. Here `~/.ssh/agent.sock` resolves
fine and holds the keys — the variable just isn't in the environment.

**Symptom.** `git@github.com: Permission denied (publickey)` from a **non-interactive** context
on a cluster — a `ssh host 'cmd'` one-liner, an `srun`/`sbatch` step, or any tool launched by
Slurm — while interactive shells on the same host do git fine.

**Cause.** `.bashrc` pins `SSH_AUTH_SOCK=~/.ssh/agent.sock`, but `.bashrc` is not sourced for
non-interactive shells or Slurm job steps. The forwarded agent is healthy; nothing points at it.

**Fix — export it explicitly in the job/command:**
```bash
export SSH_AUTH_SOCK=$HOME/.ssh/agent.sock
```

**Verify:**
```bash
SSH_AUTH_SOCK=$HOME/.ssh/agent.sock ssh-add -l                      # lists keys
SSH_AUTH_SOCK=$HOME/.ssh/agent.sock ssh -T git@github.com           # "Hi <user>! You've successfully authenticated"
SSH_AUTH_SOCK=$HOME/.ssh/agent.sock git -C <repo> ls-remote --heads origin main   # read-only, safe
```

## Why this bites harder than it looks

The shared registry loader (`packages/shared_public/src/shared_public/registry.py`) runs
`git checkout main && git fetch origin && git merge --ff-only origin/main` on **every** registry
access, with no env override for `allow_git_pull`. So on a cluster without agent auth in scope,
anything that touches the dataset registry dies — e.g.
`python -m tools.mint.composite_token_count`, dataset registration, recipe resolution — with a
`publickey` assertion that looks nothing like a registry problem.

## Dead ends — do not retry these

- **`ssh -A <host>`** does not help when reaching the cluster through the laptop-relayed tunnel:
  `SSH_AUTH_SOCK` comes back unset. The persistent `~/.ssh/agent.sock` symlink is the mechanism
  that works; use it.
- **`gh` as a git credential helper** is a dead end for `mistralai` repos, even though
  `gh auth status` shows a valid token with `repo` scope and `gh auth setup-git` is configured.
  Rewriting SSH→HTTPS (`git config --global url."https://github.com/".insteadOf "git@github.com:"`)
  gets you: `remote: Personal access tokens (classic) are forbidden from accessing this repository`
  → HTTP 403. The org blocks classic PATs. If you tried the rewrite, undo it — otherwise it
  silently redirects every SSH remote to a forbidden HTTPS path:
  ```bash
  git config --global --unset url."https://github.com/".insteadOf
  ```
- **Generating a new SSH key on the cluster** is unnecessary if `~/.ssh/agent.sock` already lists
  keys. Check `ssh-add -l` through the socket *before* creating credentials. (Registering one via
  `gh ssh-key add` would also likely fail: the usual token has `read:public_key` but not
  `write:public_key`/`admin:public_key`.)

## Caveat

The agent socket lives only as long as the laptop's forwarded connection. If the tunnel drops,
long-running Slurm jobs that need git will start failing mid-flight. For unattended work, prefer
running registry-touching steps on a cluster with native GitHub access (RNO) rather than depending
on a forwarded agent surviving for hours.
