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
                                    data/vocab-coach.sqlite3  ·  recordings in data/audio/ (M6.a1)
                                    (demo mode: data/vocab-coach-demo.sqlite3, M1.c)
```

`npm run dev` (called by `start.ps1` / `start.sh`) runs both servers with `concurrently`, plus
`scripts/wait-and-open.mjs`, which opens the browser once `/api/health` and the Vite page answer (M1.c).
Host and ports of the dev servers live in `frontend/dev-server.json`, read by `vite.config.ts` and the
opener. Demo mode (`VOCAB_DEMO=1`, `python -m app --demo`, `start.ps1 -Demo`) only changes the database
file (and the recordings folder, `data/audio-demo/`); see D-033, D-169, D-188.
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
| `app/cli_curriculum.py` | `curriculum tracks`, `show <code> [--page N]`, `start <code>`, `open <code> <n>` (module H, no AI); from M8.a2 also `generate <code> <n>` (AI), `unit <id>`, `step`, `terms`, `edit`; exit codes 0 / 1 (AI could not write) / 2 | M8.a1, M8.a2 |
| `app/domain/curriculum_unit.py`, `app/ai/schemas/curriculum_unit.py`, `app/ai/prompts/curriculum_unit.v1.txt`, `app/services/curriculum_units.py` | scenario units (M8.a2): the shapes and rules of formulas, dialogue, shadowing and final task (pure); the `curriculum_unit` task; generate (D-038), edit under a revision, steps (two marked, two derived from takes linked by `production_attempt.curriculum_unit_id`), formulas to triage; events `curriculum.unit_*` | M8.a2 |
| `app/domain/curriculum.py`, `app/services/curriculum.py`, `app/api/curriculum.py` | module H: syllabus (`content/curriculum.yaml`), NGSL / NAWL readers and unit slicing (pure); tracks, start (source + `curriculum` deck), open unit (terms in triage through `importing.commit`, event `curriculum.unit_opened`); `/api/curriculum/...` | M8.a1 |
| `app/cli_speech.py` | `speech shadow --file --target [--item] [--duration]`, `speech transcribe <id>`, `speech compare "<target>" "<heard>"` (no AI); `speech speak --file [--prompt] [--duration] [--no-correct]`, `speech correct <id>` (M6.a2a, D-184); exit codes 0 / 1 / 2 (D-176) | M6.a1, M6.a2a |
| `app/api/health.py` | `GET /api/health` → `{status, version, database: {ok, revision, at_head}, demo}` | M0, M1.a, M1.c |
| `app/api/guard.py` | ASGI middleware: Host / Origin / Sec-Fetch-Site / JSON-only checks (D-061); an `audio/*` body is accepted under `/api/speech/` only (D-170) | M2.c1, M6.a1 |
| `app/api/errors.py` | `{"detail": {"code", "message"}}` errors, 422 without `input` (D-063) | M2.c1 |
| `app/api/ai.py` | `/api/ai/status`, `/providers/{name}/credential`, `/test`, `/usage` (D-064) | M2.c1 |
| `app/api/settings.py` | `GET` / `PATCH /api/settings` | M2.c1 |
| `app/api/library.py` | `/api/import/preview\|commit`, `/items` (search, quick add, get, patch, delete, status, merge), `/decks` (with today's pace and warnings, M4.a), `/decks/{id}/status`, `/decks/queue`, `/triage`, `/duplicates`; library errors mapped in `errors.py` | M3.a, M4.a1 |
| `app/api/clock.py` | `get_now` / `NowDep`: the current time as a dependency, overridden by the API tests (D-097) | M3.c3 fix |
| `app/api/session.py` | `/api/session/today`, `/start`, `/{id}/next`, `/{id}/end` | M4.a1 |
| `app/api/reviews.py` | `/api/reviews/grade` (writes nothing), `/api/reviews` (record), `/api/reviews/reveal` | M4.a1 |
| `app/api/discovery.py` | `/api/discovery/{item_id}/start`, `/exercises`, `/complete` | M4.a1 |
| `app/api/speech.py` | `POST /api/speech/shadowing` (raw recording as the body, query parameters), `POST /api/productions/{id}/transcribe`, `GET /api/productions/{id}/audio` (streamed, `Range`); `ComparisonOut`, also used by `ProductionOut`; `POST /api/speech/speaking`, `POST /api/speech/review-answer`, `GET /api/speaking/topics` (M6.a2a) | M6.a1, M6.a2a |
| `app/services/env_file.py` | safe edit of the three AI variables of `.env` (D-062) | M2.c1 |
| `app/services/ai_connection_test.py` | shared connection test, CLI and API (D-065) | M2.c1 |
| `app/demo/` | fictional demo data (`content/demo/`: decks, errors, prompts, hand-typed sheets): dataset loader, simulated learner, 60-day simulation through the services only (session service `session-1`, `choose_exercise`, discovery without initial ratings; modules E and F with fictional AI results validated by the real schemas, `fictional_ai.py`, D-163, D-190; one-second WAV clips made with `wave`, `clips.py`), atomic `demo seed` (the database and `data/audio-demo/` replaced together, D-188) | M1.c, M4.a2, M5.a3, M6.a1, M6.a2b |
| `app/domain/` | pure business logic (see "Domain and services" below) | M1.a, M1.b |
| `app/services/` | operations that read and write the database, in the caller's transaction | M1.b |
| `app/db/` | data layer (see below) | M1.a |
| `app/ai/` | AI gateway, prompts, schemas, providers (see "AI gateway" below) | M2.a, M2.b1 (Groq, Ollama), M2.b2 (Gemini) |
| `app/speech/audio_store.py` | local recordings: accepted media types, `YYYY/MM/<32 hex>.<ext>` names (a random UUID4 by default, an injected factory for the demo, D-187), atomic write, paths resolved inside the folder only, demo folder (D-169) | M6.a1, M6.a2b |
| `app/services/backup_format.py`, `backup.py`, `backup_verify.py`, `backup_restore.py`, `backup_auto.py`, `app/api/backup.py`, `app/cli_backup.py` | module J, full backup (M10.a, D-302 to D-308): the `vocab-coach-backup-1` zip (format and value encoding, pure; creation in one read transaction; verification before any write; restore into a temporary database then a D-188 swap; automatic copy with rotation); `POST /api/backup`, `GET /api/backup/status`, `POST /api/backup/auto/run`; `backup create \| verify \| restore \| auto` | M10.a |
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
  planning.py     build_plan_inputs() + plan_today(): read-only; queued terms without a usable
                  sheet are passed as items_without_sheet (D-105, M4.a2)
  library.py      sources, decks, terms, deck links, search, quick add, duplicates lookup, deletion rules (M3.a)
  importing.py    preview() (read-only) and commit() of the rows the user validated (M3.a)
  triage.py       list_triage() (no usage sheet), apply_triage() all or nothing (M3.a)
  duplicates.py   list_groups(), merge_items() (inversion, merge_conflict) (M3.a)
  study_sessions.py  start (plan frozen, stale sessions closed), next_step() computed live, end (summary from the logs) (M4.a1)
  review_flow.py  review_step() (prompt only), grade() (writes nothing), record() (auto rating recomputed), reveal() (M4.a1)
  discovery.py    + begin_discovery() / finish_discovery(): usable sheet required, no initial ratings (M4.a1)
  productions.py  record_written_production(): attempt, targets, production.recorded (M4.a1; M5 adds AI feedback)
  enrichment.py   + save_sheet(provenance=...) and add_templates(origin=demo): the demo's hand-typed sheets (M4.a2)
  error_cards.py  create_card_from_error(): term + sheet + gap-fill + one productive card in the "Error cards" deck;
                  list_suggestions() / dismiss_suggestion() for recurring errors (M5.a3, D-163, D-164)
  corrections.py / transcripts.py / drills.py  + store_correction() / store_analysis() / store_drill(): write an
                  already validated result in the caller's transaction; the AI paths and the demo use them (M5.a3, D-165)
  speech.py       record_shadowing() (file, then a short transaction, then the transcription), transcribe_production(),
                  store_transcription(), transcription_state(), comparison_of() (M6.a1, D-169 to D-175); record(): the
                  recording core shared with free speaking and spoken answers (checks before the file, M6.a2a, D-182)
  speaking.py     record_speaking(), prepare_speaking(), correct_speaking() (`speaking_correction`, `speaking-1`) (M6.a2a)
  spoken_review.py  check_spoken_answer(): refusals first, then recording, transcription, correction (M6.a2a, D-183)
  speaking_topics.py  todays_topics(): the speaking topics, skipping the spoken prompts of 7 days (M6.a2a)
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
  exercise_choice.py  choose_exercise(direction, state, stability, reps, templates) -> type + template (M4.a1)
  grading.py      normalize_answer(), damerau_levenshtein(), grade_typed() / grade_choice() / check_production() (M4.a1)
  error_cards.py  plan_card() (term, corrected sentence, gap-fill, small sheet), group_recurring() (M5.a3)
  review_steps.py build_prompt() (never a solution), build_solution(), shuffled_options() seeded by card + reps (M4.a1)
  speech_compare.py  words(), compare(): word alignment by dynamic programming (match, close, substituted, missing,
                  extra), contractions / numbers / hyphens tolerated (M6.a1, D-173)
  speech_rules.py audio size and target limits, duration bounds per production kind, Whisper's silence rule (M6.a1);
                  RecordingKind and its bounds, speech_units() (at most 40 units of whole sentences) (M6.a2a)
  topics.py       topic file format and daily pick, shared by writing_topics.py and speaking_topics.py (M6.a2a)
```

- **Flow of a review**: `record_review` loads the item, refuses archived/known items and out-of-order
  reviews, builds an engine with the current `target_retention`, writes `review_log` (before/after), updates
  the card (`srs_payload` reassigned), logs `card.reviewed`, then `sync_consolidation` moves the item between
  `learning` and `consolidated`.
- **Flow of a plan**: `build_plan_inputs` reads settings, schedulable cards (with retrievability from the
  engine), decks with their items, discovering items, errors of the last 14 days, pending consolidation tasks
  and observed durations; `plan_session` computes the blocks and the number of new terms (formula in
  D-029). Nothing is written.
- **Flow of a session** (M4.a1): `POST /api/session/start` closes a session left open on an earlier study
  day, then returns today's open session or creates one with the plan frozen (`session-1`). `GET next` is
  computed live from the cards (`card_snapshots`) and the frozen plan's new terms: a review step carries the
  exercise chosen by `choose_exercise` and a prompt from `build_prompt`, never the answer. `POST
  /api/reviews/grade` grades without writing and returns the solution; `POST /api/reviews` grades again on
  the server, then `record_review`. A discovery is `start` (term `discovering`, first sentence), the sheet
  (`GET /items/{id}/sheet`), the exercises graded by term, then `complete` (cards `new`, due the next study
  day; the personal sentence becomes a `production_attempt`). `POST end` writes the summary computed from
  `review_log` and `event_log`.
- **Flow of an import** (M3.a): the browser reads the Markdown file and sends its text as JSON;
  `POST /api/import/preview` parses it (`parse_import`) and looks up duplicates and the target deck, without
  writing; the page lets the user fix, confirm, include or exclude rows and choose `attach | new | skip`; then
  `POST /api/import/commit` re-checks every row with the same domain functions and writes the deck (and source),
  the terms (`draft` → `triage` or `queued` through `set_item_status`), the deck links and `import.completed` in one
  transaction (D-074). The CLI `library import` runs the same two steps.
- **Flow of a shadowing** (M6.a1): `POST /api/speech/shadowing` reads the raw body (at most 10 MB) and the query
  parameters, checks media type, size, duration and target, writes the file (`AudioStore`), then in one short
  transaction the oral production (`kind=shadowing`, `text=""`, `word_count=0`), its target term and
  `production.recorded`; the file is deleted if that transaction fails. Then `gateway.transcribe()` runs with no
  session open (the clip under its generated name, never the target as a prompt), and a second short transaction
  stores the text, the `pronunciation_result` and `production.transcribed` + `pronunciation.checked`. An AI failure
  writes nothing more: the recording stays and `POST /productions/{id}/transcribe` runs it again. Reads compute the
  comparison again from `pronunciation_result`; no error is ever recorded from it (D-174).
- **Flow of free speaking** (M6.a2a): `POST /api/speech/speaking` goes through the same core (`speech.record`, the
  terms and the session checked before the file is written and again in the transaction) with `kind=speaking` and
  the topic as `prompt_text`; the transcription sets `word_count` to the words heard. `POST /productions/{id}/correct`
  then reads it (transcribed, not silent, at most 4 000 characters), cuts it into units (`speech_units`), calls
  `speaking_correction` with no session open, and `store_speaking_correction` writes `speaking-1`, the errors (source
  `speaking`, dated at the recording) and `production.corrected` in one short transaction (D-180 to D-182).
- **Flow of a spoken answer** (M6.a2a): `POST /api/speech/review-answer` checks the card, its due date, the term, the
  session and the recording before writing anything, then records (origin `review`), transcribes and corrects in
  `answer` mode in three short transactions; `POST /api/reviews` takes the production back and computes the proposed
  rating from `speaking-1` (D-183).
- **The same flows in the caller's transaction** (M6.a2b, D-189): `speech.store_recording`, `speaking.store_speaking`
  and `spoken_review.store_spoken_answer` take a transcription already obtained (and, for a spoken answer, a corrector
  instead of the AI) and write without committing. Only the demo uses them, inside its one transaction.

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
- **Transcription details** (M6.a1, D-171): Groq is asked for `verbose_json`; `ProviderResponse.transcription`
  carries the audio duration and the segments' `no_speech_prob` / `avg_logprob`, which reach
  `TranscriptionOutput.duration_s` / `segments`. `Gateway.transcribe` has no prompt parameter (D-172).
- Decisions: D-038 to D-045 (M2.a), D-046 to D-055 (M2.b1), D-056 to D-060 (M2.b2), D-171 and D-172 (M6.a1). Tools: `uv run python -m app ai simulate`
  (fake providers, throwaway database), `ai status`, `ai test`, `ai usage` (real providers).

## Frontend (`frontend/src/`)

| Path | Role |
|---|---|
| `main.tsx` | bootstraps i18n, theme, TanStack Query client, router |
| `routes.tsx` | route table (one entry per feature) |
| `components/` | `Layout` (skip link, sidebar, top bar, menu state, outlet), `Sidebar` (the one `<nav>`: left sidebar, icon rail, or menu panel; D-290), `TopBar` (fold / Menu button, "Demo data" badge, language and theme), `AiBanner` (degraded mode, every page), `LanguageSwitcher`, `ThemeSwitcher`, `NotFoundPage`, `keyboard.ts` (shortcut guard shared by triage and reviews, M4.c); base components of RV.a: `Icon` + `iconPaths.ts` (D-289), `Badge`, `Notice`, `StatTile`, `ActionTile`, `SectionHeader` (with `sectionArt.ts`: the illustrations found at build time, D-296), `HomeHero`, `EmptyState`; RV.b: `CorrectionMark`, `CategoryCode` (D-298), `PageTitle`; `charts/` (`LineChart`, `BarList`, `useElementWidth`, D-293) |

Breakpoints (CSS constants, written out in each media query because a query cannot read a variable): **600 px** (phones: one column, 40 px targets, compact top bar) and **960 px** (below it the sidebar is a panel opened by the Menu button). Browsers: `light-dark()` needs Chrome or Edge 123 or later (D-286).
| `features/home/` | home screen: hero with the day's action, stat tiles, Continue tiles, the Today card (from `features/session/`) and backend status (D-295) |
| `features/session/` | `TodayCard` and `PlanWarnings` (today's plan and its translated warnings), `/session` (`SessionPage`: start, next steps, review player, end with confirmation, summary, saved-review announcement; `StepPanels`: `wait` timer, practice info, summary), `SessionProgress`, `StepHeading` (focus on each step), `format.ts` (M4.b, M4.c) |
| `features/review/` | module C in the session (M4.c1): `ReviewPlayer` (calls, focus, autoplay, errors), `reviewMachine.ts` (pure card state machine, D-120), `ReviewPrompt` (prompt by type, before the answer), `ReviewResult` (correction and sheet summary), `RatingButtons`, `useReviewShortcuts` (keys by phase, D-122), `stepText.ts` (replay text, D-123) |
| `features/queue/` | `/queue` (M4.c2): `QueuePage` (order, status, pace, warnings, moves, status changes), `queueOrder.ts` (D-027 order, groups, moves, D-026 transitions; pure) |
| `features/discovery/` | module B in the session: `DiscoveryFlow` (start, steps, complete, errors), `ReadAndGuess`, `SheetStep` (reuses `SheetView`), `ExercisesStep` and `GradeResult`, `ProductionSteps` (repetition, personal sentence), `highlight.ts` (M4.b) |
| `speech/` | browser speech synthesis: `voices.ts` (voice choice, slow rate), `useSpeech.ts` (store, hook, cancel on route change), `SpeakButton` (M4.b, D-112) |
| `features/settings/` | `/settings`: provider cards (key / address form, connection test), provider order, AI usage, study settings; `errorMessage.ts` maps the API's `detail.code` to i18n keys (M2.c2) |
| `api/` | `client.ts` (`apiGet`, `apiSend`, `ApiError` with `code`), `health.ts`, `ai.ts`, `settings.ts`, library, import, triage, duplicates and enrichment modules, and (M4.b, M4.c) `session.ts`, `discovery.ts`, `reviews.ts` (grade, reveal, record; types mirroring the backend contracts, query and mutation hooks) |
| `i18n/` | i18next setup, `locales/en.json`, `locales/fr.json`, typed keys |
| `theme.ts`, `sidebar.ts`, `useActiveTheme.ts` | theme preference (`vocab-coach.theme`), sidebar fold state (`vocab-coach.sidebar`), the theme in effect for what CSS cannot switch (RV.a) |
| `styles/` | the CSS, in cascade layers (D-285): `index.css` (layer order and imports), `tokens.css` (every colour once, as `light-dark()`, plus type, spacing, radius, shadow and size tokens: D-286), `base.css` (Inter `@font-face`, reset, headings), `components.css` (buttons, fields, cards, tables, badges, notices, tiles, section header, hero, empty state), `layout.css` (shell, sidebar, top bar), `features/*.css` (one file per feature, no colour of its own), `contrast.ts` + `contrast.test.ts` (WCAG test of the tokens, D-292) |
| `assets/fonts/`, `assets/hero/`, `assets/sections/` | the bundled Inter variable font and its licence (D-288), the home hero photo, the section header illustrations `header-<library, writing, speaking or errors>-<light or dark>.png` (still to be added by the owner, D-296) |
| `features/styleguide/` | `/styleguide`, mounted only in development (D-291) |
| `test/` | Vitest setup, `renderApp()` / `renderWithProviders()` helpers, `mockApi()` (fetch replaced by a small router that records calls), `fixtures.ts`, `fakeSpeech.ts` (fake `speechSynthesis`) |
