# Security review (M10.b)

Scope: the application in use mode (`start.ps1 -Use`: one process, `127.0.0.1:8000`, the built frontend and the
API on the same port), plus what was already in place. Done on 2026-10-27, branch `feat/m10b-use-mode`.
Status: **OK** (already protected, proof given), **fixed** (found and corrected in M10.b), **accepted** (a risk
that stays, with its decision). Tests named `test_*` are in `backend/tests/`; "run" means the command was run
in this session.

## 1. Host / Origin guard (D-061) in single-port mode

| Threat | Protection | Proof | Status |
|---|---|---|---|
| DNS rebinding: a hostile name resolving to 127.0.0.1 reads `/`, `/assets/...`, `/api/...` | `Host` must be `127.0.0.1`, `localhost` or `[::1]` with the backend port; the guard is the outermost layer | `api/test_frontend_serving.py::test_a_foreign_host_gets_403_before_any_redirect` (4 hosts x `/`, an asset, `/api/health`, a page: 403 `forbidden_host`, no `Location`); run: `curl -H "Host: evil.example" http://127.0.0.1:8000/` gives 403 | OK |
| Foreign `Origin` and `Origin: null` on a write | 403 `forbidden_origin` | `test_the_guard_still_applies_to_writes_in_single_port_mode` (evil.example, `null`, another port) | OK |
| `Sec-Fetch-Site: cross-site` | 403 `cross_site_request` | same test | OK |
| A form posted from another site (non-JSON body) | 415 outside `/api/speech/` | same test (`text/plain` gives 415); the existing `api/test_guard.py` passes **unmodified** | OK |
| The page served on 8000 must still be able to write | `Origin: http://127.0.0.1:8000` is in the allowed list | same test (accepted, reaches the route); in the browser: grading and rating a card by keyboard, downloading a backup (`POST /api/backup`) all worked | OK |
| A redirect leaking to a hostile Host | `LocalhostRedirect` sits inside the guard and only serves `localhost` / `[::1]` with the right port | `test_localhost_is_redirected_to_the_loopback_address`, `test_a_foreign_host_gets_403_before_any_redirect` | OK |

## 2. Paths

