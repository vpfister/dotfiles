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
cluster-tunnels up       # open tunnels (+ print source config); on macOS also enable Remote Login + SSH access
cluster-tunnels down     # close tunnels; on macOS also disable Remote Login
cluster-tunnels status   # tunnel state; on macOS also: is the Mac's sshd serving / is access granted
cluster-tunnels config   # print only the source-side ~/.ssh/config block
```

- A cold `up` prompts Touch ID once per master (each destination + the source).
- Destinations are one array at the top of the script, each line `"<host>  <laptop_local_port>  <source_remote_port>"`. **Add a cluster = add one line** (pick unused ports, e.g. local `22xx` / remote `122xx`); `-L`, `-R`, and config generation follow automatically.
- Prereq: the laptop can already `ssh <source>` and `ssh <dest>`, and the laptop→source session uses agent forwarding (`ssh -A` / `ForwardAgent yes`) so the Secure-Enclave key authenticates onward to the destinations.
- **macOS `mac` host:** when `EXPOSE_LAPTOP_PORT` is set and `MANAGE_MAC_SSHD="yes"` (default), `up`/`down`/`status` also start/stop/check the laptop's own Remote Login — see the `mac` section. Needs `sudo` + Full Disk Access on the terminal; set `MANAGE_MAC_SSHD=""` to leave the Mac's sshd untouched.

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

**`cluster-tunnels up` handles the Mac side for you** (when `MANAGE_MAC_SSHD="yes"`): it enables Remote Login. It no longer touches the `com.apple.access_ssh` access group — the one-time PAM fix below removes that whole moving part.

**You need, one time, on the Mac:**

1. **Decouple sshd from the SACL — `pam_sacl -> optional` (RECOMMENDED).** The macOS "Allow access for" list (`com.apple.access_ssh` group) kept resetting around sleep / Remote Login toggling and dropped the connection right after Touch ID (`pam_acct_mgmt = 7`). Make that account check non-fatal **for sshd only** so membership stops mattering:
   ```
   grep -n sacl /etc/pam.d/sshd
   sudo cp /etc/pam.d/sshd /etc/pam.d/sshd.bak
   sudo sed -i '' -E 's/^(account[[:space:]]+)required([[:space:]]+.*pam_sacl\.so)/\1optional\2/' /etc/pam.d/sshd
   grep -n sacl /etc/pam.d/sshd        # now reads "optional"
   sudo launchctl kickstart -k system/com.openssh.sshd
   ```
   Scope is **sshd-only** — each `/etc/pam.d/<service>` is a separate stack, so `sudo`, GUI login, the screensaver unlock and Screen Sharing are untouched. It removes the per-user SSH *allowlist* (the "only these users" toggle), **not** authentication: a login still needs your key/password, and sshd is only reachable over the loopback reverse tunnel. Keep the `.bak` (a macOS update may rewrite the file).
2. **Full Disk Access for your terminal** — so `up` can run `systemsetup -setremotelogin`. System Settings -> Privacy & Security -> Full Disk Access -> add your terminal -> relaunch it. Without it, `up` prints a warning and you enable Remote Login by hand.
3. **Your key in `~/.ssh/authorized_keys`** — the source authenticates with the agent-forwarded Secure-Enclave key, so its *public* half must be present:
   ```
   ssh-add -L >> ~/.ssh/authorized_keys        # on the laptop (keep only your Secretive line)
   chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
   ```

`ssh mac` from the source then prompts Touch ID (signing with that key) and lands on the laptop. Requires the source login to have agent forwarding (`ssh -A` / `ForwardAgent yes`), which the existing setup already uses.

### Keeping sshd loaded between runs — the per-minute maintainer

With the SACL decoupled (above), the only thing that can still drop is the sshd LaunchDaemon itself (sleep / policy sync unloading it). So `up` installs a **root LaunchDaemon** (`com.vpfister.macssh-maintain`; toggle `MAINTAIN_MAC_ACCESS="yes"`) that re-runs `launchctl enable/bootstrap system/com.openssh.sshd` **at load and every `MAINTAIN_INTERVAL` seconds (60)** — as root, Full-Disk-Access-free, so sshd stays up even if `systemsetup` is TCC-blocked as a daemon. It persists across reboots while loaded.

- It no longer toggles Remote Login or touches the access group — with `pam_sacl -> optional` in place there's nothing to re-assert, and dropping the `systemsetup` toggle also removed the self-fight that used to reset the SACL each cycle.
- `down` removes it (bootout + rm), then disables Remote Login; `status` shows whether the plist is present. Files (both root-owned): daemon `/Library/LaunchDaemons/com.vpfister.macssh-maintain.plist`, script `/usr/local/sbin/cluster-tunnels-macssh`. Install needs sudo **once** (the visible `sudo -v`); the per-minute cycles need none.
- Verify: `sudo launchctl print system/com.vpfister.macssh-maintain`. Manual teardown: `sudo launchctl bootout system <plist> && sudo rm <plist> <script>`.
- With the PAM fix this daemon is now just sshd insurance; set `MAINTAIN_MAC_ACCESS=""` to drop it entirely if you'd rather have zero background moving parts.

## Managing the Mac's Remote Login by hand (CLI)

`cluster-tunnels up/down` do these for you, but for debugging or when Full Disk Access isn't granted (verified on macOS Tahoe 26 / OpenSSH 10.2):

```bash
# status (no sudo)
bash -c 'exec 3<>/dev/tcp/127.0.0.1/22' && echo "sshd serving" || echo "sshd down"
dseditgroup -o checkmember -m "$(whoami)" com.apple.access_ssh    # is your account allowed?
sudo systemsetup -getremotelogin                                  # "Remote Login: On/Off" (sudo)

