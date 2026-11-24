#!/usr/bin/env bash
# Start Atheer and open the home page in the browser. Press Ctrl+C to stop.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/atheer-server ]; then
  echo "Atheer is not installed yet. Run ./install.sh first."
  exit 1
fi
URL="http://127.0.0.1:8000/"
( sleep 2; (command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") || true ) >/dev/null 2>&1 &
echo "Atheer is running at $URL  (Ctrl+C to stop)"
exec .venv/bin/atheer-server
