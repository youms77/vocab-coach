# Progress

Updated at the end of every milestone session. Paste this file into the next planning conversation.

## Current state

- **Last milestone completed**: M2.c2 — settings page, frontend only (2026-10-16), branch
  `feat/m2c2-settings-page`, cut from `main` after PR #7 (M2.c1) was merged. **M2 is complete** except its
  acceptance criterion "one real test call succeeds with the user's key", which only the owner can run.
- **Next milestone**: **M3 — Library and import** (SPEC §10).
- The owner has not yet run anything against the real services: see "Owner's manual scenario" below.

## M2.c2 — Settings page (frontend) ✅

### Done

- **`/settings`** (`frontend/src/features/settings/`, D-066), with a "Settings" link in the top bar:
  - **one card per provider**: state (ready, not configured, turned off, key refused, paused until hh:mm), last
    error, models, key or address form (password field, never pre-filled, cleared once saved, D-067), removal
    confirmed inline, `credential_source: "environment"` disables the field and names the variable;
  - **"Test connection"** per provider: disabled while running, "Testing… n s", result with model, time, tokens,
    translated reason, HTTP status and the provider's English message in a disclosure (D-069);
  - **provider order**: up / down buttons and an on / off checkbox per provider, one `PATCH`, a warning when every
    provider is off;
  - **AI usage**: today per provider and model (requests, successes, errors, tokens, average time) and the last 7
    days (the daily counter of SPEC §7);
  - **study settings** built from `GET /api/settings` in four groups (daily study, study day, consolidation, audio),
    bounds checked before sending, a refused value shown on its field. `ui_language` is left out on purpose (D-066).
- **Demo database**: keys, test and order disabled with an explanation; study settings editable.
- **Degraded-mode banner** on every page (`components/AiBanner.tsx`), separate wording when AI is turned off.
- **API layer**: `apiSend()` (JSON writes), `ApiError` with `code` and `detail`, hooks in `api/ai.ts` and
  `api/settings.ts`; the 14 error codes, `last_error` kinds and test reasons have i18n keys (D-068).
- **i18n**: every new string in `en.json` and `fr.json` (same keys, checked by the existing test).
- **Tests** (D-070): `test/mockApi.ts` (fetch router recording calls); `SettingsPage.test.tsx` (20 tests: cards,
  save / empty / refused / locked / unreachable, removal, environment, demo, test waiting state and single request,
  failed test, 409, order, usage, bounds, server-refused value, no language field, French); `AiBanner.test.tsx` (4).
  The home page test's fetch mock now returns a fresh response per request.
- **No backend change, no migration, no new dependency, SPEC.md unchanged.** README (Configuration),
  `docs/architecture.md`, D-066 to D-070.

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes **on the commit, in a clean temporary worktree**: ruff check, ruff format --check (145 files),
  pytest **856 passed, 4 deselected**, tsc, oxlint, vitest **35 passed** (11 before). `npm --prefix frontend run
  build` passes. (In the shared checkout, `ruff check` fails on `backend/app/services/importing.py`, an
  uncommitted M3 file that is not part of this milestone.)
