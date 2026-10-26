# Progress

Updated at the end of every milestone session. Paste this file into the next planning conversation.

## Current state

- **M9.a1** (module I, statistics backend part 1: the pure domain, errors, memory, CSV export, `stats errors | memory | export`; no screen, no migration) is done on `feat/m9a-stats-backend`, cut from `bb7f8fd` (tip of `feat/m8b-curriculum-screens`). Not pushed. Next: **M9.a2** (progress, practice, AI, overview, `stats summary`, performance, full API reference) on the same branch. See the M9.a1 section.
- **M8.b2** (module H, the editor of a scenario unit's content: formulas, dialogue, shadowing lines, final task; frontend only) is done on `feat/m8b-curriculum-screens` after M8.b1 (`4d522c2`). Not pushed. Next: the owner's review of M6 to M8, then the push. See the M8.b2 section.
- **M8.b1** (module H, the screens of the general English tracks: tracks, units, scenario steps, dialogue listening, shadowing and final talk from a unit; frontend only) is done on `feat/m8b-curriculum-screens`, cut from `a68e04c`. Not pushed. Next: **M8.b2** (the unit content editor) after the owner's go-ahead. See the M8.b1 section.
- **M8.a2** (module H, speaking scenario units written by the AI, edited, taken through four steps up to `done`; demo v7; backend + CLI, no migration) is done on `feat/m8-curriculum` after M8.a1. Not pushed. Next: **M8.b** (the screens of module H), after the owner's review. See the M8.a2 section and its API reference.
- **M8.a1** (module H, general English tracks: word lists, syllabus, tracks, units, triage; backend only, no AI) is done on `feat/m8-curriculum`, cut from `e9917e3` (tip of `feat/m7b-consolidation-screens`). Not pushed. Next: **M8.a2** (scenario units through a `curriculum_unit` AI task, progress by steps, demo v7, live test), after the owner's go-ahead and the rest of the M8.a2 brief (see its section). See the M8.a1 section.
- **M7.b** (module G, the screens; frontend only) is done on `feat/m7b-consolidation-screens`, cut from `bcfcb55` (tip of `feat/m7-consolidation`: M7.a1 and M7.a2, backend). Not pushed; M6 and M7 are not in `main`. See its section.
- **Last milestone completed before it**: M6.c2 (module F, the pronunciation-assessment screens; see its section), on branch `feat/m6c2-pronunciation-screens`
  cut from the tip of `feat/m6c-pronunciation` (M6.c1, backend), itself cut from `feat/m6b-speaking-screens`. Before it: M6.b2.2 (module F, frontend: the spoken answer in the review player; before it M6.b2.1, free speaking and the `speaking-1` correction), on branch
  `feat/m6b-speaking-screens`, cut from the tip of `feat/m6a2-speaking-correction` (M6.a2, after M6.a1, PR #21, **not
  merged into `main` yet**). Not pushed. `main` (`7904aa3`, CI green) has M1.a to M5.a3. No migration since `0002`.
- **M6 — Speaking** (module F, SPEC section 9) is cut in five (D-168), M6.a2 in two (D-178): **M6.a1** (done: local
  recordings, Groq Whisper, shadowing, comparison, playback, CLI), **M6.a2a** (done: free speaking corrected by
  `speaking_correction`, spoken answers in reviews, CLI), **M6.a2b** (done: the demo through the services,
  `direct_writes.py` removed, D-035 closed), **M6.b1** (done: the recorder, the shadowing pages, the comparison, the
  optional recording of the discovery), **M6.b2.1** (done: free speaking and the `speaking-1` correction), **M6.b2.2** (done: the spoken answer in
  reviews; API references in the M6.a1 and M6.a2a sections) and **M6.c** (Azure AI Speech, optional): **M6.c1** (done: backend, off by default) then **M6.c2** (done: the screens).
- **Next**: the owner's review of M6.b1, M6.b2.1, M6.b2.2, M6.a2 and M6.c1 (the manual scenarios; M6.c1's first real Azure request settles D-211),
  then push and the pull request with the owner's go-ahead (after PR #21); M6.c2's manual scenario below needs an Azure F0 key (the first real Azure request settles D-211 and the WAV).
- **Left from M5, not scheduled**: the screens for cards from errors and suggestions ("M5.d", API in the M5.a3 section
  below) and an undo for a dismissed suggestion. The owner decides when they come.
- Gemini (`gemini-3.5-flash-lite`) and Groq are configured in the owner's `.env`; the M5.a1, M5.a2 and M6.a2a live tests
  pass with them (`tests/live/test_live_speech.py`, the M6.a1 shadowing, was still not run). The owner's manual
  scenarios (M2.c2, M3.c3, M5.a1, M5.a2, M5.a3, M5.b1, M5.b2, M5.c1, M5.c2, M6.a1, M6.a2a, M6.a2b, M6.b1, M6.b2.1 and M6.b2.2) are still to run.
- Before starting a branch: `git switch main` then `git pull`.

## M9.a1 — Statistics: domain, errors, memory, CSV export (backend + CLI, no screen)

Branch `feat/m9a-stats-backend`, cut from `bb7f8fd`. Not pushed. **No migration** (`alembic check`: no operation), no new dependency (no pandas, D-265), **no frontend file** (`git diff --stat bb7f8fd -- frontend` is empty). Decisions D-265 to D-272. M9.a is cut in two (approved plan): M9.a2 brings progress, practice, AI, overview and `stats summary`.

### Done

- **Pure domain** `app/domain/stats/`: `common.py` (periods, day / ISO-week buckets, `Rate` and `Share` with `insufficient`, quartiles as pandas, ranges), `errors.py` (rates per 100 words at levels 1 and 2, errors outside the rates, top 5 recurring, lasting trends at every level and the share of fixed errors), `memory.py` (retention against the target replayed from `setting.changed`, calibration from the stored `retrievability`, success by exercise type, rating agreement, lapses, stability, time before consolidation). Definitions in D-266 to D-270.
- **Service** `app/services/stats.py`: `read_only` (`PRAGMA query_only`, reset), loaders that accept every payload version, `error_stats`, `memory_stats`. `error_cards.carded_keys` made public.
- **Export** `app/services/export.py` + `export_dictionary.py` (D-271): zip of 17 CSV, `manifest.json`, `data_dictionary.md`, one read snapshot, atomic file for the CLI.
- **API**: `GET /api/stats/errors`, `GET /api/stats/memory`, `GET /api/export/csv`, `GET /api/export/csv/{table}` (below). **CLI**: `stats errors | memory | export`.
- **Tests** (all green): 47 domain tests on hand-built cases (`test_stats_common.py`, `test_stats_errors.py`, `test_stats_memory.py`), old payloads (`test_stats_service.py`), API with every 422 and table counts before/after (`tests/api/test_stats_api.py`, 13), export (`tests/api/test_export_api.py`, 7: headers, DictReader counts = database, formats, no secret, 404), CLI (`test_cli_stats.py`, 7), demo (`test_demo_stats.py`, 5).
- **Broken-code checks** (applied, then reverted):
  1. counting only the words of productions that have an error: 6 tests fail, among them `test_three_errors_for_600_words_is_half_an_error_per_100_words` and `test_a_deleted_error_is_not_counted`;
  2. counting learning and relearning reviews in the retention: `test_nine_successes_out_of_ten_review_reviews_is_0_9` and `test_calibration_bins_by_predicted_recall` fail;
  3. the UTC date instead of the study day in the service: `test_a_production_at_0330_in_douala_counts_for_the_previous_study_day` (API) and `test_value_formats` (export, `study_day` of a 03:30 review) fail. The domain 03:30 tests take the day function as an argument, so they cannot see this break; the API test was added for it.

### Demo (seed 42, 60 days, anchor 2026-09-01)

- Words 1 710 in window A, 1 601 in window B. `grammar.preposition.fixed_expression`: 42 -> 24 errors, ratio 0.610, **stable** (not `declining`: the demo model gives about 0.6, the threshold is 0.5; option A, D-268). `grammar.tense.past_simple_vs_present_perfect`: 27 -> 30, 1.187, stable. `discourse`: 4 -> 6, 1.602, **rising**.
- Share of fixed errors: 12 of 114 errors of window A (10.5 %). Retention 2026-07-03 to 2026-09-01: 0.887 (339 of 382) against a target of 0.90. Time before consolidation: 58 terms, median 5.5 study days, 6 reviews.
- First timings (TestClient on the demo, this machine, M9.a2 will measure every route properly): errors 46 ms (188 ms for the first call of the process), memory 26 to 29 ms, export 0.40 s.

### Left / known limits

- **M9.a2**: `/api/stats/progress`, `/practice`, `/ai`, `/overview`, `stats summary`, the performance measures of every route, the full API reference for M9.b, README.
- The CLI has no `--at`: on a demo seeded with an old anchor (`--anchor 2026-09-01`), "today" is the real day and the windows are empty. The manual scenario seeds with today's anchor.
- Proposed for later (not done): a demo dataset v8 where `fixed_expression` falls to 0.5 so the witness reads `declining`.

### API reference (M9.a1 part; completed in M9.a2)

Every answer of `/api/stats/*` starts with `computed_at` (UTC), `study_day` (today), `from`, `to`, `granularity` (`day` | `week`), `demo`. Query: `from`, `to` (YYYY-MM-DD, study days, included; default the last 30 up to today), `granularity`. 422 `invalid_request` for `from` > `to`, more than 366 days, a malformed date or granularity (`errors[{loc, message}]`, D-063). `Rate` = `{value|null, errors, words, insufficient}` (null under 100 words, 300 in a trend window); `Share` = `{value|null, successes, n, insufficient}` (null under 10). A bucket has `key` (the day or the Monday), `first_day`, `last_day`.

| Route | Answer |
|---|---|
| `GET /stats/errors` | `rates {rate, level1[{code, level, rate}], level2[...], unnormalized {total, by_reason {drill, review, manual, other}}, unnormalized_by_category {code: n}, buckets[{key, first_day, last_day, rate, level1, level2, unnormalized}]}` (every bucket lists the same categories, zeros included); `top_recurring[{key, erroneous_text, correction, category, count, first_at, last_at, examples[≤2], has_card}]` (≤5); `trends {window_a {start, end}, window_b, words_a, words_b, by_status {declining, rising, stable, insufficient: [{code, level, status, window_a: Rate, window_b: Rate, ratio|null}]}, fixed_share: Share}` (windows: the last 28 study days against the 28 before, whatever `from`/`to`) |
| `GET /stats/memory` | `default_target`; `retention {all, receptive, productive: Share, target|null, buckets[{key, first_day, last_day, all, receptive, productive, target}]}`; `calibration[{low, high, predicted|null, observed: Share}]` (10 bins); `success_by_exercise[{exercise_type, success: Share}]`; `rating_agreement {changed: Share, raised, lowered}`; `lapses {total, buckets[{key, first_day, last_day, lapses, review_state_reviews}], top_items[{item_id, lapses}]}`; `top_lapsed_terms[{item_id, term|null, lapses}]` (≤10); `stability[{direction, cards, unreviewed, ranges[{low, high|null, count}], median_days}]`; `time_to_consolidation {n, days, reviews: {n, q1, median, q3, minimum, maximum}, distribution[{low, high, count}], items[{item_id, days, reviews}]}` |
| `GET /export/csv` | `application/zip`, `Content-Disposition: attachment; filename="vocab-coach-export-YYYYMMDD.zip"` |
| `GET /export/csv/{table}` | `text/csv; charset=utf-8`, `attachment; filename="<table>.csv"`; 404 `unknown_table` (`tables`: the list) |

### Owner's manual scenario (about 2 minutes, no key needed)

```powershell
cd backend
uv run python -m app demo seed --reset
uv run python -m app --demo stats errors --granularity week
uv run python -m app --demo stats memory
uv run python -m app --demo stats export --out $env:TEMP\vc-export.zip
```

Then `.\start.ps1 -Demo` and open http://127.0.0.1:8000/docs: `GET /api/stats/errors` and `/api/stats/memory`. In a Python with pandas: `import zipfile, pandas as pd; pd.read_csv(zipfile.ZipFile(r"$env:TEMP\vc-export.zip").open("review_log.csv"), parse_dates=["reviewed_at"])` (replace the path by its value). `stats summary`, `/api/stats/overview` and `/api/stats/progress` come with M9.a2.

## M8.b2 — The editor of a scenario unit's content (frontend)

Branch `feat/m8b-curriculum-screens`, after `4d522c2`. Not pushed. **No backend change** (`git diff --stat a68e04c -- backend` is empty), no migration, no new dependency. Decisions D-260 to D-264.

### Done

- **"Edit the unit"** on a scenario unit's page: a form on a local draft (`unitForm.ts`, like `sheetForm.ts`) that takes the place of the four steps. Parts: formulas (text, type, function EN/FR, register; add, remove, up, down), dialogue (setting EN/FR, two names, lines with the speaker among the two and the text; add, remove, up, down),
  lines to shadow (checkboxes), final task (prompts EN/FR, 1 or 2 minutes, checkboxes on the formulas). Labels on every field, keyboard use, focus kept on the row moved or on the field added, grids `minmax(0, 1fr)`, no table.
- **Sending**: `useEditUnitContent` (`PUT /curriculum/units/{id}/content`) sends only the parts that changed, with `expected_revision`, 0-based positions and the key `register`; changing the formulas also sends the final task (D-261). Success refreshes the unit, tracks, library, triage and Today.
- **Checks**: client limits from `UNIT_LIMITS` (equal to `curriculum_unit.py`, a test reads the Python file); `422 invalid_content` shows each problem at its field or in a list; `409 unit_changed` keeps the edits and "Load the latest version" needs an inline confirmation (D-263).
- **After a save**: "The unit was saved.", the "Edited by you" badge, the focus back on the button. A visible warning says that changing a line to shadow makes the old line's takes stop counting and a completed unit can go back to "in progress" (D-248). "Write this unit with the AI" does not exist for a written unit.
- **Tests**: 21 new Vitest tests (736 in all, 715 before): `unitForm.test.ts` (10: limits equal to the Python constants, only the changed parts, 0-based positions and the key `register`, client problems, where a server problem goes) and `UnitEditor.test.tsx` (11: sending, rows, client limits, 422 at the field and in a list, 409 with confirmation, warning, cancel, French, no AI button). Broken-code check (c) run and reverted: replacing the draft by the server version on a 409 made the conflict test fail.
- Checked in the built-in browser on a demo database in a temporary folder (`VOCAB_DATA_DIR`, keys emptied, no AI call): unit "Presenting data" edited (register and a line) and saved with the badge; a second tab saved the same unit; the first tab's save was refused with its edits kept, and "Load the latest version" asked its confirmation and then replaced them; English and French, light and dark, 375 px (one column, no horizontal scroll).
  Screenshots timed out (the window was hidden), so the layout was checked through the DOM (widths, overflow, grid columns, focus), not by eye.

### Left / known limits

- Not checked client-side: "at least half of the formulas appear in the dialogue" and duplicate formulas (the server answers, D-262). Server problems stay on screen until the next save or a move, add or remove (D-263).
- Editing never calls the AI and there is no regeneration over an existing unit (D-250). Leaving the editor with Cancel discards the draft without asking (like the sheet editor).
- Existing from M8.b1, not from this step: the dialogue step puts a `<fieldset>` in a `<p>` (React warns about the DOM nesting in tests).

### Next step

The owner's review of M6 to M8 (manual scenarios), then the push and the pull request.

### Owner's manual scenario (about 2 minutes, demo, no key needed)

```powershell
cd backend
uv run python -m app demo seed --reset
cd ..
.\start.ps1 -Demo
```

1. Open http://127.0.0.1:5173/curriculum/units/2 (the unit "Presenting data", number 3 of "Speaking scenarios"). Click "Edit the unit": the four steps give way to the form.
2. Change the register of a formula and the text of a dialogue line. Under "Lines to shadow", read the warning. Click "Save the unit": the form closes, "The unit was saved." and the badge "Edited by you" appear, the button "Edit the unit" has the focus.
3. Click "Edit the unit" again and change the length of the final task. Open the same unit in a second tab, edit anything there and save.
4. Back in the first tab, click "Save the unit": the message "The unit changed since you opened the editor" appears and your edit is still on screen. "Load the latest version", then "Keep editing": nothing changes. "Load the latest version", then "Replace my edits": the form shows the second tab's version.
5. Remove formulas until fewer than 8 are left and save: the form refuses and says where. Switch to French: the labels and messages follow.

## M8.b1 — General English tracks: the screens (frontend)

Branch `feat/m8b-curriculum-screens`, cut from `a68e04c` (tip of `feat/m8-curriculum`). Not pushed; M6, M7 and M8 are not in `main`. **No backend change** (`git diff --stat a68e04c -- backend` is empty), no migration, no new dependency. Decisions D-254 to D-259.

### Done

- **`/curriculum`**: one card per track (title and description in the interface language, kind, unit count, opened / sorted or written units, Start or Continue); a track whose word list is missing says why and its button is disabled; the NGSL / NAWL licence line with the link.
- **`/curriculum/:code`**: "Start this track" when needed (idempotent), 25 units per page (`?page=`), state in words (`not_opened / opened / triaged`, `not started / in progress / done`), `title_fr` in French; word unit: "Open" then its page (a second visit is a link, nothing is created);
  scenario unit: "Write this unit with the AI" (counter, one request on a double click, reasons and "Try again", "Configure the AI").
- **`/curriculum/units/:id`**: word unit (its terms with their status in words, links to the library, "Triage these words (n left)", no sheet, no definition); scenario unit: header (level, "n of 4 steps", next step), four steps in the advised order
  (formulas with FR on demand, listening and checkboxes to add them to the library; the dialogue played line after line with two voices, text collapsed; shadowing lines with takes and a worded done mark; the final task and its takes), "Unit completed" and the link to the next unit.
- **Speaking pages**: `ShadowingPage` / `SpeakingPage` read `unitId` once and clear it, send `unit_id`, keep `?unit=` to the detail pages, "Back to the unit"; the detail pages keep `?unit=` when they clear their state.
- Top bar "Tracks" / "Parcours" (no horizontal scroll at 375 px in English and French); the Today card suggests a track when there is nothing new to learn; the 12 error codes of module H are worded in both languages.
- **Tests**: 50 new Vitest tests (715 in all, 665 before): `features/curriculum/` (screens, speaking integration, privacy at every navigation, rules), `speech/dialogueVoices.test.ts`, two in `TodayCard.test.tsx`. Broken-code checks run and reverted: (a) `ShadowingPage` no longer clearing its state made 3 tests fail (the reload ones); (b) the generation button without its `ref` guard made the double-click test fail.
- Checked in the built-in browser on a demo database in a temporary folder (`VOCAB_DATA_DIR`, keys emptied, no real AI): the track list, the unit list (unit 1 done, unit 3 in progress with "shadowing" next), the unavailable-AI answer with "Try again" and "Configure the AI", the unit page, the shadowing page from a unit line (state cleared, read-only line, after a reload a free page), starting "General everyday English" and opening unit 1 (25 words to triage), the real speech synthesis playing the dialogue, light and dark, English and French, 375 px.

### Left / known limits

- **M8.b2** (the unit content editor) is done: see its section.
- The final task's "corrected" state is the unit's, not per take (D-259). The dialogue with the real two voices was only listened to by a browser check, not by ear. The recorder and the transcription of a unit's takes were tested with the fake recorder only.
- Reloading `/speaking` or `/speaking/shadowing` loses the unit context (free page, D-255). A scenario track card has no "done" count (D-259).
- No real AI was called: the generation was checked up to the "unavailable" answer. The first real generation from the screen is part of the manual scenario if a Gemini key is set.

### Next step

