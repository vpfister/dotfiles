# dotfiles


These configuration files are managed with [chezmoi](https://www.chezmoi.io/).

# dotfiles


These configuration files are managed with [chezmoi](https://www.chezmoi.io/).

## TLDR;

Short installation guide for a new machine.

### 1. preliminaries

Install the following packages (for ubuntu 22.04):
```bash
# base packages
sudo apt install -y curl git libfuse2 build-essential nodejs ripgrep

# neovim
curl -LO https://github.com/neovim/neovim/releases/latest/download/nvim.appimage
chmod u+x nvim.appimage
mkdir -p ~/bin
mv nvim.appimage ~/bin/nvim.appimage
ln -s ~/bin/nvim.appimage ~/bin/nvim
source ~/.profile

# modify CapsLock -> Esc
dconf write /org/gnome/desktop/input-sources/xkb-options "['caps:escape']"
```

Install `chezmoi` with:
```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply https://github.com/vpfister/dotfiles.git
```
