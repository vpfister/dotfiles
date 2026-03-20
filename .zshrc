export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
[ -d "$HOME/.npm-global/bin" ] && export PATH="$HOME/.npm-global/bin:$PATH"

[ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
autoload -U compinit && compinit

eval "$(uv generate-shell-completion zsh)"

# Secretive Config
export SSH_AUTH_SOCK=/Users/vincent.pfister/Library/Containers/com.maxgoedjen.Secretive.SecretAgent/Data/socket.ssh

# direnv
command -v direnv &>/dev/null && eval "$(direnv hook zsh)"
command -v direnv &>/dev/null && alias tmux='direnv exec / tmux'

# starship
eval "$(starship init zsh)"

# tmux autostart
#if command -v tmux &> /dev/null && [ -z "$TMUX" ]; then
#    tmux attach -t default || tmux new -s default
#fi

# use vi mode
bindkey -v
bindkey '^R' history-incremental-search-backward
export ZSH_VI_MODE_CURSOR_BLOCK=1
export KEYTIMEOUT=1

export EDITOR=nvim
export VISUAL=nvim

# aliases
alias ll="ls -al --color=auto"
alias tailscale=/Applications/Tailscale.app/Contents/MacOS/Tailscale

export LS_COLORS="di=1;36:ln=35:so=32:pi=33:ex=31:bd=34;46:cd=34;43:su=30;41:sg=30;46:tw=30;42:ow=30;43"

export CLAUDE_CODE_USE_FOUNDRY=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export ANTHROPIC_FOUNDRY_BASE_URL='https://foundry-proxy.cheetah-koi.ts.net/anthropic'
export ANTHROPIC_FOUNDRY_API_KEY='dont-worry-this-key-will-be-auto-injected'
export ANTHROPIC_DEFAULT_OPUS_MODEL='claude-opus-4-6'
export ANTHROPIC_DEFAULT_SONNET_MODEL='claude-sonnet-4-6'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='claude-haiku-4-5'

# Dotfiles bare repo management
alias dotfiles='git --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'
command -v lazygit &>/dev/null && alias lgdots='lazygit --git-dir=$HOME/.dotfiles/ --work-tree=$HOME'

# Lazygit - Catppuccin Mocha Blue theme
export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml"

# --- Yazi wrapper (cd on exit) ---
if command -v yazi &>/dev/null; then
  function y() {
    local tmp="$(mktemp -t "yazi-cwd.XXXXXX")"
    yazi "$@" --cwd-file="$tmp"
    if cwd="$(cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
      cd -- "$cwd"
    fi
    rm -f -- "$tmp"
  }
fi

# --- Terminal fixes ---
# Ghostty terminfo fallback
if [ "$TERM" = "xterm-ghostty" ] && ! infocmp xterm-ghostty &>/dev/null; then
  export TERM=xterm-256color
fi

# Ensure COLORTERM is set for truecolor support (SSH doesn't forward it)
if [ -n "$SSH_CONNECTION" ] && [ -z "$COLORTERM" ]; then
  export COLORTERM=truecolor
fi
