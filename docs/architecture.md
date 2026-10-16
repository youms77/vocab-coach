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
                                         ▼  SQLAlchemy 2 + Alembic (M1.a)
                                    data/vocab-coach.sqlite3  ·  audio in data/audio/ (M6)
                                    (demo mode: data/vocab-coach-demo.sqlite3, M1.c)
```

`npm run dev` (called by `start.ps1` / `start.sh`) runs both servers with `concurrently`, plus
`scripts/wait-and-open.mjs`, which opens the browser once `/api/health` and the Vite page answer (M1.c).
Host and ports of the dev servers live in `frontend/dev-server.json`, read by `vite.config.ts` and the
opener. Demo mode (`VOCAB_DEMO=1`, `python -m app --demo`, `start.ps1 -Demo`) only changes the database
file; see D-033.
Planned for M10: a single-port "use" mode where FastAPI also serves `frontend/dist`.

## Backend (`backend/`)

| Path | Role | Status |
|---|---|---|
| `app/main.py` | `create_app()` factory, CORS, router mounting under `/api` | M0 |
| `app/config.py` | `Settings` (pydantic-settings, `VOCAB_` env prefix, root `.env`, loopback-only host, absolute database URL) | M0, M1.a |
| `app/__main__.py`, `app/cli.py` | `python -m app [--demo] [--reload]` runs the API; `db upgrade` / `db reset --yes`; `plan today`; `demo seed`; `ai simulate` / `ai status` / `ai test` / `ai usage`; `library import` | M0, M1.a, M1.b, M1.c, M2.a, M2.b1, M3.a |
| `app/cli_plan.py` | `plan today`: builds the plan read-only (`PRAGMA query_only`) and renders it as text or JSON | M1.b |
| `app/cli_ai.py` | `ai status` (providers, models, order; never a key), `ai test` (one real call per configured provider, optional Whisper clip, writes `ai_call_log`), `ai usage` (read-only) | M2.b1 |
| `app/cli_library.py` | `library import <file> [--deck-id] [--no-triage] [--commit]`: read-only preview, or import of the clear lines with default choices | M3.a |
| `app/api/health.py` | `GET /api/health` → `{status, version, database: {ok, revision, at_head}, demo}` | M0, M1.a, M1.c |
| `app/api/guard.py` | ASGI middleware: Host / Origin / Sec-Fetch-Site / JSON-only checks (D-061) | M2.c1 |
| `app/api/errors.py` | `{"detail": {"code", "message"}}` errors, 422 without `input` (D-063) | M2.c1 |
| `app/api/ai.py` | `/api/ai/status`, `/providers/{name}/credential`, `/test`, `/usage` (D-064) | M2.c1 |
| `app/api/settings.py` | `GET` / `PATCH /api/settings` | M2.c1 |
| `app/api/library.py` | `/api/import/preview\|commit`, `/items` (search, quick add, get, patch, delete, status, merge), `/decks`, `/triage`, `/duplicates`; library errors mapped in `errors.py` | M3.a |
| `app/services/env_file.py` | safe edit of the three AI variables of `.env` (D-062) | M2.c1 |
| `app/services/ai_connection_test.py` | shared connection test, CLI and API (D-065) | M2.c1 |
| `app/demo/` | fictional demo data: dataset loader, simulated learner, 60-day simulation through the services, provisional direct writes, atomic `demo seed` | M1.c |
| `app/domain/` | pure business logic (see "Domain and services" below) | M1.a, M1.b |
| `app/services/` | operations that read and write the database, in the caller's transaction | M1.b |
| `app/db/` | data layer (see below) | M1.a |
| `app/ai/` | AI gateway, prompts, schemas, providers (see "AI gateway" below) | M2.a, M2.b1 (Groq, Ollama), M2.b2 (Gemini) |
| `app/speech/` | transcription, pronunciation | empty (M6) |
| `alembic.ini` | Alembic configuration (URL comes from the app settings) | M1.a |
| `tests/` | pytest suite; database tests use a temporary SQLite file built by the migrations | M0, M1.a |

## Data layer (`backend/app/db/`, M1.a)

```
domain/  (pure: enums, event payloads, settings registry, taxonomy parsing)
   ▲ imported by
db/
  base.py            Base + constraint naming convention + TimestampMixin (created_at/updated_at, UTC)
  types.py           UTCDateTime (refuses naive datetimes), closed_enum() (CHECK), JSONDict / JSONList
  engine.py          engine per URL, pragmas (foreign_keys, WAL, busy_timeout), get_engine / get_session
  migrate.py         upgrade / downgrade / schema_status (revision vs head) from code
  models/            library.py · srs.py · production.py · errors.py · curriculum.py · system.py
  migrations/        env.py (batch mode) + versions/0001_initial_schema.py
  taxonomy.py        load content/error_taxonomy.yaml + sync_taxonomy()
  event_log.py       record_event(): validated event, added in the caller's transaction
  settings_store.py  get_setting / set_setting (defaults from domain, overrides in `setting`)
