# vocab-coach

**Turn the words you care about into words you actually use.**

vocab-coach is a free, local web app for French-speaking learners of English. You bring the words and
expressions you meet in your reading, classes or daily life; the app builds a usage sheet for each one,
walks you through a first discovery, schedules spaced reviews (FSRS), makes you produce sentences and speak,
logs your recurring errors (prepositions, tenses…) and shows your progress with real statistics.

> **Status: milestone M0 (foundation).** The app starts and shows an empty home screen. Features arrive
> milestone by milestone — see [`docs/PROGRESS.md`](docs/PROGRESS.md) and the roadmap in
> [`docs/SPEC.md`](docs/SPEC.md#9-roadmap).

![Home screen](docs/screenshots/home.png)

## Principles

- Active recall before any answer is shown; spaced repetition with FSRS.
- Words, collocations and spoken formulas learned in real context, with pitfalls for French speakers.
- Production first: sentences, paragraphs and speaking, with corrections that feed an error log.
- Free to run: only free AI tiers (Gemini, Groq, local Ollama) and the browser's speech synthesis.
  Works without any key in a degraded mode.
- Private: everything stays on your computer. Your data is never committed to the repository.

## Install on Windows 11

You need **Git**, **uv** and **Node.js LTS (≥ 22.22)**. Python is installed for you by uv.

1. Open **PowerShell** and install what is missing (skip what you already have):

   ```powershell
   winget install --id Git.Git -e
   winget install --id astral-sh.uv -e
   winget install --id OpenJS.NodeJS.LTS -e
   ```

   Close and reopen PowerShell afterwards so the new commands are found.

2. Get the code:

   ```powershell
   git clone https://github.com/<your-account>/vocab-coach.git
   cd vocab-coach
   ```

3. Check your environment (it tells you exactly what to install if something is missing):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\check-env.ps1
   ```

4. Start the app:

   ```powershell
   .\start.cmd
   ```

   or double-click `start.cmd` in File Explorer. The first run installs the dependencies (a few minutes),
   then your browser opens on <http://127.0.0.1:5173> as soon as the app answers. Press **Ctrl+C** in
   the terminal to stop. Add `-NoBrowser` to start without opening the browser.

   If you prefer PowerShell directly: `.\start.ps1` (if scripts are blocked, use
   `powershell -ExecutionPolicy Bypass -File .\start.ps1`).

### macOS / Linux

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js LTS, then:

```bash
git clone https://github.com/<your-account>/vocab-coach.git
cd vocab-coach
./start.sh
```

## Try the demo

To see the app with about two months of fictional history (decks, reviews, productions and errors)
without touching your own data:

```powershell
.\start.cmd -Demo
```

(`./start.sh --demo` on macOS / Linux.) The first demo launch generates `data/vocab-coach-demo.sqlite3`
in a few seconds and prints a summary; the top bar then shows a **Demo data** badge. Your own database
(`data/vocab-coach.sqlite3`) is never read or changed in demo mode. Start without `-Demo` to get back
to it.

Other demo commands (run from `backend/`):

| Command | What it does |
|---|---|
| `uv run python -m app --demo plan today` | Today's session plan on the demo database |
| `uv run python -m app demo seed --reset` | Rebuild the demo database (stop the app first) |
| `uv run python -m app demo seed --seed 7 --days 30 --reset` | Another reproducible history |

The same seed always produces the same data. Everything in the demo (`content/demo/`) is invented.

## Configuration

Copy `.env.example` to `.env` and fill in what you need. `.env` is ignored by Git.
The free AI keys (Gemini, Groq) are configured from milestone M2; step-by-step instructions will be added here.

## Daily use

Coming with milestones M3–M4 (import a word list, discover new terms, review).

## Backup

Your data lives in the `data/` folder (database and audio recordings), which is never committed.
Export/restore and automatic copies to a synced folder arrive in milestone M10.
Until then, back up `data/` yourself if it matters to you.

## Development

| Task | Command |
|---|---|
| Start backend + frontend | `.\start.ps1` / `./start.sh` (or `npm run dev` after `npm run setup`) |
| Run every check (lint, types, tests) | `npm run check` |
| Backend tests only | `uv --directory backend run pytest` |
| Frontend tests only | `npm --prefix frontend test` |

- API docs (development): <http://127.0.0.1:8000/docs>
- The backend only listens on `127.0.0.1`.
- CI (GitHub Actions) runs lint, type checks, tests and builds on Linux and Windows for every push.

### Repository layout

```
backend/    FastAPI app (Python 3.13, uv): api/, domain/, db/, ai/, speech/
frontend/   React + TypeScript + Vite: features/, components/, i18n/, api/
content/    error taxonomy, fictional demo dataset (demo/), later the track syllabus
docs/       SPEC.md (specification), PROGRESS.md, DECISIONS.md, architecture.md
scripts/    environment check, browser opener (wait-and-open.mjs)
```

See [`docs/architecture.md`](docs/architecture.md) for details. Contributors using Claude Code: start with
[`CLAUDE.md`](CLAUDE.md).

## Licence

[MIT](LICENSE).