| Threat | Protection | Proof | Status |
|---|---|---|---|
| `/assets/../.env`, `/%2e%2e/.env`, `/assets/..%2f..%2fbackend%2fapp%2fconfig.py`, `..%5c`, `\`, absolute Windows path, `%00`, NTFS stream, a sibling folder `dist2` | `resolve_file`: refuses NUL, `\` and `:` before touching the disk, resolves the path (links, `..`) and requires it to stay inside `dist`; a missing file is a 404, never `index.html` | `test_malicious_paths_never_leave_dist` (18 URLs), `test_resolve_file_refuses_decoded_paths_outside_dist` (10), `test_a_symbolic_link_out_of_dist_is_not_followed` (skipped without the symlink privilege on Windows) | OK |
| The check is really what stops them | Broken on purpose, then restored: removing the "stays inside `dist`" test made 7 of those tests fail; serving `index.html` for a missing `/assets/` file made `test_missing_files_are_404_and_never_html` fail | run in this session | OK |
| Audio route | `AudioStore.resolve` refuses any name outside the pattern (D-169) | `test_audio_store.py::test_resolve_refuses_paths_outside_the_pattern`, `test_a_name_outside_the_pattern_is_refused` | OK |
| Folder of the automatic copy | absolute, existing, writable, not inside a Git repository (except `data/`) | `test_backup_auto.py::test_folder_validation`, `test_a_folder_inside_a_git_repository_is_refused_except_under_data` | OK |

## 3. Secrets

| Threat | Protection | Proof | Status |
|---|---|---|---|
| A key in the build | keys only exist in the backend (`app/config.py`); the frontend never receives one | run: `AIza` and `gsk_` found **0** times in `frontend/dist`; `VOCAB_` found 4 times, all in `SettingsPage-*.js`, as the **names** of variables shown to the user ("put `VOCAB_GEMINI_API_KEY` in `.env`"), never a value | OK |
| A `VITE_*` variable | none exists | run: `grep VITE_` in `frontend/src`, `vite.config.ts`, `index.html`: 0 lines | OK |
| A key in responses, logs, `event_log`, exports, archives | masking (`app/ai/redact.py`), schema errors that do not quote input, credential events without values | `ai/test_redaction.py`, `ai/test_gateway_journal.py::test_a_key_in_an_error_message_never_reaches_the_database_or_the_result`, `ai/test_provider_secrets.py`, `api/test_ai_api.py::test_credential_events_carry_no_secret_and_only_real_changes`, `api/test_azure_api.py::test_a_hostile_azure_never_leaks_the_key`, `api/test_export_api.py::test_no_secret_in_the_archive` (CSV), `test_backup_service.py` (the backup archive holds neither Gemini nor Groq test key) | OK |
| A key or a secret in a 500 | the 500 body is Starlette's plain "Internal Server Error" | `test_an_unhandled_error_does_not_leak_a_traceback` (route raising an exception whose message holds a secret) | OK |
| Keys in Git history | none committed | run: `git log -p --all -G"AIza[0-9A-Za-z_-]{30,}\|gsk_[0-9A-Za-z]{20,}"`: **2 commits, 2 lines, both `KEY = "AIza..."` constants in tests** (`tests/test_env_file.py` from `995a935`, `tests/ai/test_gemini_adapter.py` from `7e60b4a`); the values contain `test`/`fake` markers and are not real keys (checked by shape, values not displayed). 0 matches for `gsk_`. The Azure test key follows no fixed pattern: not searched | OK (test fixtures) |

## 4. Tracked files

| Threat | Protection | Proof | Status |
|---|---|---|---|
| Personal data in Git | `.gitignore` covers `data/` (so `data/backups/`, exports, audio), `*.db`, `*.sqlite*`, `*.zip`, `exports/`, `backups/`, `.env`, `frontend/dist/` | run: `git check-ignore -v` on `data/backups/x.zip`, `data/exports/a.csv`, `.env`, `frontend/dist/index.html` all match; `git ls-files` filtered on database, zip, audio, `.env`, `data/`, `dist` extensions: **0 files** | OK |

## 5. Execution

| Threat | Protection | Proof | Status |
|---|---|---|---|
| `--reload` / debug in use mode | `python -m app --use` calls `uvicorn.run(..., reload=False, server_header=False)`; the application never sets `debug` | code; run: the response headers of `/` carry no `server:` line | OK |
| Listening beyond the loopback | `VOCAB_HOST` accepts only loopback names | `test_config.py` (existing); run: the listener was `127.0.0.1:8000` | OK |
| Stack trace in a 500 | see section 3 | `test_an_unhandled_error_does_not_leak_a_traceback` | OK |
| Missing security headers | `SecurityHeaders` on every response; CSP on the frontend only (D-311, D-312) | `test_security_headers_everywhere_and_csp_on_the_frontend_only`; in a browser the CSP is **enforced**: a probe `setAttribute('style', ...)` raised a `style-src-attr` violation, and 15 screens x 4 (light/dark, EN/FR) x 2 widths raised none | OK |
| Clickjacking / framing | `frame-ancestors 'none'` | header test | OK |
| `/docs`, `/redoc`, `/openapi.json` | unchanged, no strict CSP, guard unchanged | `test_docs_and_openapi_still_work_without_the_strict_csp` | OK |
| A write on a page path answered with HTML | a page path accepts GET / HEAD only | `test_a_write_on_a_page_path_is_never_answered_with_html` (405) | OK |
| A failure of `read_only` left the database connection read-only (500 on `POST /api/backup`, seen while verifying the download) | the reset of `PRAGMA query_only` now runs on the same connection, before it goes back to the pool (D-315) | `test_read_only_session.py` fails on the old code, passes on the new | **fixed** |

## 6. Input limits (existing)

| Limit | Value | Test |
|---|---|---|
| Recording | 10 MB (`MAX_AUDIO_BYTES`), by `Content-Length` and while streaming | `api/test_speech_api.py::test_too_large_by_content_length`, `test_too_large_while_streaming` |
| Import text | 300,000 characters (`MAX_TEXT_CHARS`) | `api/test_library_api.py` (`too_large`) |
| Backup archive (zip bomb) | `MAX_UNCOMPRESSED_BYTES` = 2 GiB of bytes actually read, 16 MiB manifest | `test_backup_verify.py::test_zip_bomb_is_refused` |
| Request validation | 422 without echoing the input | `api/test_ai_api.py::test_malformed_bodies_get_a_422_that_never_quotes_the_input` |

## 7. Dependencies

| Tool | Result |
|---|---|
| `npm --prefix frontend audit --omit=dev` | found 0 vulnerabilities |
| `npm --prefix frontend audit` (full) | found 0 vulnerabilities |
| `npm audit --omit=dev` (root) | found 0 vulnerabilities |
| `npm audit` (root, full) | found 0 vulnerabilities |
| `uv export --frozen --no-hashes --format requirements-txt` (105 lines) then `uvx pip-audit -r <file>` | No known vulnerabilities found |

No advisory, so nothing to upgrade and no major bump to report. `pip-audit` was run with `uvx` and is not a
dependency of the project. The audit is not added to the blocking CI (out of scope).

## 8. What is not protected, and why (accepted risks)

| Risk | Why it stays | Decision |
|---|---|---|
| Another program running as the same Windows user can read `data/` (database, recordings, backups) and `.env` | the application is single-user and local; protecting files from the same user needs OS-level encryption, out of scope | D-318 |
| No HTTPS on the loopback | traffic never leaves the machine; a certificate for `127.0.0.1` would add a warning for no gain | D-318 |
| No CSRF token | replaced by the Host / Origin / Sec-Fetch-Site / JSON-only rules (D-061), which a page of another site cannot forge | D-061, D-318 |
| The pre-upgrade copy and the backups are not encrypted | same as the first line; the card tells the owner to keep them private | D-313, D-306 |

## Not verified

- The Azure test key was not searched for in the Git history (no fixed prefix).
- The symbolic-link test is skipped on this machine (no privilege to create links).