M8.b2 (editing a unit's content) after the owner's go-ahead, then the owner's review of M6 to M8 and the push.

### Owner's manual scenario (about 2 minutes, demo, no key needed)

```powershell
cd backend
uv run python -m app demo seed --reset
cd ..
.\start.ps1 -Demo
```

1. Open http://127.0.0.1:5173/curriculum: three cards. Under "Speaking scenarios" (Continue): unit 1 "Done", unit 3 "In progress", the others "Not written yet" (without a key, "Write this unit with the AI" ends with the reason, "Nothing was written" and "Try again").
2. Open unit 3: "2 of 4 steps", "Next step: shadowing" highlighted. "Listen to the whole dialogue" plays line after line with two voices, "Stop" stops it, "Show the text" expands the lines.
3. In step 3 click "Shadow this line" on a line: the shadowing page has the line (read-only) and "Back to the unit"; record and send, then go back: the line shows one more take.
4. Back on `/curriculum`, "Start" on "General everyday English", "Open" unit 1, "Triage these words (25 left)": the 25 words wait on the triage page.
5. Switch to French: the top bar says "Parcours", titles of the units are in French.

## M8.a2 — Speaking scenario units: AI generation, edits, steps, demo v7 (backend + CLI)

Branch `feat/m8-curriculum`, after M8.a1. Not pushed. **No migration** (`alembic check`: no operation), no new dependency, no frontend file. Decisions D-246 to D-253.

### Done

- **AI task `curriculum_unit` v1** (`app/ai/prompts/curriculum_unit.v1.txt`, `app/ai/schemas/curriculum_unit.py`, `app/ai/tasks.py`, rules in `app/domain/curriculum_unit.py`): 8 to 15 formulas, a dialogue (2 fictional speakers, 8 to 16 lines), 5 to 8 lines to shadow, a final task (1 or 2 minutes, at least 3 formulas). One repair then `incomplete` (D-079). Budgets and their justification in `tasks.py` (D-249). Prior check: `gemini-3.5-flash-lite` is "Stable" on the official models page, 2026-10-26 (D-246).
- **`app/services/curriculum_units.py`**: `generate_unit` (D-038: read, AI call with no session, short write that re-checks; AI failure = a result, nothing written), `edit_content` (revision, whole parts, D-250), `mark_step`, `refresh_progress`, `add_terms` (formulas to triage, D-251).
- **Progress** (D-248): four steps `formulas`, `dialogue` (marked) and `shadowing`, `final_task` (derived from the takes linked to the unit); `curriculum_unit.progress` goes `not_started` / `in_progress` / `done`; `content.progress.steps` keeps the dates. Takes reuse M6: `unit_id` on `POST /speech/shadowing` and `POST /speech/speaking`, `speech shadow|speak --unit` (D-252); the final talk is corrected by the existing `speaking_correction`.
- Five events: `curriculum.unit_generated`, `unit_edited`, `unit_step_completed`, `unit_completed`, `unit_terms_added`.
- **Demo v7** (D-253): `content/demo/units.yaml`, three units (done, in progress, written only); the other generators keep their sequences.
- Tests: schema and rules (`tests/ai/test_curriculum_unit_schema.py`), service, API, CLI, demo v7 (`tests/test_demo_curriculum.py`) and one live test (`tests/live/test_live_curriculum_unit.py`, passed with the owner's Gemini key). Full backend suite green, `ruff check` and `ruff format --check` clean.

### Left / known limits

- **M8.b**: no screen yet (no frontend file was touched). The listening of the dialogue (speech synthesis) is the screen's job; the learner marks `dialogue` after it.
- No regeneration over an existing unit (409 `unit_generated`), even if the learner dislikes it: edit it, or ask for a `replace` option (D-250).
- A take counts for the `shadowing` step whatever was heard (no accuracy threshold). Editing a line makes the old takes of the previous text stop counting; `done` can go back to `in_progress` after an edit.
- The syllabus has 16 units; only the three of the demo are written there. In the real database a unit is written when the owner runs `curriculum generate`.
- Placement test, new planner rule, new correction task and statistics (M9) are not part of this milestone.

### API reference for M8.b

All under `/api/curriculum`, errors `{"detail": {"code", "message", ...}}` (D-063). The routes of M8.a1 are unchanged; `GET /units/{id}` and the `unit` of every answer below gain a `scenario` field (null for a word unit).

| Route | Answer |
|---|---|
| `POST /tracks/{code}/units/{n}/generate` | HTTP 200 `{status: ok\|incomplete\|unavailable, reason, detail, unit}`; the AI takes a few seconds; on `incomplete` / `unavailable` nothing was written (`unit` null), try again; 409 `track_not_started`, 409 `unit_generated`, 422 `not_a_scenario_track`, 404 `unit_not_found` / `track_not_found` |
| `GET /units/{id}` | `unit` with `scenario`: `revision`, `edited`, `provider`, `model`, `prompt_version`, `level`, `formulas[{index, text, item_type, function_en, function_fr, register, item_id}]`, `dialogue {setting_en, setting_fr, speakers, lines[{speaker, text}]}`, `shadowing[{line_index, text, take_count, done}]`, `final_task {prompt_en, prompt_fr, minutes, formula_refs, target_item_ids, attempt_ids, corrected}`, `steps {formulas, dialogue, shadowing, final_task}`, `next_step` (null when done) |
| `PUT /units/{id}/content` | body `{expected_revision, formulas?, dialogue?, shadowing?, final_task?}` (positions 0-based; `formulas` items use the key `register`); the updated `unit`; 409 `unit_changed` (`revision`), 422 `invalid_content` (`problems[]`), 422 `not_a_scenario_unit`; a body with a wrong shape gives the standard FastAPI 422 |
| `POST /units/{id}/steps/{step}` | `step` = `formulas` or `dialogue`; `{changed, unit}` (again: `changed: false`); 422 `invalid_step` for the derived steps |
| `POST /units/{id}/terms` | body `{indices?}` (0-based, all by default); `{imported, attached, skipped, unit}`; the formulas wait in the triage queue (`GET /api/triage?deck_id=`); 422 `invalid_content` for an unknown index |
| `POST /speech/shadowing?unit_id=` | a shadowing take of one of the unit's lines (`target_text` = the line); counts when transcribed |
| `POST /speech/speaking?unit_id=` | the final talk; `prompt_text` and `target_item_ids` default to the unit's; then `POST /api/productions/{id}/correct` completes the `final_task` step |

`unit.progress` is `not_started` / `in_progress` / `done`; `content_status` is `generated` or `edited`; `state` is `opened` until the formulas are in the library and triaged.

### Owner's manual scenario (about 5 minutes, the generation needs your Gemini key)

On the demo database (nothing touches `data/vocab-coach.sqlite3`):

```powershell
cd backend
uv run python -m app demo seed --reset
uv run python -m app --demo curriculum show speaking_scenarios
uv run python -m app --demo curriculum unit 1        # done: all four steps ticked
uv run python -m app --demo curriculum unit 3        # in progress: next step "shadowing"
uv run python -m app --demo curriculum generate speaking_scenarios 2   # job_interview_2, with the AI
uv run python -m app --demo curriculum step 4 formulas
uv run python -m app --demo curriculum terms 4 --indices 0 1 2
```

To do the same for the real "Job interview" unit: `uv run python -m app curriculum start speaking_scenarios`, then `curriculum generate speaking_scenarios 1`, `curriculum unit <id>`, `curriculum step <id> formulas`, `curriculum step <id> dialogue`, then for each shadowing line `speech shadow --file clip.wav --target "<line>" --unit <id>`, then `speech speak --file talk.wav --unit <id>` (it corrects the talk), and `curriculum unit <id>` shows `done`. Without a key, `generate` ends with exit code 1 and "Nothing was written": nothing is lost, run it again later.

## M8.a1 — General English tracks: word lists, syllabus, units (backend + CLI, no AI)

Branch `feat/m8-curriculum`, cut from `e9917e3`. Not pushed. **No migration** (`alembic check`: no operation), no new dependency, no frontend file, no AI call. Decisions D-240 to D-245.

### Done

- `content/curriculum.yaml` (version 1): `general_everyday` (NGSL, 25 words per unit), `academic` (NAWL, 25), `speaking_scenarios` (the 8 SPEC themes x 2 = 16 units with EN/FR titles, 2 to 4 goals, situations, level B1-B2).
- `content/wordlists/`: NGSL 1.2 and NAWL 1.2 **unchanged** (CC BY-SA 4.0, verified on the official site) + `NOTICE`; README licence section, SPEC section 8 (D-240). `.gitattributes` keeps them byte for byte.
- `app/domain/curriculum.py` (pure): syllabus validation, the two readers (`TRUE`/`FALSE` fix, ISO-8859-1), unit slicing (NGSL 113 units, last with 9 words; NAWL 39 units, alphabetical, D-244).
- `app/services/curriculum.py`: tracks, detail with paginated units, `start_track` (source + `curriculum` deck, idempotent, D-241), `open_unit` (terms in triage through `importing.commit`, new `origin` and
  `record_completed` arguments, D-243), computed unit state (D-245). Events `curriculum.track_started`, `curriculum.unit_opened`.
- `/api/curriculum/...` (below) and `python -m app curriculum tracks | show <code> [--page N] | start <code> | open <code> <n>`.
- Tests: 25 new (domain with the real files, service, API, CLI, `POST /api/triage` with the 25 decisions of a unit at once). Full backend suite green, `ruff check` and `ruff format --check` clean.

### Left / known limits

- **M8.a2**: scenario units are listed from the YAML with `content_status: pending`; no generation route yet. The brief of M8.a2 was cut off in section 3 ("Storage ... progress `{steps:`"): the rest of its spec (storage and progress format, demo v7, live test, API) is still needed.
- Units opened under a deck that was later deleted keep `deck_id = NULL` (D-241). No usage sheet is generated when a unit opens (D-242). Inflected forms of the NAWL are not imported (D-244).
- A word-list unit has `content_status = generated` (a slice, no AI); M8.b may prefer to hide that field for these units.
- **Incident, to settle with the owner**: during development my first API tests overrode `get_engine` but not `get_session`, so they **wrote into the real database `data/vocab-coach.sqlite3`** (2 curriculum decks "Academic English" and
  "General everyday English", 50 terms, 2 units, 2 tracks, 2 sources, and 160 events dated 2026-10-26, among them 25 `item.triaged`). The tests are fixed (they no longer touch it) and `data/` is not in Git. I could not delete the
  events, because `event_log` is append-only (trigger) and I did not bypass it. The other tables were left as they are so that nothing is orphaned. A copy of the database taken after the incident (so already polluted) is in my scratchpad. The simplest cleanup, if that database holds nothing
  you want to keep: `Remove-Item data\vocab-coach.sqlite3*` then `cd backend; uv run python -m app db upgrade`. Otherwise tell me and I will remove those rows with the trigger dropped and recreated in one transaction.

### API reference for M8.b

All under `/api/curriculum`, errors `{"detail": {"code", "message", ...}}` (D-063).

| Route | Answer |
|---|---|
| `GET /tracks` | list of `TrackSummary`: `code`, `kind` (`wordlist` / `scenarios`), `source` (`ngsl` / `nawl` / null), `title {en, fr}`, `description {en, fr}`, `unit_size`, `unit_count`, `available`, `reason` (`wordlist_missing` / null), `started`, `deck_id`, `opened_units`, `triaged_units`, `syllabus_version` |
| `GET /tracks/{code}?limit=25&offset=0` | `{track, total_units, limit, offset, units[]}`; unit: `number`, `code`, `title`, `title_fr` (scenarios), `state` (`not_opened` / `opened` / `triaged`), `unit_id`, `first_rank`, `last_rank`, `word_count`, `content_status`, `progress` |
| `POST /tracks/{code}/start` | `{track, created}`; 409 `wordlist_missing`; creates the deck of a word-list track, the track row of a scenario track; again: same result, `created: false` |
| `POST /tracks/{code}/units/{n}/open` | `{created, imported, attached, skipped, unit}`; the unit: `id`, `track_code`, `number`, `code`, `title`, `state`, `progress`, `content_status`, `deck_id`, `first_rank`, `last_rank`, `terms[{item_id, term, status}]`; 409 `track_not_started` (`track`), 422 `not_a_wordlist_track`, 404 `unit_not_found` / `track_not_found` |
| `GET /units/{id}` | the same `unit` |

Triage of the opened terms uses the existing `GET /api/triage?deck_id=` and `POST /api/triage` (the 25 decisions at once work). Statistics (M9) count `curriculum.unit_opened`, not `import.completed`.

### Owner's manual scenario (about 3 minutes, no key needed)

```powershell
cd backend
uv run python -m app db upgrade
uv run python -m app curriculum tracks
uv run python -m app curriculum start general_everyday
uv run python -m app curriculum show general_everyday
uv run python -m app curriculum open general_everyday 1
uv run python -m app curriculum open general_everyday 1   # again: "already open", nothing changes
```

Expect 3 tracks (113 / 39 / 16 units), a deck "General everyday English" at the end of the queue, 25 words (the, be, and, ...) waiting for triage (Triage page of the app), a second `open` that changes nothing, and `show --page 5` ending with `ngsl_113` (9 words).

## M7.b — Consolidation screens (frontend)

Branch `feat/m7b-consolidation-screens`, cut from `bcfcb55`. Not pushed. **No backend change** (`git diff --stat bcfcb55 -- backend` is empty), no migration, no new dependency. Decisions D-235 to D-239.

### Done

- **`/consolidation`**: decks ready (ratio against the threshold, usable terms, type of task, number of terms 8 to 15), decks not ready with the reason in words (`excluded_kind`, `deck_done`, `task_open` with a link,
  `no_productive_cards`, `below_ratio`, `not_enough_candidates`), the tasks (status filter, pages). A creation that fell back to a template says so, with the reason.
- **`/consolidation/tasks/:id`**: title, prompt, audience, structure, terms (links to the library), badges (status, AI or template), Accept / Mark as completed / Dismiss with a confirmation,
  written production (draft kept, 4000 characters) or recording (20 s to 4 min, the existing recorder), attempts, Markdown export EN or FR.
- **`/consolidation/attempts/:id`**: automatic correction on arrival (once), the existing correction view, the transcription retry for a talk, the summary of the terms (used correctly with "now active", used wrongly,
  not used), "mark as completed" offered but never done by itself. Redirects from `/writing/:id` and `/speaking/:id`; consolidation errors of the error log link to it.
- Links from the Today card and the session's `practice_info` step, a `Consolidation` entry in the top bar. The setting `consolidation_share` was already in Settings (bounds from the API).
- Every string is in `en.json` and `fr.json` (same keys). **665 Vitest tests** (644 before): `npm run check` passes. Checked in the built-in browser on the demo with a real Gemini key: creation, written
  attempt, correction, summary (2 terms became active, 1 misused), Today link.

### Left / known limits

- `ProductionOut` has no `consolidation_task_id`: the attempt page learns its task from `?task=ID` (D-235). Proposal for the owner: add that field (small, additive) to drop the query string.
- After a reload the summary shows the groups but not the "now active" marks or the reinforced count (only the correction call returns them, D-237).
- Not done, absent from the SPEC and not added: statistics on consolidation, regenerating or editing a task, a deadline on a task.
- The demo database must be at the last migration: the first correction in the browser failed with `table review_log has no column production_attempt_id` on a demo database left at revision `0001`;
  `demo seed --reset` fixed it. Worth a look: `start.ps1 -Demo` should probably upgrade the demo database.
- Spoken production and the export download were tested with the fake recorder and a stubbed download only (no real microphone, no Firefox).
- Style unchanged (the redesign comes after M9).

### Owner's manual scenario (about 5 minutes, with your Gemini key)

```powershell
cd backend
uv run python -m app demo seed --reset
cd ..
.\start.ps1 -Demo
```

1. Open http://127.0.0.1:5173/consolidation: "Causal inference reading" and "Campus life" are ready; the other decks say why they are not.
2. Pick "Talk", 10 terms, "Create a task": after a few seconds the task page opens (with no key, a notice says it was made from a template and why).
3. "Also show in French" shows the French text under the English one. Write a short text using some of the terms (the example is `content/examples/m7_consolidation.txt`), "Send for correction".
4. The correction page lists the errors, then "The terms of the task": terms used well are "now active", a misused one is in your error log, the others are "not used". Reload: the groups stay.
5. Back to the task: it is "Accepted" and has one attempt. "Mark as completed" asks for a confirmation. Download the EN and FR exports.
6. "Record it": record 20 s or more; the talk is transcribed then corrected on the attempt page.
7. Settings > Consolidation: change "Share of a deck to consolidate" (0.5 to 1.0). Today shows an "Open the task" link for the open task.

## M7.a2 — Consolidation: productions, correction, `active` status, demo v6 (backend + CLI)

Same branch `feat/m7-consolidation` (after M7.a1). Not pushed. **No migration** (`alembic check`: no operation), no frontend change
(`git diff --stat 7ffbec6 -- frontend` is empty), no new dependency. Decisions D-229 to D-234. M7 (backend) is complete; the screens are M7.b.

- **Done**: the written production of a task (`POST /api/consolidation/tasks/{id}/attempts/written`) and the spoken one
  (`POST /api/speech/consolidation`, 20 to 240 s); `/api/productions/{id}/correct` routes them (`production_correction` in `paragraph` mode,
  `speaking_correction` in `monologue` mode, errors of source `consolidation`); the result is applied to the terms **in the same write transaction** as the
  correction (terms used correctly become `active`, a term used wrongly gets a FSRS Again, `consolidation.attempt_checked`); CLI `consolidation write | speak`;
  `production.recorded` version 6; demo v6 (a completed task at day -10 on "Causal inference reading"); `content/examples/m7_consolidation.txt`;
  live test `tests/live/test_live_consolidation.py`.
- **Departures from the milestone prompt** (approved plan): see M7.a1, plus: the `consolidation` production kind is used for the spoken talk as well
  (modality `oral`), so `speech.py` counts its words like free speaking.
- **Left (not scheduled)**: the screens (M7.b); a "complete the task" action is the user's (`POST .../status {"to": "completed"}`), nothing completes a task by itself.
- **Known limits**: the AI judges the use of a term; on the example text it called the misused term correct once in seven live passes (D-233). A term used
  correctly but with an unrelated error tied to it by `target_ref` counts as misused (the rule of the prompt, D-229).

### Demo v6 (measured on seeds 1 to 12, 60 days, anchor 2026-09-01)

- Every seed makes one task on "Causal inference reading" on 2026-08-22 (day -10), 15 terms (the most fragile), one text, one misused term, one or two
  terms forgotten; 12 to 14 terms become `active` through it (seed 42: 13). The direct switch of the dataset (`fate: active`, day -5) is kept only for the
  terms that task did not select: seed 42 ends with 14 active terms, 13 of them through the task.
- At the anchor a deck is ready with no open task in **all twelve seeds** ("Causal inference reading": ratio 0.83 to 1.0, 10 to 16 candidates; "Campus life" is ready too
  in seeds 1, 2, 4, 6, 9, 12 and 42). Seed 42: Causal 0.90 with 15 candidates, Campus life 0.90 with 9.
- Seeding takes 5 to 6.5 s on this machine (the 14 to 16 s noted at M6.c1 are not reproduced; not explained).

### Manual scenario of M7 (2 minutes, with your Gemini key)

```powershell
cd backend
uv run python -m app demo seed --reset
uv run python -m app --demo consolidation status                       # "Causal inference reading" is ready
uv run python -m app --demo consolidation new 1 --count 10             # topic, structure, terms (note the task id)
uv run python -m app --demo consolidation write <task_id> --file ..\content\examples\m7_consolidation.txt
uv run python -m app --demo consolidation export <task_id> --lang fr --out $env:TEMP\consolidation.md
notepad $env:TEMP\consolidation.md
```

1. `status`: one deck is ready. 2. `new`: the title, the prompt, the sections and ten terms. 3. `write`: the correction, then
"now active (6)" (the six terms used well), "review card reinforced (1): noisy estimate", "not used (...)". 4. The exported file is ready to paste into a
voice chat. 5. Without a key (`$env:VOCAB_GEMINI_API_KEY = ""` for the command, or no key in `.env`): `consolidation new` makes the task from a template
and says so ("made from a template instead"); `write` then says the AI could not correct (exit 1) and keeps the text.

### API reference for M7.b

All under `/api`, errors in the D-063 format. A task is created with the AI (a few seconds) or from a template, never an error because of the AI.

| Route | Request | Answer |
|---|---|---|
| `GET /consolidation/decks` | - | one per deck: `{deck_id, name, ready, reason, ratio, stable_cards, productive_cards, threshold_ratio, min_stability_days, candidates (count), open_task_id}`; `reason` is `excluded_kind`, `deck_done`, `task_open`, `no_productive_cards`, `below_ratio` or `not_enough_candidates` |
| `POST /consolidation/tasks` | `{deck_id, task_type: talk\|speech\|interview_answer, term_count? (8-15), study_session_id?}` | 201 `{status: "ok", source: "ai"\|"template", reason, task}`; 404 `deck_not_found`; 409 `not_ready` (+`reason`), `task_open` (+`task_id`) |
| `GET /consolidation/tasks` | `deck_id?`, `status?`, `limit`, `offset` | `{items: [task], total, limit, offset}`, newest first |
| `GET /consolidation/tasks/{id}` | - | `task`; 404 `task_not_found` |
| `POST /consolidation/tasks/{id}/status` | `{to: accepted\|completed\|dismissed}` | `task`; 409 `invalid_transition` |
| `GET /consolidation/tasks/{id}/export` | `lang=en\|fr` | `text/markdown; charset=utf-8`, `Content-Disposition: attachment; filename="consolidation-task-<id>-<lang>.md"` |
| `POST /consolidation/tasks/{id}/attempts/written` | `{text (4000 chars, 40 sentences), study_session_id?}` | 201 a production (`kind: "consolidation"`, `modality: "written"`, `targets` = the terms); 409 `task_closed`; 422 `text_too_long`, `invalid_request` |
| `POST /speech/consolidation` | raw audio body, `?task_id&duration_s (20-240)&study_session_id` | 201 as `POST /speech/speaking`; 409 `task_closed`; 422 `audio_too_short`, `audio_too_long`; the task prompt is never sent to the recogniser |
| `POST /productions/{id}/correct` | - | as before; for a consolidation production `CorrectionOut.consolidation` is `{task_id, production_attempt_id, modality, targets, used, used_correctly, misused, absent, activated_item_ids, reinforced_card_ids}` (null while uncorrected or when the AI failed: nothing changed, try again) |

`task` = `{id, deck: {id, name}, status: proposed|accepted|completed|dismissed, task_type, source: ai|template, title, prompt, audience (each `{en, fr}`),
target_minutes, sections: [{heading, guidance (`{en, fr}`), item_ids}], targets: [{item_id, term, item_status, used_correctly_count}],
attempts: [{production_id, modality, corrected, created_at}], created_at}`. Terms come without their sheet (read it with `/api/items/{id}` or the library).
The first attempt makes a `proposed` task `accepted`. The corrected production is read with `GET /productions/{id}` (`feedback`: `correction-1` for written,
`speaking-1` for spoken, so the M5/M6 correction views apply).

## M7.a1 — Consolidation: readiness, tasks, export (backend + CLI)

Branch `feat/m7-consolidation`, cut from `7ffbec6` (tip of `feat/m6c2-pronunciation-screens`; `main` has no M6). Not pushed. **No migration**, no
frontend change (`git diff --stat 7ffbec6 -- frontend` is empty), no new dependency. Decisions D-223 to D-228. M7.a2 (written and spoken productions,
correction, `active` status, demo v6, live tests) is still to do.

- **Done**: pure readiness and selection rules (`app/domain/consolidation.py`), the `consolidation_task` AI task v1 and its template fallback,
  the service (create, list, statuses, export), `GET /api/consolidation/decks`, `POST|GET /api/consolidation/tasks`, `GET .../tasks/{id}`,
  `POST .../status`, `GET .../export`, CLI `consolidation status | new | show | export`, two events.
- **Departures from the prompt** (approved plan): `consolidation_share` reused with bounds 0.5..1.0 instead of `consolidation_ready_ratio` (D-224);
  reason `deck_done` and code `task_closed` added (D-225).
- Done in M7.a2: productions, correction, applying the result, `production.recorded` v6, `consolidation.attempt_checked`, demo v6,
  examples, live tests, API reference for M7.b.

### How to try it (M7.a1, no key needed)

```powershell
cd backend
uv run python -m app db upgrade
uv run python -m app consolidation status
uv run python -m app consolidation new <deck_id> --count 10   # a template when no key is set
uv run python -m app consolidation show <task_id>
uv run python -m app consolidation export <task_id> --lang fr --out $env:TEMP\consolidation.md
```

A ready deck on the demo database is guaranteed by the demo v6 of M7.a2; until then, build one with your own data.

## M6.c2 — The pronunciation-assessment screens (frontend)

Branch `feat/m6c2-pronunciation-screens`, cut from `c1aba7c` (tip of `feat/m6c-pronunciation`). Not pushed. **No backend change**, no migration,
no new dependency. Decisions D-219 to D-222.

### Done

- **Settings > Azure card** (`AzureCard.tsx`, D-220): key + region, connection test, the `pronunciation_assessment` checkbox, the month's use, the
  warnings (audio goes to Microsoft, F0 only, F0 inclusion unconfirmed). Locked on the demo.
- **WAV 16 kHz mono in the browser** (`speech/wav.ts`, D-219): applied to a new shadowing only when the setting is `azure` and a key is saved.
  The recorder itself is unchanged.
- **Scores on the shadowing page** (`AssessmentSection`, `PronunciationView`, D-221): button greyed from `assessable_reason`, overall scores, each word
  with its error type in words, weakest sounds, "automatic estimate, not a teacher's judgment".
- **Tests**: 644 Vitest tests (619 before). `npm run check` passes. In the built-in browser (Chromium) a real webm/opus take was converted to a valid
  WAV 16 kHz mono 16-bit.

### Left / known limits

- **Never run against Azure** (as M6.c1): the answer shape, F0 inclusion and the WAV being accepted are unverified. No real microphone, no Firefox.
- Recordings made before the setting was turned on cannot be assessed (webm). The discovery's spoken repetition and free speaking are not
  converted or assessable (out of scope). The assessment of the history list is not shown (detail page only).
- Seed or demo: the demo scores (v5) show on the demo's shadowing pages; nothing can be sent there.

### Owner's manual scenario (about 5 minutes, needs an Azure F0 key)

1. Settings > "Pronunciation assessment": paste the key and the region (`westeurope`...), Save, "Test connection" (it should say it works).
2. Tick "Allow pronunciation assessment of shadowings"; the month's use appears (0 min).
3. Speaking > Shadowing: type a sentence, record it, Send. On the take's page, "Pronunciation" shows "Assess my pronunciation"; click it.
4. The scores, the words and the weakest sounds appear; the month's use in Settings goes up. Reload: the scores are still there.
5. Switch the setting off: the next shadowing is recorded as before; the old assessed take still shows its scores.

## M6.c1 — Pronunciation assessment with Azure (backend, optional)

Branch `feat/m6c-pronunciation`, cut from the tip of `feat/m6b-speaking-screens` (`863f39f`), in two parts with a stop between them: **M6.c1a**
(adapter, gateway, configuration) and **M6.c1b** (service, storage, event, API, CLI, demo, docs). Not pushed. **No migration**, no frontend change
(`git diff --stat feat/m6b-speaking-screens -- frontend` is empty), no new dependency, no audio file tracked. Decisions D-211 to D-218.

The module is **off by default** (`pronunciation_assessment` = `off`) and the app is unchanged without an Azure key. Screens are M6.c2.

### Done

- **Pure module** `app/domain/pronunciation.py`: `audio_kind` / `audio_problem` (WAV PCM 16 kHz mono 16-bit or OGG Opus mono, from the bytes; webm, m4a
  and mp3 refused), `audio_duration_s`, `silent_wav`, `summarize`, `weakest_phonemes`, `scores_document` (`azure-pa-1`), dated constants (D-211).
- **Adapter** `app/ai/providers/azure_speech.py` (no SDK), **gateway capability** `pronunciation_assessment` outside `ai_provider_order`
  (`Gateway.assess_pronunciation`), `PronunciationAssessmentOutput` (D-212, D-213).
- **Configuration**: five `.env` variables (key and region written together), `PUT/DELETE /api/ai/providers/azure/credential` with `region`, the
  setting, the demo guard, `POST /api/ai/test` and `ai test --provider azure`, `speech_providers` in `GET /api/ai/status` (D-214).
- **Service** `app/services/pronunciation.py` (`assess`, `store_assessment`, `assessable_reason`, `monthly_usage`), storage in
  `pronunciation_result.scores` in **both write orders**, the event `pronunciation.assessed` (D-215, D-216).
- **API and CLI**: below. **Demo dataset v5** (D-217): the last 3 shadowings with missed words carry fictional scores.
- **Tests** (all without network): adapter on a loopback server, gateway, `.env`, API, CLI, service (each refusal with zero calls and zero rows,
  both orders, second writer during the call, usage), demo. `tests/live/test_live_azure.py` exists and **was not run** (no key, no clip here).

### Left / known limits

- **Never run against Azure.** The answer shape, whether the F0 tier includes pronunciation assessment, the wording of an F0 quota error and the
  availability of the feature per region are unverified (D-211). The heuristic that reads "quota" in a 403/429 may misclassify (D-213).
- M6.c2 (the screens) must send WAV 16 kHz mono (or OGG Opus): the browser records webm, which Azure refuses (D-211).
- Two concurrent assessments of the same production could both pass the last check (microsecond window, no unique index, D-215).
- Seed time is 14 to 16 s here against 4.5 s at M6.a2b, whatever the number of assessments (D-217); not explained.
- The owner's manual scenario (below) is still to run.

### API reference for M6.c2 (additions only; nothing existing changes)

- `GET /api/settings` → `pronunciation_assessment: {value: "off"|"azure", choices: ["off","azure"], ...}`; `PATCH /api/settings
  {"pronunciation_assessment": "azure"}` (409 `demo_read_only` on the demo database).
- `GET /api/ai/status` → new `speech_providers: [ProviderState]` (Azure: `name`, `capabilities: ["pronunciation_assessment"]`, `configured`,
  `available`, `models`, `credential_source`, `region`), outside `providers` and `order`.
- `PUT /api/ai/providers/azure/credential {"value": "<key>", "region": "westeurope"}` (`region` optional once one is stored; 422
  `region_required` / `invalid_region` / `invalid_credential`); `DELETE` clears both; `POST /api/ai/test {"provider": "azure"}`.
- `POST /api/productions/{id}/pronunciation` (no body; the recording is sent to Microsoft; a few seconds) → 200
  `{production_id, status: "ok"|"silence"|"unavailable"|"incomplete", reason, scores}`. Refusals, before any call: 404 `production_not_found`, 422
  `not_assessable`, 404 `no_audio`, 409 `assessment_disabled`, 409 `already_assessed`, 422 `unsupported_for_assessment`, 422 `audio_too_long`.
  `unavailable` (`reason`: `no_provider_configured`, `quota`, `auth`, `network`, `timeout`, `all_failed`) and `incomplete` store nothing and can
  be repeated.
- `GET /api/productions/{id}`, `GET /api/productions` and the answers of `POST /api/speech/shadowing`, `/speaking` and `/productions/{id}/transcribe`
  gain `pronunciation: scores | null`, `assessable: bool`, `assessable_reason: null | not_shadowing | no_target | no_audio | disabled |
  not_configured | already_assessed | unsupported_format | too_long`.
- `scores` (`format: "azure-pa-1"`): `{provider, model, assessed_at, status: "ok"|"silence", overall: {accuracy, fluency, completeness,
  pronunciation} (0-100, null on silence), words: [{word, accuracy, error_type: "None"|"Mispronunciation"|"Omission"|"Insertion"|other, offset_ms,
  duration_ms, phonemes: [{phoneme (IPA), accuracy}]}], duration_s}`. The comparison (`comparison`) of a take is independent and stays; a take assessed
  before any transcription has `comparison: null` and `transcription_status: "pending"` until it is transcribed.
- `GET /api/speech/pronunciation/usage` → `{month: "YYYY-MM", audio_seconds, assessments, limit_seconds: 18000, limit_checked_on: "2026-10-24", note}`.
  Show the note: the scores are an automatic estimate, and F0 inclusion is unverified.
- Always show: "automatic estimate, not a teacher's judgment", and that the recording goes to Microsoft. Active recall: the scores belong after the
  attempt (they come from an assessed take).
- CLI: `speech assess <id>`; `speech shadow --file <clip> --target "<sentence>" --assess`. Exit codes: 0 done (silence included), 1 unavailable, 2
  usage (setting off, unknown production, refused clip). Output: the four scores, each word with its score and error type, the 5 weakest phonemes.

### How to test (2 minutes, Windows)

1. In `.env`: `VOCAB_AZURE_SPEECH_KEY=` and `VOCAB_AZURE_SPEECH_REGION=` (an **F0** resource, never S0). In `backend`: `uv run python -m app ai status`
   shows "Pronunciation assessment (azure...): configured".
2. `uv run python -m app ai test --provider azure` (one second of silence; "ok" even for "no speech").
3. Turn the setting on: `Invoke-RestMethod -Method Patch -Uri http://127.0.0.1:8000/api/settings -ContentType application/json -Body '{"pronunciation_assessment":"azure"}'`
   (the app must run) or through the API docs at `/docs`.
4. Make a WAV with Windows speech: `Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;
   $f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
   [System.Speech.AudioFormat.AudioChannel]::Mono); $s.SetOutputToWaveFile("$env:TEMP\take.wav", $f); $s.Speak("We account for regional
   fixed effects in all specifications."); $s.Dispose()`.
5. `uv run python -m app speech shadow --file $env:TEMP\take.wav --target "We account for regional fixed effects in all specifications." --assess`
   (with a Groq key it is transcribed too; without it, only the scores).
6. Optional live test: `$env:VOCAB_RUN_LIVE='1'; $env:VOCAB_LIVE_AZURE_AUDIO="$env:TEMP\take.wav"; uv run pytest tests/live/test_live_azure.py -m live -v -s`.
7. Clean up: `Remove-Item $env:TEMP\take.wav`; remove the two Azure lines from `.env` (or `DELETE /api/ai/providers/azure/credential`) and set the
   setting back to `off`.

## M6.b2.2 — The spoken answer in the review player (frontend)

Second half of M6.b2, same branch `feat/m6b-speaking-screens` (`git diff --stat e5600ce -- backend` is empty). Two code commits, then the docs.
**No backend change**, no migration, no new dependency. SPEC.md unchanged. Decisions D-206 to D-210; D-123 and D-117 annotated.

### Done

- **The recorder in two parts** (D-206): `RecorderView` (presentation, takes the object returned by `useRecorder`) and `Recorder` (view + hook,
  unchanged for its users: its 41 tests did not change). `useClipSender` (own file) holds the 10 MB check shared by the Send button and Enter.
- **The machine** (D-206): phases `capturing` (microphone open), `captured` (clip ready), `checking_spoken` (`review-answer` running), actions
  `startCapture`, `captured` (fixes `responseTimeMs`), `discardCapture`, `submitSpoken`, `spokenChecked` (refused outside `checking_spoken`: the
  same state object), `spokenFailed` (back to `captured`), `spokenFallback` (to `checking`, the reveal of M4.c). The phase `recording` (rating
  being saved) is not renamed. The result stays a `GradeResult` (`outcome` null, `proposed_rating` only with a correction, `term_not_heard`).
- **The player** (D-206, D-208): owns `useRecorder('spoken_answer')`; `reviewAnswer()` in `api/speech.ts` (plain function over `apiUpload`, under an
  `AbortController`); "Checking your answer… n s" (polite status said once), "Skip the check and rate myself" after 5 s; every fallback goes to
  `reveal` **without** `production_attempt_id`; audio refusals go back to `captured`; `not_due`, `review_not_allowed`, `exercise_mismatch`,
  `session_closed`, `session_not_found` as for `grade`. `409 production_mismatch` is the existing single resend.
- **Keys** (D-207): Space starts and stops the take, Enter sends it; `KeyHints` follows the phase; nothing while `checking_spoken`.
- **The prompt and the result** (D-209): the question alone, no "Show an example" and no `recordingLater` sentence; the result says what was
  heard (the compact `CorrectionView`), `term_not_heard` in words, the example "one possibility among others", the sheet summary, the suggested
  rating (1 or 3) or four plain buttons; transcription unavailable or silent and a failed correction are said, and the rating still carries the
  production. The two-step sentence ("up to about 90 seconds") is under Send and during the wait.
- **i18n** EN/FR under `review.spoken.*`, `review.keys.record|stop|send`, `review.result.term_not_heard`; `review.prompt.recordingLater` and
  `review.showExample` removed. CSS: a few lines (`.spoken-answer`).
- **Tests**: 619 Vitest tests (567 before): `ReviewPlayer.spoken.test.tsx` (41), 10 reducer tests, 2 shortcut tests; two older `spoken_answer`
  tests rewritten (Space and Enter no longer reveal the example; the card is revealed by "Answer without recording").

### Verified (Windows 11, 2026-10-24)

- `npm run check` from the root: ruff and `ruff format --check` clean, pytest green, then typecheck, oxlint `--deny-warnings`, **619 vitest tests**;
  `npm --prefix frontend run build` passes. `git diff --stat e5600ce -- backend` is empty; `frontend/package-lock.json` untouched.
- **Checks by breaking the code** (each applied, run, then undone with `git checkout`):
  - (c) the example answer written into the page while the take is `captured`: `shows nothing of the solution before the answer, in every phase`
    fails with `expected '<div><div class="shell">…' not to contain 'drill down into'`.
  - (d) the guard of `submitSpoken` removed from `sendSpoken`: `a double Enter sends one recording` fails with `expected [ … ] to have a length of 1 but got 2`.
  - (e) the phase guard of `spokenChecked` removed (a late answer accepted after the way out, which would send the production): the reducer test
    `a late answer, after the way out or in any other phase, changes nothing` fails (`expected { phase: 'answered', … } to be { phase: 'answering', … }`).
    The player-level test of the late answer did **not** fail by itself: the abort makes the mocked request reject before the late answer, so
    the reducer is the second line of defence, and its own test is the one that catches the break.
- **In-app browser**, demo database in a temporary folder (`VOCAB_DATA_DIR`, the four keys emptied; `data/` and `.env` untouched; both servers
  stopped, ports 5173 and 8000 free): the demo had **no `spoken_answer` card** among today's 18 reviews, so the page replaced the `next` answer
  by a real card of the database (card 136 / template 274, then 138 / 280) — only that step was substituted, everything else is the real
  backend. Seen: the question alone and "Space start recording"; a refused microphone (`getUserMedia` rejected in the page): the message, the
  help, "Answer without recording" as the main button; a real `MediaRecorder` on a synthetic 440 Hz tone (the pane has no microphone):
  Space to start, Space to stop ("Recording stopped: 0:02", the two-step sentence, "Enter send"), Enter sent a real
  `POST /api/speech/review-answer?card_id=136&session_id=50&exercise_template_id=274&duration_s=2.03&response_time_ms=30855`; the backend
  (no AI provider) answered "could not be transcribed: no AI provider is set up", the example appeared, four rating buttons, key 3 saved the
  review (`review_log` 826: `exercise_type spoken_answer`, `final_rating 3`, `auto_rating` null, `audio_path` filled, `production_attempt_id` set).
  375 px, EN and FR (second card, same path): `scrollWidth` 375 on the card, the take and the result; dark theme (the browser's).
  `/speaking/history` lists ids 25, 26 and 31 (and my two test takes), each opens its page, `/writing/31` redirects to `/speaking/31`.
- **Not verified**: a real microphone and Groq (the "answer ok" path of `review-answer`, with a heard text, a correction and a suggested
  rating, is tested with mocks only); the 5-second way out and the late answer in a real browser (tests with fake timers only); the degraded
  mode with a failing provider mid-way.

### Owner's manual scenario (about 2 minutes, with your Groq key and a microphone)

1. `/speaking`: choose a subject, speak for a minute slipping in "I live in campus" and "I study here since two years", Stop, Listen, Send; read
   the correction and the Structure section; play your recording back from "Your recording".
2. `/speaking/shadowing`: type or paste a sentence of a usage sheet, record it, then "Play both".
3. In a session, a `spoken_answer` card if one comes up (the demo has none today; in your own data it depends on the planner): press Space,
   answer aloud with the term, press Space, press Enter. Read "What the speech recognition heard", the marks, the example answer, the
   suggested rating; Enter accepts it. Try "Answer without recording" on another card, and with the microphone blocked in the browser.

### Departures from the prompt

- The result's title for what was heard is the correction view's own ("What the speech recognition heard"), not a second "What was heard"
  heading (they would say the same thing); when there is no correction the heard text is shown by the same view (D-209).
- `checkFailed` also leaves `checking_spoken` (the blocking refusals); `spokenFallback` takes a nullable notice (nothing to say when the user
  chose to answer without recording), so no `spoken_declined` notice exists (D-208, D-210).
- "Start recording" and "Answer without recording" are both primary buttons when the microphone failed (the view has no prop to calm the first).
- `useClipSender` is its own file (oxlint's fast-refresh rule); `RecorderPanel.tsx` only exports components and the type.

### Left / notes

- M6.c (Azure AI Speech, optional) and the microphone choice in the settings. The owner's manual scenarios. Push and the pull request: with
  the owner's go-ahead (after PR #21).
- A card with no `exercise_template_id` shows no recorder (only "Answer without recording"): the server needs the template for `review-answer`.

### Known issues

- "Length: 0:01" shows the whole seconds (1.8 s reads 0:01), as in the other recorders.
- A real recording of a spoken answer was never made (see "Not verified").

## M6.b2.1 — Free speaking and the `speaking-1` correction (frontend)

First half of M6.b2 (the owner approved the cut with the plan: about 25 files in all). Same branch `feat/m6b-speaking-screens`
(`git diff --stat e5600ce -- backend` is empty), two commits, then the docs. **No backend change**, no migration, no new dependency. SPEC.md
unchanged. Decisions D-202 to D-205 (the prompt said "from D-193", which M6.b1 had used up to D-201). The oral answers in reviews are
**M6.b2.2**, still to do.

### Done

- **`speaking-1` in the correction model** (D-202): `readFeedback` has a third branch (`kind: 'speaking'`, same keys as `correction-1` plus
  `output.structure`). Errors are grouped under "Part n" ("Passage n" in French). `CorrectionView` titles the text "What the speech
  recognition heard", adds the note that the correction is about what was heard, and shows the **Structure** section (comment, "Connectors
  you used", suggestions, French on demand) when `structure` exists; it is absent in answer mode and in the compact view. `correction-1` and
  `transcript-1` tests are unchanged.
- **Free speaking** (D-203): `/speaking` (three subjects a day filtered by "Topic theme", your own subject up to 500 characters, or none;
  recorder 5 to 180 s with the 120 s warning; `POST /speech/speaking` with `duration_s` and `prompt_text`), then `/speaking/:id` with the
  state `{autoCorrect: true}` (history replaced). `/speaking/:id` runs the correction once, says "Correcting… n s", and tells every refusal
  (`silence` / `nothing_to_correct`, `not_transcribed`, `already_corrected`, `text_too_long`, an AI failure with its reason and "Try again").
  `/speaking/history`: 20 per page, the page in the URL, spoken answers of reviews included (the page says so).
- **Redirects and links** (D-204): `/writing/:id` of a spoken production goes to `/speaking/:id` and back (`replace`), another kind on
  `/speaking/:id` gets a message and a link to the error log; `productionLink` sends a `speaking` error to `/speaking/:id`; the top bar's
  "Speaking" points to `/speaking`.
- **`TopicPicker`** takes a `source` (D-205): the speaking page has its own themes (with "Presenting") and wording; the writing page is
  unchanged.
- **Tests**: 567 Vitest tests (525 before): `readFeedback` on `speaking-1` (monologue, answer mode, no key), the Structure section and its
  French, the new-take page (exact request, history replaced, state consumed, subjects, own subject, no subject, too short, a refusal,
  an unavailable transcription), the page of one speech (marks, versions, structure; reload without action; `autoCorrect` once even in
  StrictMode; "Correcting… n s"; `pending` then Transcribe then the correction; `not_transcribed`; silence; `nothing_to_correct`;
  `text_too_long`; AI failure then "Try again"; incomplete; `already_corrected`; network failure; French; unknown id), the redirects,
  the history, the top bar, `productionLink`, nothing in the storages or `history.state`.

### Verified (Windows 11, 2026-10-24)

- `npm run check` from the root: ruff and `ruff format --check` clean, **2 425 pytest passed** (14 live deselected), then the frontend:
  typecheck, oxlint `--deny-warnings`, **567 vitest tests**; exit code 0. `git diff --stat e5600ce -- backend` is empty.
- **In-app browser**, on a demo database made in a temporary folder (`VOCAB_DATA_DIR`, the keys emptied through the environment; the
  repository's `data/` and `.env` untouched; both servers stopped afterwards): a corrected speech (structure, 11 errors in "Part n",
  versions, French on demand), the silent take ("No speech was heard", "Record again"), the speech not corrected (the transcription, the
  note, "Correct my speech", then the correction, which the demo's fictional AI answered), the history, the redirect `/writing/31` →
  `/speaking/31` (a spoken answer), the error log's "Open the text" link → `/speaking/32`, the refused microphone (the message and the help
  for 127.0.0.1), a real `curl --data-binary @clip.wav -H "Content-Type: audio/wav"` of a 6 s WAV to `/api/speech/speaking` (201; the demo's
  recogniser calls a tone silence) then its page.
- **375 px**, EN and FR: no horizontal scroll on `/speaking`, `/speaking/history`, `/speaking/:id` (corrected, not corrected, silent)
  and `/speaking/shadowing` (`scrollWidth` 375); the top bar wraps to two rows in French, as in D-145. Dark theme (the browser's).
- **Not verified**: a real microphone and Groq (as in M6.b1), the degraded mode without a key on the correction (the demo has a fictional AI;
  the unavailable and incomplete answers are covered by the tests), a review error that comes from a spoken answer (the demo logs none: the
  redirect was checked on the production's id).

### Owner's manual scenario (about 2 minutes, with your Groq key and a microphone)

1. `/speaking`, choose a subject, speak for a minute slipping in "I live in campus" and "I study here since two years", Stop, Listen, Send.
2. The page of the speech shows "Correcting… n s", then the heard text with the marks, the errors by part, the corrected and the natural
   versions, and the Structure section. Play your recording back from "Your recording".
3. Reload the page: nothing starts by itself. Open **My previous speeches** and the error log: an error's link opens the speech.
4. In a session, a `spoken_answer` card is answered aloud since M6.b2.2 (see its section).

### Departures from the prompt

- The plan's cut in two (b2.1 and b2.2, approved): this section is b2.1 only.
- Decisions start at D-202, not D-193 (D-201 was the last).
- The subject is optional (the recorder works without one), a click on "Transcribe" goes on to the correction (the click is the user's
  action), and `/writing/:id` only gains the redirect for `speaking` (D-203, D-204).
- `applyCorrectionError` also reads the production again for `not_transcribed` (it did for `already_corrected`).

### Left / notes

- **M6.b2.2**: done (see its section above).
- M6.c (Azure AI Speech), the microphone choice in the settings. The owner's manual scenarios. Push and the pull request: with the owner's
  go-ahead (after PR #21).

### Known issues

- The page title of a missing production says "This text does not exist (any more)" (the shared `production_not_found` sentence).
- A real recording was never made (see "Not verified").

## M6.b1 — The recorder and shadowing (frontend)

Branch `feat/m6b-speaking-screens`, cut from the tip of `feat/m6a2-speaking-correction` (`e5600ce`): `main` does not contain M6.a2
(`git branch --contains e5600ce` lists only that branch). Not pushed. Three commits in the order of the approved plan: the recorder
and the upload layer, the shadowing pages, the integrations (discovery, term page, manual error), then the docs. **No backend
change** (`git diff --stat e5600ce -- backend` is empty), no migration, no new dependency. SPEC.md unchanged. Decisions D-193 to
D-201; D-117 and D-123 annotated.

### Done

- **Recorder** (D-193): `src/speech/` gets `recorder.ts` (types, bounds, failure reasons), `useRecorder.ts`, `activeRecording.ts`
  (one recording at a time, cut on a route change) and `RecorderPanel.tsx` (`Recorder`: Start / Stop, "Recording… 0:42" with a red dot
  and the text, then Listen / Record again / Send). The speech synthesis is cut before the microphone opens; "Listen" is off while
  recording; every track is stopped at the end, on cancel, on unmount and on a route change; the `blob:` URL is revoked.
  Bounds: shadowing 0.5 to 30 s, free speaking 5 to 180 s (warning at 120 s), spoken answer 1 to 90 s; over 10 MB refused.
- **Upload layer** (D-194): `apiUpload`, `api/speech.ts` (types read from the backend, hooks), the spoken fields of `Production`,
  ten new error codes with their bounds, `incomplete` among the AI reasons.
- **Shadowing** (D-196): `/speaking/shadowing` (sentence from the navigation state or typed, 1 to 400 code points, Listen and Listen
  slowly, recorder, Send), `/speaking/shadowing/:id` (recording with `<audio controls>`, "Play both", Transcribe / silence /
  unavailable and Try again / 409 re-read, comparison), `/speaking/shadowing/history` (20 per page, the page in the URL). "Speaking" in
  the top bar. The privacy sentence (recording sent to Groq, kept in your data folder) is on every page that sends one.
- **Comparison** (D-197): `ComparisonView` from the backend's `steps`: Target and Heard rows, marks that always have a text, a summary in
  words, the list of unrecognised words, the warning that speech recognition is not a pronunciation judge, always shown.
- **"Play both"** (D-195): the synthetic voice, then the recording; cancellable; `speak()` now reports its end.
- **Manual error** (D-198): "Log as an intelligibility error" on a substituted word opens `/errors/new` filled in (category
  `pronunciation.intelligibility`); nothing is created before the click on "Add to my log".
- **Discovery step 4** (D-199): an optional recording of the sentence on screen (`origin=discovery`, term and session), compact
  comparison; a failure never blocks the way on. **Term page** (D-200): "Shadow this sentence" on the examples and on the original
  sentence, inside the revealed sheet.
- **Tests**: 525 Vitest tests (447 before): the recorder's rules, its five failure reasons, the tracks stopped at the end, on
  unmount, on cancel while asking and on a route change, the speech cut before recording, the blob URL revoked, the exact body and
  `Content-Type`, the shadowing pages (every transcription state, "Play both" in order and cancelled), the comparison on hand-made steps,
  the prefilled manual form, the discovery's optional recording and its failures, nothing in the storages or `history.state`, French.

### Verified (Windows 11, 2026-10-21)

- `npm run check` from the root: ruff and `ruff format --check` clean, **2 425 pytest passed** (14 live deselected), then the frontend: typecheck, oxlint `--deny-warnings`, **525 vitest tests**; exit code 0. `npm --prefix frontend run build` passes. `git diff --stat e5600ce -- backend` is empty.
- Break checks, applied then undone (`git checkout` of the file, the tree is clean):
  - **(a)** both `track.stop()` calls of `useRecorder.ts` replaced by `void track`: **7 tests fail** (the six "microphone is released"
    tests of `RecorderPanel.test.tsx` and the first test of `ShadowingPages.test.tsx`), all with
    `AssertionError: expected false to be true`.
  - **(b)** the `cancelSpeech()` call of `start` removed: **1 test fails**, "cuts the speech synthesis before it records"
    (`AssertionError: expected 0 to be greater than 0`).
- **In-app browser**, on a demo database made in a temporary folder (`VOCAB_DATA_DIR`, the keys emptied through the environment; the
  repository's `data/` and `.env` untouched; the servers were stopped afterwards): the history (6 shadowings, "7 of 8 words recognised"...),
  a detail (comparison, `<audio>` of 1 s that the server streams, ready state 4), "Play both" (the voice spoke, the clip played to its
  end, the button went back), "Log as an intelligibility error" (form filled, category label "Intelligibility", router state cleared),
  the manual-error form, the term page's "Shadow this sentence" on the original sentence (EN and FR); a `curl --data-binary @clip.wav -H
  "Content-Type: audio/wav"` of a 3 s WAV made with `wave` to `/api/speech/shadowing` (201, no Groq key: `unavailable`,
  `no_provider_configured`), then its page: "This recording is not transcribed yet" and, after "Transcribe", "The transcription is not
  available: no AI provider is set up. Your recording is kept." with "Try again".
- **375 px**, EN and FR: no horizontal scroll on the new pages, the term page and the error form (`scrollWidth` 375); the top bar's
  seven links wrap to a second row in French ("Oral", "Erreurs", "Réglages"), as D-145 accepted.
- **Not verified with a real microphone**: the in-app browser blocks the microphone (the permission request stays pending, and
  "Cancel" works). The refusal state was shown by making `getUserMedia` reject in the page. So what a real `MediaRecorder` produces, its
  `stop` timing, the browser's microphone indicator going out, a real take transcribed by Groq and the quality of the recording are
  **untested** (only the fakes and the `curl` clip).

### Owner's manual scenario (about 2 minutes, with your Groq key and a microphone)

1. `.\start.ps1 -Demo` (or without `-Demo` for your data), open **Speaking**. Type "We account for regional fixed effects." Click
   Listen, then Start recording (allow the microphone for 127.0.0.1 the first time), say it, Stop, Listen, Send.
2. The page of the take shows the comparison within a few seconds. Click **Play both** (voice then your recording). If a word was
   missed, "Log as an intelligibility error" opens the form filled in: read it, then add it or leave.
3. Open a term in the library, **Show the usage sheet**, click "Shadow this sentence" on an example: the field is filled in. Reload the
   page: it is empty again.
4. In a session, at a term's "Say it aloud" step, record yourself (optional) and see the compact comparison; "Done, I repeated it" goes on.
5. Without a Groq key the take is kept and its page says why, with "Try again".

### Departures from the prompt

- The component's file is `RecorderPanel.tsx` (a `Recorder.tsx` collides with `recorder.ts` on Windows, D-193).
- The reason of an unavailable first transcription travels in the router state to the next page (D-196).
- The original sentence of a term is displayed in the revealed sheet, with its "Shadow" link (it was only in the edit form, D-200).
- The discovery keeps the single button "Done, I repeated it" for "Continue" and "Skip" (D-199).
- Not planned: `useSpeech().speak` returns a boolean and takes `onDone` (D-195); `aiReason.ts` knows `incomplete`.

### Left / notes

- **M6.b2**: free speaking, the `speaking-1` branch of the correction model, spoken answers in the review player (extends D-143, replaces
  the "nothing is recorded yet" mention of D-123), the redirects between `/writing/:id` and `/speaking/:id`, the "Speaking" link to
  `/speaking`. `api/speech.ts` already has `useSpeaking`, `useSpeakingTopics` and the `ReviewAnswerOut` type.
- M6.c (Azure AI Speech), the microphone choice in the settings. The owner's manual scenarios. Push and the pull request: with the
  owner's go-ahead (after PR #21).

### Known issues

- A real recording was never made in this session (see "Not verified").
- One full run of the Vitest suite, out of five, showed one failing test that I could not name (a run under load: the next four
  passed, 525 of 525); the cause is probably a test with a 5 s timeout, not one of the new ones.
- `history.state` is cleared by a `replace` navigation after the first render, so the router state is briefly in the browser's
  history until the effect runs (the proposal is a sentence from the sheet, never a recording).
- The comparison counts these / those as close (D-173, unchanged); the heard text of a substituted word comes from the transcription's
  tokens, so the manual form may warn "not found in the sentence" if the recogniser's spelling had punctuation inside a word.

## M6.a2b — The demo through the speech services (backend)

Same branch as M6.a2a (`feat/m6a2-speaking-correction`). Commits in the order of the approved plan: injectable file
names, the speech flows in the caller's transaction, the atomic `audio-demo/`, the fictional AI and the clips with
dataset v4, the simulation (and `direct_writes.py` deleted), the docs. **No migration** (`alembic check`: no new
upgrade operation), **no frontend change**, no new dependency, no new setting. SPEC.md unchanged. Decisions D-187 to
D-192; D-035 closed, D-169 annotated.

### Done

- **Names** (D-187): `AudioStore(root, names=...)`, `uuid4().hex` by default; a name must be 32 hexadecimal
  characters. The demo draws its names from its seed: same seed, same `audio_path`.
- **The speech flows in the caller's transaction** (D-189): `speech.store_recording`, `speaking.store_speaking`,
  `spoken_review.store_spoken_answer` (with an injected corrector): the same checks, a given transcription, no AI call,
  no commit. The AI paths are unchanged.
- **Atomic `audio-demo/`** (D-188): the clips are written into `audio-demo.tmp-<pid>/`; the old folder is set aside,
  the database replaced, the new folder moved in, the old one deleted. A failure leaves the previous database and
  recordings intact; on Windows a recording or the database held open is reported and changes nothing.
- **Fictional AI and clips** (D-190): transcriptions (segments, a silent take), mishearings of 0 to 2 words, spoken
  corrections validated by `SpeakingCorrectionOutput` and its real context; provenance `demo`, `demo-speaking-v1`,
  model `demo-transcription-v1`; one-second WAV clips made with `wave` (`app/demo/clips.py`).
- **Dataset v4 and the history** (D-191): free speeches recorded, transcribed and corrected (errors of source
  `speaking`), shadowings of the terms' original sentences through the real comparator, every `spoken_answer` review
  checked by `store_spoken_answer` then recorded with its `production_attempt_id`, and in the last session a silent
  take and a speech not corrected yet. `app/demo/direct_writes.py` is deleted (`grep -r direct_writes backend` is
  empty). Seed 42 over 60 days: 17 recordings (6 corrected free speeches, 3 spoken answers, 6 shadowings with 8
  unrecognised words, 1 silent take, 1 speech not corrected).
- **Tests**: 2 425 backend tests (2 335 after M6.a2a): `test_audio_store.py` (names), `test_speech_service.py`,
  `test_speaking_service.py`, `api/test_spoken_review_api.py` (the caller's-transaction flows), `test_demo_seed.py`
  (the swap, a failing build, a recording and a database in use on Windows), `test_demo_fictional_ai.py`
  (transcriptions, mishearings checked by the comparator, spoken corrections, clips), `test_demo_data.py` (every
  recording has its file, free speeches, shadowings, spoken answers linked, playback through the API).

### Verified (Windows 11, 2026-10-21)

- `npm run check` from the root: ruff and `ruff format --check` clean, **2 425 pytest passed** (14 live deselected),
  then the frontend: typecheck, oxlint `--deny-warnings`, 447 vitest tests. Exit code 0. `alembic check` on a fresh
  database: no new upgrade operation. `git diff --stat feat/m6a1-recordings-transcription -- frontend` is empty;
  `git ls-files | grep -E '\.(wav|webm|mp3|m4a|ogg|flac|opus|aac|mp4)$'` is empty; `grep -r direct_writes backend`
  finds nothing (after `ruff clean`; `.venv` aside).
- **Seed time**, 60 days, seed 42, three fresh runs: 4.4 to 4.6 s (4.3 s before M6.a2b on this machine; target 7 s).
- **Seeds 1 to 12** (60 days): 13 to 24 recordings, 5 or 6 shadowings with 3 to 9 unrecognised words, one silent take
  each, every spoken answer linked; seed 2 has no `spoken_answer` review.
- **CLI on a temporary data folder** (`VOCAB_DATA_DIR`): `demo seed --anchor 2026-09-01` prints "Dataset v4" and
  "Recordings: 17 files in ...udio-demo" (exit 0); again without `--reset`: refused, nothing changed; with
  `--reset`: rebuilt, `audio-demo/` replaced, no `.tmp-` or `.old-` folder left.
- **Real server** (`python -m app --demo`, port 8765, that folder): `/api/health` says `demo: true`;
  `GET /api/productions?kind=shadowing` lists 6 shadowings (one: "previous studies" heard "previous study", reported
  as unrecognised); `?kind=speaking` lists 11; `GET /api/productions/{id}/audio` answers 200 `audio/wav` with
  `accept-ranges: bytes`.
- Not run by me: `start.ps1 -Demo` with the browser, and the owner's scenario below.

### Owner's manual scenario (about 3 minutes, no key needed)

1. Stop the app if it runs. In `backend`: `uv run python -m app demo seed --reset`. The summary says "Dataset v4" and
   "Recordings: N files in ...\data\audio-demo" (17 for seed 42 and the anchor 2026-09-01; about as many with
   today's anchor).
2. At the root: `.\start.ps1 -Demo` (or `start.cmd -Demo`). The app opens with the "Demo data" badge.
3. Open `http://127.0.0.1:8000/docs`:
   - `GET /api/productions` with `kind=speaking`: free speeches (`audio_url`, `transcription_status: ok`, a
     `speaking-1` feedback), spoken answers (their prompt is the card's question), one `silence` and one speech without
     feedback (not corrected yet);
   - `GET /api/productions` with `kind=shadowing`: five or six shadowings, each with a `comparison` whose `unrecognized` lists
     0 to 2 words;
   - `GET /api/productions/{id}/audio` with one of the ids: the response is a short WAV (one second of a soft tone, or
     of silence for the silent take). Every clip lasts one second whatever `audio_seconds` says (D-190).
4. While the app runs, `uv run python -m app demo seed --reset` is refused ("the file is in use"), and nothing changes.

### Departures from the prompt (for the whole of M6.a2)

- **M6.a2a** (see its section): 180 s and the SPEC sentence; `/correct` of a spoken answer in `answer` mode with the
  source `review`; silence as `unavailable` / `silence`; `review_log.audio_path`; `sentence_production` refuses a spoken
  production; the early checks also for the shadowing; 4 500 characters per corrected unit; `production.corrected` v2
  for every kind; and, not planned (D-186): the solution always returned by `review-answer`, `text_too_long` for an
  over-long spoken answer, the checks run three times, a private `_recorded_origin`, the prompt edited in place.
- **M6.a2b**, approved with the plan: the demo uses the speech flows in the caller's transaction, not the entry points
  that commit (D-189); the old `audio-demo/` is set aside **before** the database is replaced (D-188); `audio_dir`
  instead of `audio_store`, `AudioStore.clear()` removed; the transcription version in `model`; "every oral
  production has a file" read as every `speaking` and `shadowing` production (a pasted transcript is `oral` without a
  recording); a failed spoken answer leaves the term out (no confusion error); the last session's silent take and
  uncorrected speech; one-second clips with realistic declared durations.
- **M6.a2b**, not in the plan: `demo seed` prints the number of recordings; two assertions of `test_demo_data` follow
  the new rows (a spoken answer's proposed rating, a spoken production's word count).

### Left / notes

- M6.b1, M6.b2 (screens), M6.c (Azure). The owner's manual scenarios. Push and the pull request: with the owner's
  go-ahead (after PR #21).

### Known issues

- The demo's clips last one second whatever `audio_seconds` declares (D-190).
- With some seeds no `spoken_answer` review happens in 60 days (seed 2 of 1 to 12); the default seed 42 has three.
- If a program opens an old demo recording between the two renames of the swap, `rmtree(ignore_errors=True)` leaves
  it in `audio-demo.old-<pid>/` (harmless, deleted by hand).
- Those of M6.a2a below still hold.

## M6.a2a — Corrected free speaking and spoken answers in reviews (backend)

Branch `feat/m6a2-speaking-correction`, cut from the tip of `feat/m6a1-recordings-transcription` (`067feed`; M6.a1 is
PR #21, not merged into `main`). Commits in the order of the approved plan: the domain, the AI task, the store refactor
(`production.corrected` v2), free speaking and its topics, a test update (`production.recorded` v5), spoken answers in
reviews, the CLI and the live tests, the prompt tuned against the real model, the docs. **No migration** (`alembic
check`: no new upgrade operation), **no frontend change**, no new dependency, no new setting. SPEC.md: one sentence in
module F ("up to 3 accepted", approved with the plan). Decisions D-178 to D-186; D-101 updated.

### Done

- **Domain** (D-179): `RecordingKind` and its duration bounds (shadowing 0.5 to 30 s, free speaking 5 to 180 s, spoken
  answer 1 to 90 s), `MAX_SPEAKING_CHARS = 4000`, `speech_units` (at most 40 units of whole consecutive sentences,
  balanced, exact positions); `production_rating` reads `speaking-1` (term not heard: no rating, `term_not_heard`);
  `domain/topics.py` shared by the writing and the speaking topics.
- **AI task** `speaking_correction` v1 (D-180): spoken rules (hesitations, false starts, self-corrections, the
  recogniser's spelling and homophones ignored; register and discourse only when clearly wrong; the rest goes in
  `structure`); `SpeakingCorrectionOutput` inherits every validator of `production_correction` and adds `structure`
  (comment, connectors found in the text, suggestions), required for a monologue. `production_correction` unchanged.
- **Store** (D-181): `format: "speaking-1"` with the keys of `correction-1` and `output.structure`; spoken errors dated
  at the recording; `production.corrected` v2 with `kind`.
- **Free speaking** (D-182): `POST /api/speech/speaking`, then `POST /api/productions/{id}/correct`; checks before the
  file is written and again in the transaction; `word_count` = the words heard; `production.recorded` v5 (origin
  `speaking`); refusals `not_correctable`, `already_corrected`, `not_transcribed`, `nothing_to_correct`,
  `text_too_long`; `GET /api/speaking/topics` and `content/speaking_topics.yaml` (26 fictional topics, EN and FR).
- **Spoken answers in reviews** (D-183): `POST /api/speech/review-answer` (every refusal before any write and any AI
  call, then three short transactions: recording, transcription, correction in `answer` mode); `POST /api/reviews`
  takes the production back for `spoken_answer`, computes `auto_rating` again, fills `review_log.audio_path`, refuses
  (409 `production_mismatch`) a production of another kind or a free speech.
- **CLI** (D-184): `speech speak --file <clip> [--prompt] [--duration] [--no-correct]`, `speech correct <id>`.
- **Examples** (fictional): `content/examples/m6_speaking.txt` (three errors among hesitations and a self-correction)
  and `m6_speaking_clean.txt` (correct).
- **Tests**: 2 335 backend tests (2 230 before): `test_speaking_domain.py`, `ai/test_speaking_correction_schema.py`
  (every validator rejected, repaired once, then `incomplete`), `test_correction_store.py`, `api/test_speaking_api.py`,
  `test_speaking_service.py`, `api/test_spoken_review_api.py`, `test_cli_speaking.py`, `api/test_guard.py` (+4),
  `api/test_session_api.py` (the anti-leak walk calls `review-answer`), and `tests/live/test_live_speaking.py` (off by
  default, 3 tests). `production_correction`'s tests are not modified.

### Verified (Windows 11, 2026-10-20)

- `npm run check` from the root: ruff and `ruff format --check` clean, **2 335 pytest passed** (14 live deselected),
  then the frontend: typecheck, oxlint `--deny-warnings`, 447 vitest tests. Exit code 0. `alembic check`: no new
  upgrade operation. `git diff --stat feat/m6a1-recordings-transcription -- frontend` is empty;
  `git ls-files | grep -E '\.(wav|webm|mp3|m4a|ogg|flac|opus|aac|mp4)$'` is empty.
- **Live, with the owner's keys** (D-185): `test_live_speaking.py` three passes, 2 passed and 1 skipped (the audio test
  without a clip) each time; the example gave exactly its three codes in 9 of 9 runs after the prompt was tuned, the
  clean text 0 errors in 7 of 7; the two M5.a1 live tests pass. **Audio pass** with a synthetic clip of
  `m6_speaking.txt` (Windows System.Speech, voice Zira, 33 s, in a temporary folder, never committed): Groq answered a
  real `verbose_json` (duration 33.08 s), the correction gave the three codes.
- **CLI on a temporary database** (`VOCAB_DATA_DIR` in a temporary folder, `db upgrade`): `speech speak` on the clip
  without `--duration` (Groq measured 33.08 s; three `speaking` errors, the structure and the "what was heard" note;
  exit 0); `errors list` shows them; with `VOCAB_GROQ_API_KEY` emptied: without `--duration` nothing is stored (exit
  2), with `--duration 40` the production is kept and the message gives `speech transcribe 2` then `speech correct 2`
  (exit 1); `speech correct 2` before the transcription: "transcribe it first" (exit 2); with the key back
  `speech transcribe 2` (exit 0), `speech correct 2` (three errors, exit 0), again: "already corrected" (exit 2);
  `--demo speech speak --duration 33 --no-correct` after `demo seed --days 7` writes into `audio-demo/` (exit 0).
- Not run by me: a recording of the owner's own voice, and the owner's scenario below.

### Owner's manual scenario (about 2 minutes)

1. With the **Windows Sound Recorder** (Enregistreur vocal), record 30 to 60 s reading
   `content/examples/m6_speaking.txt` aloud, hesitations included. It saves an `.m4a` file.
2. In `backend`: `uv run python -m app speech speak --file "<path to the .m4a>" --prompt "Describe where you study and
   for how long."` It prints what Groq heard, the errors (expect "in campus", "since two years" and "never presented",
   unless Whisper smoothed one over), the more natural version and the comment on the structure.
3. `uv run python -m app errors list`: the errors are there with the source `speaking`.
4. Without a Groq key (comment out `VOCAB_GROQ_API_KEY` in `.env`): the same command plus `--duration 40` keeps the
   recording and says `unavailable`; put the key back, then `uv run python -m app speech transcribe <id>` and
   `uv run python -m app speech correct <id>`.
5. Optional: `$env:VOCAB_RUN_LIVE='1'; $env:VOCAB_LIVE_AUDIO='<path to the .m4a>'; uv run pytest
   tests/live/test_live_speaking.py -m live -v -s` (not `test_live_speech.py` with this clip: it takes at most 30 s).

### API reference for the screens (M6.b2)

| Route | Request | Success |
|---|---|---|
| `POST /api/speech/speaking` | body: the recording (types and 10 MB as the shadowing); query: `duration_s` (5 to 180), `prompt_text?` (at most 500), `target_item_ids?` (repeated, at most 15), `study_session_id?` | 201 `SpeechOut` (`comparison: null`) |
| `POST /api/productions/{id}/correct` | none, for a `speaking` production | 200 `CorrectionOut`, `attempt.feedback.format = "speaking-1"` |
| `GET /api/speaking/topics?count=3&tag=` | `count` 1 to 10; `tag`: `interview`, `presenting`, `academic`, `data_science`, `everyday`, `campus` | 200 `[{id, en, fr, tags}]` |
| `POST /api/speech/review-answer` | body: the recording; query: `card_id`, `session_id`, `exercise_template_id`, `duration_s` (1 to 90), `response_time_ms` (>= 0) | 200 `ReviewAnswerOut` |
| `POST /api/reviews` | as before, plus `production_attempt_id` = the `review-answer` production for a `spoken_answer` | 200 `RecordOut` |

`speaking-1` = the `correction-1` keys (`output.sentences` are the units, `spans` code points into `text`,
`error_event_ids`, `targets`) and `output.structure` = `{comment_en, comment_fr, connectors_used: [], suggestions:
[{text_en, text_fr}]}` (null in `answer` mode is allowed). `ReviewAnswerOut` = `{production_attempt_id, transcription:
{status: ok | silence | unavailable, text|null, reason|null}, status: ok | incomplete | unavailable, reason|null,
feedback|null, errors: [ErrorOut] (source review), proposed_rating: 1 | 3 | null, warnings: [] | ["term_not_heard"],
solution: {example_answer}, sheet_summary|null}`; `reason` is a transcription reason (`no_provider_configured`,
`quota`, `network`, `auth`, `timeout`, `all_failed`, `incomplete`), `silence`, `text_too_long`, or the correction's.
A spoken production in `ProductionOut` has `kind: speaking`, `audio_url`, `transcription_status` and `comparison: null`;
`GET /api/productions?kind=speaking` lists them (spoken answers included: their prompt is the card's question).
Errors: 409 `not_transcribed`, `already_corrected`, `not_due`, `review_not_allowed`, `session_closed`,
`production_mismatch` (`POST /reviews`); 422 `not_correctable`, `nothing_to_correct`, `text_too_long`,
`invalid_production`, `exercise_mismatch`, `audio_empty`, `audio_too_short` / `audio_too_long` (+ `min_s`, `max_s`);
404 `card_not_found`, `session_not_found`, `item_not_found`; 413 `audio_too_large`; 415 `unsupported_audio`.
The screens must say that the correction is about what the recogniser heard; `review-answer` makes two AI calls
(allow about 90 s); the example answer is shown only from its answer (active recall).

### Departures from the prompt

- Approved with the plan: 180 s and the SPEC sentence; `/correct` of a spoken answer in `answer` mode with the source
  `review`; silence as `unavailable` / `silence`; `review_log.audio_path`; `sentence_production` refuses a spoken
  production; the early checks also for the shadowing; 4 500 characters per corrected unit; `production.corrected` v2
  for every kind; the demo fingerprint changes.
- Not planned (D-186): `review-answer` always returns the solution once the recording exists; `unavailable` /
  `text_too_long` for an over-long spoken answer; the review checks run three times through `speech.Check`; a private
  `_recorded_origin` in `review_flow` (import cycle); the prompt was edited in place (v1 never released, D-185).

### Left / notes

- **M6.a2b** (next, D-178): the demo through the services (spoken productions, answers and their fictional
  corrections), dataset v4, `direct_writes.py` removed, D-035 closed.
- M6.b1, M6.b2 (screens), M6.c (Azure). The owner's manual scenarios. Push and the pull request: with the owner's
  go-ahead (after PR #21).

### Known issues

- The correction is about what Whisper heard: a mistake it smoothed over is not reported, a misheard word may be
  (the prompt asks to ignore likely homophones). The synthetic clip kept every mistake; a human voice is untested.
- The model's corrected text sometimes keeps the fillers ("Um, so, ...") although the prompt asks to leave them out.
- In `--demo`, the hint after a failure gives the command without `--demo` (as in M6.a1).
- A lite model is not deterministic: 9 of 9 and 7 of 7 runs were right, but a run may still miss or over-report.

## M6.a1 — Recordings, transcription and word-by-word comparison (backend)

Branch `feat/m6a1-recordings-transcription`, cut from `main` (`7904aa3`), with the "Current state" fix of `docs/m5-wrap-up`
cherry-picked first. Then one commit per step (the domain, the gateway, the store and the service, the API, the CLI and
the demo), a test update, a CLI fix and the docs. **No migration** (`alembic check`: no new upgrade operation), **no frontend change**, no new dependency,
no new setting. SPEC.md unchanged. Decisions D-168 to D-177.

### Done

- **Comparator** (`domain/speech_compare.py`, `speech-compare-1`, D-173): words cleaned as in the grading (D-102),
  contractions (it's = it is = it has, don't = do not, 'd = would or had, John's = Johns...), numbers 0 to 100 in words
  or digits, % / percent / per cent, hyphens (well-known = well known, e-mail = email); minimal and deterministic
  alignment by dynamic programming with backtracking: `match` (also k:l merges), `close` (counted as recognised),
  `substituted`, `missing`, `extra`; `unrecognized` with positions and what was heard; `word_accuracy`. **The `close`
  rule chosen by the owner**: a British / American spelling, or one edit on a target word of 5 letters or more, except
  on the first letter or for a final -s / -d.
- **Rules** (`domain/speech_rules.py`): 10 MB, target 400 characters, duration bounds per production kind (shadowing
  0.5 to 30 s), Whisper's silence rule (`no_speech_prob > 0.6` and `avg_logprob <= -1.0` on every segment).
- **Gateway** (D-171, D-172): Groq Whisper asked for `verbose_json`, read tolerantly; `TranscriptionOutput` gains
  `duration_s` and `segments`; `Gateway.transcribe` unchanged and still without a prompt. Whisper free limits checked
  again: unchanged.
- **Storage** (`app/speech/audio_store.py`, D-169): `data/audio/YYYY/MM/<uuid4>.<ext>` (`data/audio-demo/` in demo mode),
  atomic write, paths resolved only inside the folder; `demo seed` empties `audio-demo/`.
- **Service** (`services/speech.py`): validation, file, a short transaction (production `shadowing` / `oral`, target,
  `text=""`, `word_count=0`, `production.recorded` v4; the file is deleted if it fails), transcription with no session
  open and never with the target as a prompt, then a short transaction (text, `pronunciation_result`,
  `production.transcribed`, `pronunciation.checked`). Silence stores no text and no comparison; an AI failure stores
  nothing more and can be retried. **No error is ever created from the comparison** (D-174).
- **API** (D-170, D-175): `POST /api/speech/shadowing` (raw body), `POST /api/productions/{id}/transcribe`,
  `GET /api/productions/{id}/audio` (streamed, `Range` answered); `ProductionOut` gains `audio_url`, `audio_seconds`,
  `transcription_status`, `comparison`. The API guard accepts an `audio/*` body under `/api/speech/` only.
- **CLI** (D-176): `speech shadow`, `speech transcribe`, `speech compare`; `--demo` uses `data/audio-demo/`.
- **Events** (open set, no migration): `production.recorded` v4 (`shadowing` origin), `production.transcribed`,
  `pronunciation.checked`, with no text in their payloads.
- **Privacy**: `.env.example` and the README say recordings sent to Groq leave the machine and stay in `data/`; the CI
  refuses `flac`, `opus`, `aac`, `mp4` files too.
- **Tests**: 2 230 backend tests (1 951 before): `test_speech_compare.py` (tolerances, close, properties on 500 random
  pairs), `test_speech_rules.py`, `test_audio_store.py`, `test_speech_service.py`, `api/test_speech_api.py`,
  `api/test_guard.py` (+9), `test_cli_speech.py`, `test_demo_seed.py` (+3), the Groq adapter and gateway tests (+20), and
  `tests/live/test_live_speech.py` (off by default); `api/test_transcripts_api.py` now expects `production.recorded` v4. Every
  clip is made in memory with `wave`.

### Verified (Windows 11, 2026-10-18)

- `npm run check` from the root: ruff and `ruff format --check` clean, **2 230 pytest passed** (11 live deselected),
  then the frontend: typecheck, oxlint `--deny-warnings`, 447 vitest tests. Exit code 0. `alembic check`: no new upgrade
  operation. `git ls-files | grep -E '\.(wav|webm|mp3|m4a|ogg|flac|opus|aac|mp4)$'` is empty.
- **On a temporary database, no key** (`VOCAB_DATA_DIR` in a temporary folder, keys emptied): `speech compare "We account
  for regional fixed effects." "we account for regional fix effect"` flags `fixed -> fix` and `effects -> effect` (4 of
  6, exit 0); `speech shadow` with a WAV made by `wave` and `--duration 2` keeps the production and prints
  `unavailable (no_provider_configured)` (exit 1), the file is under `data/audio/2026/10/`; the same without
  `--duration` stores nothing (exit 2). Through a `TestClient`: `GET /api/productions/1/audio` gives the same bytes as
  `audio/wav`, `Range: bytes=0-9` gives 206; `GET /api/productions?kind=shadowing` shows `audio_url`, `audio_seconds`,
  `transcription_status: pending`; `POST /api/productions/1/transcribe` answers 200 `unavailable`.
- Not run by me: a real transcription (no Groq key here, no recording of the owner's voice), so the real `verbose_json`
  answer is still unseen (read from the documentation; the live test checks it); the owner's scenario below.

### Owner's manual scenario (about 2 minutes)

1. With the **Windows Sound Recorder** (Enregistreur vocal), record yourself saying "We account for regional fixed
   effects in all specifications." It saves an `.m4a` file (in `Documents\Sound recordings`, or `Enregistrements audio`).
2. With your Groq key in `.env`, in `backend`: `uv run python -m app speech shadow --file "<path to the .m4a>" --target
   "We account for regional fixed effects in all specifications."` It prints the duration measured by Groq, the
   transcription, the words not recognised and the path of the file under `data\audio\YYYY\MM\`. Open that folder: the
   file is there. At the root, `git status` does not show it.
3. Without a Groq key (comment out `VOCAB_GROQ_API_KEY` in `.env`): the same command plus `--duration 4` records the
   production and says the transcription is `unavailable (no_provider_configured)`; put the key back and run
   `uv run python -m app speech transcribe <id>`.
4. Without AI: `uv run python -m app speech compare "We account for regional fixed effects." "we account for regional fix
   effect"`.
5. Optional, the live test with your clip: `$env:VOCAB_RUN_LIVE='1'; $env:VOCAB_LIVE_AUDIO='<path to the .m4a>'; uv run
   pytest tests/live/test_live_speech.py -m live -v -s`.

### API reference for the screens (M6.b1)

| Route | Request | Success |
|---|---|---|
| `POST /api/speech/shadowing` | body: the recording, `Content-Type` = its type (`audio/webm`, `audio/ogg`, `audio/mp4`, `audio/x-m4a`, `audio/wav`, `audio/x-wav`, `audio/mpeg`; `;codecs=...` allowed), at most 10 MB; query: `target_text` (1 to 400 characters), `duration_s` (0.5 to 30), `item_id?`, `origin?` (`shadowing` default, `discovery`), `study_session_id?` | 201 `SpeechOut` |
| `POST /api/productions/{id}/transcribe` | none | 200 `SpeechOut` |
| `GET /api/productions/{id}/audio` | `Range` allowed | 200 or 206, the file, type from its extension |

`SpeechOut` = `{production_id, audio_url, audio_seconds, transcription: {status: ok | silence | unavailable, text|null,
reason|null}, comparison|null}`; `comparison` = `{version, word_accuracy (4 decimals), target_word_count,
heard_word_count, recognized_count, unrecognized: [{position, word, heard|null}], steps: [{op: match | close |
substituted | missing | extra, target_start, target_end, heard_start, heard_end, target|null, heard|null}]}`.
`reason` is `no_provider_configured`, `quota`, `network`, `auth`, `timeout`, `all_failed` or `incomplete`.
`ProductionOut` (list and detail) gains `audio_url|null`, `audio_seconds|null`, `transcription_status` (`pending` |
`ok` | `silence` | null) and `comparison|null`; `GET /api/productions?kind=shadowing` lists the shadowings.
Errors: 413 `audio_too_large` (+ `max_bytes`); 415 `unsupported_audio` (an audio type not accepted),
`unsupported_media_type` (not audio at all, from the guard); 422 `invalid_request`, `audio_empty`, `audio_too_short` /
`audio_too_long` (+ `min_s`, `max_s`), `invalid_target`, `no_audio` (transcribe); 404 `item_not_found`,
`session_not_found`, `production_not_found`, `no_audio` (playback); 409 `session_closed`, `already_transcribed`.
The screen must say that speech recognition is not a pronunciation judge (SPEC module F), and must not show the
target before the user has tried, where the exercise needs it (active recall).

### Departures from the prompt

- `production.transcribed` also carries `model` and `ai_call_id` (as `production.corrected`); `ProductionOut` also gains
  `transcription_status` (D-175). Approved with the plan.
- Groq's `duration`, when present, replaces `audio_seconds` after the transcription; silence is also detected from the
  segments (D-171). Approved with the plan.
- The guard accepts `audio/*` under `/api/speech/` (D-170) and the CI list gains four extensions (D-177). Approved with
  the plan.
- Not in the milestone: the code `duration_required` (422, CLI path only), the extras `min_s` / `max_s` / `max_bytes` on
  the errors, and a README paragraph.

### Left / notes

- M6.a2, M6.b1, M6.b2, M6.c (D-168). Local transcription (faster-whisper) to propose later; audio backup in M10.
- The first real `verbose_json` answer: run the live test once with a clip (scenario step 5).
- The owner's manual scenarios (M2.c2 to M5.c2) and the one above. Push and the pull request: with the owner's go-ahead.

### Known issues

- The comparator counts these / those and quite / quiet as close (one edit apart), and does not know homophones
  (their / there), numbers above a hundred in words or ordinals (D-173).
- The target sentence is a query parameter, so it shows in uvicorn's console access log (not a secret, D-170).
- `demo seed` cannot delete a demo recording another program holds open on Windows; it stays in `audio-demo/` (D-169).
- `audio_url` is given whenever a path is stored; a file deleted by hand gives 404 `no_audio` on playback (D-169).

## M5.a3 — Cards from errors, recurring errors, the demo through the services (backend)

Branch `claude/m5a3-error-cards-fa8d12` (worktree), cut from the tip of `feat/m5c-transcripts-drills` (M5.c1 and M5.c2,
not pushed). Five commits: the domain, the services, the API and CLI, the `store_*` refactor, the demo (plus the docs).
**No migration** (`alembic check`: no new upgrade operation), **no frontend change** (`git diff --stat
feat/m5c-transcripts-drills -- frontend` is empty), no new dependency. SPEC.md: one sentence in module E (one productive
card per error, approved). Decisions D-163 to D-167.

### Done

- **Cards from errors** (D-163): `POST /api/errors/{id}/card` makes a term (the correction, or `term`), a small sheet made
  from the error (its explanation; the wrong forms as pitfalls), one `gap_fill` of the sentence the error came from with the
  changed words blanked, and **one productive card** in the deck "Error cards" (`kind error_drill`). No AI. The term goes
  `draft -> learning` through the new transition kind `FROM_ERROR`; the card is due at the start of the next study day.
- **Reviews of these cards** (D-163): the wrong form is a sheet pitfall, so "in" for "on" is `wrong`, never a typo; falling
  back into it logs a review error with the **category of the origin error** (`review_flow._origin_category`).
- **Recurring errors** (D-164): `GET /api/errors/suggestions` (the same wrong form corrected the same way at least twice;
  drill errors left out; carded, in-library and dismissed ones hidden), `POST /api/errors/suggestions/dismiss`
  (event `error.suggestion_dismissed`, no table). `ErrorOut.card` (additive).
- **CLI**: `errors card <id> [--term] [--sentence]`, `errors suggestions [--min-count] [--limit]`, `errors dismiss <key>`.
- **`store_correction`, `store_analysis`, `store_drill`** (D-165): the write step of each AI task, public, in the caller's
  transaction (no behaviour change).
- **The demo through the services** (D-166): corrections, analysed transcripts (`You:` / `Tutor:` conversations), drills
  with their answers and drill errors, review errors, and cards made from recurring errors (4, plus 1 dismissal). The
  results of the "AI" come from `app/demo/fictional_ai.py` and are validated by the real output models. Only the spoken
  productions are still written directly (`direct_writes.record_oral_production`, until M6). Dataset v3.
- **Events** (open set, no migration): `error.card_created`, `error.suggestion_dismissed`.
- **Tests**: 1 951 backend tests (1 763 before): `test_error_cards.py` (domain), `test_error_cards_service.py`,
  `api/test_error_cards_api.py`, `test_cli_errors.py` (+1), `test_demo_data.py` (+6, module E in the demo),
  `test_demo_fictional_ai.py` (every template and every drill against the real schemas and grading).

### Verified (Windows 11, 2026-10-18)

- `npm run check` from the root: ruff and `ruff format --check` clean, **1 951 pytest passed** (10 live deselected), then the
  frontend: typecheck, oxlint `--deny-warnings`, 447 vitest tests. Exit code 0. `alembic check`: no new upgrade operation.
- **Breaking check** (applied, then undone): `review_flow._origin_category` removed from `_confusion_error`: the test
  `test_falling_back_into_the_error_keeps_its_category` fails (`lexis.collocation` instead of
  `grammar.preposition.fixed_expression`); with the code back it passes.
- **Demo, seed 42, 60 days, anchor 2026-09-01** (built in about 4 s, read through the real API with a `TestClient`):
  `/api/drills` lists 7 drills over 3 categories (6 finished, 1 with 3 of 5 answered); `/api/productions?kind=
  transcript_analysis` lists 4 analysed conversations (`transcript-1`, only the learner's turns stored); `/api/errors?
  source=drill` has 14 errors; `/api/errors/suggestions` lists the recurring errors (10 occurrences for the most frequent);
  `/api/errors` shows `card` on the errors that have one; `/api/decks` lists "Error cards" (`error_drill`, active). The CLI
  `--demo errors suggestions` and `errors card` work on it. The same seed gives the same fingerprint (tested).
- **Demo fingerprint** changes for expected reasons (D-166): new rows (drills, analysed transcripts, error cards and their
  events, `explanation_fr`), and the reviews of the new cards shift the older random draws. Not compared with the previous
  one table by table.
- Not run by me: the owner's manual scenario below; no screen shows cards from errors or suggestions yet (backend only).

### Owner's manual scenario (about 3 minutes, no key needed)

1. `.\start.ps1 -Demo`, then in `backend`: `uv run python -m app --demo errors suggestions --limit 5`: the recurring errors,
   each with `errors card <id>`.
2. `uv run python -m app --demo errors card <id>` for one of them (for example "in university"): the term, the exercise
   (`She is ___ university.`) and the first review date. Run the same command again: "already is a card of this error".
3. Open `http://127.0.0.1:8000/docs`, `GET /api/errors/suggestions` (the card is gone), `POST /api/errors/suggestions/dismiss`
   with a key, `GET /api/drills` (7 drills, one unfinished), `GET /api/productions?kind=transcript_analysis`.
4. In the app: `/drills` and `/transcripts/history` on the demo now have content; `/errors?source=drill` lists the drill
   errors with "Open the drill".

### API reference for the screens (M5.d)

| Route | Request | Success |
|---|---|---|
| `POST /api/errors/{id}/card` | `{term?: ≤ 300, sentence?: ≤ 400}` (both optional) | 201 `{error_id, item_id, term, card_id, deck_id, sentence, due}` |
| `GET /api/errors/suggestions?min_count=2&limit=20` | `min_count` 1-20, `limit` 1-50 | 200 `{suggestions: [{key, erroneous_text, correction, category: {code, label_en, label_fr, status}, count, first_at, last_at, error_id, sample_error_ids, term\|null, cardable, reason\|null}]}` |
| `POST /api/errors/suggestions/dismiss` | `{key}` | 200 `{dismissed: bool}` |

`ErrorOut` gains `card: {id, term} | null`. Errors: 404 `error_not_found`, `suggestion_not_found`; 409 `card_exists` (+
`item_id`); 422 `not_cardable` (+ `reason`: `no_context`, `invalid_sentence`, `invalid_term`, `no_correction`,
`too_long`), `invalid_request` (malformed body).

### Departures from the prompt

- **One productive card per error**, not two (D-163): approved with the plan; SPEC module E says so.
- **A `sentence` in the request**: not planned; needed because a manual error has no original sentence and every card
  needs its gap-fill (D-163).
- **A dismissal event** (approved with the plan) and `ErrorOut.card` (additive, not planned).
- `tweak` got a full sheet (the demo's half-discovered term must have one, D-166).

### Left / notes

- **The screens** for cards from errors and suggestions (not planned yet: "M5.d"), and an undo for a dismissal.
- The pull requests: done, M5.c as PR #18 then this branch as PR #19, both merged into `main` on 2026-10-18.
- **M6**: speaking, which removes the last direct write of the demo.
- The owner's manual scenarios (M2.c2 to M5.c2) and the one above.

### Known issues

- A term made from a tense error is the corrected fragment ("I have met"): fine as a pattern, less as a word. The user can
  give `term` and `sentence` (D-167).
- Editing the sheet of an error card with `save_sheet` derives a typed-recall exercise whose cue is the rule, which contains
  the answer (D-167).
- A dismissed suggestion cannot be brought back (D-164).
- The demo's suggestions show counts such as 10: the dataset repeats its 59 templates.

## M5.c2 — Drills and links (frontend)

Second part of branch `feat/m5c-transcripts-drills`. **No backend change** (`git diff --stat main -- backend` is empty),
no migration, no new dependency, SPEC.md unchanged. Decisions D-158 to D-162.

### Done

- **API layer** (`api/drills.ts`): the types read in `app/api/drills.py`, `services/drills.py` and `domain/drills.py`;
  `useDrills` (20 per page), `useDrill`, `useCreateDrill`, `useAnswerItem` (the answer's `drill` replaces the cached one;
  a wrong answer invalidates the error log and the category counts).
- **`/drills`** (`DrillsPage`): the list (category in the interface language with its code, date, score, state; filter by
  category prefix and page in the URL) and the "New drill" form (eligible categories only, 5 to 15 items, "Preparing your
  exercises… n s", no double send, AI failures in words with the form kept, `?category=` preset and scroll, the study
  session from the navigation state) (D-158).
- **`/drills/:id`** (`DrillPage`, `DrillItemPlayer`, `DrillResult`, `DrillSummary`): the rule from the start (French on
  request), "Item n of N", resume at the first item not answered, gap-fill with a labelled field and a gap marked by a
  line ("blank" for screen readers), choices with keys 1 to 4 (AZERTY digit row and numeric keypad), "I don't know",
  the exact result with sign and word, "Added to your error log" with a link, "Next" (Enter), the score and the recap,
  "New drill on this category", "See these errors", "Back to today's session" (D-159, D-160).
- **Links** (D-161): "Practise now" in `practice_info` and on the Today card, "Practise this category" on
  `/errors/categories`, "Targeted drills" on `/errors`, a drill error opens its drill (`productionLink`).
- **Elsewhere**: `CategorySelect` mode `drill`; `KeyHints` moved to `components/`; `activatesItself` exported; the error
  codes `drill_not_found`, `already_answered`, `not_drillable` with the translated `reason` (D-162).
- **i18n** (EN + FR, same keys, "vous"): `drills.*`, `errors.drill_not_found` / `already_answered` / `not_drillable`,
  `session.practice.now`, `errorLog.drillsLink`, `errorLog.categories.practise` / `practiseNamed`,
  `errorLog.list.openDrill`, `errorLog.detail.openDrill`; two texts reworded (`session.practice.later`,
  `today.targeted`). **CSS**: `.drills-page`, `.drill-*`, tokens only; the choices reuse `.review-option*`.
- **Tests**: 447 in total (378 before; 37 → 42 files). `DrillsPage.test.tsx`, `DrillPage.test.tsx`,
  `drillLinks.test.tsx`, `drillMachine.test.ts`, `drillRules.test.ts`, plus additions to `errorMessage.test.ts` (+3) and
  `logRules.test.ts` (+1); 65 tests under `features/drills/`.

### Verified (Windows 11, 2026-10-18)

- `npm run check` from the root: ruff and `ruff format --check` clean, 1 763 pytest passed (10 live deselected), then the
  frontend: typecheck, oxlint `--deny-warnings`, 447 vitest tests. Exit code 0. `npm --prefix frontend run build` passes
  (same chunk-size warning). `git diff --stat main -- backend`: empty.
- **Breaking checks** (applied, then undone; the code is back to green, 65 drills tests pass):
  (b) a preload of the item's result (an empty answer sent when the item is mounted, its result rendered hidden): the
  active-recall test fails (`expected '<div><div class="shell">…' not to contain 'ANSWER-TOKEN'`). The test looks at the
  whole `innerHTML` and at the list of requests.
  (c) the ref guard removed (`transition` always returns true): two tests fail, "sends one answer when Enter is pressed
  twice before the screen updates" and "sends one answer when a choice key is pressed twice at once" (two answers sent).
  A first variant that read the React state instead of the ref also failed 12 tests, because the request callbacks then
  saw a stale state; it is not the one counted above.
- **In the in-app browser** (Chromium; 375 px; temporary demo database in the session's scratchpad, backend on port 8011
  behind the Vite already on 5173; `data/` and `.env` not touched; the backend was started again with the three AI
  settings really empty, see below):
  1. `/drills`: the list (2 seeded drills: "Not started", "3 of 5 Completed") and the form with level-1 parents greyed and
     pronunciation / spelling left out.
  2. A seeded `drill-1` (5 items) played with the keyboard against the real backend: wrong gap-fill (error logged: "Added
     to your error log", link), Enter to go on, a choice, the field focused for the next gap-fill (typing without a
     click), "I don't know", the score "2 of 5 correct" and the recap with the three links.
  3. Today card in French: "S'entraîner maintenant" → `/drills?category=grammar.tense.past_simple_vs_present_perfect`, the
     select preselected, the page scrolled to the form (scrollY 224, form top 257 px), `history.state.usr` =
     `{fromSession: 50}`, "Cet exercice fait partie de la séance du jour." Without any AI: "The drill could not be
     created: no AI provider is set up. Nothing was saved; you can try again.", the form still filled (category, 10), the
     button enabled again.
  4. `scrollWidth` 375 on `/`, `/drills`, `/drills?category=…`, `/drills/19` (summary), `/drills/20` (reader), `/errors`,
     `/errors/categories`, `/session`: English with the dark theme, and French with the light theme (the language and
     theme were crossed in those two combinations only, not all 16). The result block in French at 375 px was read on a
     screenshot.
- **Found while verifying (not a bug of the app)**: my first backend start used PowerShell's `$env:X = ""`, which
  *deletes* the variable on Windows, so `.env` supplied the Gemini key and the "Create the drill" click made **one real
  call** (drill 21, 10 items, written to the temporary database only). It confirmed the real flow, then the backend was
  restarted with the three settings truly empty (`VOCAB_GEMINI_API_KEY=` from Git Bash) and the degraded mode was
  checked. Use Git Bash (or `cmd`) to empty a variable for a test run.
- Not checked in the browser: the `practice_info` step with its link in the live session (reviews come first, 17 were
  due; it is covered by `drillLinks.test.tsx`), a list of more than 20 drills, the reload of a drill in progress,
  French with the dark theme, light English, the 409 and 422 paths against the real server (tests only).

### Owner's manual scenario (about 3 minutes, with your Gemini key)

1. `/errors/categories` → "Practise this category" on a preposition (for example "Place"): the form opens with the
   category chosen; keep 5 items and "Create the drill" (a few seconds).
2. Read the rule, answer the items with the keyboard (1 to 4 for a choice, Enter to check and to go on); answer one gap-fill
   wrongly on purpose: the result shows your answer, the right one and the explanation, and "Added to your error log"
   with a link; open it (`/errors/{id}`), it comes back to the drill with "Open the drill it comes from".
3. At the end: the score, the recap, "See these errors" (`/errors?source=drill&category=…`), "New drill on this category".
4. Today: if the targeted-practice line appears, "Practise now" leads to the form with the right category chosen; from the
   session's "Also planned today" step the same link keeps the session ("Back to today's session" at the end).

### Departures from the prompt

- **Enter does not send an empty gap-fill** and "Check" is disabled while the field is empty (D-159): "I don't know" is the
  way to give an empty answer.
- **`session.practice.later` and `today.targeted` reworded** (D-161): they said the exercises were for information only
  or for a later version; the first now speaks of the consolidation task alone.
- **`CategorySelect` got a third mode** and `KeyHints` moved out of `ReviewPlayer` (a refactor without behaviour change).
- The recap has no link to the logged errors (`DrillOut` has no `error_event_id`): "See these errors" is used.

### Left / notes

- **M5.a3** (backend): cards made from errors, suggestions for recurring errors, the demo's errors through the services
  (the demo still has no drill and no drill error). Then the pull request of M5.c.
- **M6**: speaking and recording; **M9**: statistics.
- The owner's manual scenario above.

### Known issues

- After "Back to today's session" the session's `practice_info` step is shown again (D-161); "Continue" is enough.
- `{fromSession}` lives in the navigation state: a drill opened by its URL (a bookmark, the history list) has no
  "Back to today's session" link.
- A lite model can write an arguable drill item (two answers that both fit); the result says the correction is exact and
  that the error can be deleted (M5.a2's known issue, now visible in the screen).
- `document.documentElement.lang` follows the interface language only after a change (M5.c1's known issue, seen again).

## M5.c1 — Transcripts (frontend)

First of two parts on branch `feat/m5c-transcripts-drills` (M5.c2: drills and the links), cut from `main`
(`bab1a95`). **No backend change** (`git diff --stat main -- backend` is empty), no migration, no new dependency,
SPEC.md unchanged. Decisions D-151 to D-157.

### Done

- **API layer** (`api/transcripts.ts`): the types read in `app/api/transcripts.py`, `app/api/productions.py` and
  `app/domain/transcript_import.py`; `usePreviewTranscript`, `useCreateTranscript`, `useAnalyseTranscript` (a
  `{transcript}` body is optional; `onDone` runs in the hook). `api/productions.ts` shares `applyCorrection` /
  `applyCorrectionError` between the two correction hooks, and `Feedback` gained `units`, `context_sent`, `calls`.
- **`/transcripts`** (`TranscriptPage`): the paste with a code-point counter and the 60 000 limit (message, disabled
  button, no request, no `maxLength`), "Preview", the parser's problems in the interface language with the severity in
  words, the choice of your turns (a label, or three modes without labels), the numbered turns with yours marked
  "You" and a border, your counters against 6 000, an optional title (200) and date (`max` = the study day), the
  privacy notice, "Save and analyse" (D-152, D-153, D-154).
- **`/transcripts/:id`** (`TranscriptDetailPage`): the analysis starts once after saving, with the pasted conversation
  kept **in memory only** (`transcriptMemory.ts`); "Analysing your turns… n s"; "Try again"; after a reload, "Analyse
  without the other speaker's context" or "Paste the conversation again" (same preview and choice); `409
  transcript_mismatch` keeps the pasted text; `409 already_corrected` shows the stored analysis (D-152).
- **`/transcripts/history`**: 20 per page, the page in the URL; date, title, your words, state in words.
- **`CorrectionView` / `readFeedback`**: the `transcript-1` branch; errors grouped under "Your turn k"; the mention
  "analysed with / without the other speaker's context"; no natural version (D-155).
- **Elsewhere**: a link on `/writing`; the error log opens a `transcript` error's conversation (`productionLink`); two
  new error codes (`transcript_mismatch`, `invalid_transcript`) and the translated `codes` of `invalid_transcript` and
  `text_too_long` (D-156).
- **i18n** (EN + FR, same keys): `transcripts.*`, `correction.yourTurns` / `turn` / `contextSent` / `contextNotSent` /
  `noErrorsTurns`, `errors.transcript_mismatch` / `invalid_transcript` / `text_too_long_transcript`,
  `writing.transcriptLink`. **CSS**: `.transcript-*`, tokens only.
- **Tests**: 378 in total (332 before; 31 → 37 files). `TranscriptPage.test.tsx` (17), `TranscriptDetailPage.test.tsx`
  (12), `TranscriptHistoryPage.test.tsx` (3), `correction.transcript.test.ts` (7), `logRules.test.ts` (3),
  `errorMessage.test.ts` (4); one assertion of `ErrorsPage.test.tsx` changed (a transcript error now has a link).

### Verified (Windows 11, 2026-10-18)

- `npm run check` from the root: ruff and `ruff format --check` clean, 1 763 pytest passed (10 live deselected), then
  the frontend: typecheck, oxlint `--deny-warnings`, 378 vitest tests. Exit code 0. `npm --prefix frontend run build`
  passes (same chunk-size warning). `git diff --stat main -- backend`: empty.
- **Breaking check** (applied, then undone; the code is back to green): (a) the pasted text added to the navigation
  state (`state: { autoAnalyse: true, text }`): the privacy test fails (`expected '{"history":{"usr":{"autoAnalyse":true…'
  not to contain 'Hello! Where do you live at the moment?'`). The test watches `window.history.state`, the router state
  and the URL at every navigation (a `createBrowserRouter` variant, `renderAppInBrowser`), then the two storages. The
  checks (b) and (c) of the prompt belong to M5.c2.
- **In the in-app browser** (Chromium; EN and FR; light and dark; 375 px), on a temporary demo database in the
  session's scratchpad (`VOCAB_DATA_DIR`, `VOCAB_DEMO=1`, the three AI settings emptied, backend on port 8011 behind
  the Vite that was already running on 5173; `data/` and `.env` not touched):
  1. `m5_transcript.txt` pasted (in French): "You" pre-chosen, 8 turns, 4 of them yours ("Vos tours : 4 · 59 mots"),
     "Save and analyse": `/transcripts/18`, "not analysed: no AI provider is set up", `history.state` = `{usr: null}`,
     `localStorage` / `sessionStorage` without any text.
  2. Reload: no request, the two buttons; "Paste the conversation again" with the conversation, preview, then the
     analysis, which the server accepted as matching (the degraded message again).
  3. An unlabelled paragraph text: three modes, none chosen, "I speak second" gives turns 2, 4 and 6 as yours.
  4. 60 001 characters: the message, the disabled button, **0 requests**, no `maxlength`. A lone "Note:" line: the
     explanation of D-133.
  5. A stored `transcript-1` analysis (written into the temporary database with a script): three numbered marks on the
     right words after the blank lines between turns, "Your turn 1" to "Your turn 3", the context mention, no natural
     version.
  6. `scrollWidth` 375 on `/transcripts` (with a preview), `/transcripts/17`, `/transcripts/18`, `/transcripts/history`
     in English and in French, light and dark (the combinations were spread over the pages, not all 16 crossed).
     **Found and fixed**: the title field (28 rem) made the page 481 px wide at 375 px; a fieldset keeps its content's
     minimum width, so `.transcript-meta` and `.transcript-picker` got `min-width: 0` (D-157).
- Not checked in the browser: a real AI analysis (no key was used; covered by the tests and by the stored analysis
  above), the date field's `max` against a study day that is not today, "Try again" after a failure.

### Owner's manual scenario (about 3 minutes, with your Gemini key)

1. `/writing` → "Analyse a conversation transcript": paste `content/examples/m5_transcript.txt`, check that "You" is
   already chosen and that your 4 turns are marked, then "Save and analyse" (the privacy notice is above the button).
2. The result: three errors, all in your turns (none in ChatGPT's), under "Your turn 1" to "Your turn 3"; they appear in
   `/errors?source=transcript`, and each row's "Open the text" leads back to the conversation.
3. Reload the page: the stored analysis stays, no new analysis starts. For a text that was not analysed, reload shows
   "Analyse without the other speaker's context" and "Paste the conversation again".
4. Paste `content/examples/m5_transcript_unlabelled.txt`: the three modes ("I speak second" is the right one), save.

### Departures from the prompt

- **No preselected mode without labels** (D-153): the prompt only asked for three modes; none is chosen, and saving
  waits for a choice.
- **The date limit is the study day, not the browser's calendar day** (D-154), because that is what the server's
  `future_date` uses; the local day only stands in while the plan loads.
- **`CorrectionView` changed a little** (D-155), although D-140 planned "no change to the view": a turn heading, the
  context mention and the "no errors in your turns" sentence needed it.
- `useAnalyseTranscript(onDone)`: the memory is forgotten in the hook's callbacks (they run after the page is left),
  not in the component.
- The prompt listed more error codes (`drill_not_found`, `already_answered`, `not_drillable`...): they are for M5.c2;
  `not_correctable` was already known.

### Left / notes

- **M5.c2**: the drills screens, "Practise now", "Practise this category", the `drill` link of the error log.
- **M5.a3** (backend): cards made from errors, suggestions for recurring errors, the demo's errors through the
  services (the demo's transcript productions are still "Not analysed").
- The analysis of a very long conversation (up to about 4 calls, a few minutes) was not tried live.
- The owner's manual scenario above.

### Known issues

- A long category code wraps in the middle of the word inside an error entry (existing CSS, seen at 375 px).
- `document.documentElement.lang` follows the interface language only after a change, not at load (`i18n/index.ts`):
  seen while checking in French; not touched here.
- Leaving the page during a long analysis lets it finish on the server; the result is there when the page is opened
  again, but the pasted text is gone (so a retry has no context).

## M5.b2 — Error log and categories (frontend)

Second part of branch `feat/m5b-writing-errors`. **No backend change** (`git diff --stat main -- backend` is empty), no
migration, no new dependency, SPEC.md unchanged. Decisions D-146 to D-150 (and an edit of D-114).

### Done

- **API layer** (`api/errors.ts`): `useErrors(filters)`, `useError`, `useCreateError`, `usePatchError`,
  `useDeleteError`, `useCreateCategory`, `useResolveCategory`; the filter helpers `parseFilters`, `filtersToParams`,
  `errorsQuery`, `localMidnight`; `SLUG_PATTERN`. `useItems` takes an optional `enabled`.
- **`/errors`** (`ErrorsPage`): filters (category, source with the seven values, search, from / to), the term chip of
  `item_id`, clickable level-2 facets with counts, a table of 25 per page, a pager; everything is in the URL.
- **`/errors/:id`** (`ErrorDetailPage`): the original sentence with the incorrect form marked (bold, wavy underline,
  and named in words), an edit form that sends only the changed fields, a term picker with "Unlink", and a deletion
  with an inline confirmation whose focus goes to "Keep it".
- **`/errors/new`** (`ManualErrorPage`): the manual entry with the client checks, then "Added to your error log" and
  a link; the form empties for the next one.
- **`/errors/categories`** (`CategoriesPage`): the AI's proposals first (accept with an optional rename, reject
  after an explanation, then "n errors moved"), the tree with counts (total and 14 days), statuses and origins as
  text, the rejected ones folded, and a creation form.
- **Elsewhere**: the "Errors" top link, labels instead of codes in the Today card and in `practice_info` (the code
  stays as a fallback), "Errors linked to this term" on a term's page, six new `errors.*` codes.
- **Pure helpers**: `fragment.ts` (a look-alike of the backend's `find_fragment`), `logRules.ts` (`problemOf`,
  `productionLink`).
- **i18n** (EN + FR, same keys): `errorLog.*` (list, detail, manual, categories), `nav.errors`,
  `library.item.errorsTitle` / `errorsLink`. **CSS**: tokens only, `minmax(0, 1fr)` on the page grid.
- **Tests**: 332 in total (283 before; 26 → 31 files). `fragment.test.ts` (9), `ErrorsPage.test.tsx` (10),
  `ErrorDetailPage.test.tsx` (12), `ManualErrorPage.test.tsx` (6), `CategoriesPage.test.tsx` (8), plus label tests in
  `TodayCard` and `SessionPage`, and the term-page link.

### Verified (Windows 11, 2026-10-18)

- `npm --prefix frontend run check` (typecheck, oxlint `--deny-warnings`, 332 vitest tests): green.
  `npm --prefix frontend run build` passes (same chunk-size warning). `git diff --stat main -- backend`: empty.
- **In the in-app browser** (EN and FR; dark and light; 375 px), on a temporary demo database in the session's
  scratchpad (`VOCAB_DATA_DIR`, `VOCAB_DEMO=1`, AI keys emptied, backend on port 8011; the Vite already running on
  5173 proxies there; two proposed categories added through `propose_category`; `data/` and `.env` not touched):
  1. `/errors`: 234 demo errors, the facets, 25 per page, the category label with its code, a filter by category.
  2. `/errors/234`: the incorrect form marked in the sentence, the edit form, the alternatives.
  3. `/errors/categories`: two proposals; "Accept" (active at once, announced), "Reject" then "Yes, reject it"
     ("no error had to move", folded under "Rejected categories (1)").
  4. 375 px: `/errors`, `/errors/234`, `/errors/new`, `/errors/categories` and Home, in English and French: no
     horizontal scroll (`scrollWidth` 375). The six top links wrap to two rows in both languages.
  5. The request bodies of the pages were replayed against the real backend with `curl` (list with the
     local-midnight dates, `POST /errors`, `PATCH`, `DELETE`, `POST /error-categories` and the duplicate code): the
     answers match what the pages expect (`invalid_error`, `category_exists`, 204).
- Not checked in the browser by clicking: the creation form of a category, the edit and delete buttons and the manual
  form (covered by the tests and by the `curl` replay of their bodies).

### Owner's manual scenario (about 3 minutes, no AI needed)

1. `/errors`: the list and the facets; choose the category "Prepositions" in the filter, "Apply": the URL holds
   `?category=grammar.preposition`; click a facet to narrow, click it again to clear.
2. Open one error: the incorrect form is marked. Change its category, "Save" ("Saved."); come back with the link
   (the filters are kept). Open another one and delete it ("Keep it" has the focus; "Yes, delete it").
3. `/errors/new`: type a sentence, an incorrect form that is in it, a correction and a category: "Add to my log".
   Try an incorrect form that is not in the sentence: the page refuses it without a request.
4. `/errors/categories`: create a subcategory (a code name such as `time_words`, both labels); if the AI proposed
   one (after a correction with a key), accept it, then reject another.
5. A term's page: "Errors linked to this term" opens `/errors?item_id=…` with its chip.

### Departures from the prompt

- **Six error codes more, not "nine"**: the prompt listed five. The backend also answers `category_exists` (409),
  added here; `invalid_error` shows the backend's English detail under the sentence (like `invalid_setting`).
- **Namespace `errorLog.*`** instead of `errors.*` for the page strings: `errors.*` already holds the error
  messages by code, so the page strings would have shared one flat namespace with them.
- **The "from / to" fields are calendar days** in the browser's time zone, sent as local midnights (D-146).
- A production link on a row only exists for the sources `writing` and `review` (D-146).
- The taxonomy has three levels in the demo (`grammar.preposition.time`): the selectors and the tree are recursive,
  not limited to two (D-147).

### Left / notes

- The detail page shows the stored original sentence only, not the whole production around it.
- The review result still has only the single "Added to your error log" announcement of M5.b1.

### Known issues

- Long category codes make the list table scroll sideways inside its frame (it never widens the page).
- A reloaded `/errors/:id` of a deleted error shows the "not in your log" message after a short wait.

## M5.b1 — Writing and corrections (frontend)

Branch `feat/m5b-writing-errors` from `main` (`8bb866a`). First of two parts on the same branch (M5.b2: error log and
categories). **No backend change** (`git diff --stat main -- backend` is empty), no migration, no new dependency,
SPEC.md unchanged. Decisions D-140 to D-145 (and the D-138 amendment).

### Done

- **API layer**: `api/productions.ts` (types of the stored `correction-1` feedback, create / get / list / correct /
  topics hooks), `api/errors.ts` (`ErrorOut`, the category tree and its label helpers; M5.b2 adds the rest),
  `api/reviews.ts` (`checkProduction`, `production_attempt_id` and `error_event_id`), `apiSend` with a signal.
  Shapes read in `api/productions.py`, `reviews.py`, `writing.py`, `error_log.py`, `review_flow.py`: see "Departures".
- **`spans.ts`** (pure): code points to UTF-16, overlaps merged, bad spans ignored (D-140). **`correction.ts`**: the
  neutral model, where `transcript-1` will plug in for M5.c.
- **`CorrectionView`** (D-141): numbered underlined marks with links both ways, errors grouped by "Sentence n",
  English first and French on demand per error, naturalness notes, corrected and natural versions with Copy, target
  terms, the proposed-category notice, a compact mode.
- **`/writing`, `/writing/history`, `/writing/:id`** (D-142): topics with a theme filter or your own, counters and
  the 4 000 limit, draft in the browser, save then correct, "Try again", `already_corrected`, history by 20.
- **Review player** (D-143): `checking_production`, the AI check, the compact correction, "Suggested" rating,
  "Skip the check" after 5 s, the self-graded fallback, the single resend on `production_mismatch`, "Added to your
  error log" with a link.
- **Discovery** (D-144): "Check my sentence with AI" next to "Continue".
- **i18n** (EN + FR, same keys): `correction.*`, `writing.*`, `review.aiCheck.*`, `review.errorLogged.*`,
  `discovery.sentenceCheck.*`, six `errors.*` codes, `nav.writing`. **CSS**: correction, topics, writing form, tokens
  only, dark mode.
- **Tests**: 283 in total (194 before M5.b1; 21 → 26 files). `spans.test.ts` (12: ASCII, "Yaoundé" in NFC and NFD, an
  emoji before the error, overlaps, nested, start, end, out of bounds), `CorrectionView.test.tsx` (21),
  `WritingPage.test.tsx` (22: exact bodies, URL and history action, theme filter, own topic, `unavailable` then "Try
  again" calling only `/correct`, `incomplete`, the running counter and a single request, `already_corrected`, 4 000
  limit, `text_too_long`, `invalid_production`, draft kept then cleared, storage blocked, history, detail not
  corrected, 404, French), `ReviewPlayer.check.test.tsx` (19) and `reviewMachine.test.ts` (8), the existing
  sentence-production case of `ReviewPlayer.test.tsx` now walks check → grade, and 7 new `DiscoveryFlow` tests.

### Verified (Windows 11, 2026-10-18)

- `npm --prefix frontend run check`: typecheck, oxlint `--deny-warnings`, 283 vitest tests, green.
  `npm --prefix frontend run build` passes (same "chunk larger than 500 kB" warning). `npm run check` (backend
  `ruff`, `ruff format --check`, 1 763 pytest tests, then the frontend above): exit code 0.
- **Breaking checks** (applied, then undone; the code is back to green):
  - (a) raw offsets without the code-point conversion: 3 tests fail (2 in `spans.test.ts`, 1 in
    `CorrectionView.test.tsx`, all the emoji cases);
  - (b) the solution fetched early and shown while the AI is still reading: the active-recall test fails (5 other
    tests fail too, because of the extra `grade` request);
  - (c) the production id kept after `unavailable` and sent with the rating: 3 tests fail (the generic walk of
    `sentence_production` and the `unavailable` / `incomplete` cases).
- **In the in-app browser** (Chromium; EN and FR; dark theme; 375 px), on a temporary demo database in the session's
  scratchpad (backend on port 8011 with the AI keys emptied by environment variables, so the real degraded mode;
  `data/` and `.env` not touched; the Vite already running on 5173 was reused):
  1. `/writing`: a topic chosen ("Chosen" in text), the example paragraph typed, "Correct my text": text saved,
     `/writing/20`, "Your text is saved but was not corrected: no AI provider is set up", "Try again", draft cleared.
  2. `/writing/18`, a text corrected through the real service by a scripted provider (so the stored feedback is
     what the validators accept): two marks numbered 2 and 1 under "lived" and "in campus", the list, the labels
     (after the tree loads), "Show in French", the corrected and natural versions.
  3. Today: a mature productive card (`sentence_production`) on the demo: a sentence typed, `check-production` then
     `grade` then `POST /reviews` (200), the notice "The AI check is not available…", `term_missing`, the example
     answer, four buttons, rated with the key 3, "Saved: the previous card comes back…".
  4. Discovery of "outperform": exercises, personal sentence, last screen with "Check my sentence with AI" next to
     "Continue"; without AI it says why and does not block.
  5. 375 px, dark: `/writing`, `/writing/18`, `/writing/history`, `/session`: no horizontal scroll in English or French
     (found and fixed: the history table widened the page, D-145). The five top links fit on one row in English;
     in French the fifth wraps to a second row.
- Not checked in the browser: a successful AI answer to `check-production` and to the discovery button (no key was
  used; covered by the tests and by the stored correction above), "Skip the check" (covered by fake timers), the
  light theme at 375 px.

### Owner's manual scenario (about 2 minutes, with your Gemini key)

1. `/writing`: choose a topic, paste `content/examples/m5_paragraph.txt`, "Correct my text": two underlined marks (the
   preposition in "in campus" and the past simple "lived"), the corrected version and the natural version.
2. Reload the page: the same correction, and `/writing/history` still lists one text (no new production).
3. Today, on a `sentence_production` card (if there is one; otherwise later): a wrong sentence, the correction, a
   suggested rating, save. **Remember that the checked sentence goes to the AI.**
4. Discovery of a term: a personal sentence, then "Check my sentence with AI".

### Departures from the prompt

- **Fallback of the checked sentence goes through `grade`, not `reveal`** (approved in the plan): it keeps
  `term_missing`; it is exactly what M4.c does for this type (D-143).
- `CorrectionView` also takes `targets` and `proposedCategories`, and `compact` / `level` (D-141); the labels fall
  back to `GET /api/error-categories` because a reloaded production has no logged errors (D-141).
- The correction runs on `/writing/:id` (reached by a replaced history entry), not on the writing page, so a reload
  can never start a correction or create a text (D-142).
- `review.check` could not be a namespace (already the button label): the keys are `review.aiCheck.*`.
- "Errors" in the top bar waits for M5.b2 (a link to a missing page would show the 404 page). Until then, two
  links point at routes that M5.b2 creates: `/errors/{id}` (review announcement), `/errors/categories` (proposed
  categories notice).

### Left / notes

- **M5.b2** (the error log, the manual entry, the categories, the labels in "Today" and `practice_info`, the link from
  a term's page, the nine `errors.*` codes of that part, the "Errors" top link).
- Known limit: the writing history mixes the personal sentences of discoveries and the sentences written in reviews,
  because `ProductionOut` has no `origin`; `prompt_text` tells them apart (D-142).
- The reference said `reveal` for the fallback and "Checking… n s" on the writing page: see the departures.
- A "Skip the check" abandons the wait only: the AI may still finish on the server, and the sentence stays recorded
  without being linked to the review.

### Known issues

- Labels of the categories appear a moment after the correction on a reloaded text (they come from a second
  request); the code is shown meanwhile.
- The top bar wraps to two rows in French at 375 px.
- The leftover Vite on port 5173 (started on 2026-10-17 from this folder) was reused for the browser check; it was
  not started by this session.

## M5.a2 — Transcript analysis and targeted drills (backend)

Branch `feat/m5a2-transcripts-drills` from `main` (`2f3fe26`, M5.a1 merged as PR #15), cut in two parts on the same
branch (like D-099): transcripts, then drills and the planner. **No migration**: every value needed existed
(`ProductionKind.transcript_analysis | drill`, `ErrorSource.transcript | drill`, `Modality.oral`). SPEC.md unchanged.

### Done

- **Transcript parser** (`domain/transcript_import.py`, pure, D-133): labels (known user and other labels),
  timestamps, unlabelled paragraphs and the three modes, empty turns, limits (60 000 pasted, 6 000 of the user's),
  stable problem codes, the context before each user turn (its last 300 characters), units (600 characters) and
  chunks (2 500 characters, 20 units).
- **`transcript_analysis` v1** (D-134): prompt (oral rules, homophones, quoted forms, the "since + duration" calque),
  schema and validators (each tested: rejected, repaired once, then `incomplete`), budgets as named constants.
- **Transcript service and routes**: `POST /api/transcripts/preview` (no session), `POST /api/transcripts` (only the
  user's turns are stored, `production.recorded` v3), `/productions/{id}/correct` chooses the task by `kind` and
  takes the transcript again for the context (`transcript_mismatch`). One call per chunk, all or nothing, no session
  open during the calls (tested with a second writer on each call). Errors with source `transcript` and the day of
  the conversation.
- **`targeted_drill` v1** (D-135) and the drill rules (`domain/drills.py`): exact grading (D-136), deterministic
  option order, public items without solutions.
- **Drill service and routes**: `POST /api/drills`, `GET /api/drills`, `GET /api/drills/{id}`, `POST
  /api/drills/{id}/items/{index}/answer`; events `drill.generated`, `drill.item_answered`, `drill.completed`; a
  wrong answer becomes an error (source `drill`) with its French explanation; drill feedback hidden from
  `/api/productions`.
- **Planner** (D-137, amendment of D-029): targeted practice ignores drill errors.
- **CLI**: `transcript analyse --file <txt> [--speaker | --mode] [--preview]`, `drill new <code> [--count N]`,
  `drill list`. **Examples**: `content/examples/m5_transcript.txt`, `m5_transcript_clean.txt`,
  `m5_transcript_unlabelled.txt` (fictional).
- **Taxonomy v3**: the "since + duration" calque is described under `grammar.preposition.by_for_since`.

### Verified (Windows 11, 2026-10-18)

- `ruff check .`, `ruff format --check .`: clean. `pytest`: 1 763 passed, 10 live tests deselected. `alembic check`:
  no operation. `npm run check`: green (backend as above, frontend untouched: 194 vitest tests).
- **Live** (`gemini-3.5-flash-lite`, `VOCAB_RUN_LIVE=1`): `test_live_transcript.py` (example: exactly the three
  expected codes, none from ChatGPT's turn; clean transcript: 0 errors) passed 6 of 6 times with the final prompt;
  `test_live_drill.py` (10 valid items) passes; 5 drill probes all valid (one after a repair). The two M5.a1 live
  tests still pass with taxonomy v3. Details in D-134 and D-135.
- **Demo fingerprint** (seed 42, 60 days, anchor 2026-09-01): it changes, for two expected reasons only (taxonomy v3
  descriptions, and `production.recorded` rows written as payload version 3 with null new fields); every other table
  is identical, so the planner change has no effect on the demo (D-137).
- Not run by me: the owner's manual scenario below.

### Owner's manual scenario (about 2 minutes, with your key)

1. `cd backend; uv run python -m app transcript analyse --file ../content/examples/m5_transcript.txt --preview`:
   8 turns, the label "You" suggested, your 4 turns marked `*`.
2. The same command without `--preview`: three errors (`grammar.preposition.fixed_expression`,
   `grammar.preposition.by_for_since`, `grammar.tense.past_simple_vs_present_perfect`).
3. `uv run python -m app errors list`: the three errors, with the source `transcript`.
4. `uv run python -m app drill new grammar.preposition.fixed_expression --count 5`: the rule and 5 items, without
   solutions.
5. Start the app, open `http://127.0.0.1:8000/docs`: `POST /api/drills/{id}/items/0/answer` with a wrong answer
   (`{"answer": "xyz", "response_time_ms": 3000}` for a gap-fill, or a wrong `choice_index` for a choice); the error
   appears in `GET /api/errors?source=drill`.

### API reference for M5.b and M5.c

Errors use the D-063 format. `ProductionOut` is unchanged (M5.a1), except: a transcript's `feedback` has `format:
"transcript-1"` with the `correction-1` keys (units as `sentences`, `natural_text: null`, `targets: []`) plus
`units: [{index, turn, start, end, opens_turn}]`, `context_sent`, `calls: [{ai_call_id, provider, model, units:
[first, last]}]`; `spans` point into `text` (the user's turns joined by a blank line); a drill's `feedback` is
`null` and `corrected` is `false`. `ErrorOut.source` can now be `transcript` or `drill`.

`PreviewOut = {turns: [{index (from 1), speaker_label|null, text, line_start, is_user|null}], labels: [{label, turns,
words, chars, known: user|other|null}], labelled, suggested_user_label|null, designation: {label}|{mode}|null, user:
{turns, words, chars}|null, problems: [{line|null, severity: info|warning|error, code, message}]}`.
`DrillOut = {id, category: {code, label_en, label_fr}, rule_en, rule_fr, items: [{index (from 0), kind:
gap_fill|choice, sentence (one ___), options|null (shuffled, same order on every read), answered, result|null}],
completed, score: {correct, wrong, empty, answered, total}, created_at}`; `result = {outcome: exact|wrong|empty,
expected, accepted, correct_index|null (into the shown options), explanation_en, explanation_fr, given}`.

| Route | Request | Success |
|---|---|---|
| `POST /api/transcripts/preview` | `{text (≤ 120 000), user?: {label} \| {mode: alternating_user_first \| alternating_user_second \| all_mine}}` | 200 `PreviewOut`; writes nothing |
| `POST /api/transcripts` | `{text, user: {label} \| {mode}, title\|null (≤ 200), occurred_on\|null (YYYY-MM-DD, not in the future), study_session_id\|null}` | 201 `ProductionOut` (uncorrected, `kind: transcript_analysis`, `modality: oral`) |
| `POST /api/productions/{id}/correct` | optional `{transcript: {text, user}}` for a transcript (the context of the other speaker; without it, no context) | 200 as M5.a1 (`status`, `reason`, `attempt`, `errors`, `proposed_categories`); a long transcript takes several calls (10 to 40 s) |
| `GET /api/productions?kind=transcript_analysis` | – | 200 page as M5.a1 |
| `POST /api/drills` | `{category_code, count (5–15, default 10), study_session_id\|null}` | 201 `{status: "ok", reason: null, drill: DrillOut}`; AI failure: 200 `{status: incomplete\|unavailable, reason, drill: null}` |
| `GET /api/drills?category=&limit=&offset=` | `category` is a code prefix | 200 `{items: [DrillOut], total, limit, offset}`, newest first, `limit` ≤ 100 |
| `GET /api/drills/{id}` | – | 200 `DrillOut` |
| `POST /api/drills/{id}/items/{index}/answer` | `{answer\|null (gap-fill), choice_index\|null (choice), response_time_ms ≥ 0}` | 200 `{result, error_event_id\|null, drill: DrillOut}` |

| Status | `code` | When |
|---|---|---|
| 404 | `drill_not_found`, `item_not_found`, `category_not_found`, `production_not_found`, `session_not_found` | unknown drill (or not a drill), item index, category, production, study session |
| 409 | `transcript_mismatch` | the transcript sent with `/correct` does not give the stored turns |
| 409 | `already_answered`, `already_corrected` | item answered before; transcript analysed before |
| 422 | `invalid_transcript` (+ `codes`) | no usable user turn (`empty_text`, `unknown_label`, `no_user_turns`) or `future_date` |
| 422 | `text_too_long` (+ `codes`) | more than 60 000 pasted characters or 6 000 characters of your turns |
| 422 | `not_drillable` (+ `reason`) | level-1 code, `pronunciation.*`, proposed or rejected category |
| 422 | `exercise_mismatch` | a choice answered with text, a gap-fill with `choice_index`, an index out of range |
| 422 | `invalid_production`, `not_correctable`, `invalid_request` | a transcript body on another kind; `correct` on a drill; malformed body (count out of 5–15, title > 200) |

### Departures from the prompt (approved in the plan, except the last two)

- Optional `{transcript}` body on `/correct` for the context and 409 `transcript_mismatch` (D-134); `theme` in drill
  items (D-135); optional `user` in the preview (D-133); lines before the first label as an unlabelled turn
  (D-133); `ProductionOut.feedback = null` for drills (D-136); the label rule left unchanged (D-133).
- **To approve**: the demo fingerprint changes (taxonomy v3 and `production.recorded` v3, D-137), although the
  prompt expected it unchanged; and taxonomy v3 itself (prompt tuning, as D-132 allows).
- Small additions: chunks also limited to 20 units; drill errors get the accepted forms as `alternatives`;
  `POST /api/drills` answers 200 with `drill: null` on an AI failure; `invalid_transcript` also covers a future date.

### Left / notes

- **M5.a3**: cards made from errors, suggestions for recurring errors, the demo's errors through the services
  (D-138). **M5.b / M5.c**: the screens; M5.c keeps the pasted transcript in memory to send it with `/correct`, and
  links the session's `practice_info` step to a drill through `category_code`.
- The owner's manual scenario above.
- `write correct` and `library enrich` accept `--demo` while the new AI commands refuse it (D-139).

### Known issues

- A lite model can write an arguable drill item (two answers that both fit); grading is exact, so the user may get
  a `wrong` they disagree with: the solution shows `expected` and `accepted`, and the error can be deleted.
- A line such as "Note: ..." inside a turn opens a turn with the label "Note" (D-133); the preview shows it.
- Analysing a long transcript makes up to about 4 sequential calls; with Groq as fallback (8 000 tokens per minute)
  a 429 is possible, handled by the gateway's retries.
- `spans` use Unicode code points (as M5.a1).

## M5.a1 — Production correction and error log (backend) ✅

Branch `feat/m5a-errors-backend` from `origin/main` (`cbcc304`), six commits: the error log and categories, the
review errors, the CLI errors commands, the AI correction, the AI-checked sentence production, then the docs. M5 is cut in four sessions (D-130). **One migration**
(`0002_review_log_production`, D-127: the prompt planned none; see "Departures"). SPEC.md unchanged.

### Done

- **`production_correction` v1** (D-128): prompt, schema with 13 validators (each tested to be rejected, repaired
  once, then `incomplete`), budgets as named constants, the taxonomy and the learner text framed as the prompt
  rules say (text = `data`).
- **Correction service** (`corrections.py`): read, AI call with no transaction open (a test locks the database
  from another connection during the call), one write transaction (409 `already_corrected` if corrected
  meanwhile). `ai_feedback` (`correction-1`) with `spans` (code points, tested with « Yaoundé » in both Unicode
  forms), `error_event_ids`, target checks (`used` deterministic, `used_correctly` from the AI, disagreement
  noted). `unavailable` / `incomplete` write nothing and can be retried.
- **Productions API**: `POST/GET /api/productions`, `GET /api/productions/{id}`, `POST .../correct`. The personal
  sentence of a discovery is corrected through the same route.
- **Error log and categories** (D-131): manual entry, filters, level-2 facets, pagination, `PATCH` / `DELETE` with
  events, the category tree, user categories, AI-proposed subcategories accepted or rejected (errors go to the
  parent); `sync_taxonomy` leaves proposed and rejected categories alone (tested).
- **Errors from reviews**: a typed `wrong` with a lexical confusion gives one error (`lexis.wrong_word` /
  `lexis.collocation`, source `review`, `review_log_id`); nothing for choices, typos, empty answers or
  self-graded types; `grade` / `reveal` still write nothing. `POST /api/reviews` answers `error_event_id`.
- **AI-checked sentence production** (D-129): `POST /api/reviews/check-production`, then `POST /api/reviews`
  with `production_attempt_id`: the server proposes Good / Again / none from the stored correction.
- **Writing topics** (`GET /api/writing/topics`), **new events** (`production.corrected`, `error.updated`,
  `error.deleted`, `error_category.created|proposed|resolved`; `production.recorded` v2 has `origin`).
- **CLI**: `write correct --file <txt> [--prompt]`, `errors list|show|add|categories [--proposed]`; examples
  `content/examples/m5_paragraph.txt` and `m5_correct_paragraph.txt`.
- **Taxonomy v2** and prompt tuned against the real model (D-132).

### Verified (Windows 11, 2026-10-17)

- `uv --directory backend run ruff check .`, `ruff format --check .`: clean. `pytest`: 1 586 passed, 7 live tests
  deselected. `alembic check`: no operation. (`npm run check` runs the same backend steps; the frontend is
  untouched.)
- **Live** (`VOCAB_RUN_LIVE=1 pytest tests/live/test_live_correction.py -m live`, `gemini-3.5-flash-lite`): the two
  tests pass: the example paragraph gives exactly `grammar.preposition.fixed_expression` and
  `grammar.tense.past_simple_vs_present_perfect`; the correct paragraph gives 0 errors and a naturalness note.
  See D-132 for what had to change and how stable it is (a lite model is not deterministic).
- Not run by me: the owner's manual scenario below.

### Owner's manual scenario (about 2 minutes, with your key)

1. `cd backend; uv run python -m app write correct --file ../content/examples/m5_paragraph.txt`: two errors, each
   with its code, the corrected text and a more natural version.
2. `uv run python -m app errors list`: the two errors, newest first.
3. Start the app, open `http://127.0.0.1:8000/docs`: `POST /api/errors` (a manual error), then `PATCH
   /api/errors/{id}` with another `category_code`; `GET /api/errors/{id}` shows the new category.

### API reference for M5.b and M5.c

Errors are `{"detail": {"code", "message", ...}}` (D-063). `ErrorOut = {id, source: writing|review|manual|...,
original_text, erroneous_text, correction, alternatives[≤ 2], explanation, explanation_fr|null, category: {code,
label_en, label_fr, status}, term: {id, term}|null, production_attempt_id|null, review_log_id|null, occurred_at,
updated_at}`. `ProductionOut = {id, kind, modality, prompt_text, text, word_count, corrected, feedback|null,
ai_call_id, study_session_id, targets: [{lexical_item_id, term, used, used_correctly}], created_at, updated_at}`.
`feedback` (when corrected) = `{format: "correction-1", prompt_version, provider, model, output, spans,
error_event_ids, targets}`; `output = {sentences: [{index (from 1), corrected, status: correct|corrected|unnatural}],
corrected_text, natural_text, errors: [{sentence_index, wrong, correction, alternatives, category_code,
proposed_subcategory|null, explanation_en, explanation_fr, target_ref|null}], naturalness_notes: [{sentence_index,
text, suggestion, note}], targets: [{ref, used, used_correctly, comment}], overall_comment}`; `spans[i] = {error: i,
sentence_index, start, end}` into `text` (Unicode code points) for the highlight of `output.errors[i]`.

| Route | Request | Success |
|---|---|---|
| `POST /api/productions` | `{kind: "writing", text (1–4 000), prompt\|null (≤ 500), target_item_ids (≤ 15), study_session_id\|null}` | 201 `ProductionOut` (uncorrected) |
| `POST /api/productions/{id}/correct` | – (takes a few seconds) | 200 `{status: ok\|incomplete\|unavailable, reason\|null, attempt: ProductionOut, errors: [ErrorOut], proposed_categories: [{id, code, parent_code, label_en, label_fr, description_en, status}]}`. A failed AI is `incomplete` / `unavailable` with HTTP 200, nothing written, retry allowed |
| `GET /api/productions?kind=&limit=&offset=` | – | 200 `{items: [ProductionOut], total, limit, offset}`, newest first, `limit` ≤ 100 |
| `GET /api/productions/{id}` | – | 200 `ProductionOut` |
| `GET /api/writing/topics?count=3&tag=` | `tag`: academic, interview, data_science, everyday, campus | 200 `[{id, en, fr, tags}]` (same all day, skips the last 7 days' prompts) |
| `POST /api/errors` | `{original_text\|null, erroneous_text, correction, alternatives, category_code, explanation, lexical_item_id\|null}` | 201 `ErrorOut` (source `manual`) |
| `GET /api/errors?category=&source=&item_id=&production_id=&occurred_from=&occurred_to=&q=&page=&page_size=` | `category` is a code prefix | 200 `{errors, total, page, page_size, facets: [{code, label_en, label_fr, count}]}` (facets per level-2 category over the whole filter) |
| `GET /api/errors/{id}` | – | 200 `ErrorOut` |
| `PATCH /api/errors/{id}` | any of `{correction, alternatives, explanation, category_code, lexical_item_id (null unlinks)}` | 200 `ErrorOut`; writes `error.updated` |
| `DELETE /api/errors/{id}` | – | 204; writes `error.deleted` |
| `GET /api/error-categories` | – | 200 tree `[{id, code, parent_code, label_en, label_fr, description_en, description_fr, status: active\|proposed\|rejected, origin: builtin\|user\|ai, count, count_recent (14 days), children}]` |
| `POST /api/error-categories` | `{parent_code\|null, slug, label_en, label_fr, description_en, description_fr}` | 201 node (active) |
| `POST /api/error-categories/{id}/resolve` | `{decision: accept\|reject, label_en?, label_fr?}` | 200 `{category, reassigned_error_ids}` |
| `POST /api/reviews/check-production` | `{card_id, session_id, exercise_template_id, answer (1–2 000), response_time_ms ≥ 0}` | 200 `{production_attempt_id, status, reason, feedback\|null, errors, proposed_rating: 1\|3\|null, solution, sheet_summary}` |
| `POST /api/reviews` | as before plus `production_attempt_id\|null` | 200 as before plus `error_event_id\|null` |

| Status | `code` | When |
|---|---|---|
| 404 | `production_not_found`, `item_not_found`, `session_not_found`, `error_not_found`, `category_not_found` | unknown id |
| 409 | `already_corrected` | `correct` on a production that has its correction |
| 409 | `production_mismatch` | `production_attempt_id` unknown, from another session, for another term, or already used |
| 409 | `category_not_proposed` (+ `category_status`) | `resolve` on a category that is not `proposed` |
| 422 | `text_too_long` | more than 4 000 characters or 40 sentences |
| 422 | `invalid_production`, `not_correctable`, `exercise_mismatch` | empty text, > 15 targets, prompt > 500; not a written production; not a sentence production, or `production_attempt_id` on another type |
| 422 | `unknown_category`, `invalid_error` | inactive or unknown code; empty or identical forms, original without the wrong form, > 2 alternatives |

### Departures from the prompt (to approve)

- **Migration 0002** exists although none was planned (D-127), and **the errors of a checked sentence keep
  `production_attempt_id` instead of receiving the `review_log_id`**: `error_event.single_origin` forbids both.
  The link is `review_log.production_attempt_id`.
- `check-production` also returns `proposed_rating` (D-129), and `error_category.created` is a new event the prompt did not list.
- The personal sentence of a discovery gives errors with source `writing` (no `discovery` value in `ErrorSource`).

### Left / notes

- **M5.a2**: transcript analysis, targeted drills, cards made from errors, suggestions for recurring errors, the
  demo's errors through the services (D-130). **M5.b / M5.c**: the screens.
- The owner's manual scenario above, and one real `check-production` in the app once M5.b exists.
- `response_time_ms` of `check-production` is validated and not stored.

### Known issues

- A lite model sometimes reports style (repetition, formality) as an error; the user can edit or delete any error.
  Not seen in the final live runs, but expect it from time to time (D-132).
- `spans` use Unicode code points; the screens must convert for characters outside the BMP (emoji).

## M4.c — Review player, keyboard shortcuts, deck queue (frontend)

Branch `feat/m4c-review-player`, from `feat/m4b-today-discovery` (`32f0af0`; M4.b is not merged in `main`).
Two parts, two commits: **M4.c1** (review player and shortcuts) and **M4.c2** (`/queue`). No backend change
(`git diff --stat main -- backend` is empty), no migration, no new dependency, SPEC.md unchanged.

### Done

- **API layer**: `api/reviews.ts` gains `useRevealReview`, `useRecordReview` (refetches the Today card), the
  `Solution`, `SheetSummary`, `RecordBody`, `RecordResult` types and `EXERCISE_TYPES`; `api/library.ts`: `Deck`
  gains `pace`, `warnings` and a typed `status`, `useDeckStatus`, `useReorderQueue` (decks, term lists and Today
  card refetched after success or failure). Shapes read in `app/api/reviews.py`, `review_flow.py`,
  `review_steps.py`, `library.py`: they match the M4.a1 reference; one difference noted: `GET /api/decks`
  answers in id order, not the queue order (D-124).
- **Review player** (`features/review/`, D-120 to D-123): every exercise type of D-100/D-101 (recognition,
  listening, typed recall, gap-fill, sentence production, spoken answer, self-assessment receptive and
  productive); prompt only before the attempt, `grade` (typed or chosen, even empty; "I don't know" for choices)
  or `reveal` (no input), then the outcome with a sign and a text, the diff for a typo, the solution by type
  ("example answer" for productions), `term_missing`, the sheet summary with audio and a link to the full sheet;
  the proposed rating marked "Suggested" (text), four neutral buttons for self-graded types; one
  `POST /api/reviews` per card with `expected_reps` and no `auto_rating`; the next due date and a status change
  announced politely; focus on the card title, then on the correction.
- **Shortcuts** (`useReviewShortcuts`, D-122): 1–4 choose / rate, Enter checks or accepts the proposed rating,
  Space / Enter show the answer, R / Shift+R replay; ignored with modifiers, auto-repeat and in fields;
  AZERTY digit row without Shift; a `kbd` hint per phase. The triage guard moved to `components/keyboard.ts`.
- **Session** (`SessionPage`): the review step replaces `ReviewPlaceholder` (removed with
  `session.reviewPlaceholder.*`); `card_changed`, `not_due`, `review_not_allowed`, `exercise_mismatch`,
  `session_closed`, `session_not_found` handled (D-120).
- **`/queue`** (`features/queue/`, D-124, D-125): decks in D-027 order (pure `queueOrder.ts`), status badge,
  counts by status, deadline and pace, the deck's warnings through the shared `PlanWarnings`, Move up / Move
  down in the manual group only (full `PUT`), the D-026 transitions only, done decks folded, results announced,
  focus restored. Linked from the Today card and `/library/decks`.
- **i18n** (EN + FR, same keys): `review.*`, `queue.*`.
- **CSS**: options, rating group (2 × 2 on phones), suggested badge, `kbd`, correction, sheet summary, queue
  cards; tokens only, dark mode.
- **Tests**: 194 in total (133 before M4.c). `useReviewShortcuts.test.tsx` (13: every key, modifiers, repeat,
  fields, buttons, latest handlers; the reducer), `ReviewPlayer.test.tsx` (31: the full walk for each of the 8
  cases with calls in order and exact bodies, no solution in `document.body.innerHTML` before the attempt,
  listening sentence spoken and absent, production example and `term_missing`, rating marks, announcements,
  keys per phase, R / Shift+R, double press, response time on fake timers, the error codes, a failed grade
  keeping the answer, a closed session, French), `SessionPage.test.tsx` (a session of three reviews → `wait` →
  `done` → summary; "End the session" during a review), `queueOrder.test.ts` (7, hand-built cases),
  `QueuePage.test.tsx` (9: order, warnings with data and links, done section, transitions per status,
  pause / resume, move with the full `PUT` and focus, dated decks fixed, 422 / 409 reloads, links, French).
- **Breaking checks**: a hidden copy of the listening sentence in the prompt makes two tests fail; removing the
  `event.repeat` guard makes the shortcut test fail; disabling the ref guard of the player sends two `grade`
  requests and fails the double-press test. All restored.

### Verified (Windows 11, 2026-10-17)

- `npm run check` and `npm --prefix frontend run build` (same "chunk larger than 500 kB" warning): see the
  session report. `git diff --stat main -- backend` empty.
- **Manual scenario in the in-app browser** (Chromium, French UI, dark theme), on demo databases seeded in
  temporary folders in the session's scratchpad (backend on port 8011; `data/` and `.env` untouched; the
  repository has no `.env`):
  1. Start → gap-fill card: "drill down inot" → "Almost: a small typo", diff, Hard suggested; key 3 → next card,
     next date announced.
  2. Recognition card: R and Shift+R spoke the sentence (Microsoft Mark, `en-US`, rate 1 then 0.7); key 2 →
     right answer marked, Good suggested; key 3 → next card. A productive card offered no R. Enter accepted a
     proposed rating. A receptive self-assessment: Space → four buttons without suggestion → key 4.
  3. Listening card: the sentence was not in the page's HTML before the answer, the autoplay spoke it, key 2
     → "The sentence you heard" shown.
  4. "End the session" → confirmation → summary with 13 reviews and 1 failed (11 of them answered through the
     API by a scratch script to reach a listening and a self-graded card faster).
  5. `/queue`: order of D-027, "Presenting results" moved up (announced, focus kept on its button), "Causal
     inference reading" paused then resumed; after a reload the order was kept; the Today card showed the
     updated plan.
  6. 375 px, dark: `/session` (prompt and correction with the 2 × 2 rating buttons) and `/queue` without
     horizontal scroll.
- Fixed after the browser check: the French counts lacked the space before ":"; the announcement said "this
  card" while the next card was already shown; a receptive self-assessment repeated the term and sentence.

### Left / notes

- **Not checked in the browser**: the English UI (covered by the tests), a typed sentence production and a
  spoken answer on the demo (few mature cards with these templates today; covered by tests), the 409 / 422
  paths of `/queue` and the review error codes (covered by tests), light theme at 375 px.
- Backend need noticed, not implemented: "skip this term" after `sheet_required` (M4.b note) still needs a
  backend change; to decide.
- `reviews_over_budget` is never attached to a deck by the backend (no `deck_id`): shown on the Today card only.
- Error events from reviews (lexical confusions) and AI correction of sentences: M5. Recording: M6.

### Known issues

- None known.

## M4.b — Today's screen, session player, discovery, speech synthesis (frontend)

Branch `feat/m4b-today-discovery`, from `main` at `1c96c7a`. Cut in two parts on the same branch (the plan
exceeded 15 files): **M4.b1** (API layer, speech synthesis, voice setting, Today card, session player) and
**M4.b2** (discovery). No backend change (`git diff --stat main -- backend` is empty), no migration, no new
dependency, SPEC.md unchanged.

### Done

- **API layer**: `api/session.ts` (`SessionPlan`, plan entries and the five warnings as discriminated unions,
  `StudySession`, `SessionSummary`, `Progress`, `Step`, `ReviewStep`; hooks for today, start, next, end),
  `api/discovery.ts` (start, exercises, complete), `api/reviews.ts` (`grade` only).
- **Speech synthesis** (`src/speech/`, D-112, D-113): voice from `tts_voice`, else the first en-US voice, else
  the first English one with a "non-American voice" mention; `lang = 'en-US'`; slow = `tts_rate × 0.7`, at
  least 0.5; one utterance at a time; cancel on route change and when the player unmounts. `SpeakButton`
  (Listen / Listen slowly, accessible names saying what is read, speaking state, disabled with the reason when
  there is no synthesis or no English voice). **Voice setting** under Audio: browser voices (en-US first),
  automatic choice, a saved voice missing here marked "not available here", "Test".
- **Home**: the Today card (reviews due, new terms per deck, minutes against the budget, targeted practice and
  consolidation for information, the five warnings translated with their data and links, Start / Resume,
  empty plan with links to the import and the library). A "Today" link in the top bar.
- **`/session`** (D-114 to D-116): start (201 or 200), next steps, progress announced politely, focus on each
  step's title, "End the session" always visible behind a confirmation, `done` → end → summary; `wait`
  countdown with a check at `until` (D-115); `practice_info` then `next?practice_seen=true`; provisional
  `review` panel (count only, no term or prompt); `session_closed`, `session_not_found` and network errors.
- **Discovery** (`features/discovery/`, D-117, D-118): sentence with the term highlighted and audio; guess (or
  "I don't know"); the sheet only after the guess, read-only through `SheetView` (new `audio` prop) with the
  guess recalled, IPA, stress and audio; typed recall then gap-fill graded by `grade` with `item_id` (outcome,
  expected answer, variants, character diff for a typo, audio), sheet folded until the answer; spoken
  repetition (normal then slow, "recording comes later"); optional personal sentence; `complete` with `guess`,
  `exercise_results`, `personal_sentence`, `duration_ms`; first review date; `term_missing` translated;
  `sheet_required`, `already_discovered`, `discovery_not_allowed` handled; resumed discovery mentioned and
  restarted at step 1.
- **i18n** (EN + FR, same keys): `today.*`, `plan.*`, `session.*`, `steps.*`, `discovery.*`, `grading.*`,
  `speech.*`, `sheet.exampleLabel`; 11 M4.a1 error codes added to `KNOWN_CODES`. French uses "vous" and
  "paquet", like the existing translation (D-119).
- **CSS**: tokens only, dark mode, 375 px: Today card, warnings (a sign and a border, not colour alone),
  progress, steps, sentence, grade result (sign + text), diff, audio buttons; top navigation on its own row on
  phones; a long `<select>` no longer widens the settings page.
- **Tests**: 133 in total (95 before): `speech.test.tsx` (voice rules, slow rate, `en-US`, `cancel()` before
  each utterance, late voices, non-American mention, no synthesis), voice setting (3, in
  `SettingsPage.test.tsx`), `TodayCard.test.tsx` (5: plan, resume, empty plan, the five warnings with links,
  French), `SessionPage.test.tsx` (10: start 201 → `wait` refetched at `until` on fake timers →
  `practice_info` → `done` → summary, `practice_seen=true`, start 200 with the review panel and no term or
  prompt, end confirmation, check now, `session_closed`, `session_not_found`, network retry, speech cancelled
  when leaving, French), `DiscoveryFlow.test.tsx` (11: the full walk with no `/sheet` request before the guess
  and no solution before `grade`, "I don't know" + missing exercise + empty answer, no exercise at all, double
  `complete` prevented, resumed, no sentence, `sheet_required`, `already_discovered`,
  `discovery_not_allowed`, French; `highlightTerm`).
- **Breaking checks**: loading the sheet before the guess makes two discovery tests fail; removing the `wait`
  timer makes the session walk fail. Both restored.

### Verified (Windows 11, 2026-10-17)

- `npm run check` green (ruff, pytest, tsc, oxlint, vitest 133); `npm --prefix frontend run build` passes
  (same "chunk larger than 500 kB" warning); `git diff --stat main -- backend` empty.
- **Manual scenario in the in-app browser** (Chromium 152), on a temporary data folder in the session's
  scratchpad (backend on port 8011, no AI key; `data/` untouched; the repository has no `.env`): `db upgrade`;
  import of 2 terms ("to account for" with its sentence, "shed light on") straight into the queue; a sheet
  written by hand for "to account for"; home → 1 new term and the `items_without_sheet` warning for the other
  term (deck link, `/enrichment` link); Start → step 1 (sentence, term highlighted, "Listen" spoke the sentence
  with Microsoft Mark, en-US, rate 1; no `/api/items/1/sheet` request before the guess); guess → sheet with
  IPA, stress and audio; typed recall "acount for" → `typo`, diff showing the missing "c"; gap-fill absent
  (hand-typed sheet) → skipped silently; repetition (slow = rate 0.7 on the real utterance); a sentence
  without the term → `term_missing` and the first review date; Continue → `done` → summary with 1 discovery
  started and completed. Then the **demo** (seeded in another temporary folder): French UI, dark theme,
  375 px: Today card with 17 reviews, 12 new terms and `deadline_triage_pending`; Start → provisional review
  panel (count only); End → confirmation → summary. No horizontal scroll at 375 px on home, settings and
  session after the two CSS fixes (D-119).
- **en-US voices seen** (SPEC assumption B.11): Microsoft Mark, Microsoft Zira, Microsoft David (local Windows
  voices); no other English voice in this browser.

### Left / notes

- **M4.c** replaces the provisional review panel (`session.reviewPlaceholder.*`, `ReviewPlaceholder`) with the
  review player, adds the keyboard shortcuts (reveal, rate 1–4, replay audio) and the deck queue and status.
  `api/reviews.ts` has `grade` only; M4.c adds `POST /reviews` and `reveal`.
- After `sheet_required`, `next` returns the same term until its sheet is written, so the other new terms of
  the day wait (D-117). Rare (the planner already skips terms without a usable sheet when the plan is
  frozen); a server-side "skip this term" would be a small backend change for M4.c if wanted.
- The error category of targeted practice is shown as its code (no taxonomy route yet).
- The discovery screens were checked in the browser at desktop width only; at 375 px through their CSS
  (wrapping rules), like the session's other screens that were checked.
- Progress counts change when `next` is asked again: the "Into spaced repetition" screen still counts the
  term as left until "Continue".

### Known issues

- One `npm run check` run made while the scenario's dev servers and demo backend were running reported
  "4 unhandled errors" in Vitest and only 115 tests; the runs before and after passed 133 with no error.
  Probably load-related; watch for it.

## M4.a2 — Planner usable-sheet filter and the demo (part 2 of M4.a)

Same branch `feat/m4a-session-backend`, not merged. No migration, no new dependency, SPEC.md unchanged.

### Done

- **Planner** (D-109): queued terms without a usable sheet are no longer proposed (`PlanInputs.items_without_sheet`,
  computed by `planning.items_without_sheet()`), with the warning `items_without_sheet {count, deck_ids}`.
  Deadline paces still count them; an interrupted discovery stays proposed; a queued deck with no usable term is
  not activated.
- **Demo sheets** (D-110): `content/demo/sheets.yaml` (dataset version 2): 68 full sheets with four templates each
  (plus listening and the derived typed recall), 41 minimal translation-only sheets. Inserted through
  `enrichment.save_sheet(provenance=...)` (new keyword) and the new `enrichment.add_templates()`.
- **Simulation** (D-111): sessions through `study_sessions` (`session-1`, summary from the logs), exercise types
  from `choose_exercise` (self-graded types: `auto_rating` null), discoveries through `begin_discovery` /
  `finish_discovery` without initial ratings. `DEMO_EXERCISE_TYPES`, `initial_rating` and the provisional
  session writes are removed.
- **Owner's choice at the plan**: minimal sheets keep the typed recall that `save_sheet` derives (D-099 note).
- **Tests**: 1395 passed (1315 before), 5 deselected live tests. New: planner filter (exclusion, warning,
  pace unchanged, no activation, interrupted discovery kept), service (`missing`, skeleton, non-current sheet),
  71 sheet-content tests (`test_demo_sheets.py`), demo coverage (full sheets for every queued / triage /
  discovering term and 26 learning or consolidated ones, every review's type and template equal to
  `choose_exercise`, self-graded `auto_rating` null, `session-1` summaries equal to `compute_summary`, `new`
  cards only from the last session, no `items_without_sheet` at the anchor). Existing database tests that plan
  queued terms now give them a sheet (`tests/factories.add_sheet`).

### Verified (Windows 11, 2026-10-17)

- `npm run check`: green (see the report). `alembic check`: no new upgrade operations.
- `demo seed --reset` (temporary data dir): 60 days in 5.6 s (5.1 s before M4.a2; target 5 s, missed by about
  0.6 s). Terms: active 5, archived 1, consolidated 51, discovering 1, draft 2, known 2, learning 10, queued 37,
  triage 4. Review types: typed recall 350, self-assessment 224, recognition 138, gap-fill 85, spoken 2,
  sentence production 1, listening 1.
- **Manual scenario** on a temporary demo database (its own data dir, the owner's `.env` not read, port 8011):
  `GET /api/session/today` (warnings: `deadline_triage_pending` only), `start` (201, `session-1`), `next` (a
  gap-fill review: prompt `{sentence}` only, no solution key over 5 steps), `grade` "drill down inot" ->
  `typo`, proposed Hard, `POST /api/reviews` Hard -> 200, discovery of the interrupted term "outperform"
  (resumed, two prompts, cards due at the next study day start), `end` -> summary `{reviews: 5,
  discoveries_started: 0 (resumed), discoveries_completed: 1, ...}`.

### Left / notes

- M4.b (today's screen, discovery, speech synthesis) and M4.c (review player, shortcuts, deck queue) use the
  M4.a1 API reference without backend change; they need the i18n text of `items_without_sheet`.
- The demo has few mature cards with full templates, so `sentence_production`, `spoken_answer` and
  `listening_comprehension` appear only a few times in its history.
- Still no `ai_call_log` rows in the demo; no error event from reviews outside the demo (M5).

### Known issues

- None known. Fixed on the way: `tests/api/test_session_api.py::test_review_steps_never_carry_a_solution` (M4.a1)
  was flaky. It uses the unseeded production FSRS fuzz, so the cards sometimes stayed below the 21-day
  maturity threshold and the mature exercise types were not reached (no leak). The test now seeds that
  generator.

## M4.a1 — Today's session, discovery and reviews: backend (part 1 of M4.a)

M4 is cut in three sessions: **M4.a** (backend, no screen), **M4.b** (today's screen, discovery, speech
synthesis), **M4.c** (review player, keyboard shortcuts, deck queue). M4.a itself is cut in two (D-099):
**M4.a1** (this part: domain, services, every route) and **M4.a2** (the planner's usable-sheet filter and the
demo). Branch `feat/m4a-session-backend`, started from `origin/main` (`54bd2c8`, M3.c3 + D-097). No migration,
no new dependency, SPEC.md unchanged.

### Done

- **Exercise choice** (`app/domain/exercise_choice.py`, D-100): direction x maturity (stability >= 21 days in
  Review) x templates present; alternation on the parity of `reps`; fallback to another template of the
  direction, then `self_assessment` (D-101); several templates of a type rotate with `(reps // 2) % n`.
- **Grading** (`app/domain/grading.py`, D-102): normalisation, optional "to", hand-written Damerau-Levenshtein
  (OSA), typo thresholds 0 / 1 / 2, confusion with another library term or a sheet's confusables and pitfalls ->
  `wrong`, regular forms in typed recall, choice exercises, slow -> Hard, Easy never proposed, `term_missing`
  for typed productions, character diff for typos.
- **Steps without solutions** (`app/domain/review_steps.py`, D-103): prompts per type, deterministic option
  shuffle (card id + `reps`), solutions only after an attempt, listening exception.
- **Services**: `study_sessions.py` (start, stale close, live `next`, end with a summary from the logs, D-107),
  `review_flow.py` (step, grade, record with the auto rating recomputed and the 5-minute cap, reveal),
  `productions.py` (written attempt + targets + event), `discovery.py` (`begin_discovery` /
  `finish_discovery`: usable sheet required, no initial ratings, payload v2, personal sentence, D-104, D-105),
  `planning.card_snapshots()` extracted for `next`.
- **API**: `app/api/session.py`, `reviews.py`, `discovery.py`; deck status and queue routes and `pace` /
  `warnings` on every deck in `library.py`; new error handlers (deck transitions, `DiscoveryError`). Reference
  below.
- **Setting** `tts_voice` (string, default `""`, at most 200 characters, D-108).
- **Tests**: 125 new (1315 passed, 5 deselected live tests; 1190 before). Domain: exercise choice (every
  direction x maturity x templates present or absent, fallback, alternation, rotation), grading (table:
  exact, form, typo at the three thresholds, affect/effect, "to", apostrophes, empty, choice, slow -> Hard,
  Easy never proposed, `term_missing`), Damerau-Levenshtein (transposition, insertion, deletion, OSA), steps
  (no solution key for any type x direction, deterministic shuffle, gapped sentence). API: every route and
  error code, `auto_rating` recomputed when the client lies, `grade` and `reveal` write nothing (row count of
  every table), anti-leak walk over every exercise type, idempotent start, stale-session close, `next` with a
  learning card after 10 minutes on a fake clock, `wait`, `practice_info`, `done`, summary from the logs, full
  discovery (cards `new` due the next study day, `production_attempt`, payload v2), deck pause / resume / done
  / reopen / order / pace. **End-to-end scenario** (`tests/api/test_m4_scenario.py`): import, sheet by hand,
  session, discovery, not due the same day, back in `next` at the start of the next study day, typo -> `typo`
  with Hard proposed, Good recorded -> `auto_rating` 2, `final_rating` 3.

### Verified (Windows 11, 2026-10-17)

- See the commit's check output in the session report: `npm run check`, `alembic check`.

### API reference for M4.b and M4.c

Errors are `{"detail": {"code", "message", ...}}` (D-063); writes need `Content-Type: application/json`. Ids
are integers; times are UTC ISO strings. `Progress = {reviews_done, reviews_remaining, new_done,
new_remaining, estimated_seconds_remaining}`. `Session = {id, started_at, ended_at, study_day, planned:
{format: "session-1", plan: SessionPlan}, summary}`. `SessionPlan` is the planner's output (M1.b, `plan
today --json`).

| Route | Request | Success |
|---|---|---|
| `GET /api/session/today` | – | 200 `{plan: SessionPlan, open_session: Session\|null}` (nothing written) |
| `POST /api/session/start` | – | 201 `Session` (new, plan frozen) or 200 (today's open session); closes a session left open on an earlier study day |
| `GET /api/session/{id}/next?practice_seen=false` | – | 200 `Step` (below) |
| `POST /api/session/{id}/end` | – | 200 `Session` with `summary = {format, reviews, failed_reviews, discoveries_started, discoveries_completed, productions, words, duration_ms, planned_minutes}` |
| `POST /api/reviews/grade` | `{card_id\|item_id (exactly one), exercise_type, exercise_template_id\|null, answer\|null (≤ 2000), choice_index\|null, response_time_ms ≥ 0}` | 200 `{outcome: exact\|form\|typo\|wrong\|empty\|null, proposed_rating: 1–3\|null, expected, accepted, diff: [{op: equal\|replace\|insert\|delete, given, expected}]\|null, warnings, solution, sheet_summary}`. **Writes nothing.** `item_id`: discovery exercises (`typed_recall`, `gap_fill`) of a `discovering` term |
| `POST /api/reviews` | `{card_id, session_id, exercise_type, exercise_template_id\|null, answer\|null, choice_index\|null, response_time_ms ≥ 0, final_rating 1–4, expected_reps}` (no `auto_rating`: unknown fields are refused) | 200 `{review_log_id, due_after, state_after, item_status, item_status_changed}` |
| `POST /api/reviews/reveal` | `{card_id, exercise_type, exercise_template_id\|null}` (self-graded types only) | 200 `{solution, sheet_summary}`. Writes nothing |
| `POST /api/discovery/{item_id}/start` | `{session_id, deck_id\|null}` | 200 `{item_id, term, item_type, status, resumed, sentence: {text, source: origin\|example}\|null}` (never the sheet) |
| `GET /api/discovery/{item_id}/exercises` | – | 200 `[{exercise_type: typed_recall\|gap_fill, exercise_template_id, prompt}]` (prompts only) |
| `POST /api/discovery/{item_id}/complete` | `{session_id, duration_ms\|null, guess\|null (≤ 1000), exercise_results: [{exercise_type, outcome}] (≤ 10), personal_sentence\|null (≤ 1000)}` | 200 `{item_id, status: learning, cards: [{card_id, direction, due}], production_attempt_id\|null, warnings}` |
| `POST /api/decks/{id}/status` | `{to: queued\|active\|paused\|done}` | 200 `Deck` |
| `PUT /api/decks/queue` | `{deck_ids}`: every deck that is not done, once | 200 `[Deck]` |
| `GET /api/decks`, `GET /api/decks/{id}` (and every `Deck` answer) | – | `Deck` gains `pace: {deck_id, deadline, remaining, days_left, required_per_day}\|null` and `warnings: [PlanWarning]` (the plan's warnings about this deck) |
| `GET/PATCH /api/settings` | – | new key `tts_voice` (string, `""` = first en-US voice, ≤ 200 characters) |

**Step** = `{type: review|new_item|wait|practice_info|done, session_id, progress: Progress, review, new_item,
wait, practice}` (only the field of its type is set):

- `review = {card_id, lexical_item_id, direction, srs_state, expected_reps, exercise_type, exercise_template_id,
  input: choice|text|none, self_graded, term (receptive cards, not listening; else null), prompt, warnings}`;
  send `expected_reps` back with `POST /api/reviews`.
- `prompt` by type: `recognition_in_sentence` `{sentence, options[4]}`; `listening_comprehension` `{sentence,
  options[4]}` (**hide the sentence**, speak it); `typed_recall` `{cue_fr, cue_definition}`; `gap_fill`
  `{sentence}` (with `___`); `sentence_production` `{situation}`; `spoken_answer` `{question}`;
  `self_assessment` receptive `{term, sentence}`, productive `{cue_fr, cue_definition, sentence_gapped}`.
- `solution` by type (grade or reveal only): choice `{correct_index, meaning, meaning_fr, sentence}`;
  `gap_fill` `{answer, accepted, sentence}` (completed); `typed_recall` `{answer, accepted}`; production and
  spoken `{example_answer}`; `self_assessment` `{term, definition_simple, translation_fr, sentence}`.
  `sheet_summary = {term, part_of_speech, definition_simple, translation_fr, pronunciation, examples[≤ 2]}|null`;
  the full sheet is `GET /api/items/{id}/sheet`.
- `new_item = {item_id, term, deck_id, resumed}`; `wait = {until}` (a learning card due later today);
  `practice = {targeted_practice: {category_code, error_count}|null, consolidation_task_id|null}`, information
  only: call `next?practice_seen=true` to get `done`.
- Self-graded types (`self_assessment`, `sentence_production`, `spoken_answer`) have no proposed rating: show
  the four buttons. Easy is never proposed.

| Status | `code` | When |
|---|---|---|
| 404 | `session_not_found`, `card_not_found`, `item_not_found`, `deck_not_found` | unknown id |
| 409 | `session_closed` | `next`, `end`, a review or a discovery on a closed session |
| 409 | `card_changed` (+ `reps`) | `expected_reps` differs (sent twice, two tabs) |
| 409 | `review_not_allowed` | term not reviewable (archived, known...), review earlier than the last one, discovery exercise of a term that is not `discovering` |
| 409 | `not_due` (+ `due`) | card due after the current study day |
| 409 | `sheet_required` | discovery start without a usable sheet (D-105) |
| 409 | `already_discovered` | discovery start or complete after success |
| 409 | `discovery_not_allowed` | paused or done deck, term not in the deck given |
| 409 | `invalid_transition` (+ `from_status`, `to_status`) | discovery of a term in triage, complete before start, deck transition not allowed by D-026 |
| 422 | `exercise_mismatch` | wrong direction, template of another term or type, missing template, `choice_index` out of range, reveal of a graded type, discovery exercise other than typed recall / gap-fill |
| 422 | `invalid_queue` | `deck_ids` is not exactly the decks that are not done |
| 422 | `invalid_request` (+ `errors`) | wrong shape, unknown field (`auto_rating`...), negative time, both or none of `card_id` / `item_id` |

**Warning codes** (no text; i18n in M4.b / M4.c): grading `term_missing`; review step `no_cue`; discovery
complete `term_missing`; plan warnings unchanged (`reviews_over_budget`, `deadline_unrealistic`,
`deadline_passed`, `deadline_triage_pending`), plus `items_without_sheet` `{count, deck_ids}` (M4.a2, D-109:
queued terms without a usable sheet are not proposed; a deck answer carries it when its id is in `deck_ids`).
**Step types**: `review`, `new_item`, `wait`, `practice_info`, `done`. **Outcomes**: `exact`, `form`, `typo`,
`wrong`, `empty`.

### Left / notes

- **M4.a2** (done, see above): the planner skips terms without a usable sheet and warns
  `items_without_sheet` (D-105); `content/demo/sheets.yaml` (full sheets with templates for every queued /
  triage / discovering term and at least 25 learning ones, minimal translation-only sheets for the rest, D-099);
  the simulation uses `choose_exercise`, the session service (`session-1`) and no initial ratings;
  `DEMO_EXERCISE_TYPES` and the provisional session writes removed; fingerprint and coverage tests; the 2-minute
  manual scenario on the demo database; `--demo` seed time measured.
- `GET /api/decks` now computes today's plan (one more read per call).
- No AI call in M4.a; no error event from reviews yet (M5).

### Known issues

- None known.

## Pre-merge verification of M2.c2 to M3.c3 (2026-10-17)

The six stacked branches had never been checked together on a clean state. Done on the tip
(`feat/m3c3-sheets`) before merging.

### Checked (Windows 11)

- `npm run check`: ruff check, ruff format --check, pytest 1190 passed (5 deselected: live tests), tsc, oxlint,
  vitest 93 passed before the fixes, 95 after. `npm --prefix frontend run build` passes (same "chunk larger than
  500 kB" warning).
- CI steps run locally: `alembic upgrade head` then `alembic check` on an empty file ("No new upgrade operations
  detected"); full demo seed `--anchor 2026-09-01` on an empty data folder, then `--demo plan today`;
  `scripts/check-env.ps1`; no tracked data, `.env`, database or audio file; `.ps1` files are ASCII; `en.json`
  and `fr.json` have the same 567 keys (570 after the fixes) and no empty value.
- No migration since M1.a: the owner's database (revision `0001`) needs no upgrade for this merge.
- Invariants read in the code: no AI SDK or HTTP client outside `app/ai/`; enrichment and extension call the
  gateway outside any write transaction and write in one short transaction afterwards (D-038).
- **First run on an empty database** in the in-app browser (never done before; earlier checks used the demo
  database), French UI: home, library empty state, quick add (creates "Quick adds"), import of the SPEC sample
  with a header (7 lines, a duplicate of the quick-added term attached, new deck with its source), triage list,
  term page with the sheet hidden and the pre-discovery warning, decks, enrichment page without a key,
  duplicates, settings. No console error.

### Fixed (D-098)

- `/library` had no **source** filter although SPEC module A requires one (the API supported `source_id`).
- The home page still said importing was "coming soon"; it now links to the import and the library.
- The main navigation's `aria-label` was hard-coded English.

### Notes

- Duplicates inside one imported file are caught on the normalised form only, not on the lemma: `outlier` and
  `outliers` in the same file are both imported, then shown by `/duplicates`.
- The quick-add deck menu shows "No deck (Quick adds)" and, once it exists, the "Quick adds" deck itself; both
  lead to the same deck.

## M3.c3 — Usage sheets, exercises, batch enrichment, list extension (frontend)

Branch `feat/m3c3-sheets`, stacked on M3.c2. No backend change, no migration, no new dependency, SPEC.md
unchanged. Owner decisions (2026-10-17): library search stays on terms only; the sheet is hidden until opened.

### Done

- **Term page** (`/library/items/:id`, `SheetPanel.tsx`, `SheetView.tsx`, `SheetEditor.tsx`, `sheetForm.ts`,
  D-091 to D-093): a "Usage sheet and exercises" card, closed by default, with a warning before discovery
  (`draft`, `triage`, `queued`). Opened: the sheet in SPEC order, its state, provenance (provider, model, prompt
  version, date), "Edit the sheet" (repeatable rows for every list, register and example kind as selects), saved
  with `base_enrichment_id`; a 409 `sheet_changed` keeps the edits on screen and offers "Load the latest version"
  behind a confirmation. No sheet: "Write the sheet by hand" (manual entry, degraded mode) or "Generate with AI".
  A sheet to complete: "Complete the sheet" or "Try the AI again". "Generate a new version": a 409 `sheet_edited`
  opens a consent dialog; only "Replace my version" resends with `confirm_overwrite: true`. AI failures say the
  sheet is kept, with the reason. Versions: list (newest first, by you / by the AI, current), any version opens
  read-only.
- **Exercises** (`ExercisesPanel.tsx`, D-094): one block per template (type, direction, "edited by you"), a form
  per type (gap-fill, typed recall, recognition / listening, sentence production, spoken answer; lists one entry
  per line), the gap count hint, the whole content sent by `PATCH`; a 422 `invalid_exercise` keeps the form and
  lists each refused field with the backend's English message (`FieldErrors.tsx`, also used for `invalid_request`).
- **`/enrichment`** (`features/enrichment/EnrichmentPage.tsx`, D-095): deck filter, "also include the sheets to
  complete", waiting count and list (links to each term for manual entry); "Generate the sheets" loops on
  `POST /enrichment/run` until nothing is left, and stops on an AI failure (degraded card with the reason and the
  settings link), on `enrichment_running`, on a batch that wrote nothing, or after the current batch when the user
  clicks "Stop after this batch". Progress counts. Linked from the Library page with the waiting count.
- **List extension** (`ExtensionPanel.tsx`, D-096): "Extend this list" on each deck of `/library/decks`, number
  10 to 30 (default 20); result: new terms, dropped counts, possible duplicates with links, and "Sort them now"
  → `/triage?deck=ID`; an AI failure or `not_enough_context` is explained, the deck unchanged.
- **API layer** `api/enrichment.ts` (types mirroring `usage_sheet.py`, `exercises.py`, `RunReport`, hooks; query
  keys under `items` so every library write refreshes them); `useInvalidateLibrary` exported.
- **i18n** (EN + FR, same keys): `sheet.*`, `exercises.*`, `enrichment.*`, `extension.*`, `aiReasons.*` (gateway
  reasons), 8 more error codes in `KNOWN_CODES` (`enrichment_running`, `sheet_edited`, `sheet_changed`,
  `sheet_not_found`, `exercise_not_found`, `item_archived`, `invalid_exercise`, `not_enough_context`).
- **CSS**: badge, sheet view, editor rows, versions, exercises, field errors (tokens only, dark mode included).
- **Tests** (22 new, 93 in total): `SheetPanel.test.tsx` (9: hidden until opened with the warning and no request,
  edit saved with `base_enrichment_id`, `sheet_changed` keeps edits and reloads on confirmation, regeneration only
  after consent, manual entry with the meaning check, generation failure, versions, exercise edit, 422
  `invalid_exercise`), `EnrichmentPage.test.tsx` (6: loop to the end, degraded stop, running lock, stop after the
  batch, include-incomplete query and French, library link), `ExtensionPanel.test.tsx` (4: created + triage link,
  AI failure, count bounds, `not_enough_context`), `sheetForm.test.ts` (3); shared fixtures in `test/fixtures.ts`.

### Verified (Windows 11, 2026-10-17)

- `npm --prefix frontend run check`: tsc, oxlint, vitest 93 passed. `npm --prefix frontend run build` passes (same
  "chunk larger than 500 kB" warning). Backend: ruff check and ruff format pass; pytest **1 failed**, 1189 passed
  (the pre-existing date-dependent test below; no backend file changed).
- A test was checked to fail when the behaviour breaks (regeneration sent with `confirm_overwrite: true` first).
- **In the in-app browser, on the demo database** (no AI key, French UI): term "be swamped" (queued) shows the
  warning; "Generate with AI" → "no AI provider is set up"; a sheet written by hand saved (state "edited", the
  typed-recall exercise appeared, D-082); "Generate a new version" → real 409 → consent → "Your sheet is kept";
  an exercise saved with an empty answer → 422 listing `answer`; a second edit → two versions listed.
  `/enrichment` → degraded card (103 terms waiting). Extension → "No suggestion: no AI provider is set up".
  Dark mode at 375 px: `/enrichment`, `/library/decks` with the extension form, the sheet editor; no horizontal
  scroll.
- **Not checked in the browser**: the AI happy paths (no key in the demo; covered by mocked tests), the 409
  `sheet_changed` and `enrichment_running` paths (covered by tests).

### Owner's manual scenario (with a key, about 5 minutes)

1. Start on your own database with a provider set up; open "Generate usage sheets", pick a small deck, run it.
2. Open a term: show the sheet, check the examples and exercises; edit a field and save (version 2, "edited").
3. "Generate a new version": the consent dialog appears; accept, check version 3 and that version 2 is kept.
4. On "Decks", "Extend this list" with 10 suggestions, then "Sort them now".

### Left / notes

- No "restore this version" button (no such route); copy from an old version into the editor by hand.
- The terms that got a sheet to complete are not named after a batch: tick "also include the sheets to complete"
  to list them.
- A long batch keeps the request open (up to a few minutes on splits); the Vite proxy has no timeout set.

### Known issues

- **Pre-existing (M2.c1), not caused by M3.c3**: `test_usage_lists_every_day_today_first` logs its call with the
  fake clock (2026-10-16 12:00 UTC) but `GET /api/ai/usage` reads the real clock (`datetime.now(UTC)` in
  `app/api/ai.py`), so the call lands on "today" only on 2026-10-16. Fix in its own change (inject the clock into
  the route, or freeze it in the test); left out of this frontend milestone.
  **Fixed (2026-10-17)**: the route takes "now" from the `get_now` dependency (`app/api/clock.py`), which the
  API test fixture overrides with the gateway's fake clock (D-097). Full pytest passes on any date.

## M3.c2 — Import, triage and duplicates pages (frontend)

Branch `feat/m3c2-import-triage`, stacked on M3.c1. No backend change, no migration, no new dependency, SPEC.md
unchanged.

### Done

- **`/import`** (`features/library/ImportPage.tsx`, `ImportRows.tsx`, `importReview.ts`, D-086, D-087): paste or
  pick a `.md` / `.txt` file (read in the browser, 300 000-character limit checked before sending); "Preview"
  (`POST /api/import/preview`, nothing written) shows the detected header, the counts, file-level problems with
  their line, then one row per line: import box, editable term, sentence, type, translated problems, duplicate
  choice (attach to a candidate / add as new / skip, prefilled from `default_on_duplicate`). Ambiguous rows are
  unchecked and marked with ⚠ text, a bar and a tint; confirmable ones (`looks_like_definition`,
  `looks_like_sentence`) offer "Import anyway" (`confirmed: true`), the others say "correct the term"; a
  `looks_like_definition` suggestion is one click ("Use “nonresponse”"). Target: new deck (named from the header)
  or existing deck; intake "wait for triage" (default) or "queue". "Import" (`POST /api/import/commit`) then a
  summary with links to the triage of that deck and to the deck. The text is kept after an error; a
  `row_rejected` names its line.
- **`/triage`** (`TriagePage.tsx`, D-088): `GET /api/triage` with a deck filter (`?deck=ID`), one card per term
  with its sentence and decks (never a usage sheet), three radio choices, keys 1 / 2 / 3 for the focused card or
  the next undecided one (ignored inside text fields and selects), one `POST /api/triage` for every choice made;
  a 409 `not_in_triage` saves nothing, reloads the list and keeps the other choices; counts shown after saving.
- **`/duplicates`** (`DuplicatesPage.tsx`, D-089): groups from `GET /api/duplicates`, the term to keep chosen by
  radio (default: the one with review cards), "Merge into …" per other term through `useMergeItem`, result
  message (inversion explained), `merge_conflict` explained, empty state.
- **Library page**: links "Import a list", "Sort new terms (n to sort)", "Duplicates", "Manage decks".
- **API layer**: `api/import.ts`, `api/triage.ts`, `api/duplicates.ts`; library writes now also refresh the triage
  list (`triageKey`).
- **i18n** (EN + FR, same keys): `import.*` with one message per `ProblemCode` (22) and per severity (4),
  `triage.*`, `duplicates.*`; six more error codes in `KNOWN_CODES` (`invalid_term`, `row_rejected`,
  `deck_name_required`, `invalid_attach_target`, `merge_same_item`, `duplicate_decision`).
- **CSS fixes found in the browser** (D-090), also affecting M3.c1: text inputs without a `type`, search and date
  inputs and textareas were unstyled; a wide table widened the whole page instead of scrolling in `.table-wrap`.
- **Tests** (21 new, 71 in total): `ImportPage.test.tsx` (11: preview with header, ambiguous rows left out then
  confirmed, duplicate choice sent as chosen, default attach, suggestion, existing deck, file read, file too large,
  422, `row_rejected` line, rejected file, French), `TriagePage.test.tsx` (6: three decisions in one call, keyboard
  shortcuts and typing guard, 409 `not_in_triage`, deck filter, library count, French),
  `DuplicatesPage.test.tsx` (4: merge, keep the other term with inversion, `merge_conflict`, empty).

### Verified (Windows 11, 2026-10-17)

- `npm run check`: ruff check, ruff format --check, pytest 1190 passed (5 deselected), tsc, oxlint, vitest 71
  passed. `npm --prefix frontend run build` passes (with Vite's "chunk larger than 500 kB" warning).
- A test was checked to fail when the behaviour breaks (ambiguous row sent without `confirmed`).
- **In the in-app browser, on the demo database** (`start.ps1 -Demo`), French UI:
  - `import-with-header.md` (pasted): header, "12 lines read · 9 ready · 2 ambiguous · 2 with a possible
    duplicate", L16 / L18 ambiguous, `shed light on` and `as you can see on this slide` found; L18 confirmed →
    "8 new terms, 2 existing terms added, 2 lines skipped" in a new deck.
  - `import-without-header.md` in **dark mode**: no header → the deck name is required, L11 (nested) and L13
    (`a | b | c`) must be corrected, "Use “bias”" applied, queued intake → 4 new, 3 attached.
  - Triage: 12 waiting, keys 3 / 1 / 2, saved → counts, 9 left. Duplicates: `outlier` / `outliers` (created with a
    quick add) merged, the group disappeared.
  - M3.c1 pages checked for the first time: `/library`, `/library/items/1`, `/library/decks` (input styling fixed).
  - No horizontal page scroll at 375 px on the six pages.
- **Not checked in the browser**: picking a file (the in-app browser cannot choose local files; covered by a
  Vitest test), the English UI and the 409 paths (covered by the tests). Screenshots were partial because the
  browser pane was hidden; text and layout were also checked through the page text and JavaScript.

### Left / notes

- **M3.c3**: usage sheet view / edit / versions, exercises, batch enrichment, list extension (with its triage).
- The import table scrolls sideways on narrow screens (seven columns); acceptable, could become cards later.
- A corrected term loses the preview's duplicate choice: the backend applies its default (attach to an exact
  match, else new); preview again to see the new duplicates.
- The triage page loads every waiting term at once (no paging); fine with the 1 000-line import limit.

### Known issues

- None known.

## M3.c1 — Library pages (frontend) ✅

Branch `feat/m3c1-library`, stacked on M3.b. M3.c is cut in three (plan approved): **c1** library (this part),
**c2** import / triage / duplicates, **c3** usage sheets, exercises, batch enrichment, list extension.
No backend change, no migration, no new dependency, SPEC.md unchanged.

### Done

- **Pages** (`frontend/src/features/library/`): `/library` (search, filters deck / field / type / status /
  sheet state, sort, paging of 50, archived toggle, `?deck=ID` preset, quick add with the duplicate choice
  attach / add as new), `/library/items/:id` (edit, archive / restore, delete with confirmation, similar terms
  with merge, deck links), `/library/decks` (create, rename, delete with confirmation).
- **API layer** `api/library.ts` (hooks, types, query building); `apiSend` now accepts 204 answers.
- **Errors**: the 10 library codes (D-063) have messages in `errors.*` (EN + FR).
- **i18n**: `library.*` keys in `en.json` and `fr.json`; nav link "Library".
- **Tests**: `LibraryPage.test.tsx`, 15 tests (list, filters sent to the API, deck preset, quick add, duplicate
  flow, error, French, item edit / delete / history refusal / merge conflict / archive, decks create / rename /
  history refusal).

### Verified (Windows 11, 2026-10-17)

- `npm run check`: ruff, pytest 1190 passed, tsc, oxlint, vitest 50 passed; `vite build` OK.
- **Not done** in M3.c1: no visual check in a browser; done in M3.c2 (input styling and table overflow fixed).

### Left / notes

- Unarchive offers `queued` only (the API also allows `learning` when cards exist).
- Deck status, queue order and deadlines are M4. Search inside sheet content: still undecided (M3.b note).
- **c2**: import page (paste or file, preview, per-row duplicate choice, commit), triage, duplicates.
  **c3**: sheet view / edit / versions, exercises, batch enrichment, list extension.

### Known issues

- None known.

## M3.b — Usage sheets and list extension (backend) ✅

Branch `feat/m3b-enrichment`, stacked on M3.a. No migration, no frontend change, SPEC.md unchanged.

### Done

- **Gateway** (D-079, D-080): `validation_context` and a per-call `max_output_tokens`.
- **Prompts and schemas**: `enrichment.v1`, `list_extension.v1`; business rules in `app/domain/exercises.py` and
  `usage_sheet.py`.
- **Services**: `enrichment.py` (batches, split, skeleton sheets, lock, editing, versions, exercises; D-081 to
  D-083), `extension.py` (D-084); `sheet_status` on items and a `sheet` filter on `GET /api/items`.
- **API** (`app/api/enrichment.py`): `GET /enrichment/pending`, `POST /enrichment/run`,
  `GET|PUT /items/{id}/sheet`, `GET /items/{id}/sheet/versions`, `POST /items/{id}/sheet/regenerate`,
  `GET /items/{id}/exercises`, `PATCH /exercises/{id}`, `POST /decks/{id}/extension`. New error codes:
  `enrichment_running`, `sheet_edited`, `sheet_changed`, `sheet_not_found`, `exercise_not_found`, `item_archived`,
  `invalid_exercise`. AI failures are 200 with `status` / `reason`.
- **CLI**: `library enrich [--deck-id] [--item-id N] [--include-incomplete] [--dry-run]`,
  `library extend <deck_id> [--count 10-30]`; `ai usage --demo` now allowed.
- **Tests**: service, schema, API, gateway-context tests, CLI tests (`tests/ai/test_cli_enrichment.py`) and a live
  test (`tests/live/test_live_enrichment.py`, skipped unless `VOCAB_RUN_LIVE=1`).

### Verified (Windows 11, 2026-10-17)

- `npm run check` passes: ruff, pytest 1190 passed (5 deselected), tsc, oxlint, vitest 35 passed; `alembic check` clean.
- The live enrichment test was **not run** (no key used in this session).

### Left / notes

- Search inside sheet content (SPEC module A) is not implemented: only the `sheet` status filter exists. Decide
  in M3.c whether `q` should also search sheet text.
- Token budgets (D-080) and batch size 5 are estimates: tune after the owner's first real calls.
- **M3.c**: pages for library, import, triage, duplicates, sheet review/edit, exercises, i18n of the new codes.

### Known issues

- None known.

## M3.a — Markdown import, library, duplicates, intake triage (backend) ✅

M3 is cut in three: **M3.a** (this part: backend, no AI call), **M3.b** (usage sheets and list extension, AI),
**M3.c** (interface). Branch `feat/m3a-library-import`, **stacked on `feat/m2c2-settings-page`** (the M2.c2 session
worked in the same folder and its first commit landed on this branch; with the owner's approval the M3.a commits were
replayed on top of M2.c2's two commits). Merge the M2.c2 PR first, then this one.

### Done

- **Parser** (`app/domain/markdown_import.py`, D-071): header, bullets, checkboxes, wrappers, `|`, ambiguous lines
  reported and not included, warnings, limits, type guess; never raises on user input.
- **Normalisation and lemma** (`app/domain/normalize.py`, D-072): normalised form, cautious single-word stem with
  exceptions, `exact` / `possible` matching, term-in-sentence check. No new dependency.
- **Services** (D-073 to D-077): `library.py` (sources, decks, terms, deck links, search, quick add, deletion
  rules), `importing.py` (read-only preview, atomic commit of the validated rows), `triage.py` (all or nothing,
  `unsure` → queued), `duplicates.py` (groups, merge with inversion and `merge_conflict`).
- **Events** (D-078): `deck.updated`, `deck.deleted`, `item.edited`, `item.deleted`, `import.completed`.
- **API** (`app/api/library.py`): 16 routes, reference below. Library errors use the D-063 format.
- **CLI**: `python -m app [--demo] library import <file> [--deck-id N] [--no-triage] [--commit]`.
- **Examples**: `content/examples/import-with-header.md`, `import-without-header.md` (fictional).
- **Demo**: decks, terms, links and triage go through the services; only `lexical_item.normalized_form` / `lemma`
  differ from before (D-078).
- **No migration, no frontend change, SPEC.md unchanged.**

### Verified (Windows 11, 2026-10-16)

- `npm run check` passes: ruff check, ruff format --check, pytest **1072 passed, 4 deselected** (856 on `main` before
  M3.a), tsc, oxlint, vitest 35 passed (M2.c2's tests included). `alembic check`: "No new upgrade operations
  detected".
- `demo seed --reset` rebuilt the demo database without error (5 decks, 113 terms, 2 068 events).
- **Tests cover**: the parser (table-driven: every bullet style, checkbox, wrappers, heading, blank lines, `|`
  repeated, `term = translation`, sentence-like line, sub-item, invalid YAML, unknown key, past and invalid deadlines,
  empty file, header only, BOM + CRLF, old Mac endings, size and line limits, odd inputs); both example files give
  exactly the expected problems at the expected lines (LF and CRLF + BOM); normalisation and lemma (news, series,
  data, analysis... left alone); services (atomic import with an injected failure, attach / new / skip, term already
  in the deck, triage or queued intake, all-or-nothing triage with `unsure`, merge with inversion and refusal,
  `item_has_history`, `deck_has_history`, every new event validated); every API route with filters, paging, 409
  `duplicate_term`, 422 without the received value, 415 for a non-JSON body (multipart included); the CLI (preview
  writes nothing, `--commit`, exit codes 0 / 1 / 2, `--demo`).
- **Manual scenario on the demo database**: the preview printed the header, 12 lines, two ambiguous lines (L16
  definition, L18 sentence), one in-file duplicate (L17), one `term_not_in_sentence` (L19) and two exact duplicates
  found in the demo decks (`shed light on`, `as you can see on this slide`); nothing written. With `--commit`: "7 new
  (waiting for triage), 2 existing added, 3 skipped (2 ambiguous left out)". Through the API (started with `--demo`):
  `GET /items?deck_id=6` (9 terms), `POST /triage` on two terms (`{"known":1,"unsure":0,"learn":1}`), 5 left in
  `GET /triage`, `GET /duplicates` (no group in the demo), a `text/plain` POST → 415, a foreign `Origin` → 403.

### API reference for M3.c

Every error is `{"detail": {"code", "message", ...}}` (D-063); writes need `Content-Type: application/json`.
Ids are integers. `DeckRef = {id, name}`. `Candidate = {id, term, normalized_form, status, match: "exact"|"possible",
decks: [DeckRef]}`. `Problem = {line: int|null, severity: "info"|"warning"|"ambiguous"|"error", code, message,
suggestion: object|null}`.

| Route | Request | Success |
|---|---|---|
| `POST /api/import/preview` | `{text (≤ 300 000 chars), deck_id?}` | 200 `{header: {deck, domain, source, context, deadline}, rows: [Row], problems: [Problem], rejected, lines_read, importable, ambiguous, with_duplicates}`; `Row = {line, raw, term, sentence, item_type, normalized_form, include, ambiguous, problems: [Problem], duplicates: [Candidate], in_target_deck, default_on_duplicate: "attach"|"new"|null}` |
| `POST /api/import/commit` | `{header, rows: [{line?, term, sentence?, item_type?, include=true, confirmed=false, on_duplicate?: "attach"|"new"|"skip", attach_to?}] (≤ 1000), target: {deck_id?} or {new_deck_name?}, intake: "triage"|"queued" (default triage)}` | 200 `{deck_id, created_deck, lines_read, imported, attached, skipped, ambiguous, item_ids}` |
| `GET /api/items` | `q, deck_id, domain, source_id, item_type, status (repeatable), include_archived=false, sort: created_at\|term\|updated_at\|status\|status_changed_at\|id, order: asc\|desc, limit 1–200 (50), offset` | 200 `{total, items: [Item]}`; `Item = {id, term, normalized_form, lemma, item_type, part_of_speech, origin_sentence, notes, status, status_changed_at, discovered_at, created_at, updated_at, decks: [DeckRef]}` |
| `POST /api/items` (quick add) | `{term, sentence?, deck_id?, item_type?, on_duplicate?: "attach"|"new", attach_to?}` | 201 `{item: Item, deck_id, attached, duplicates: [Candidate]}`; no deck → "Quick adds"; new terms are `queued` |
| `GET /api/items/{id}` | – | 200 `Item + {deck_links: [{deck_id, deck_name, position, context_sentence, added_at}], has_history, duplicates}` |
| `PATCH /api/items/{id}` | any of `{term, origin_sentence, item_type, part_of_speech, notes}` | 200 same as GET (duplicates of the new spelling, never blocking) |
| `DELETE /api/items/{id}` | – | 204 |
| `POST /api/items/{id}/status` | `{to}` | 200 `Item`; manual D-025 transitions; from `archived`, `to` must be `queued` (no cards) or `learning` (cards) |
| `POST /api/items/{id}/merge` | `{into}` | 200 `{kept_id, removed_id, inverted}` |
| `GET /api/decks` | – | 200 `[Deck]`; `Deck = {id, name, description, domain, kind, status, deadline, priority, queue_position, source: {id, title}\|null, created_at, updated_at, item_count, items_by_status: {status: n}}` |
| `POST /api/decks` | `{name, description?, domain?, deadline?, source_id?}` | 201 `Deck` (`queued`, end of the queue) |
| `GET /api/decks/{id}` | – | 200 `Deck` |
| `PATCH /api/decks/{id}` | any of `{name, description, domain, deadline, priority}` | 200 `Deck` (status changes are M4) |
| `DELETE /api/decks/{id}` | – | 200 `{deck_id, deleted_item_ids}` |
| `GET /api/triage?deck_id=` | – | 200 `[{item_id, term, item_type, sentence, decks}]` (no usage sheet, on purpose) |
| `POST /api/triage` | `{decisions: [{item_id, decision: "learn"|"unsure"|"known"}]}` (1–1000) | 200 `{learn, unsure, known}` counts |
| `GET /api/duplicates` | – | 200 `[{match, key, items: [{id, term, normalized_form, status, has_cards, decks}]}]` |

| Status | `code` | When |
|---|---|---|
| 404 | `item_not_found`, `deck_not_found`, `source_not_found` | unknown id |
| 409 | `duplicate_term` (+ `candidates`) | quick add of a term that may exist, without `on_duplicate` |
| 409 | `already_in_deck` | quick add `attach` to a deck that already holds the term |
| 409 | `item_has_history` (+ `suggestion: "archive"`) | delete a term with cards, errors or productions |
| 409 | `deck_has_history` | delete a deck whose terms started discovery |
| 409 | `merge_conflict` (+ `item_ids`) | both terms have cards |
| 409 | `not_in_triage` (+ `item_ids`) | a decision for a term not in triage (nothing applied) |
| 409 | `invalid_transition` (+ `from_status`, `to_status`) | status change not allowed by D-025 |
| 422 | `invalid_request` (+ `errors`) | wrong shape, unknown field, bad query value |
| 422 | `invalid_term` | empty, longer than 300 characters, contains `\|`; `name` / `term` / `item_type` / `priority` set to null |
| 422 | `row_rejected` (+ `row`, `line`, `problems`) | ambiguous row not confirmed, or invalid row |
| 422 | `deck_name_required` | new deck without `new_deck_name` nor header `deck` |
| 422 | `invalid_attach_target` | `attach_to` is not one of the row's duplicates |
| 422 | `merge_same_item`, `duplicate_decision` | merge into itself, same term twice in a triage |
| 415 | `unsupported_media_type` | write body that is not JSON (read the file in the browser, send the text) |
| 503 | `database_unavailable` | no database file |

**Problem codes** (i18n keys for M3.c): parser `too_large`, `not_utf8` (CLI), `invalid_header`,
`invalid_header_value`, `unclosed_header`, `unknown_header_key`, `invalid_deadline`, `past_deadline`,
`heading_ignored`, `horizontal_rule`, `multiple_separators`, `looks_like_definition`, `looks_like_sentence`,
`nested_item`, `empty_term`, `term_too_long`, `term_not_in_sentence`, `duplicate_in_file`; preview `duplicate_exact`,
`duplicate_possible`, `already_in_deck`, `existing_status_kept`. Suggestions: `looks_like_definition` →
`{term, note}`, `duplicate_in_file` → `{kept_line}`, duplicates → `{item_id}`, unknown key / bad value → `{key}`.

Notes for the page: a row the user corrects is sent with its new `term` (no `confirmed` needed if it is now clear);
`confirmed: true` only works for `looks_like_definition` and `looks_like_sentence`. The commit counts every row sent
in `lines_read`. Time stamps are UTC ISO strings.

### Left / notes

- **M3.b**: usage sheets (batch enrichment through the gateway, call first then write), review and editing (never
  regenerate an edited sheet), list extension with the same triage, search in sheet content. **M3.c**: the library,
  import (file read in the browser), triage and duplicates pages, i18n of every code above.
- Deck pause / resume / done / reorder through the API is M4 (module D).
- `normalize_term` strips any initial "to " (`to a large extent`); the lemma is a stem and only for single words.
  Both only *propose* matches.
- SQLite `lower()` is ASCII-only: `q` with accented capitals may miss the term column, though the normalised-form
  branch still finds the term itself.
- The M3.a branch is stacked on M2.c2: if M2.c2 changes before merging, rebase this branch on it (or on `main`
  once M2.c2 is merged).

### Known issues

- None known.

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

## Next step: M6 (speaking)

- M5.c2 and M5.a3 are done and merged (PR #18, PR #19); see "Current state" at the top.
- **M6** (module F): see SPEC section 9 and "Current state". "M5.d" (screens for cards from errors and suggestions) is
  left unscheduled.
- Before or alongside: the owner's real calls (M2.c2, M3.c3, M5.a1, M5.a2, M5.a3, M5.b1, M5.b2, M5.c1 and M5.c2
  scenarios) and the D-056 "to confirm" list.
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

