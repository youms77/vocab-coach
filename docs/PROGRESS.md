# Progress

Updated at the end of every milestone session. Paste this file into the next planning conversation.

## Current state

- **Last milestone completed**: M2.b1 — Groq + Ollama adapters and the `ai status | test | usage` CLI
  (2026-10-16), branch `feat/m2b1-ai-providers`, **cut from `feat/m2a-ai-core`** (PR #4, M2.a, is still open:
  merge it first, then retarget this PR on `main`). M1.a, M1.b and M1.c are merged (PR #1, #2, #3).
- **Next milestone**: **M2.b2** — the Gemini adapter (design already decided, D-055), then **M2.c** — API
  endpoints, settings page, "test connection" button.
- The owner has not yet run anything against the real services: see "Owner's manual scenario" below.

## M2.b1 — Real providers (Groq, Ollama) and `ai status | test | usage` ✅

M2.b was cut in two at the owner's request (about 15 significant files plus tests and fixtures): this part
holds the HTTP foundation, Groq (text + Whisper), Ollama and the CLI; Gemini is M2.b2.

### Done

- **Facts verified in the official documentation (2026-10-16)**, with sources, in D-046: Gemini models, free
  tier and privacy, quotas (not public), regions, JSON, thinking, errors; Groq limits per plan, models, JSON,
  429 headers, audio limits; Ollama API, errors, models. Gemini's are for M2.b2; what could not be verified is
  listed there.
- **`app/ai/http.py`** (D-049): `urllib` client, no SDK and no new dependency; error statuses are normal
  answers, network failures become `ProviderError` with fixed wording, no redirects, loopback bypasses the
  proxy, http(s) only, multipart encoder.
- **`providers/common.py`, `schema.py`** (D-049): `retry_after` in seconds, `34s`, `2m59.56s`, `700ms` and HTTP
  dates; JSON fence removal; Pydantic schema simplification (inlined `$ref`, dropped validation keywords,
  closed objects), tested on the shape of an M3 usage sheet.
- **Groq** (`openai_compat.py` + `groq.py`, D-047): chat completions with `json_schema` best-effort on the
  documented models, `json_object` on the others, gpt-oss reasoning kept low; Whisper upload with refusal of an
  empty, over-25-MB or unsupported clip *before* any request.
- **Ollama** (`ollama.py`, D-048): native `/api/chat`, `stream: false`, `format` schema + schema in the prompt,
  "configured" = an http(s) base URL, model-not-found tells to `ollama pull`.
- **Errors** (D-050): every status, header and body shape translated to the D-039 kinds; a daily quota is told
  from a per-minute limit by the message wording (Groq documents no other way).
- **Policy** (D-051): new `EXHAUSTED_RETRY_COOLDOWN = 60 s` (closes the M2.a open point), `health.blocked_by()`
  reports the real cause, and a provider timeout floor (Ollama: 60 s, never beyond the 90 s budget). Other
  constants kept, with the reasons.
- **`build_providers()`** (D-052) returns Groq and Ollama, configured or not; new optional
  `VOCAB_GROQ_TEXT_MODEL`, `VOCAB_GROQ_TRANSCRIPTION_MODEL`, `VOCAB_OLLAMA_MODEL`.
- **CLI** (`cli_ai.py`, D-053): `ai status`, `ai test [--provider] [--audio]`, `ai usage [--days]`; exit codes
  0 / 1 (a test failed) / 2 (nothing configured, usage error, no database, `--demo`); never a key or an address;
  no session open during a call.
- **Tests** (D-054): fake HTTP servers on the loopback, fixtures from the documentation, hostile-server secret
  tests, live tests (`tests/live/`, off by default) and a test proving they stay off.
- **No migration, no frontend change, SPEC.md unchanged.** README: Groq and Ollama set-up, privacy warning,
  `ai` commands, live tests. `.env.example`: Ollama address and model variables.

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **621 passed, 3 deselected** (the live tests;
  394 existing + 227 new), tsc, oxlint, vitest 11 passed.
- `alembic upgrade head && alembic check` on a temporary database: "No new upgrade operations detected".
- Without any key (the three variables forced to empty so the owner's `.env` is never read): `ai status` lists
  Groq and Ollama as not configured and says the app runs in degraded mode; `ai test` exits 2 ("Nothing is
  configured"); `ai test --provider groq` exits 2; `ai test --provider gemini` exits 2 ("not available yet");
  `--demo ai test` exits 2; `ai usage` says nothing was recorded; the API started and `/api/health` answered
  `database.at_head: true`; `git status` shows no `.env` and no `data/`.
- **Tests cover** every case of the brief: request construction (URL, headers, body, key never in the URL),
  valid answers with tokens, every error class from fixtures, `retry_after` formats, empty / blocked / truncated
  / non-JSON output; the gateway with real adapters over HTTP (429 per minute then success, daily quota then
  fallback then skip then probe, invalid key ignored until `reload()`, invalid JSON repaired once then
  `incomplete`, timeout, repeated 429 set aside for a minute, Ollama stopped); the key absent from every error,
  repr, log, database column, status, traceback and CLI output; the CLI (every exit code, `--audio`, no open
  transaction during a call).
- **Not run by me, on purpose**: no real provider call, no live test, no `ai test` with a real key. The `.env`
  was never opened.

### Owner's manual scenario (with your own keys, about 2 minutes)

1. `uv run python -m app ai status` (from `backend/`): configured or not, models, order, no key shown.
2. `uv run python -m app ai test`: one `ok` per configured provider with model and time; exit code 0.
3. Put a wrong key in `.env` for a moment: a clear `auth` message, no key in it, exit code 1.
4. Cut the network: `unavailable (network)`.
5. `uv run python -m app ai test --provider groq --audio my_clip.wav`: the transcribed text.
6. `uv run python -m app ai usage`: today's calls.
7. Without any key: `start.cmd -NoBrowser` starts as before, `ai test` says nothing is configured (exit 2).
8. Optional: `$env:VOCAB_RUN_LIVE=1; uv --directory backend run pytest tests/live -m live -v`.

### Left / notes

- **Not yet verified**: CI on GitHub for this branch (it runs on the PR); everything against the real services
  (the fixtures come from the documentation and public reports; the first real calls may call for adjustments:
  the exact Groq 429 / 401 bodies, whether the `vocab-coach/0.1` User-Agent is accepted, Whisper's real
  response, Ollama's first-load time).
- **Gemini (M2.b2)**: build the adapter from D-055. Re-check the models, pricing and error pages first (read on
  2026-10-16). Risk n° 1: the `responseFormat` JSON field has never been exercised against the real service; the
  fallback is `responseMimeType` + `responseJsonSchema`. Add `VOCAB_GEMINI_MODEL`, the Gemini section of the
  README (key from Google AI Studio, privacy warning already there), the live test, and revisit
  `MAX_WAIT_S` with real Gemini delays. Hypothesis B.11 (free tier in Cameroon) is confirmed or not by the
  owner's call.
- **Groq free plan**: the default text model has 8 000 tokens per minute: M3 tasks that may fall back to Groq
  must keep input + output well under that, or the answer is a 413 (`bad_request`). `llama-3.x` are not in the
  free table: if `openai/gpt-oss-20b` is retired, change the default (or `VOCAB_GROQ_TEXT_MODEL`).
- A transcription refused locally (too big, empty, wrong extension) is journalled as a `bad_request` without
  HTTP status and counts as a request in `ai usage` (accepted imprecision, D-047).
- On Windows a refused connection takes about 2 s to fail (the OS retries): Ollama stopped costs 2 s per call
  until it is set aside for a minute.
- Another milestone note: the M2.a degraded-mode test now forces empty environment variables instead of
  `delenv` (D-052): keys in the owner's `.env` can no longer turn it into a network call.

### Known issues

- None known.

## M2.a — AI gateway core, offline ✅

### Done

- **Gateway** (`app/ai/`, D-038 to D-045): `Gateway.generate_json(task, inputs, schema)` and
  `.transcribe(audio)` share one core; Pydantic validation; retry with exponential backoff and jitter
  (`retry_after` honoured up to 20 s); one repair of invalid output, then `incomplete`; fallback along the
  `ai_provider_order` setting; quota cooldown; auth providers marked until `reload()`; 90 s time budget;
  `pin_provider`; `status()`; `get_gateway()` (no real provider yet: every call is
  `unavailable(no_provider_configured)`, so the app runs in degraded mode).
- **Results, not exceptions**: `ok` / `incomplete` / `unavailable` + reason; programming errors raise.
- **Journal**: one `ai_call_log` row per request, written in its own short session (exception to D-023,
  documented); no prompt, response, user text or key; messages masked and cut to 300 characters. **No
  migration** (the M1.a table was enough; `alembic check` is empty).
- **Prompts and schemas**: versioned files with a validated header, single-pass substitution, user text
  framed as data with a delimiter it cannot forge; task registry pinning the prompt version; the
  `connection_test` task and `ConnectionTestOutput`.
- **Secrets**: `VOCAB_GEMINI_API_KEY`, `VOCAB_GROQ_API_KEY` (`SecretStr`), `VOCAB_OLLAMA_BASE_URL`; empty =
  not configured; keys masked (raw, URL-encoded, form-encoded); `.env.example` documented without URLs.
- **Settings**: the registry now supports list values; `ai_provider_order` (default
  `["gemini","groq","ollama"]`, `[]` = AI off).
- **Usage**: `services/ai_usage.py`, per study day, provider and model, from `ai_call_log`.
- **Dev tool**: `python -m app ai simulate` (three scenarios, fake providers, throwaway database).
- **CLAUDE.md**: two permanent rules (every AI call goes through the gateway; never keep a write
  transaction open during an AI call).

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **394 passed** (280 + 114 new, ~28 s;
  the AI tests take ~2.6 s), tsc, oxlint, vitest 11 passed.
- `alembic upgrade head && alembic check` on a temporary database: "No new upgrade operations detected".
- **Tests cover** every acceptance criterion, all offline (an autouse fixture refuses any non-local socket
  connection and DNS lookup): first-try success; 429 then success (`retry_after` honoured, then > 20 s
  goes to fallback); quota (fallback, skipped during cooldown with no log line, probed again after);
  repeated 429; auth + `reload()`; invalid output (repair message in the sent prompt, then `incomplete`,
  no fallback); no provider configured (0 calls, 0 rows); every `unavailable` reason; time budget;
  `pin_provider`; transcription and capability filtering; keys never in the database, result, `logging`
  or `repr(Settings)`; journal write failure; prompts (headers, placeholders, registry, `{{other}}`, `$x`,
  braces, fake delimiters, version in result and log, input too long); `ai_provider_order`; usage with
  the 04:00 Douala boundary; concurrent access to the health state.
- **Manual scenario**: `pytest -k ai` green (209 selected, the keyword also matches unrelated names);
  `python -m app ai simulate` prints the three scenarios, the log rows and the usage, and the personal
  database has the same SHA-256 before and after; `start.cmd -NoBrowser` without any key starts and
  `/api/health` answers (`database.at_head: true`); `git status` shows no `.env` or `data/`.

### Left / notes

- **Not yet verified**: CI on GitHub for this branch (it runs on the PR).
- Provisional values to revisit in M2.b with the real quotas (all in `app/ai/policy.py`): 3 attempts, 20 s
  maximum wait, 90 s budget, 1 h cooldown, 30 s request timeout. A provider that returns 429 on every
  request is retried three times (3 s of waiting) on each call; M2.b may add a short cooldown for that.
- `app/ai/health.py` is its own file (the plan had it inside `gateway.py`).
- Callers (M3 onwards) must follow the rule: call the AI first, then write in a short transaction.
- Transcription uses a fixed 60 s request timeout and has no size check yet (provider limits are M2.b/M6).
- While checking the startup I ran `alembic upgrade head` once against the personal database by mistake; it
  was already at head and its SHA-256 did not change.

### Known issues

- None known.

## M1.c — Demo data, demo mode, waiting for the API ✅

### Done

- **Demo mode** (D-033): `VOCAB_DEMO` / `python -m app --demo` use `data/vocab-coach-demo.sqlite3`;
  combined with `VOCAB_DATABASE_URL` it fails at startup. Demo marker = reserved `setting` row `_demo`
  (`{dataset_version, seed, days, anchor}`), outside the settings registry. `/api/health` adds `demo`; the
  top bar shows a "Demo data" badge (EN/FR).
- **`python -m app demo seed`** `[--seed 42] [--days 60] [--anchor YYYY-MM-DD] [--reset] [--if-missing]`:
  always the demo file; refuses unmarked data (even with `--reset`) and a marked database without
  `--reset`; atomic build in a temporary file; reports a file held open by the app on Windows; prints rows
  per table, terms by status, cards by state, errors by category (levels 1 and 2) and the duration.
- **Dataset** (`content/demo/`, version 1, all invented): 5 decks, 113 terms (all four unit types, 60 with an
  origin sentence, 3 shared between decks, 17 with a lexical confusion), 59 error templates over 17 taxonomy
  codes, 10 production prompts and filler sentences.
- **Simulation** (`app/demo/`, D-034): 60 study days through the real services (planner, discovery, reviews,
  item and deck statuses) with a seeded FSRS engine; simulated learner; productions with error rates per
  100 words (fixed expressions fall from 3 to 1, past simple vs present perfect stable at 2, connectors
  rising); lexical errors from failed reviews; one `study_session` per session (provisional format).
- **Provisional direct writes** (D-035) for deck/term creation, triage decisions, productions, errors and
  sessions; new event `deck.item_added`; `study_session_id` accepted by the discovery services.
- **Launch** (D-036): `start.ps1 -Demo` / `start.cmd -Demo` / `start.sh --demo` run `db upgrade` then
  `demo seed --if-missing` on the demo database. `scripts/wait-and-open.mjs` opens the browser once the API
  and the Vite page answer (90 s limit, never stops the servers); `concurrently --kill-others-on-fail`;
  `frontend/dev-server.json` shared by Vite and the opener.
- **CI**: full 60-day `demo seed` + `--demo plan today` on a temporary data folder (Linux and Windows);
  `node --check` of the opener (Windows job).
- **No migration and no new setting.**

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **280 passed** (~27 s), tsc, oxlint,
  vitest **11 passed**.
- **Seed duration**: 2.4–4.4 s for 60 days (CLI, owner's machine).
- **Tests cover**: determinism (same seed ⇒ same fingerprint, other seed ⇒ different; clock columns
  `created_at`, `updated_at`, `recorded_at` excluded); every deck and item status; new / learning / review
  / relearning cards; ≥ 10 error codes, prepositions and tenses on top (level 2); fixed-expression rate per
  100 words lower in the last 30 days; ≥ 80 % stable productive cards in "Causal inference reading";
  integrity (no review before discovery, increasing review log per card, nothing after the anchor day's
  start, every row has its event, status history matches, bank codes in the taxonomy, no duplicate term
  per deck); plan at the anchor (reviews, new terms, deadline pace, triage warning); safety checks (unmarked
  data, marked without `--reset`, `VOCAB_DEMO` + `VOCAB_DATABASE_URL`, file in use, failed build keeps the
  previous file, personal database untouched by the CLI); `/api/health` `demo`; badge shown/absent (Vitest).
- Seeds 1 to 12 all meet the coverage criteria (checked with a throwaway script).
- **Manual scenario**:
  1. `start.cmd -Demo`: first launch printed the seed summary; the opener waited for the API ("App ready")
     and exited 0 while the servers kept running; `/api/health` → `demo: true`; badge present;
  2. `uv run python -m app --demo plan today`: 10 reviews, 12 new terms (one resumed), deadline pace and
     `deadline_triage_pending` warning;
  3. `start.cmd -NoBrowser` without `-Demo`: `demo: false`, no badge, the opener did nothing; the personal
     database has the same SHA-256 and modification time as before the demo run; `plan today` is empty;
  4. `demo seed` refuses (exit 2); `demo seed --reset` while the app runs reports the locked file and keeps
     the database; after stopping the app, `--reset` prints the same summary.

### Left / notes

- **Not yet verified**: CI on GitHub for this branch; `start.sh --demo` on macOS/Linux (only `bash -n`).
- Usage sheets and exercise templates for the demo come with M3; productions, errors and sessions move to
  their services in M4/M5 (the simulation will call them instead of `direct_writes.py`).
- The demo history's anchor is the day it was generated: after a few days without `--reset`, the demo shows a
  growing review backlog (like a real user who stopped).

### Known issues

- None known.

## M1.b — FSRS service, statuses, queue, planner ✅

### Done

- **Dependency**: `fsrs` 6.3.2 (latest on PyPI on 2026-10-16, checked with `pip index versions`; source read
  before writing the adapter), declared `>=6.3.2,<7`. See D-022.
- **SRS** (`app/domain/srs.py`, `fsrs_engine.py`): internal `SrsEngine` interface, library-free state,
  FSRS adapter (`new` → Learning step 0, `Card.to_dict()` payload, UTC normalisation), fuzzing with an
  injected generator (off or seeded for tests and simulations).
- **Review service** (`app/services/reviews.py`): `record_review()` applies the final rating, stores the
  proposed one, updates `reps`/`lapses`, the full `review_log` snapshot, `card.reviewed`, then the item
  status; refuses out-of-order reviews and items that are not learning/consolidated/active.
- **Item statuses** (`app/domain/item_status.py`, `app/services/items.py`, `discovery.py`): explicit
  transition table with a dedicated error, automatic learning ↔ consolidated (productive stability ≥ 7 days),
  `mark_active`, unarchive, `start_discovery`, `complete_discovery` (with or without initial ratings), new
  event `card.created`.
- **Decks and queue** (`app/domain/deck_queue.py`, `app/services/decks.py`): transition table, pause/done
  semantics, queue order (deadline then position), dense `reorder_queue`, n-n terms proposed once,
  automatic activation proposed by the planner without writing.
- **Study day, durations, forecast**: `study_day_of` / `study_day_bounds`; default durations then observed
  medians (D-028); `forecast_load` over 14 study days.
- **Planner** (`app/domain/planner.py`, `app/services/planning.py`): pure `plan_session()` → serialisable
  `SessionPlan` (blocks, durations, caps, limiting constraint, decks to activate, deadline paces, coded
  warnings). Formula in D-029 and D-030.
- **CLI**: `python -m app plan today [--at ISO] [--json]`, read-only (`PRAGMA query_only`).
- **Tests**: test database built once per session and copied per test (D-032).
- **No migration and no new setting** (the consolidation threshold reuses
  `consolidation_min_stability_days`).

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **246 passed**, tsc, oxlint, vitest 8
  passed.
- `alembic upgrade head && alembic check`: "No new upgrade operations detected".
- **Tests cover** every acceptance criterion of the milestone: SRS (new + Good/Again, Again in Review → lapse
  and Relearning, reps, before/after snapshot, exact `to_dict` round trip, 0.95 vs 0.90 retention, fake
  engine, earlier review refused, seeded fuzz), statuses (every allowed and forbidden transition, events,
  consolidation around the threshold, discovery with and without ratings, unarchive), queue (order, dense
  reorder, pause, automatic activation without writes, n-n), study day (04:00 switch in Africa/Douala,
  learning steps due later today), planner (reviews first, quota, budget, overflow, 7-day anticipation,
  30 terms / 10 days → 3 per day, unrealistic deadline, past deadline, interrupted discovery first,
  targeted practice, durations), forecast (overdue on day 0, archived excluded), CLI (database unchanged).
- **Manual scenario**:
  1. `uv run python -m app plan today` → empty readable plan: no reviews, 0 new terms, budget 45 min,
     limit "nothing to learn";
  2. `--json` → valid JSON;
  3. `uv run pytest -k "planner or srs or queue or status" -v` → readable names, all green;
  4. `start.cmd -NoBrowser` starts as before; `/api/health` answers directly and through the Vite proxy.

### Left / notes

- **Not yet verified**: CI on GitHub for this branch (it runs on the PR).
- Deviations approved with the plan: Good on a new card → step 1 (+10 min); `supply` limit value; durations
  by class; reviews refused for any status outside learning/consolidated/active; `via_deck` optional;
  `reorder_queue` covers every deck that is not done.

### Known issues

- None known.

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

## Next step: M2.b2 (Gemini), then M2.c (endpoints and settings page)

- **M2.b2**: the Gemini adapter (`generateContent`, design in D-055), its schema converter, `VOCAB_GEMINI_MODEL`,
  Gemini in `build_providers()`, README section for the Google AI Studio key, live test. First re-check the
  Gemini facts of D-046 and settle the owner's findings from the real Groq / Ollama calls.
- **M2.c**: API endpoints, settings page (keys written to `.env`, then `get_settings.cache_clear()` +
  `get_gateway().reload()`; order, daily usage from `services/ai_usage.py`), "test connection" button
  (`generate_json("connection_test", ..., pin_provider=...)`, as `ai test` already does).
- The demo database stays without `ai_call_log` rows until a later milestone decides how to simulate them.

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

