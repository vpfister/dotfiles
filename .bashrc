# ~/.bashrc: executed by bash(1) for non-login shells.

# --- Interactive guard ---
case $- in
*i*) ;;
*) return ;;
esac

# --- History & shell options ---
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s checkwinsize

# --- Linux-specific defaults ---
if [[ "$(uname)" == "Linux" ]]; then
  [ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

  # debian chroot indicator
  if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
  fi

  # fallback prompt (overridden by starship below)
  case "$TERM" in
  xterm-color | *-256color | xterm-ghostty) color_prompt=yes ;;
  esac
  if [ "$color_prompt" = yes ]; then
    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
  else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '
  fi
  unset color_prompt
  case "$TERM" in
  xterm* | rxvt*)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
  esac

  # color support for ls/grep
  if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
  fi
fi

# --- Common aliases ---
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias dotfiles='git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
command -v lazygit &>/dev/null && alias lgdots='lazygit --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

if [ -f ~/.bash_aliases ]; then
  . ~/.bash_aliases
fi

# --- Bash completion (Linux) ---
if [[ "$(uname)" == "Linux" ]]; then
  if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
      . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
      . /etc/bash_completion
    fi
  fi
fi

# --- Machine-specific: Slurm/Mistral environment ---
if [[ -f /mnt/vast/shared/config/.bashrc ]]; then
  source /mnt/vast/shared/config/.bashrc
  export ACCOUNT=vincent.pfister
  export SBATCH_ACCOUNT=discovery
  export SLURM_ACCOUNT=discovery
  export SALLOC_ACCOUNT=discovery
  export MISTRAL_ROOT="$HOME/workspace/mistral"

  # Anthropic/Claude env vars (Foundry-specific)
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
  export CLAUDE_CODE_USE_FOUNDRY=1
  export ANTHROPIC_FOUNDRY_API_KEY='dont-worry-this-key-will-be-auto-injected'
  export ANTHROPIC_FOUNDRY_BASE_URL=http://codex-foundry-proxy.tenant-slurm/anthropic
  export ANTHROPIC_MODEL='claude-opus-4-6[1m]'
  export ANTHROPIC_SMALL_FAST_MODEL='claude-haiku-4-5@20251001'
fi

# --- PATH additions ---
export PATH="$HOME/.local/bin:$PATH"
[ -d "$HOME/.npm-global/bin" ] && export PATH="$HOME/.npm-global/bin:$PATH"

# --- Editor ---
export EDITOR=nvim
export VISUAL=nvim

# --- Terminal fixes ---
# Ghostty terminfo fallback
if [ "$TERM" = "xterm-ghostty" ] && ! infocmp xterm-ghostty &>/dev/null; then
  export TERM=xterm-256color
fi

# Ensure COLORTERM is set for truecolor support (SSH doesn't forward it)
if [ -n "$SSH_CONNECTION" ] && [ -z "$COLORTERM" ]; then
  export COLORTERM=truecolor
fi

# --- macOS-specific ---
if [[ "$(uname)" == "Darwin" ]]; then
  export SSH_AUTH_SOCK="$HOME/Library/Containers/com.maxgoedjen.Secretive.SecretAgent/Data/socket.ssh"
fi

# --- Lazygit - Catppuccin Mocha Blue theme ---
if [[ "$(uname)" == "Darwin" ]]; then
  export LG_CONFIG_FILE="$HOME/Library/Application Support/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
else
  export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
fi

# --- Tool initialization ---
eval "$(uvx --generate-shell-completion bash)"

# fzf keybindings and completion (Linux)
if [[ "$(uname)" == "Linux" ]]; then
  [ -f /usr/share/doc/fzf/examples/key-bindings.bash ] && source /usr/share/doc/fzf/examples/key-bindings.bash
  [ -f /usr/share/bash-completion/completions/fzf ] && source /usr/share/bash-completion/completions/fzf
fi

# direnv
command -v direnv &>/dev/null && eval "$(direnv hook bash)"
command -v direnv &>/dev/null && alias tmux='direnv exec / tmux'

eval "$(starship init bash)"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
