export PATH="/opt/homebrew/bin:$PATH"

. "$HOME/.local/bin/env"
autoload -U compinit && compinit

eval "$(uv generate-shell-completion zsh)"

# Secretive Config
export SSH_AUTH_SOCK=/Users/vincent.pfister/Library/Containers/com.maxgoedjen.Secretive.SecretAgent/Data/socket.ssh

# starship
eval "$(starship init zsh)"

# tmux autostart
#if command -v tmux &> /dev/null && [ -z "$TMUX" ]; then
#    tmux attach -t default || tmux new -s default
#fi

# use vi mode
bindkey -v
export ZSH_VI_MODE_CURSOR_BLOCK=1
export KEYTIMEOUT=1

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

# Lazygit - Catppuccin Mocha Blue theme
if [[ "$(uname)" == "Darwin" ]]; then
    export LG_CONFIG_FILE="$HOME/Library/Application Support/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
else
    export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
fi
