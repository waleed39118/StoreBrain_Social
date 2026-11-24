#!/usr/bin/env bash
# Atheer installation for macOS and Linux.
set -euo pipefail
cd "$(dirname "$0")"
echo "============================================"
echo "  Atheer - installation / تثبيت أثير"
echo "============================================"

PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[!] Python 3.11 or newer is required: https://www.python.org/downloads/"
  exit 1
fi

[ -d .venv ] || "$PY" -m venv .venv
echo "Installing Atheer and its libraries (first time takes a few minutes)..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python scripts/setup_env.py

read -r -p "Add demo data (doctor, patients, two appointments today)? [Y/n] " ans || ans="y"
case "${ans:-y}" in
  [Nn]*) ;;
  *) .venv/bin/atheer-admin seed-demo --with-appointments || true ;;
esac
echo
echo "Done. Run ./start.sh to launch Atheer."
