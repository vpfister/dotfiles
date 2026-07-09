---
name: cluster-tunnels
description: Use when you need to reach, ssh into, run commands on, or copy files to/from one compute cluster from another that cannot route to each other directly (e.g. from rno to ala0 or bar0), or when setting up / debugging the laptop-relayed SSH tunnels that bridge them. Symptoms include `ssh ala0` failing from a cluster, kex_exchange_identification errors, or "remote port forwarding failed".
---

# Cluster-to-cluster SSH tunnels (laptop relay)

Clusters that can't reach each other directly are bridged through the **laptop**, which can reach both. The laptop runs chained SSH forwards so a "source" cluster can `ssh` straight into "destination" clusters.

**Topology**
```
source(rno):<rport>  --(-R)-->  laptop:<lport>  --(-L)-->  dest:22   # reach a dest
source(rno):<rport>  --(-R)-->  laptop:22                            # reach the laptop ("mac")
```
Currently wired: `rno -> ala0`, `rno -> bar0`, and `rno -> mac` (the laptop itself).

**Full reference / history:** Notion page *"SSH Tunnel Between Two Clusters (rno ↔ ala0) via Laptop"* — https://app.notion.com/p/3876ba59a7fe81ceb95cce8f48ef7c7d

## Key fact: tunnels are initiated from the LAPTOP only

The source cluster cannot open the tunnels itself (it can't route to the laptop or the destinations). Every forward originates on the laptop. Therefore:

- **To bring tunnels up/down:** run `cluster-tunnels` on the **laptop**.
- **If `ssh ala0` fails from the source cluster** (e.g. you are running on rno): the cause is almost always that the laptop-side tunnels are down. You **cannot** fix it from the source side — ask the user to run `cluster-tunnels up` on their laptop, then retry.

## Setup / manage tunnels — on the laptop (zsh)

The launcher is bundled in this skill dir (`cluster-tunnels`). Install it on the laptop's PATH:
```
cp ~/.claude/skills/cluster-tunnels/cluster-tunnels ~/.local/bin/ && chmod +x ~/.local/bin/cluster-tunnels
```
Commands:
```
cluster-tunnels up       # open all tunnels (default) + print source-side ssh config
cluster-tunnels down     # close all tunnels it opened
cluster-tunnels status   # show which tunnels are alive
cluster-tunnels config   # print only the source-side ~/.ssh/config block
```

- A cold `up` prompts Touch ID once per master (each destination + the source).
- Destinations are one array at the top of the script, each line `"<host>  <laptop_local_port>  <source_remote_port>"`. **Add a cluster = add one line** (pick unused ports, e.g. local `22xx` / remote `122xx`); `-L`, `-R`, and config generation follow automatically.
- Prereq: the laptop can already `ssh <source>` and `ssh <dest>`, and the laptop→source session uses agent forwarding (`ssh -A` / `ForwardAgent yes`) so the Secure-Enclave key authenticates onward to the destinations.

## One-time source-side config (e.g. on rno)

`cluster-tunnels config` prints blocks to paste into `~/.ssh/config` on the source cluster:
```
Host ala0
    HostName 127.0.0.1
    Port 12222
    User vincent.pfister
    HostKeyAlias ala0-via-tunnel
    StrictHostKeyChecking accept-new
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%C
    ControlPersist 60m
```
Create the socket dir once on the source (else `unix_listener: cannot bind to path ...`):
```
mkdir -p ~/.ssh/sockets && chmod 700 ~/.ssh/sockets
```

## Execute commands across clusters — from the source cluster

Once tunnels are up and the config is in place, each destination is just a normal ssh host on the source:
```
ssh ala0 'nvidia-smi'                   # run a command on ala0
ssh ala0 'cd ~/proj && sbatch job.sh'   # quote the remote command
scp ./file ala0:~/dest/                 # copy TO ala0
scp ala0:~/remote/file ./               # copy FROM ala0
rsync -avz ./dir/ ala0:~/dir/           # rsync over the tunnel
ssh bar0 'hostname'                     # same for bar0
```
`ControlPersist` keeps the master warm, so repeated commands reuse one connection (≈ one Touch ID per 60-min window per host).

## Reach the laptop from a cluster (host `mac`)

Same reverse leg, but pointed at the laptop's **own sshd** instead of a destination: `source:<port> -> laptop:22`. It's enabled by `EXPOSE_LAPTOP_PORT` at the top of the script (rides on the same reverse connection to the source) and adds a `Host mac` block to the printed config. From the source cluster:
```
ssh mac 'pbpaste'               # run a command on the laptop
ssh mac 'open -a Safari'        # drive laptop-only tools
scp ./file mac:~/Downloads/     # copy to the laptop
```

**Two one-time prerequisites on the Mac** (cannot be done from the cluster):

1. **Enable Remote Login AND allow your user** (two separate things): System Settings -> General -> Sharing -> **Remote Login = On** (macOS has no sshd by default), then open the ⓘ and set **Allow access for** to *All users* or add your account. Turning the service on is not enough — if your user isn't allowed, sshd reads `authorized_keys` (so the key is accepted) but then **closes the session**, showing `Connection closed` right after Touch ID (looks like a key/auth bug, but isn't).
2. **Authorize the forwarded key:** the source authenticates using the agent-forwarded Secure-Enclave key, so that key's *public* half must be in the Mac's `~/.ssh/authorized_keys`:
   ```
   ssh-add -L >> ~/.ssh/authorized_keys        # on the laptop (keep only your Secretive line)
   chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
   ```
   `ssh mac` from the source then prompts Touch ID (signing with that key) and lands on the laptop. Requires the source login to have agent forwarding (`ssh -A` / `ForwardAgent yes`), which the existing setup already uses.

## Gotchas (hard-won)

- **Use `127.0.0.1`, not `localhost`**, everywhere — `localhost` resolving to `::1` vs `127.0.0.1` silently breaks forwards (`Connection closed by ::1`).
- **The `-L` target is `localhost:22` resolved on the destination side** — never the destination's laptop-config alias (it won't resolve remotely → every forwarded connection dies with `kex_exchange_identification: Connection closed`).
- **Forwards live on the ssh ControlMaster and outlive the client process** that requested them. To change one, use `ssh -O cancel`/`ssh -O forward` — do **not** `kill` the process (the forward stays). `cluster-tunnels down` then `up` resets cleanly.
- **Editing the script (zsh):** brace forward-spec variables — `${lport}` not `$lport` — or zsh interprets `:l` as a history modifier and mangles the spec (`2200:localhost` → `2200ocalhost`, "Bad local forwarding specification").
- **macOS Remote Login is two settings:** enabling the service does not imply access — your user must also be in *Allow access for* (Sharing -> Remote Login -> ⓘ), or sshd accepts the key then drops the session (`Connection closed` right after Touch ID).
- **Restricted ports:** clusters may reject some listen ports even above 1024; bump the port if a forward is refused (`remote port forwarding failed for listen port N`).
- **Laptop sleep drops everything** — re-run `cluster-tunnels up`. For auto-reconnect across sleeps, swap `ssh -f -N` for `autossh` in the script.

## Touch ID / Secure-Enclave keys

Authenticate per *connection*, not per *operation*: `ControlPersist 60m` (already in the printed config) means one fingerprint per host per ~hour, because multiplexed sessions reuse the master without re-signing. macOS caps biometric reuse at 5 min, so longer windows come only from connection multiplexing, not from a key cache. (Secretive has no TTL setting.)