- A test was checked to fail when the behaviour breaks (not clearing the key after saving).
- **Manual scenario** in the in-app browser, through the real Vite proxy, on a **temporary data folder and a
  temporary `.env`** (never the repository's): banner on the home page and its link; invented Gemini key saved (the
  temporary `.env` got the line, the field was emptied, the key was nowhere in the page's HTML, the banner went away);
  Ollama address `http://127.0.0.1:9` (nothing listening) saved then tested → "could not be reached" with the last
  error "network problem"; order changed (Groq first, Ollama off) and confirmed by `GET /api/ai/status`; unknown time
  zone refused next to its field with the backend's reason; French; light theme; phone width (375 px) after a fix
  (wide usage tables made the page scroll sideways).
- **No real AI request** was made: the invented Gemini key was never tested.

### Owner's manual scenario (about 3 minutes)

1. `start.cmd`, then **Settings** in the top bar. Without keys: the banner says the app runs without AI.
2. Paste your Gemini key, **Save**: "Saved", the field empties, the card says "Ready", the banner disappears.
3. **Test connection**: "It works: gemini-3.5-flash-lite answered in … s" — this is M2's last acceptance criterion
   and the first real use of the `responseFormat` field (D-056). If it fails, send the sentence and the provider
   message.
4. Same for Groq (and Ollama if installed: `http://127.0.0.1:11434`).
5. AI usage shows the test calls; change the order and check `uv run python -m app ai status` (from `backend/`).
6. `start.cmd -Demo`: the AI controls are disabled with an explanation.

### Left / notes

- **Still to confirm with real calls** (unchanged, D-056): `responseFormat`, upper-case `thinkingLevel`, real
  `retryDelay` values, free tier from Cameroon.
- Leaving the page during a test: the request continues and the status is refreshed, but the result is not shown on
  return (D-069).
- `ui_language` (backend setting) and the browser-stored language are not synchronised (D-066).
- The frontend has no formatter (no Prettier in the project); code follows the existing style by hand.

### Known issues

- None known.

## M2.c1 — AI and settings API (backend) ✅

M2.c was cut in two: this part is the backend (protection, `.env` writing, endpoints); the settings page and the
"test connection" button are **M2.c2**.

### Done

- **Protection of the API** (D-061, `app/api/guard.py`): Host check on every request, Origin / `Sec-Fetch-Site`
  check on writes, JSON-only write bodies; applies to the whole app (`/docs` too). Checked through a real Vite: the
  proxy rewrites `Host` and forwards `Origin`.
- **`.env` writing** (D-062, `app/services/env_file.py`): closed list of three variables, comments / order / CRLF
  kept, atomic replace, lock, Windows retries, refused when an environment variable defines the same name.
- **Shared connection test** (D-065): `app/services/ai_connection_test.py`, used by `ai test` (CLI tests unchanged)
  and the API; a lock per provider.
- **Endpoints** (D-063, D-064): `/api/ai/status`, `/api/ai/providers/{name}/credential` (PUT, DELETE),
  `/api/ai/test`, `/api/ai/usage`, `/api/settings` (GET, PATCH). New event `ai.credential_changed`. One error
  format, 422 answers without the received value.
- **Tests**: `tests/test_env_file.py`, `tests/ai/test_connection_test_service.py`, `tests/api/` (guard, AI
  endpoints, settings endpoints; real adapters over fake servers, temporary `.env` and database, network blocked).
- **No migration, no frontend change, SPEC.md unchanged.** README (Configuration), `docs/architecture.md`.

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **856 passed, 4 deselected** (735 before this
  milestone), tsc, oxlint, vitest 11 passed. `alembic check`: "No new upgrade operations detected".
- Manual scenario on a **temporary data folder and a temporary `.env`** (never the repository's): API started,
  `status` (nothing configured), PUT of an invented key (`configured: true`, no restart), an invalid key (422 with a
  clear message), a malformed body (422 without the value), `test` → `unavailable / auth` HTTP 400 "API key not
  valid" (**this was a real request to Google with an invented key**: it confirms that Gemini's 400 `API_KEY_INVALID`
  reaches the app as `auth`, D-059; it says nothing about `responseFormat`, which Google validates after the key),
  `usage` (1 request, error `auth`), DELETE (`VOCAB_GEMINI_API_KEY=` left in the file), PATCH of the order (taken
  into account at once), a PUT with a foreign `Origin` (403), a foreign `Host` (403), a `text/plain` body (415).
- The real `.env` and the personal database were never opened. `ai test` with a real key was **not provided** by the
  owner for this milestone and is still pending (see M2.b2's manual scenario).

### API reference for M2.c2

Every error is `{"detail": {"code", "message", ...}}`. Writes need `Content-Type: application/json`.

| Route | Request | Success (200) |
|---|---|---|
| `GET /api/ai/status` | – | `{ai_off, degraded, demo, order: [str], providers: [{name, capabilities: [str], configured, enabled, available, cooldown_until: ISO\|null, misconfigured, last_error: str\|null, models: {capability: model}, credential_source: "env_file"\|"environment"\|"none", credential_kind: "api_key"\|"base_url"}]}` (providers always `gemini, groq, ollama`, in that order) |
| `PUT /api/ai/providers/{name}/credential` | `{"value": str}` (extra fields refused) | the provider object above |
| `DELETE /api/ai/providers/{name}/credential` | – | the provider object |
| `POST /api/ai/test` | `{"provider": str}` | `{provider, status: "ok"\|"incomplete"\|"unavailable", reason: str\|null (no_provider_configured, network, quota, auth, timeout, all_failed), model, elapsed_ms, input_tokens, output_tokens, error_code, http_status, message, detail_kind: "none"\|"provider"\|"schema"}`. A call can last up to ~90 s: the page must show a waiting state. |
| `GET /api/ai/usage?days=7` (1–90) | – | `{days: [{day: "YYYY-MM-DD", requests, successes, input_tokens, output_tokens, rows: [{provider, model, requests, successes, errors: {code: n}, input_tokens, output_tokens, avg_duration_ms\|null}]}]}`, today first, empty days included |
| `GET /api/settings` | – | `{key: {value, default, is_default, type: "int"\|"float"\|"str"\|"list", minimum, maximum, choices, item_choices}}` for every setting |
| `PATCH /api/settings` | `{key: value, ...}` | the same object as `GET`, all or nothing |

| Status | `code` | When |
|---|---|---|
| 403 | `forbidden_host`, `forbidden_origin`, `cross_site_request` | guard (the page itself never triggers them) |
| 415 | `unsupported_media_type` | write body that is not JSON |
| 422 | `invalid_request` (+ `errors: [{loc, message}]`) | body or query of the wrong shape (e.g. `days=0`) |
| 422 | `invalid_credential` | key or address that cannot be saved (message says why, never the value) |
| 422 | `invalid_setting` (+ `key`) | unknown key, wrong type, out of bounds, duplicate or unknown provider in the order |
| 404 | `unknown_provider` | provider name not gemini / groq / ollama |
| 409 | `set_in_environment` | an environment variable defines the key: editing refused |
| 409 | `env_file_locked` | another program holds `.env` (close it, retry) |
| 409 | `test_in_progress` | the same provider is already being tested |
| 409 | `demo_read_only` | demo database: credential writes, test and order change refused |
| 500 | `env_file_write_failed` | `.env` could not be written |
| 503 | `database_unavailable` | usage / settings with no database file (`db upgrade` first) |

Notes for the page: `ollama` has `credential_kind: "base_url"` (a URL, shown in clear by the user's own choice, but
never returned by the API: show the state "configured", not the value). `configured` is true after a PUT without a
restart. `last_error` is one of `rate_limited, quota_exhausted, transient, network, auth, bad_request,
invalid_output`. Status codes and `code` values should get i18n keys; `message` is English.

### Left / notes

- **M2.c2**: the settings page (keys, order, test button, usage), i18n en / fr, a banner when `degraded`, handling
  of `demo`, `credential_source: "environment"` (field disabled with an explanation) and the error codes above.
  The browser calls go through the Vite proxy, which already forwards `Origin`; nothing to change in `vite.config.ts`.
- **Still to confirm with real calls** (unchanged from M2.b2, D-056): `responseFormat`, upper-case `thinkingLevel`,
  real `retryDelay` values, free tier from Cameroon.
- `Origin`-less writes (curl, scripts) are accepted by design: only a browser sets `Origin`, and a browser page
  cannot remove it.
- The per-provider test lock and the `.env` lock are per process: fine for one local backend, not for several.

### Known issues

- None known.

## M2.b2 — Gemini adapter ✅

### Done

- **Facts re-verified in the official documentation (2026-10-16)**, D-056: models (new: `gemini-4-argon` has no
  free tier), free tier and privacy (unchanged), quotas and regions (unchanged), `responseFormat` confirmed in
  the v1beta discovery document (the older JSON fields are marked deprecated), thinking levels per model
  (`gemini-3.8-flash` has no minimal level), `temperature` ignored on recent models, error pages (still only the
  Interactions API). Two points of the documentation contradict each other (thinking on 2.5 models) and the real
  `generateContent` error body is still undocumented: both are listed as "to confirm".
- **`providers/gemini.py`** (D-057): `generateContent` v1beta, key in `x-goog-api-key` only, default
  `gemini-3.5-flash-lite` (`VOCAB_GEMINI_MODEL`, new in `Settings` and `.env.example`), model name validated before
  it enters the URL, thinking table + 512 tokens of headroom, thoughts left out of the answer, tokens = candidates +
  thoughts, blocked / truncated / empty answers are `invalid_output`.
- **Risk n° 1 isolated** (D-058): one function builds the JSON fields (`responseFormat` or the older
  `responseMimeType` + `responseJsonSchema`); a 400 that names the refused field makes the adapter fall back for
  that call and use the older fields from then on.
- **`to_gemini_schema`** (`providers/schema.py`): the Groq / Ollama simplification, but `minimum`, `maximum`,
  `minItems`, `maxItems` are kept. Groq and Ollama schemas are byte-identical to M2.b1's.
- **Errors** (D-059): both body shapes (classic `status` + `details[]`, Interactions `error.code`); a `PerDay`
  quota is `quota_exhausted` with `retry_after` ignored; per-minute 429 uses `retryDelay` / `Retry-After` /
  "retry in Ns"; 400 `API_KEY_INVALID` and the region / free-tier `FAILED_PRECONDITION` are `auth`; 402 is a quota
  problem; 404 points to `VOCAB_GEMINI_MODEL`.
- **Policy** (D-060): `MAX_WAIT_S` kept at 20 s, with the reasoning and tests on Gemini-shaped delays (14 s and 20 s
  wait, 21 s and 57 s fall back, a daily quota never waits).
- **Wiring**: `build_providers()` returns Gemini, Groq and Ollama; `ai status` / `ai test` lost their "not available
  yet" special cases (`ai test --provider gemini` works like the others).
- **Tests** (offline, loopback fake servers, 26 fixtures in `tests/ai/fixtures/gemini/`): adapter (request, thinking
  table, both JSON modes, every answer and error row), schema converter, gateway with Gemini + Groq (retry, fallback,
  cooldowns, `reload()`, repair, JSON-field switch), hostile-server secret tests, CLI, settings, `build_providers`,
  plus the live test (`tests/live`, off by default).
- **README**: Google AI Studio key section with the free-tier privacy warning; `docs/architecture.md`; D-056 to D-060.
- **No migration, no frontend change, SPEC.md unchanged.**

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **735 passed, 4 deselected** (the live tests;
  621 before this milestone), tsc, oxlint, vitest 11 passed.
- Without any key (variables forced to empty, data directory in a temporary folder): `ai status` lists Gemini,
  Groq and Ollama as not configured with their models and no "not available yet"; `ai test --provider gemini` exits
  2 (no database / not configured); `--demo ai test` exits 2; nothing created in the repository.
- **Not run by me, on purpose**: no real Gemini call, no live test, no `ai test` with a key. The `.env` was never
  opened.

### Owner's manual scenario (with your own key, about 2 minutes)

1. Create a key at <https://aistudio.google.com/apikey>, put `VOCAB_GEMINI_API_KEY=...` in `.env` (README, section
   Gemini).
2. `uv run python -m app ai status` (from `backend/`): Gemini configured, model `gemini-3.5-flash-lite`.
3. `uv run python -m app ai test --provider gemini`: `gemini: ok (...)`, exit 0. This is the first real exercise
   of the `responseFormat` field. If it fails, send the one-line message.
4. A wrong key: a clear `auth` message (never the key), exit 1. From a country the free tier does not serve: `auth`
   with a region / free-tier message.
5. `uv run python -m app ai usage`: today's calls with Gemini's tokens (candidates + thinking).
6. Optional: `$env:VOCAB_RUN_LIVE=1; uv --directory backend run pytest tests/live -m live -v` (a warning says if
   the older JSON fields had to be used).

### Left / notes

- **To confirm by the first real call** (D-056): the `responseFormat` field and the upper-case `thinkingLevel`
  are accepted; the real error bodies and quota ids; the real `retryDelay` values (then re-examine D-060);
  whether the free tier works in Cameroon (hypothesis B.11). If `responseFormat` is refused, D-058's switch
  already copes; the default should then be changed.
- **Gemini first means content goes to Google's free tier first** (may be used to improve its products): the
  README says so; the settings page (M2.c) is where the order and the keys become editable.
- `gemini-3.1-flash-lite` and any model set through `VOCAB_GEMINI_MODEL` outside the thinking table get no
  `thinkingConfig` (a model that thinks by default is protected by the 512-token headroom only).
- Live tests are 1 request per provider, 2 for Gemini if the JSON field has to be switched.

### Known issues

- None known.

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

## Next step: M3 (library and import)

- **M3 — Library and import** (SPEC §10, module A): Markdown import with preview, quick add, batch enrichment
  through the gateway (call the AI first, then write in a short transaction), review and editing, intake triage, list
  extension, duplicates, search and filters.
- Before or alongside: the owner's real calls (M2.c2 scenario above) to close M2 and the D-056 "to confirm" list.
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

