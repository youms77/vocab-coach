#!/usr/bin/env bash
# Starts vocab-coach in development mode on macOS / Linux (Windows: use start.ps1 or start.cmd).
# Usage: ./start.sh [--no-browser]
set -euo pipefail

cd "$(dirname "$0")"

missing=0
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[missing] $1 - $2" >&2
    missing=1
  fi
}
need git "https://git-scm.com/downloads"
need uv "curl -LsSf https://astral.sh/uv/install.sh | sh"
need node "install Node.js LTS from https://nodejs.org (>= 22.22)"
need npm "comes with Node.js"
if [ "$missing" -ne 0 ]; then
  exit 1
fi

node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22||(a===22&&b>=22)?0:1)' \
  || { echo "[missing] Node.js >= 22.22 required (found $(node --version))" >&2; exit 1; }

echo "==> Backend dependencies (uv sync)"
uv --directory backend sync --quiet
[ -d node_modules ] || { echo "==> Launcher dependencies"; npm install --no-fund --no-audit; }
[ -d frontend/node_modules ] || { echo "==> Frontend dependencies"; npm --prefix frontend install --no-fund --no-audit; }

if [ "${1:-}" != "--no-browser" ]; then
  export VOCAB_OPEN_BROWSER=1
fi

echo
echo "vocab-coach is starting:"
echo "  app  http://127.0.0.1:5173"
echo "  api  http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop."
echo

exec npm run dev
