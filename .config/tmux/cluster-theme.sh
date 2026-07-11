#!/usr/bin/env bash
# Per-machine tmux status styling driven by ~/.config/host-style.sh
#
# Reads name/accent/icon/border from the (git-excluded) per-machine config,
# derives a subtle tinted background + subdued/active border colors from the
# accent, and pushes everything into tmux options consumed by .tmux.conf.
# Re-run automatically on `<prefix> r` (source-file). No config -> neutral.
set -u

# ---- catppuccin mocha base --------------------------------------------------
base_r=30; base_g=30; base_b=46          # #1e1e2e

# blend <hex> <accent-percent> -> "#rrggbb" (accent mixed into the base)
blend() {
  local hex=${1#\#} a=$2
  local r=$((16#${hex:0:2})) g=$((16#${hex:2:2})) b=$((16#${hex:4:2}))
  printf '#%02x%02x%02x' \
    $(( (base_r*(100-a) + r*a) / 100 )) \
    $(( (base_g*(100-a) + g*a) / 100 )) \
    $(( (base_b*(100-a) + b*a) / 100 ))
}

# ---- read per-machine config (optional) -------------------------------------
name=""; accent=""; icon=""; border=""
config="${HOST_STYLE_CONFIG:-$HOME/.config/host-style.sh}"
# shellcheck source=/dev/null
[ -r "$config" ] && . "$config"

# ---- fallbacks --------------------------------------------------------------
: "${accent:=#6c7086}"                                    # neutral overlay grey
: "${name:=$(hostname -s 2>/dev/null || hostname)}"       # short hostname
border="${border:-$accent}"

tint=$(blend "$accent" 18)   # status-bar background (dark, smooth)
mid=$(blend "$accent" 40)    # inactive pane borders (subdued)

# ---- icon glyph (nerd font) -------------------------------------------------
# Glyphs are emitted as raw UTF-8 byte escapes (\xHH) via printf: this keeps the
# file pure ASCII (literal PUA glyphs get stripped by some editors) AND works on
# macOS /bin/bash 3.2, whose printf does NOT support \u/\U (bash 4.2+ only).
case "$icon" in
  mac|apple)       glyph=$(printf '\xef\x85\xb9')     ;;  # nf-fa-apple
  linux)           glyph=$(printf '\xef\x85\xbc')     ;;  # nf-fa-linux
  kubernetes|k8s)  glyph=$(printf '\xf3\xb1\x93\xbe') ;;  # nf-md-kubernetes
  server)          glyph=$(printf '\xef\x91\xb3')     ;;  # nf-oct-server
  cloud)           glyph=$(printf '\xef\x83\x82')     ;;  # nf-fa-cloud
  gpu)             glyph=$(printf '\xf3\xb0\xa2\xae') ;;  # nf-md-expansion_card
  chip)            glyph=$(printf '\xf3\xb0\x98\x9a') ;;  # nf-md-chip
  microchip)       glyph=$(printf '\xef\x8b\x9b')     ;;  # nf-fa-microchip
  "")              glyph=""                      ;;
  *)               glyph=$icon                   ;;  # raw glyph passthrough
esac
[ -n "$glyph" ] && label="$glyph $name" || label="$name"

# ---- push into tmux ---------------------------------------------------------
tmux set -g @cluster_name   "$label"
tmux set -g @cluster_accent "$accent"

# Rounded pill caps for status-left (also built at runtime, same reason).
tmux set -g @cluster_lcap "$(printf '\xee\x82\xb6')"   # left half-circle
tmux set -g @cluster_rcap "$(printf '\xee\x82\xb4')"   # right half-circle

# styles do not format-expand, so set them directly here
tmux set -g status-style              "bg=$tint"
tmux set -g pane-border-style         "fg=$mid"
tmux set -g pane-active-border-style  "fg=$border"
