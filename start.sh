#!/usr/bin/env bash
# Starts vocab-coach in development mode on macOS / Linux (Windows: use start.ps1 or start.cmd).
# Usage: ./start.sh [--no-browser] [--demo] [--use] [--rebuild]
#   --demo     fictional demo data in data/vocab-coach-demo.sqlite3 (your database is not touched)
#   --use      daily use: one process on http://127.0.0.1:8000 serving the built frontend, no reload
#   --rebuild  with --use: build the frontend even if it looks up to date
set -euo pipefail

cd "$(dirname "$0")"

open_browser=1
demo=0
use=0
rebuild=0
for arg in "$@"; do
  case "$arg" in
    --no-browser) open_browser=0 ;;
    --demo) demo=1 ;;
    --use) use=1 ;;
    --rebuild) rebuild=1 ;;
    *) echo "Unknown option: $arg (use --no-browser, --demo, --use, --rebuild)" >&2; exit 2 ;;
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

if [ "$use" -eq 1 ]; then
  [ -d node_modules ] || { echo "==> Launcher dependencies"; npm install --no-fund --no-audit; }
  [ -d frontend/node_modules ] || { echo "==> Frontend dependencies"; npm --prefix frontend install --no-fund --no-audit; }

  # Build when the build is missing or a source is newer than index.html (or with --rebuild).
  stale=$rebuild
  if [ ! -f frontend/dist/index.html ]; then
    stale=1
  elif [ -n "$(find frontend/src frontend/index.html frontend/package.json frontend/vite.config.* -type f -newer frontend/dist/index.html -print -quit)" ]; then
    stale=1
  fi
  if [ "$stale" -eq 1 ]; then
    echo "==> Frontend build (npm run build)"
    npm --prefix frontend run build
  else
    echo "==> Frontend build is up to date"
  fi

  echo "==> Database (copy before upgrade, migrations, error taxonomy)"
  uv --directory backend run python -m app db prepare || {
    echo "The database was not prepared (see the message above). The app was not started." >&2
    exit 2
  }
  if [ "$demo" -eq 1 ]; then
    echo "==> Demo data"
    uv --directory backend run python -m app demo seed --if-missing || {
      echo "The demo data could not be generated (see the message above). The app was not started." >&2
      exit 1
    }
  fi

  # One fixed port: another port would be another origin and the browser would lose its preferences.
  port="${VOCAB_PORT:-8000}"
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use. If vocab-coach is already running, close it and start again." >&2
    exit 2
  fi

  export VOCAB_USE_MODE=1
  if [ "$open_browser" -eq 1 ]; then
    export VOCAB_OPEN_BROWSER=1
    node scripts/wait-and-open.mjs &
  else
    unset VOCAB_OPEN_BROWSER
  fi
  echo
  echo "vocab-coach is starting:"
  echo "  app  http://127.0.0.1:$port"
  echo "  api  http://127.0.0.1:$port/docs"
  echo "Press Ctrl+C to stop."
  echo
  exec uv --directory backend run python -m app --use
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
