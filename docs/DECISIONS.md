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

## D-011 — Data layer stack and versions (M1.a, 2026-10-16)

- **Decision**:
  - SQLAlchemy **2.1.4** (typed declarative models: `Mapped[...]`, `mapped_column`) and Alembic **1.20.0**;
  - PyYAML **6.0.3** to read the taxonomy file;
  - **tzdata 2026.5** (Python's `zoneinfo` has no time-zone database on Windows; the `timezone` setting
    needs it).
- **How the versions were checked**: `python -m pip index versions <pkg>` on 2026-10-16, then `uv add`.
- **Migrations**:
  - they live in `backend/app/db/migrations/`, with `alembic.ini` in `backend/`;
  - `env.py` takes the URL from the app settings and runs in `render_as_batch=True` mode (SQLite cannot
    `ALTER` most things).
- **Naming convention**: one on `MetaData` (`ix/uq/ck/fk/pk`), so batch migrations can find constraints by
  name.
- **Pragmas on every connection**: `foreign_keys=ON`, `journal_mode=WAL` and `busy_timeout=5000`.
- **Database file**:
  - default `data/vocab-coach.sqlite3`, resolved to an absolute path from the code location, never from
    the current folder (the backend runs from `backend/`);
  - overridable with `VOCAB_DATABASE_URL`.

## D-012 — fsrs library findings (M1.a; library installed in M1.b)

- **What was read**: `fsrs` **6.3.2** (latest on PyPI). The wheel was downloaded and read, not installed.
- **What the library exposes**:
  - `Card`: `card_id`, `state`, `step`, `stability`, `difficulty`, `due`, `last_review`;
  - `ReviewLog`: `card_id`, `rating`, `review_datetime`, `review_duration`;
  - `State`: Learning, Review and Relearning, **with no New state**;
  - **no `reps` or `lapses` counters**.
- **Decisions**:
  - `card.srs_state` keeps `new` (never reviewed); the M1.b service maps it to Learning, step 0;
  - `reps` and `lapses` are kept by the app;
  - our primary key is the card identity, and `srs_payload` stores `Card.to_dict()` for an exact restore;
  - `elapsed_days` and `scheduled_days` are floats, because learning steps are minutes.

## D-013 — Many-to-many decks and terms (M1.a, approved by owner)

- **Decision**:
  - `deck_item` links decks and terms (unique per pair, with its own position and an optional
    deck-specific context sentence);
  - cards hang off `lexical_item`, so a term in two decks has a single pair of cards.
- **Why**: the same term often comes from several readings; duplicating cards would double the reviews and
  split the statistics.

## D-014 — UTC everywhere, study day computed (M1.a)

- **Decision**:
  - every timestamp column uses `UTCDateTime`, which refuses naive datetimes, stores UTC and returns
    `tzinfo=UTC`;
  - plain dates (a deck deadline) use `Date`;
  - the "study day" is not stored: it will be derived from UTC times and the `timezone` and
    `day_start_hour` settings (defaults `Africa/Douala`, 4 h).
- **Why**: comparing naive and aware datetimes becomes impossible. Late-night reviews belong to the previous
  study day without changing any stored data.

## D-015 — Closed vs open value sets (M1.a)

- **Decision**:
  - **closed sets** fixed by the spec (deck status, item status, card state, sources...) are `StrEnum`s in
    `app/domain/enums.py`, stored as strings with a named CHECK constraint
    (`Enum(native_enum=False, create_constraint=True, length=32)`);
  - **open sets** that will grow (exercise type, event type, AI task) are plain strings validated by the
    application.
- **Why**: the database guards what is settled, and new exercise or event types need no migration.
- **Migration detail**: Alembic 1.20 autogenerate emitted each enum CHECK three times. The hand-reviewed
  migration keeps only the one created by `sa.Enum`, and a test guards against duplicates coming back.

## D-016 — Error taxonomy as versioned YAML + idempotent sync (M1.a)

- **Decision**:
  - the built-in taxonomy lives in `content/error_taxonomy.yaml`: a tree with EN/FR labels, descriptions
    and examples;
  - `sync_taxonomy()` runs on every `db upgrade`: it inserts missing codes and refreshes built-in texts;
  - it never deletes, and never touches user or AI-proposed categories;
  - a code's parent is its prefix (checked when the file is loaded);
  - statistics will aggregate by code prefix, and events may point at intermediate nodes.
- **Why**: the taxonomy is reviewable in Git and translatable, and editing it cannot lose user data.

## D-017 — `event_log` without foreign keys, append-only (M1.a)

- **Decision**:
  - no foreign keys, separate `occurred_at` (business date) and `recorded_at`;
  - payloads validated by Pydantic models (`app/domain/events.py`, `extra="forbid"`, `payload_version`);
  - `record_event()` adds the row in the caller's transaction, so a rollback removes both;
  - SQLite triggers refuse `UPDATE` and `DELETE` on the table;
  - `setting.changed` only accepts registry keys, which can never be secrets.
- **Why**: history must survive the deletion of what it describes, and demo data can backdate events.

## D-018 — Integer primary keys (M1.a)

- **Decision**: auto-increment integer primary keys everywhere (`setting` uses its key).
- **Why**: simpler and faster with SQLite, and restore (M10) loads into an empty database, so there are no
  identifier clashes to avoid.

## D-019 — `shadowing` production kind (M1.a, approved by owner)

- **Decision**: `production_attempt.kind` gains `shadowing`, alongside writing, speaking, consolidation,
  transcript_analysis and drill.
- **Why**: module F (shadowing) produces recordings and transcripts like other productions, so the same table
  and the same statistics apply.

## D-020 — Mutable JSON columns (M1.a)

- **Decision**: JSON columns that the app edits use `MutableDict` / `MutableList`.
  - They track **top-level** changes only; a nested change needs a reassignment or `flag_modified`
    (documented in `app/db/types.py`).
  - `event_log.payload` and `setting.value` use plain `JSON`: they are never modified in place.
- **Why**: in-place edits of a usage sheet must not be silently lost, and full deep tracking would be costly.

## D-021 — Database commands, startup and health (M1.a)

- **Commands**:
  - `python -m app` still runs the API (D-002);
  - `python -m app db upgrade` runs migrations, then the taxonomy sync;
  - `python -m app db reset --yes` checkpoints the WAL, renames the file to `*.bak-YYYYMMDD-HHMMSS` in
    `data/`, then recreates it; without `--yes` it refuses and changes nothing.
- **Launch scripts**: `start.ps1` (and therefore `start.cmd`) and `start.sh` run `db upgrade` before the
  servers, and stop with a clear message if it fails.
- **`/api/health`**:
  - adds `database: {ok, revision, at_head}`, and `status` stays `"ok"`;
  - it never creates a missing database file.
- **CI**: runs `alembic upgrade head && alembic check` on a temporary database (Linux and Windows jobs).