```

- **Tables (21), by module**:
  - library (A): `source`, `deck`, `deck_item`, `lexical_item`, `enrichment`, `exercise_template`;
  - SRS (C): `card`, `review_log`;
  - production (E, F, G): `production_attempt`, `production_target`, `pronunciation_result`,
    `consolidation_task`, `consolidation_task_item`;
  - errors (E): `error_category`, `error_event`;
  - tracks (H): `curriculum_track`, `curriculum_unit`;
  - system (D, I, J): `study_session`, `event_log`, `ai_call_log`, `setting`.
- **Rules**:
  - every schema change is a new Alembic migration;
  - `alembic check` must stay empty (CI enforces it);
  - business code writes its rows **and** an event in the same transaction, then commits;
  - statistics read `event_log` and `review_log` only.
- **Startup**: the launch scripts run `python -m app db upgrade` before the servers. It creates
  `data/vocab-coach.sqlite3` on first run, applies new migrations and syncs the taxonomy.

## Domain and services (M1.b)

```
api/, cli_plan.py, cli_library.py  entry points: open a session, call services, commit or roll back
   │
services/                         read/write the database; never commit (D-023)
  reviews.py      record_review(): SRS state, reps/lapses, review_log snapshot, card.reviewed, status check
  items.py        set_item_status / transition_item / mark_active / unarchive_item / sync_consolidation
  discovery.py    start_discovery() (activates a queued deck), complete_discovery() (creates both cards)
  decks.py        change_deck_status(), reorder_queue()
  durations.py    observed_estimates(): medians from review_log and discovery.completed events
  planning.py     build_plan_inputs() + plan_today(): read-only
  library.py      sources, decks, terms, deck links, search, quick add, duplicates lookup, deletion rules (M3.a)
  importing.py    preview() (read-only) and commit() of the rows the user validated (M3.a)
  triage.py       list_triage() (no usage sheet), apply_triage() all or nothing (M3.a)
  duplicates.py   list_groups(), merge_items() (inversion, merge_conflict) (M3.a)
   │
domain/                           pure: no session, no network, no clock (`now` is a parameter)
  study_day.py    as_utc(), study_day_of(), study_day_bounds()        (timezone + day_start_hour)
  srs.py          Rating, SrsCardState, SrsEngine (Protocol), EngineFactory
  fsrs_engine.py  FsrsEngine: the only importer of `fsrs`; injected fuzz generator (D-022)
  item_status.py  ITEM_TRANSITIONS table, InvalidItemTransition, consolidation rule
  deck_queue.py   DECK_TRANSITIONS, DeckSnapshot, queue_order(), queued_candidates() (n-n once)
  durations.py    default durations, duration classes, estimate_durations()
  forecast.py     CardSnapshot, forecast_load() (14 study days, overdue on day 0)
  planner.py      PlanInputs → plan_session() → SessionPlan (blocks, caps, limit, warnings)
  markdown_import.py  parse_import(text, today) → ParsedImport (header, rows, problems with stable codes) (M3.a)
  normalize.py    normalize_term(), naive_lemma() (single-word stem), classify_match(), term_in_sentence() (M3.a)
```

- **Flow of a review**: `record_review` loads the item, refuses archived/known items and out-of-order
  reviews, builds an engine with the current `target_retention`, writes `review_log` (before/after), updates
  the card (`srs_payload` reassigned), logs `card.reviewed`, then `sync_consolidation` moves the item between
  `learning` and `consolidated`.
- **Flow of a plan**: `build_plan_inputs` reads settings, schedulable cards (with retrievability from the
  engine), decks with their items, discovering items, errors of the last 14 days, pending consolidation tasks
  and observed durations; `plan_session` computes the blocks and the number of new terms (formula in
  D-029). Nothing is written.
- **Flow of an import** (M3.a): the browser reads the Markdown file and sends its text as JSON;
  `POST /api/import/preview` parses it (`parse_import`) and looks up duplicates and the target deck, without
  writing; the page lets the user fix, confirm, include or exclude rows and choose `attach | new | skip`; then
  `POST /api/import/commit` re-checks every row with the same domain functions and writes the deck (and source),
  the terms (`draft` → `triage` or `queued` through `set_item_status`), the deck links and `import.completed` in one
  transaction (D-074). The CLI `library import` runs the same two steps.

## AI gateway (`backend/app/ai/`, M2.a, M2.b1, M2.b2)

```
caller (service / route)      call the AI first, then write the result in its own short transaction
   │  get_gateway().generate_json(task, inputs, schema)  /  .transcribe(audio)
   ▼
