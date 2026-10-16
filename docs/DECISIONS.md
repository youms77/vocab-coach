# Decision log

One entry per technical decision: what was decided, why, and what it affects. Newest at the bottom.
Decisions that change `docs/SPEC.md` require the owner's approval and must say so.

---

## D-001 — Monorepo with root launcher (M0, 2026-10-16)

- **Decision**: one repository with `backend/` (uv project) and `frontend/` (Vite project). A small root
  `package.json` only holds launcher scripts and `concurrently`, which runs API and web app in one terminal.
  `start.ps1` / `start.cmd` (Windows) and `start.sh` (macOS/Linux) check tools, install dependencies when
  missing, then call `npm run dev`.
- **Why**: one command on every OS, Ctrl+C stops both processes, no PowerShell job juggling.
  `start.cmd` exists because PowerShell script execution is often blocked by default on Windows.

## D-002 — uv manages Python (M0)

- **Decision**: `backend/.python-version` pins 3.13; `uv sync` downloads that interpreter if missing.
  `uv.lock` is committed and CI uses `uv sync --locked`. The backend is not packaged (`tool.uv.package = false`);
  it runs with `uv run python -m app`.
- **Why**: reproducible installs; a classmate does not need to install the right Python first.

## D-003 — Backend binds to loopback, enforced in config (M0)

- **Decision**: `Settings.host` only accepts `127.0.0.1`, `localhost` or `::1`; anything else fails at
  startup. Settings use the `VOCAB_` prefix and read the repository-root `.env`.
- **Why**: spec section 7 (security). Enforcing it in code prevents an accidental `0.0.0.0`.

## D-004 — Dev proxy instead of CORS calls (M0)

- **Decision**: the frontend always calls relative `/api/...` URLs; Vite proxies them to `127.0.0.1:8000`.
  CORS is still configured for the Vite origins as a fallback.
- **Why**: the same frontend code works unchanged in the single-port "use" mode planned for M10, where
  FastAPI serves the built frontend.

## D-005 — Frontend toolchain versions (M0)

- **Decision**: Vite 8, React 19, React Router 8 (library mode, `createBrowserRouter`), TanStack Query 5,
  i18next 26 + react-i18next 17, Vitest 5 + Testing Library + jsdom. Linting with **oxlint** (the current
  `create-vite` default) plus `tsc -b` for type checking. TypeScript stays on **~6.0**: TypeScript 7 is out
  but the lint/tooling ecosystem (e.g. typescript-eslint, which requires `<6.1`) has not caught up.
- **Why**: versions checked with `npm view` on 2026-10-16. oxlint is fast, needs almost no configuration and
  works on Windows. Requires **Node.js >= 22.22** (React Router 8's engine requirement); LTS recommended.
- **Note**: the spec suggests Recharts for charts; it will be added in M9 when needed, not now.

## D-006 — Language detection: stored choice only (M0)

- **Decision**: i18next reads the language only from `localStorage` (`vocab-coach.language`), never from the
  browser; default and fallback are English. French and English files must have identical keys and
  placeholders (enforced by `src/i18n/locales.test.ts`); keys are type-checked via `i18next.d.ts`.
- **Why**: spec principle 8 (immersion, English by default) — a French Windows/browser would otherwise switch
  the UI to French automatically.

## D-007 — Theme (M0)

- **Decision**: CSS custom properties in `styles.css`; dark palette applied by `prefers-color-scheme` unless
  the user picks Light/Dark, stored as `data-theme` on `<html>` and in `localStorage` (`vocab-coach.theme`).
  System fonts only (Segoe UI on Windows).
- **Why**: dark mode from day one (spec section 8), no web fonts so the app works offline.

## D-008 — Test client dependency: httpx2 (M0)

- **Decision**: backend dev dependency `httpx2` instead of `httpx`.
- **Why**: Starlette 1.8 deprecates `httpx` for its `TestClient` and asks for `httpx2`.

## D-009 — CI layout (M0)

- **Decision**: GitHub Actions with four jobs: hygiene (fails if `data/`, `.env`, databases or audio files are
  tracked), backend (ruff check, ruff format --check, pytest), frontend (typecheck, oxlint, vitest, build),
  and a **Windows** job (parses the PowerShell scripts, runs `check-env.ps1` under Windows PowerShell 5.1,
  backend tests, frontend tests and build). Actions pinned: `actions/checkout@v7`, `actions/setup-node@v7`,
  `astral-sh/setup-uv@v10.3.0` (setup-uv no longer publishes moving major tags).
- **Why**: the owner develops on Windows; the Windows job catches path and script problems that Linux CI would miss.

## D-010 — What M0 deliberately does not install (M0)

- **Decision**: SQLAlchemy, Alembic, the `fsrs` library and AI SDKs are **not** added in M0.
- **Why**: they belong to M1/M2, whose sessions must check the current versions and APIs at that time.
