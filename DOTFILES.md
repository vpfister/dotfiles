# Dotfiles

Personal dotfiles managed with a [bare git repository](https://www.atlassian.com/git/tutorials/dotfiles) pattern.
Tracks configuration for: **nvim**, **tmux**, **zsh** (macOS), **bash** (Linux), **alacritty**, **ghostty**, **Claude Code**, **opencode**, **herdr**.

---

## How it works

A bare git repo lives at `~/.dotfiles/`. The work tree is `~` (your home directory).
The `dotfiles` alias wraps git to use this setup:

```bash
alias dotfiles='git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
```

Most files live at their real paths. Agent configuration uses relative symlinks;
both a link and its target must be explicitly added to the repo.

---

## Setting up a new machine

### 1. Install prerequisites

Make sure `git` is available. On macOS, also install [Homebrew](https://brew.sh).

### 2. Clone the bare repo

```bash
git clone --bare git@github.com:vpfister/dotfiles.git ~/.dotfiles
```

### 3. Define the alias temporarily

```bash
alias dotfiles='git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
```

### 4. Checkout the files

There will likely be conflicts with existing config files on the machine.
This script backs them up automatically before checking out:

```bash
# Back up any conflicting files
dotfiles checkout 2>&1 \
  | grep -E "^\s+" \
  | awk '{print $1}' \
  | xargs -I{} sh -c 'mkdir -p ~/.dotfiles-backup/$(dirname {}) && mv ~/{} ~/.dotfiles-backup/{}'

# Now check out
dotfiles checkout

# Hide untracked files from status output
dotfiles config status.showUntrackedFiles no
```

Conflicting files are moved to `~/.dotfiles-backup/` with their directory structure preserved.
Review them afterwards and keep anything you want to merge back in.

### 5. Reload your shell

```bash
source ~/.zshrc   # macOS
source ~/.bashrc  # Linux
```

The `dotfiles` alias is now permanently available.

---

## Keeping a machine up to date (pull)

```bash
dotfiles pull
```

If you have local modifications to tracked files, stash them first:

```bash
dotfiles stash
dotfiles pull
dotfiles stash pop
```

---

## Pushing changes to the repo

### Add and commit a changed file

```bash
dotfiles add ~/.config/nvim/lua/config/keymaps.lua
dotfiles commit -m "nvim: update keymaps"
dotfiles push
```

### Add a new config file

```bash
dotfiles add ~/.config/ghostty/config
dotfiles commit -m "ghostty: initial config"
dotfiles push
```

### Check what has changed

```bash
dotfiles status       # tracked files with changes
dotfiles diff         # see the actual diff
```

### Before committing

Since `showUntrackedFiles` is set to `no`, newly created files won't appear in `dotfiles status`. Before committing, verify that no required untracked files are missing. Use targeted status checks to surface them:

```bash
dotfiles status -u <directory>/
```

---

## OS-specific configuration

Some files contain conditional blocks to handle macOS vs Linux differences.
Use the following patterns:

**zsh / bash:**
```bash
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS-specific
else
    # Linux-specific
fi
```

**tmux (`~/.tmux.conf`):**
```tmux
if-shell "uname | grep -q Darwin" "set -g default-command 'reattach-to-user-namespace -l zsh'"
```

**nvim (`init.lua` or any plugin file):**
```lua
if vim.fn.has("mac") == 1 then
    -- macOS-specific
end
```

---

## Rust toolchain (rustup / cargo)

Rust is installed per-user via [rustup](https://rustup.rs), independent of any system packages.
Everything lives under `~/.rustup/` (toolchains) and `~/.cargo/` (binaries, registry).

### Install on a new machine

```bash
# Install rustup + stable toolchain (non-interactive)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Source in the current shell
. "$HOME/.cargo/env"

# (Optional) Extra cargo binaries
cargo install starship --locked
cargo install ripgrep fd-find bat --locked
cargo install slurmer tree-sitter-cli
```

The installer adds `. "$HOME/.cargo/env"` to shell configs, which prepends `~/.cargo/bin` to `$PATH` so user-installed Rust takes precedence over any system version.

The dotfiles already source `~/.cargo/env` in `.bashrc`, `.profile`, and `.zshrc`, so after `dotfiles checkout` you only need the `curl` + `cargo install` steps above.

---

## Touch ID for sudo (macOS, incl. inside tmux)

Make `sudo` accept Touch ID — and crucially make it work **inside tmux**, where it
otherwise silently falls back to the password prompt (tmux runs outside the GUI/Aqua
session, so the Touch ID dialog can't be shown without a reattach shim).

Per machine (not tracked — `/etc/pam.d/` is a system path):

```bash
brew install pam-reattach
# pam_reattach MUST come before pam_tid; the brew "opt" path survives version upgrades
sudo tee /etc/pam.d/sudo_local >/dev/null <<EOF
auth       optional       $(brew --prefix pam-reattach)/lib/pam/pam_reattach.so
auth       sufficient     pam_tid.so
EOF
```

Verify and test **inside tmux**:

```bash
cat /etc/pam.d/sudo_local          # pam_reattach line first, then pam_tid
sudo -k && sudo ls                 # should prompt Touch ID, not a password
```

Notes / gotchas:

- `/etc/pam.d/sudo` already `include`s `sudo_local` on macOS 13+, and `sudo_local`
  survives OS updates (unlike editing `/etc/pam.d/sudo` directly).
- Only `pam_tid.so` (no `pam_reattach`) → Touch ID works in a **plain terminal but not
  in tmux**. That's the usual symptom.
- Order matters: `pam_reattach` must be the **first** `auth` line so it reattaches to
  the Aqua session before `pam_tid` tries to show the fingerprint dialog.
- **Clamshell / lid closed:** the Touch ID sensor is unavailable, so sudo falls back to
  the password regardless of config.
- A stale tmux **server** that predates this setup won't pick it up — `tmux kill-server`
  and reopen tmux from a GUI terminal (PAM itself is re-read per `sudo` call, so no
  restart is needed once the server is GUI-born).

---

## Claude Code (`~/.claude/`)

Hand-written config and selected skills are tracked; runtime state is not.

Tracked: `CLAUDE.md`, `settings.json`, `sp.md` and its `output-styles/sp.md`
symlink, `statusline.sh`, the hook scripts (`mode-mirror.sh`,
`notify-needs-input.sh`), and portable skills and skill links.

Not tracked: `settings.local.json` (auth env vars), `.credentials.json`, and all runtime
state — `sessions/`, `projects/*/memory/`, `file-history/`, `backups/`, `daemon*`,
`plugins/`, `jobs/`, `tasks/`. Fleet code, protocol, and state under `fleet/`,
and project instructions and references under `projects/`, are local to the
cluster and not tracked here. On RNO, the fleet code and project references
link to `~/workspace/mistral_agent_ops/scripts/vpfister/agent_ops/`.

`settings.json` invokes the optional local fleet and Herdr hooks only when
their scripts exist. Other hook scripts it invokes must be tracked.

---

## Codex and shared skills

`~/.codex/AGENTS.md` links to `~/.claude/CLAUDE.md`. Codex discovers personal
skills in `~/.agents/skills/`. Selected skill directories there link to the
tracked Claude skills; `find-skills`, `herdr`, Finance QA, and KARL live in
`~/.agents/skills/` and Claude links to them. Finance QA and KARL have small
portable entry points; their detailed local references are not tracked here.
Vibe links to the same instructions and skills. Keep portable relative
symlinks and their targets tracked.

Codex's live `config.toml`, authentication, hooks, rules, and runtime state are
currently machine-specific and are not tracked. The installer-generated
`~/.agents/.skill-lock.json` is also not tracked.

---

## Agent GitHub access on Linux

Tracked files: `.local/bin/with-agent-github`,
`.config/git/agent-github.gitconfig`, and the `cc`/`cdx` aliases in `.bashrc`
and `.zshrc`. On Linux, those aliases give only the agent process a Git config
that rewrites the canonical SSH URLs for `mistralai/mistral`, `vortex`, and
`registry` to HTTPS and uses the local `gh` OAuth login. Ordinary terminal Git
commands keep using SSH; stored remotes are unchanged. On macOS the aliases keep
their previous behavior, and the wrapper itself is a pass-through.

The helper uses `$HOME` and finds `gh` through `PATH`; it has no cluster-specific
paths. It preserves existing `GIT_CONFIG_*` settings and clears `GH_TOKEN` and
`GITHUB_TOKEN` only in its child process so an inherited token cannot override
the chosen local login. Linux `cdx` disables the daemon and preserves the Git
variables, including names containing `KEY`.

### Bootstrap each independent cluster home

1. Install `git`, `gh`, and the agent CLI on `PATH`. Codex must support the flags
   used by `cdx`. Check out these dotfiles, then open a new shell. Existing shells
   and running agents retain their previous aliases/environment.
2. If that home has no working GitHub CLI login, run:

   ```bash
   env -u GH_TOKEN -u GITHUB_TOKEN gh auth login --hostname github.com --web --git-protocol ssh --skip-ssh-key
   ```

   Complete browser/organization SSO authorization once. An existing working
   OAuth login can be reused. Nodes sharing a home/config store share that login;
   independent cluster homes need separate provisioning. Classic PATs are
   forbidden by Mistral policy.
3. Keep authentication local and untracked. `gh auth status` reports the store
   location; normally it is `~/.config/gh/hosts.yml` on a headless Linux host.
   Protect the directory with mode 0700 and credential file with 0600. Respect
   `GH_CONFIG_DIR` or `XDG_CONFIG_HOME` if customized. Never put credentials in
   dotfiles, remote URLs, or shell startup exports. Check the lifetime/refresh
   behavior of each newly issued credential rather than assuming it matches
   another cluster's token.
4. Verify cluster-managed GitHub/API egress and any organization IP policy. A
   valid token cannot replace a network route that depends on the laptop.
   Confirm the organization's requirements for long-term headless credentials.

After provisioning, these read-only checks should succeed without SSH forwarding:

```bash
with-agent-github gh api user --jq .login
env -u SSH_AUTH_SOCK GIT_SSH_COMMAND=false with-agent-github git -C "$HOME/workspace/mistral" ls-remote origin HEAD
env -u SSH_AUTH_SOCK GIT_SSH_COMMAND=false with-agent-github git -C "$HOME/workspace/vortex" ls-remote origin HEAD
```

The account should be `vpfister`. Compare `git remote get-url origin` with
`with-agent-github git remote get-url origin`: ordinary Git should report SSH,
the wrapper HTTPS. `git config --local --get remote.origin.url` should still
report the stored SSH URL.

Non-interactive jobs opt in with `~/.local/bin/with-agent-github COMMAND ...`;
they do not rely on interactive aliases. Slurm/container launchers must preserve
`GIT_CONFIG_*`, provide the intended home/config store, and expose `gh` on PATH.
Add repository-specific config entries only when a job needs another private
dependency. GitHub PR/API commands use OAuth in both human and agent sessions;
SSH authenticates Git transport only.

Revocation or loss of SSO access requires human reauthorization. For rotation,
validate a replacement, update all runtime consumers and backups, then revoke
the old token individually. `gh auth logout` only removes local configuration;
revoking the whole GitHub CLI app grant affects other devices too. Bitwarden
can hold a management/backup copy but is not a runtime unlock dependency.

---

## What is NOT tracked

The following are intentionally excluded and must be managed per machine:

- `~/.ssh/` — SSH keys and config
- `~/.gnupg/` — GPG keys
- `~/.netrc` — credentials
- `~/.config/gh/` — GitHub CLI login and machine-local configuration
- VPN configuration
- Any file containing tokens, secrets, or API keys
- `~/.config/tmux/plugins/` — installed by TPM on each machine

---

## Adding a new machine-specific app

When you configure a new app (e.g. alacritty on a new Linux machine):

```bash
dotfiles add ~/.config/alacritty/alacritty.toml
dotfiles commit -m "alacritty: initial config"
dotfiles push
```

On machines where that app isn't installed, the config file will simply be present but unused — that's fine.
