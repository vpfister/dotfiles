#!/bin/sh
# Mirror permission_mode to a per-session file for the status line to read.
# Claude omits permission_mode from the status line payload, but hooks get it.
# Uses only shell builtins - this runs on every tool call.
payload=$(cat)

case "$payload" in
  *'"session_id":"'*) rest=${payload#*'"session_id":"'}; sid=${rest%%\"*} ;;
  *) exit 0 ;;
esac

case "$payload" in
  *'"permission_mode":"'*) rest=${payload#*'"permission_mode":"'}; mode=${rest%%\"*} ;;
  *) exit 0 ;;
esac

case "$sid" in ''|*/*) exit 0 ;; esac

dir="$HOME/.claude/session-mode"
[ -d "$dir" ] || mkdir -p "$dir" || exit 0
printf '%s' "$mode" > "$dir/$sid"
exit 0
