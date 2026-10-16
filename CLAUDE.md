# CLAUDE.md — permanent rules for Claude Code in this repository

vocab-coach is a local, single-user web app (FastAPI + React) that turns the words a French-speaking
B1 learner cares about into active English vocabulary: AI usage sheets, discovery, FSRS reviews, error
log, speaking practice, statistics. The owner is a statistics student on **Windows 11**.

## Read first, every session

1. `docs/SPEC.md` — the product specification. Its decisions are settled.
2. `docs/PROGRESS.md` — what is done, what is left, known bugs, next step.
3. `docs/DECISIONS.md` — technical decisions already taken and why.
4. The milestone prompt the owner pasted.

If the spec looks wrong, or the milestone forces you to depart from it: **stop, explain, propose the
change and wait for approval**. Never change a spec decision silently.

## Commands

Run from the repository root.

| Task | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Check tools | `.\scripts\check-env.ps1` | (checked by `start.sh`) |
| Start app (dev) | `.\start.ps1` (or double-click `start.cmd`) | `./start.sh` |
| Install / update deps | `npm run setup` | `npm run setup` |
| All checks | `npm run check` | `npm run check` |
| Create / upgrade the database | `cd backend; uv run python -m app db upgrade` | same |
| Start on the demo database | `.\start.ps1 -Demo` (or `start.cmd -Demo`) | `./start.sh --demo` |
| (Re)build the demo database | `cd backend; uv run python -m app demo seed [--reset] [--seed N] [--days N] [--anchor YYYY-MM-DD]` | same |
| Any command on the demo database | `cd backend; uv run python -m app --demo plan today` | same |
| Backend tests | `uv --directory backend run pytest` | same |
| Backend lint / format | `uv --directory backend run ruff check .` / `ruff format .` | same |
| Frontend checks | `npm --prefix frontend run check` (typecheck + oxlint + vitest) | same |
| Frontend build | `npm --prefix frontend run build` | same |

URLs in development: app `http://127.0.0.1:5173`, API `http://127.0.0.1:8000` (docs at `/docs`).
Vite proxies `/api` to the backend, so the frontend always calls relative `/api/...` URLs.

## Architecture rules

- `backend/app/domain/` is **pure**: no database, no network, no FastAPI imports. Business logic
  (FSRS wrapper, scheduler, Markdown parser, error taxonomy, statistics) lives here and is unit-tested.
- `backend/app/api/`: one router module per feature, mounted under `/api`. Routes stay thin.
- `backend/app/db/`: SQLAlchemy 2 models + Alembic migrations. **Every schema change is a migration**;
  the database must always be creatable from scratch with `alembic upgrade head`.
- `backend/app/ai/`: the only place that talks to AI providers. Prompts are versioned text files in
  `app/ai/prompts/`; every stored AI result records provider, model and prompt version. Outputs are
  validated by Pydantic schemas.
- Every module writes events to `event_log` in addition to its own tables. Statistics are computed from
  `event_log` and `review_log`, never from ad hoc counters.
- Frontend: one folder per module in `frontend/src/features/`; shared UI in `components/`; HTTP calls in
  `api/` through TanStack Query; routes declared in `src/routes.tsx`.

## Non-negotiables

- **No paid API at runtime.** Free tiers only (Gemini, Groq, Ollama, Web Speech API, optional Azure F0).
  The app must keep working without any key (degraded mode).
- **No personal data in Git**: `data/`, `.env`, databases, audio, exports and backups are ignored. Demo data
  must be fictional. CI fails if such files are tracked.
- **Secrets stay in the backend**: keys come from `.env` via `app/config.py` and are never sent to the
  frontend or logged.
- **Loopback only**: the backend binds to `127.0.0.1` (`VOCAB_HOST` refuses anything else). Do not weaken this.
- **Every user-visible string goes through i18n** (`frontend/src/i18n/locales/en.json` and `fr.json`, same
  keys). English is the default; never derive the language from the browser.
- **Active recall**: no screen may show an answer before the user has attempted it.
- **Never invent a library version, model name, quota or price.** Check: `npm view <pkg> version`,
  `uv add <pkg>` / `pip index versions <pkg>`, or the official documentation, and say what you checked.
- Do not add features absent from `docs/SPEC.md` without asking.

## Code conventions

- Everything in the repository is in **English**: code, comments, commits, docs. (The owner may talk to you
  in French; answer in French but write repository content in English.)
- Python 3.13, type hints everywhere, ruff (config in `backend/pyproject.toml`, line length 100).
- TypeScript strict; oxlint with warnings as errors; translation keys are type-checked.
- Tests: pytest for the backend (domain logic first), Vitest + Testing Library for the frontend.
- Cross-platform: the owner runs Windows. Use `pathlib`, no shell-specific tricks in app code, no
  hard-coded `/` paths; scripts exist as `.ps1` (Windows) and `.sh` (macOS/Linux). Keep `.ps1` files ASCII
  so Windows PowerShell 5.1 reads them correctly.
- UI: sober, readable, dark mode via CSS tokens in `frontend/src/styles.css`; accessibility basics
  (labels, focus styles, keyboard use).

## How to run a milestone session

1. Start in **plan mode**: list files to touch, migrations, risks; wait for approval.
2. Implement in small steps; after each step run the relevant tests and linters and show the real output.
3. Do not change the data schema beyond what the milestone plans without saying so.
4. Work on a branch named after the milestone (`m1-data-model`, ...); merge into `main` only when
   `npm run check` passes.
5. At the end: update `docs/PROGRESS.md` (done / left / known bugs / next step) and `docs/DECISIONS.md`
   (every technical decision and its reason), then commit with **Conventional Commits**
   (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`, `ci:`).
6. Finish with a short report: what works, what does not yet, how to test it.
