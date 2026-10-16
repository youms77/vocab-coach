# Progress

Updated at the end of every milestone session. Paste this file into the next planning conversation.

## Current state

- **Last milestone completed**: M1.a — Data layer (2026-10-16), branch `feat/m1a-data-model` (PR open,
  merged by the owner after green CI).
- **Next milestone**: M1.b — FSRS service, planner, queue, demo data.

## M1.a — Data layer ✅

### Done

- **Dependencies** (checked on 2026-10-16, see D-011): SQLAlchemy 2.1.4, Alembic 1.20.0, PyYAML 6.0.3,
  tzdata 2026.5.
- **Database infrastructure** (`app/db/`):
  - engine with SQLite pragmas (`foreign_keys`, WAL, `busy_timeout`);
  - constraint naming convention;
  - `UTCDateTime`, closed enums with CHECK, mutable JSON types;
  - default file `data/vocab-coach.sqlite3`, resolved to an absolute path; `VOCAB_DATABASE_URL` overrides it.
- **Schema**: all 21 tables for modules A to J (SPEC §6, updated), created by a single hand-reviewed
  migration, `0001_initial_schema`. It includes the partial unique index (one current usage sheet per term)
  and the append-only triggers on `event_log`.
- **Error taxonomy**: `content/error_taxonomy.yaml` (36 categories, EN/FR) plus an idempotent
  `sync_taxonomy()`.
- **Event log**: catalogue of 16 event types with Pydantic payloads (`app/domain/events.py`), and
  `record_event()` writing in the caller's transaction.
- **Settings**: typed registry with defaults and bounds (`app/domain/settings_defaults.py`), and
  `get_setting` / `set_setting`. Writing a setting logs `setting.changed`; writing back the default removes
  the override.
- **Commands and startup**:
  - `python -m app db upgrade` and `python -m app db reset --yes` (backup `*.bak-YYYYMMDD-HHMMSS`);
  - `start.ps1`, `start.cmd` and `start.sh` run `db upgrade` before starting the servers.
- **`/api/health`**: adds `database: {ok, revision, at_head}`. The frontend is unchanged.
- **CI**: an `alembic upgrade head && alembic check` step in the backend (Linux) and Windows jobs.

### Verified (Windows 11, 2026-10-16)

- **Automated checks**:
  - `npm run check` passes: ruff check, ruff format --check, pytest **62 passed**, tsc, oxlint, vitest 8
    passed;
  - `npm --prefix frontend run build` passes;
  - `alembic upgrade head && alembic check` reports "No new upgrade operations detected".
- **Tests cover**:
  - upgrade from scratch, model and migration parity, downgrade then upgrade;
  - SQLite pragmas;
  - foreign keys, CHECK constraints (deck status, rating 5, attempt + review) and UNIQUE constraints (two
    productive cards, two current usage sheets);
  - `UTCDateTime`;
  - delete cascades, with `error_event` set to NULL and `event_log` left intact;
  - a term in two decks;
  - taxonomy idempotence and user categories left untouched;
  - event validation and rollback;
  - settings bounds;
  - `/api/health`;
  - `db reset` with and without `--yes`.
- **Manual scenario**:
  1. with no database file, `start.cmd -NoBrowser` creates it (36 categories);
  2. `/api/health` shows `at_head: true`, directly and through the Vite proxy;
  3. the home screen still renders;
  4. `db upgrade` twice reports "0 added, 0 updated";
  5. `db reset` without `--yes` refuses (exit code 2);
  6. `data/` is ignored by Git.

### Left / notes

- **Not yet verified**: CI on GitHub for this branch (it runs on the PR).
- **Local setup this session**: uv 0.13.1 installed with winget; `git config core.filemode false` set locally
  (Windows had flagged `start.sh` as mode 644; the index keeps 755).

### Known issues

- None known.

## Next step: M1.b — FSRS service, planner, queue, demo data

- Install `fsrs` (6.3.2 was current on 2026-10-16; check again) behind an internal SRS interface. Map our
  `new` state to Learning, step 0, and fill the `review_log` before/after snapshot (see D-012).
- Item status transition rules; deck queue (activation, reordering, deadlines); daily planner (reviews
  before new items, quota, deadline pacing, time budget, duration estimate).
- Fictional demo data, backdated with `occurred_at`.

## M0 — Foundation ✅

### Done

- Monorepo: `backend/` (FastAPI, Python 3.13 via uv, ruff, pytest) and `frontend/` (React 19 + TypeScript 6 +
  Vite 8, React Router 8, TanStack Query 5, react-i18next, Vitest, oxlint).
- Backend: app factory, settings from root `.env` with `VOCAB_` prefix, **loopback-only host enforced**,
  `GET /api/health`. Empty packages `domain/`, `db/`, `ai/` (+ `prompts/`), `speech/` matching the spec layout.
- Frontend: layout with skip link, top bar, language switch (EN default / FR, stored choice only) and theme
  switch (System / Light / Dark); empty home screen ("Today's session", backend status); 404 page. All strings
  in `en.json` / `fr.json` with type-checked keys.
- One-command launch: `start.cmd` / `start.ps1` (Windows), `start.sh` (macOS/Linux) → checks tools, installs
  deps when missing, runs API (`127.0.0.1:8000`) and web app (`127.0.0.1:5173`, opens the browser).
- `scripts/check-env.ps1`: checks Git, uv, Node.js ≥ 22.22, npm; reports Python and GitHub CLI; prints `winget`
  install commands for anything missing.
- CI (`.github/workflows/ci.yml`): hygiene (no data/secrets tracked), backend, frontend, Windows jobs.
- Docs: `CLAUDE.md`, `docs/SPEC.md` (English translation of brief Part B), `docs/DECISIONS.md` (D-001…D-010),
  `docs/architecture.md`, `README.md`, MIT `LICENSE`, `.env.example`, `.gitignore`, `.gitattributes`,
  `.editorconfig`.

### Verified (in a Linux sandbox, 2026-10-16)

- Backend: `ruff check`, `ruff format --check`, `pytest` → 7 passed.
- Frontend: `tsc -b`, `oxlint --deny-warnings`, `vitest run` → 8 passed (home render, backend down, FR switch
  persisted, dark theme, 404, translation key/placeholder parity), `vite build` OK.
- `./start.sh --no-browser` starts both servers; `/api/health` answers directly and through the Vite proxy;
  home screen checked in light, dark and French/mobile.
- No sensitive files tracked (same check as the CI hygiene job).

### Not yet verified (owner must check on Windows)

- `start.cmd` / `start.ps1` and `scripts/check-env.ps1` on the real Windows 11 machine (only parsed, not run,
  outside Windows; the CI Windows job runs `check-env.ps1` and parses `start.ps1`).
- CI on GitHub (runs on the first push).
- Installed versions on the owner's machine (Python, Node.js) — spec section 11.

### Known issues

- None known.

