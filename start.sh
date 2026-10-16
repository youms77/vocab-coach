#!/usr/bin/env bash
# Starts vocab-coach in development mode on macOS / Linux (Windows: use start.ps1 or start.cmd).
# Usage: ./start.sh [--no-browser] [--demo]
#   --demo  fictional demo data in data/vocab-coach-demo.sqlite3 (your database is not touched)
set -euo pipefail

cd "$(dirname "$0")"

open_browser=1
demo=0
for arg in "$@"; do
  case "$arg" in
    --no-browser) open_browser=0 ;;
    --demo) demo=1 ;;
    *) echo "Unknown option: $arg (use --no-browser and/or --demo)" >&2; exit 2 ;;
  esac
done

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

if [ "$demo" -eq 1 ]; then
  # Read by the backend settings: every command below and the API use the demo database.
  export VOCAB_DEMO=1
  echo "Demo mode: data/vocab-coach-demo.sqlite3 (fictional data; your database is not touched)."
else
  unset VOCAB_DEMO
fi

# Creates the database on first run, applies new migrations, loads the error taxonomy.
echo "==> Database (migrations + error taxonomy)"
uv --directory backend run python -m app db upgrade || {
  echo "The database could not be prepared (see the message above). The app was not started." >&2
  exit 1
}
if [ "$demo" -eq 1 ]; then
  # Generates the demo history the first time only (a few seconds).
  echo "==> Demo data"
  uv --directory backend run python -m app demo seed --if-missing || {
    echo "The demo data could not be generated (see the message above). The app was not started." >&2
    exit 1
  }
fi
[ -d node_modules ] || { echo "==> Launcher dependencies"; npm install --no-fund --no-audit; }
[ -d frontend/node_modules ] || { echo "==> Frontend dependencies"; npm --prefix frontend install --no-fund --no-audit; }

# scripts/wait-and-open.mjs opens the browser once the API answers, only when this is set.
if [ "$open_browser" -eq 1 ]; then
  export VOCAB_OPEN_BROWSER=1
else
  unset VOCAB_OPEN_BROWSER
fi

echo
echo "vocab-coach is starting:"
echo "  app  http://127.0.0.1:5173"
echo "  api  http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop."
echo

exec npm run dev