gateway.py   Gateway         one shared core for text and transcription
   │  tasks.py + prompt_loader.py    registry (pinned prompt version) -> rendered prompt
   │  policy.py                      constants + decision per error type (retry, repair, fallback, cooldown)
   │  health.py                      cooldown / misconfigured / last error, in memory, with a lock
   │  redact.py                      keys masked in every message
   │  journal.py                     one ai_call_log row per request, own session, commit at once
   ▼
providers/   Provider protocol: name, capabilities, is_configured(), model_for(), generate_json(), transcribe()
   │         (optional `min_request_timeout_s`: a local model that must load first)
   ├─ gemini.py        GeminiProvider (text, generateContent v1beta; JSON fields in one function)
   ├─ groq.py          GroqProvider (text + Whisper)      ── extends ──▶ openai_compat.py (chat completions)
   ├─ ollama.py        OllamaProvider (native /api/chat, no key, "configured" = a base URL)
   ├─ fake.py          scripted provider, tests + `ai simulate`
   ├─ schema.py        Pydantic JSON Schema -> the plain subset a provider accepts
   └─ common.py        retry_after formats, JSON fences
http.py      urllib client: error status = a normal answer, network failure = ProviderError with fixed
             text, no redirects, loopback bypasses the system proxy, http(s) only
```

- **Result, not exceptions**: `AiResult` has `status` (`ok` | `incomplete` | `unavailable`), the validated
  `data`, provider, model, `prompt_version` (`<task>.v<N>`), tokens, number of requests and `call_id`.
  `unavailable` carries a reason: `no_provider_configured`, `network`, `quota`, `auth`, `timeout`,
  `all_failed`. Programming errors (unknown task, input too long, wrong schema) raise.
- **Flow of a call**: render the prompt (single pass, user text framed as data) -> candidates = providers
  of the `ai_provider_order` setting that are configured, capable and not cooling down -> for each: send,
  validate with Pydantic, log the request, then success / retry with backoff / one repair of invalid
  output / fallback. No candidate at all -> `unavailable(no_provider_configured)`, nothing logged.
- **Adding a task**: a prompt file `prompts/<task>.v<N>.txt`, a schema class in `schemas/`, an entry in
  `tasks.py`. The gateway is unchanged.
- **Usage**: `services/ai_usage.py` aggregates `ai_call_log` per study day, provider and model.
- **Secrets**: keys come from `.env` through `Settings` (`SecretStr`), stay in the backend and are masked
  in every message (by the adapter, then again by the gateway); the key only travels in an HTTP header.
  Tests run with a socket guard that allows only the loopback interface: the adapters are tested against
  fake HTTP servers (`tests/ai/fake_server.py`), never the real services.
- **Real providers** (`build_providers()`): Gemini, Groq and Ollama, configured or not, so `status()` and
  `pin_provider` know them. Models are defaults in the adapters, overridable by `VOCAB_GEMINI_MODEL`,
  `VOCAB_GROQ_TEXT_MODEL`, `VOCAB_GROQ_TRANSCRIPTION_MODEL`, `VOCAB_OLLAMA_MODEL`. Gemini's API key goes
  in the `x-goog-api-key` header only; its error bodies are read in two shapes (D-059).
- **Live tests** (`tests/live/`, marker `live`): one real request per configured provider, only with
  `VOCAB_RUN_LIVE=1`; excluded from `npm run check` and the CI.
- Decisions: D-038 to D-045 (M2.a), D-046 to D-055 (M2.b1), D-056 to D-060 (M2.b2). Tools: `uv run python -m app ai simulate`
  (fake providers, throwaway database), `ai status`, `ai test`, `ai usage` (real providers).

## Frontend (`frontend/src/`)

| Path | Role |
|---|---|
| `main.tsx` | bootstraps i18n, theme, TanStack Query client, router |
| `routes.tsx` | route table (one entry per feature) |
| `components/` | `Layout` (top bar, skip link, "Demo data" badge, outlet), `AiBanner` (degraded mode, every page), `LanguageSwitcher`, `ThemeSwitcher`, `NotFoundPage` |
| `features/home/` | home screen with empty "Today's session" and backend status |
| `features/settings/` | `/settings`: provider cards (key / address form, connection test), provider order, AI usage, study settings; `errorMessage.ts` maps the API's `detail.code` to i18n keys (M2.c2) |
| `api/` | `client.ts` (`apiGet`, `apiSend`, `ApiError` with `code`), `health.ts`, `ai.ts`, `settings.ts` (query and mutation hooks) |
| `i18n/` | i18next setup, `locales/en.json`, `locales/fr.json`, typed keys |
| `theme.ts`, `styles.css` | theme preference and CSS design tokens (light/dark) |
| `test/` | Vitest setup, `renderApp()` helper, `mockApi()` (fetch replaced by a small router that records calls) |