# enable / disable  (needs the TERMINAL to have Full Disk Access)
sudo systemsetup -f -setremotelogin on
sudo systemsetup -f -setremotelogin off

# access list (SACL) — only needed if you kept pam_sacl required;
# with pam_sacl -> optional (recommended) this is moot
sudo dseditgroup -o create com.apple.access_ssh
sudo dseditgroup -o edit -a "$(whoami)" -t user com.apple.access_ssh

# restart sshd after editing /etc/ssh/sshd_config
sudo launchctl kickstart -k system/com.openssh.sshd
```

If commands run *over* ssh later hit "Operation not permitted" on `~/Desktop` etc., also grant Full Disk Access to `/usr/libexec/sshd-keygen-wrapper` (ssh sessions run in the Background launchd domain with no TCC entries).

## Troubleshooting `ssh mac` (hypotheses, not certainties)

From a long, flaky debugging session on macOS **Tahoe 26 / OpenSSH 10.2**. Treat as leads to check.

**Symptom:** `ssh mac` gets a banner + Touch ID, then `Connection closed` with no shell. The key is fine — it fails at the *account* stage.

- **Resolved cause — macOS SSH access-list (SACL).** A debug-sshd trace showed key accepted + signature verified, then `pam_acct_mgmt = 7 (permission denied)` / `Access denied ... by PAM account configuration` (`pam_sacl` + `com.apple.access_ssh`). The group kept resetting around sleep/toggling and re-adding it never proved durable (even *All users* left the group absent and still denied). **Fix that stuck: `pam_sacl -> optional` in `/etc/pam.d/sshd`** (sshd-only — see the *mac* section), which makes the account check non-fatal so membership no longer matters.
- **Username case-sensitivity** (OpenSSH 10.2 / Tahoe): the config `User`, the Mac account, and the group member must match case (`whoami`).
- **Isolate network/tunnel vs. account** — reproduce on pure loopback to rule out the IP/tunnel:
  - On the Mac: `sudo /usr/sbin/sshd -ddd -p 2223 -E /tmp/x.log`, then `ssh -p 2223 localhost` -> read the reason in `/tmp/x.log`.
  - Tunnel is healthy if, from the source, `bash -c 'exec 3<>/dev/tcp/127.0.0.1/12224; head -c 40 <&3'` returns a banner (or holds open).
- **Other suspects:** `pam_opendirectory` account denial (`log show --last 2m --predicate 'process == "opendirectoryd"' --info --debug`); or the Tahoe 26.3.x `/private/tmp/com.apple.launchd.*/Listeners` socket bug (blocks SSH pre-auth — `rm` it).

## Gotchas (hard-won)

- **Use `127.0.0.1`, not `localhost`**, everywhere — `localhost` resolving to `::1` vs `127.0.0.1` silently breaks forwards (`Connection closed by ::1`).
- **The `-L` target is `localhost:22` resolved on the destination side** — never the destination's laptop-config alias (it won't resolve remotely → every forwarded connection dies with `kex_exchange_identification: Connection closed`).
- **Forwards live on the ssh ControlMaster and outlive the client process** that requested them. To change one, use `ssh -O cancel`/`ssh -O forward` — do **not** `kill` the process (the forward stays). `cluster-tunnels down` then `up` resets cleanly.
- **Editing the script (zsh):** brace forward-spec variables — `${lport}` not `$lport` — or zsh interprets `:l` as a history modifier and mangles the spec (`2200:localhost` → `2200ocalhost`, "Bad local forwarding specification").
- **macOS Remote Login is two settings:** enabling the service does not imply access — by default your account must also be in the `com.apple.access_ssh` group (GUI *Allow access for*), or sshd accepts the key then drops the session (`Connection closed` right after Touch ID). That access state resets around sleep/toggling and never stayed put, so this setup makes the SACL check non-fatal for sshd only (`pam_sacl -> optional` in `/etc/pam.d/sshd`) instead of chasing membership. See the *mac* section / *Troubleshooting `ssh mac`*.
- **Restricted ports:** clusters may reject some listen ports even above 1024; bump the port if a forward is refused (`remote port forwarding failed for listen port N`).
- **Laptop sleep drops everything** — the reverse connection dies (re-run `cluster-tunnels up`, or use `autossh`), and on the Mac side sleep makes sshd unreachable and can reset the Remote Login access list. For an always-reachable `mac`, keep the laptop awake on AC: `sudo pmset -c sleep 0 womp 1` (add `disablesleep 1` for lid-closed, AC + airflow only).

## Touch ID / Secure-Enclave keys

Authenticate per *connection*, not per *operation*: `ControlPersist 60m` (already in the printed config) means one fingerprint per host per ~hour, because multiplexed sessions reuse the master without re-signing. macOS caps biometric reuse at 5 min, so longer windows come only from connection multiplexing, not from a key cache. (Secretive has no TTL setting.)
