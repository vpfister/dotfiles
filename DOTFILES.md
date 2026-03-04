# Dotfiles

Personal dotfiles managed with a [bare git repository](https://www.atlassian.com/git/tutorials/dotfiles) pattern.
Tracks configuration for: **nvim**, **tmux**, **zsh** (macOS), **bash** (Linux), **alacritty**, **ghostty**.

---

## How it works

A bare git repo lives at `~/.dotfiles/`. The work tree is `~` (your home directory).
The `dotfiles` alias wraps git to use this setup:

```bash
alias dotfiles='git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
```

No symlinks. Files live at their real paths. Only explicitly added files are tracked.

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

## What is NOT tracked

The following are intentionally excluded and must be managed per machine:

- `~/.ssh/` — SSH keys and config
- `~/.gnupg/` — GPG keys
- `~/.netrc` — credentials
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
