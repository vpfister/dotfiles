# host-style.example.sh — per-machine tmux styling
#
# Copy this to ~/.config/host-style.sh on each machine and uncomment the block
# for the cluster you're on (or edit freely). The real file is intentionally
# NOT tracked by dotfiles — only this .example is committed.
#
# Fields:
#   name    label shown in the status pill (lowercase). Falls back to the short
#           hostname if unset.
#   accent  hex color for the pill + active pane border. The status-bar
#           background tint and inactive borders are derived from it.
#   icon    optional: mac | linux | kubernetes | server | cloud | gpu | chip |
#           microchip  (or paste a raw glyph). No CoreWeave glyph exists in Nerd
#           Fonts; 'cloud' or 'gpu' (a graphics/expansion card) fit rno best.
#   border  optional: override the active-pane-border color (defaults to accent)
#
# Colors below are catppuccin mocha accents. Hostname signature for each cluster
# is noted so you know which block to pick.

# --- ala --- slurm-eus-04a-prod-login-*
# name="ala";     accent="#cba6f7"; icon="linux"   # mauve

# --- bar --- slurm-bar-login-*
# name="bar";     accent="#fab387"; icon="linux"   # peach

# --- col --- slurm-col-login-*
# name="col";     accent="#a6e3a1"; icon="linux"   # green

# --- ice --- fs-login-*
# name="ice";     accent="#89dceb"; icon="linux"   # sky (icy)

# --- rno --- slurm-login-* (.rno-login, or bare slurm-login-...)
name="rno"
accent="#89b4fa"
icon="cloud" # blue (CoreWeave; 'gpu' also fits)

# --- sko --- slurm-sko-login-*
# name="sko";     accent="#f9e2af"; icon="linux"   # yellow

# --- staging --- slurm-staging-login-*
# name="staging"; accent="#f38ba8"; icon="linux"   # red (non-prod, caution)

# --- mac --- local laptop
# name="mac";     accent="#b4befe"; icon="mac"     # lavender

# No file / nothing set -> neutral grey (#6c7086) + short hostname label.
