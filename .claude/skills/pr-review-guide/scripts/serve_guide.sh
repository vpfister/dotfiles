#!/usr/bin/env bash
# Serve a generated guide and print the URL that works from the laptop.
#
#   serve_guide.sh <dir> [port]
#
# Ports below 20000 are reserved on cluster nodes; default 20788.
# Re-serving the same dir is a no-op: the file is read from disk per request,
# so regenerating index.html is picked up without restarting.
set -euo pipefail

DIR="${1:?usage: serve_guide.sh <dir> [port]}"
PORT="${2:-20788}"
DIR="$(cd "$DIR" && pwd)"

[ -f "$DIR/index.html" ] || { echo "ERROR: no index.html in $DIR" >&2; exit 1; }

if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/"; then
  SERVED=$(curl -s "http://127.0.0.1:${PORT}/" | wc -c)
  LOCAL=$(wc -c < "$DIR/index.html")
  if [ "$SERVED" = "$LOCAL" ]; then
    echo "already serving this dir on :${PORT} (${SERVED} bytes)"
  else
    echo "WARNING: :${PORT} is serving something else (${SERVED} vs ${LOCAL} bytes)." >&2
    echo "         kill it (pkill -f \"http.server ${PORT}\") or pass another port." >&2
    exit 1
  fi
else
  cd "$DIR"
  nohup python3 -m http.server "$PORT" --bind 0.0.0.0 >/tmp/serve_guide_${PORT}.log 2>&1 &
  sleep 1.5
  curl -sf -o /dev/null "http://127.0.0.1:${PORT}/" \
    || { echo "ERROR: server did not come up; see /tmp/serve_guide_${PORT}.log" >&2; exit 1; }
  echo "started http.server on :${PORT}"
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "   http://${IP}:${PORT}/"
echo
echo "(host $(hostname); stop with: pkill -f \"http.server ${PORT}\")"
