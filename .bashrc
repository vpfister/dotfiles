eval "$(uvx --generate-shell-completion bash)"
export SSH_AUTH_SOCK="$HOME/Library/Containers/com.maxgoedjen.Secretive.SecretAgent/Data/socket.ssh"

# Lazygit - Catppuccin Mocha Blue theme
if [[ "$(uname)" == "Darwin" ]]; then
    export LG_CONFIG_FILE="$HOME/Library/Application Support/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
else
    export LG_CONFIG_FILE="$HOME/.config/lazygit/config.yml,$HOME/.config/lazygit/catppuccin-mocha-blue.yml"
fi
