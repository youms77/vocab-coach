# Architecture

See `docs/SPEC.md` section 5 for the target architecture. This file describes what exists **now** and how
the pieces talk to each other. Update it when a milestone adds a layer.

## Runtime (development, as of M0)

```
Browser ── http://127.0.0.1:5173 ──> Vite dev server (frontend/)
                                         │  /api/* proxied
                                         ▼
                                    FastAPI on 127.0.0.1:8000 (backend/app)
                                         │
                                         ▼  (from M1)
                                    SQLite file in data/  ·  audio in data/audio/
```

`npm run dev` (called by `start.ps1` / `start.sh`) runs both servers with `concurrently`.
Planned for M10: a single-port "use" mode where FastAPI also serves `frontend/dist`.

## Backend (`backend/`)

| Path | Role | Status |
|---|---|---|
| `app/main.py` | `create_app()` factory, CORS, router mounting under `/api` | M0 |
| `app/config.py` | `Settings` (pydantic-settings, `VOCAB_` env prefix, root `.env`, loopback-only host) | M0 |
| `app/__main__.py` | `python -m app [--reload]` entry point used by the launcher | M0 |
| `app/api/health.py` | `GET /api/health` → `{status, version}` | M0 |
| `app/domain/` | pure business logic | empty (M1) |
| `app/db/` | SQLAlchemy models, Alembic migrations | empty (M1) |
| `app/ai/` | AI gateway, prompts, schemas | empty (M2) |
| `app/speech/` | transcription, pronunciation | empty (M6) |
| `tests/` | pytest suite | M0: health, config |

## Frontend (`frontend/src/`)

| Path | Role |
|---|---|
| `main.tsx` | bootstraps i18n, theme, TanStack Query client, router |
| `routes.tsx` | route table (one entry per feature) |
| `components/` | `Layout` (top bar, skip link, outlet), `LanguageSwitcher`, `ThemeSwitcher`, `NotFoundPage` |
| `features/home/` | home screen with empty "Today's session" and backend status |
| `api/` | `client.ts` (fetch wrapper for `/api`), `health.ts` (query hook) |
| `i18n/` | i18next setup, `locales/en.json`, `locales/fr.json`, typed keys |
| `theme.ts`, `styles.css` | theme preference and CSS design tokens (light/dark) |
| `test/` | Vitest setup and `renderApp()` helper |
