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

## D-022 — SRS interface, FSRS adapter and fuzzing (M1.b, 2026-10-16)

- **Version**: `fsrs` **6.3.2**, the latest on PyPI (`python -m pip index versions fsrs` via `uvx pip`,
  2026-10-16), declared `fsrs>=6.3.2,<7`. The wheel source was read before writing the adapter.
- **Interface** (`app/domain/srs.py`):
  - `SrsEngine` (Protocol) with `initial_state`, `review` and `retrievability`;
  - `SrsCardState`, a library-free dataclass (state, due, step, stability, difficulty, last review, opaque
    `payload`);
  - `EngineFactory = Callable[[retention], SrsEngine]`.
  Services never see an `fsrs` type; a fake engine in the tests proves they do not depend on FSRS.
- **Adapter** (`app/domain/fsrs_engine.py`, the only module that imports `fsrs`):
  - our `new` is Learning, step 0;
  - `srs_payload` stores `Card.to_dict()` and is the restore source (exact round trip); columns mirror it;
  - `srs_algorithm` = `fsrs-6.3.2` on the card and in `review_log`;
  - it stays in `domain/`: pure computation that never reads the clock (`card_id` and `due` are always
    passed; instants are normalised to `datetime.UTC`, because `review_card` refuses any other `tzinfo`).
- **Learning steps**: the library defaults, written out (1 min, 10 min; relearning 10 min). A new card rated
  Good goes to step 1, due in 10 min; Again stays at step 0, due in 1 min. The milestone text said "first
  learning step" for Good; the tests check the real behaviour (approved with the plan).
- **Target retention**: read from the `target_retention` setting at every review. Not retroactive: due dates
  already set are not recomputed.
- **Fuzzing**: on in production. fsrs draws from the module-global `random.random`, which cannot be seeded
  without touching global state. So the adapter builds the scheduler with `enable_fuzzing=False` and applies
  the same fuzz ranges itself with an injected `random.Random` (uniform whole-day draw within the library's
  bounds). Tests pass `fuzz=False`; M1.c will pass `Random(seed)` for a reproducible 60-day simulation.
- **Note**: fsrs computes retrievability from whole elapsed days.

## D-023 — Service layer (M1.b)

- **Decision**: database operations live in `app/services/` (reviews, items, discovery, decks, durations,
  planning).
  - They take a `Session`, work in the caller's transaction and never commit (like `record_event`, D-017).
  - Entry points (the CLI now, the API from M3) commit or roll back.
  - `discovery.py` is separate from `items.py` to avoid an import cycle (a review re-checks the item status;
    discovery records reviews).
- **Why**: `domain/` stays pure and unit-tested; one transaction per user action keeps rows and events
  consistent.

## D-024 — Repetitions and lapses (M1.b)

- **Decision**:
  - `reps` +1 on every review;
  - `lapses` +1 only for Again on a card in Review state: failing a learning or relearning step is not a
    lapse;
  - `review_log` gets the full before/after snapshot, with `elapsed_days` and `scheduled_days` in fractional
    days.
- **Refusals** (`ReviewNotAllowed`): a review earlier than the card's last review (the same instant is
  accepted); a card whose item is not `learning`, `consolidated` or `active` (this covers `archived` and
  `known`).
- **Why**: the usual SRS meaning of a lapse (forgetting a graduated card), so M9 lapse statistics compare
  with other tools.

## D-025 — Item status rules (M1.b)

- **Decision**: an explicit table in `app/domain/item_status.py` maps every allowed transition to the only
  operation allowed to perform it (manual, start discovery, complete discovery, automatic, mark active,
  unarchive). Anything else raises `InvalidItemTransition`. Every change writes `item.status_changed`.

  | From | To |
  |---|---|
  | draft | triage, queued, known, archived |
  | triage | queued, known, archived |
  | queued | discovering (start discovery), triage, known, archived |
  | discovering | learning (complete discovery only), archived |
  | learning | consolidated (automatic), active (module G), archived |
  | consolidated | learning (automatic), active (module G), archived |
  | active | archived |
  | known | queued, archived |
  | archived | learning if the item has cards, else queued (unarchive) |

- **Consolidated** ⇔ the productive card's stability ≥ `consolidation_min_stability_days` (existing
  setting, default 7, also used by module G). Checked after every review; `active` is never downgraded.
- **Unarchive**: back to `learning` when the item has cards (then the consolidation check runs), else
  `queued`.
- **Discovery**:
  - `start_discovery(item, via_deck)` refuses a paused or done deck and a deck the item is not in, and turns
    a queued deck active;
  - `complete_discovery` creates both cards (refused if one exists) and logs a new `card.created` event per
    card;
  - without initial ratings the cards stay `new`, due at the start of the next study day; with them, the
    first reviews are recorded at once;
  - `discovery.completed` keeps the measured `duration_ms`.

## D-026 — Deck statuses: pause and done (M1.b)

- **Decision**:
  - `queued → active | paused | done`, `active → paused | done`, `paused → active | done`, `done → active`
    (reopen);
  - `paused` and `done` stop new terms only: cards already created are still reviewed;
  - `activated_at` keeps the first activation; `completed_at` is set on done and cleared on reopen;
  - a queued deck becomes active only when its first term starts discovery, never because the planner
    proposed it.
- **Why**: reviews are memory upkeep and must never stop because a list is paused.

## D-027 — Queue order (M1.b)

- **Decision**:
  - supplying decks (`queued`, `active`) are ordered by future deadline first (earliest first), then manual
    `queue_position` (unset last), then id;
  - a deadline today or in the past gives a `deadline_passed` warning, and the deck keeps its normal place;
  - a term in several decks is proposed once, through its first eligible deck, and only while `queued`;
  - `reorder_queue(deck_ids)` must list every deck that is not done exactly once; it writes dense positions
    0..n-1 and `deck.reordered`;
  - the `priority` column is not used: the manual position covers it.

## D-028 — Duration estimates (M1.b)

- **Defaults** (`app/domain/durations.py`): receptive card 15 s, typed productive card 25 s, oral answer
  60 s, discovery 150 s, targeted-practice block 5 min, consolidation block 10 min.
- **Observed values**:
  - reviews are grouped by duration class (receptive, typed productive, oral), because exercise types only
    arrive in M4; a class's median response time over the last 30 days replaces the default from 30 reviews;
  - discovery: median `duration_ms` of `discovery.completed` events over 30 days, from 10 values.
- A due card is planned by its direction (receptive or typed productive); the exercise is chosen at review
  time.

## D-029 — Planner formula and constants (M1.b)

- **Blocks**:
  1. due reviews, i.e. due before the end of the study day: new/learning/relearning cards by due date, then
     Review cards by increasing retrievability; the two cards of a term are not adjacent when avoidable;
  2. new terms;
  3. targeted practice: the most frequent error code of the last 14 days with at least 2 errors (ties: the
     most recent);
  4. consolidation: a `proposed` or `accepted` task.
- **New terms allowed**: `n = min(cap_quota, cap_budget, cap_anticipation, available)`, with
  `B = budget × 60`, `Q` the quota and `P` the sum of the deadline paces:
  - `cap_quota = Q` if `P ≤ Q`, else `min(P, 2Q)`;
  - `cap_budget = max(0, ⌊(B − reviews − targeted block − consolidation block) / discovery⌋)`;
  - `cap_anticipation = max(0, ⌊7 × (B − L7) / (NEW_ITEM_CARDS × NEW_CARD_REVIEWS_FIRST_WEEK × card)⌋)`,
    where `L7` is the mean forecast load of the next 7 study days, `card` the mean of the receptive and
    productive estimates, `NEW_ITEM_CARDS = 2` and `NEW_CARD_REVIEWS_FIRST_WEEK = 4`.
- **Reported limit**: `nothing_to_learn` without candidates; otherwise the binding cap, ties in the order
  budget, anticipation, quota; `supply` when fewer terms exist than allowed (added with the plan).
- **Overflow**: time accumulates in block order (reviews, targeted practice, consolidation); entries past the
  budget get `overflow: true`. Reviews over budget → 0 new terms and a `reviews_over_budget` warning.
- **Order of new terms**: interrupted discoveries, each deadline deck's pace, active decks in queue order,
  then queued decks (listed in `decks_to_activate`).
- **Warnings**: a stable code and parameters, no text; the frontend translates them.

## D-030 — Deadline pace and the 2 × quota cap (M1.b)

- **Decision**:
  - `required = ⌈remaining / days_left⌉`; `remaining` = queued + discovering terms of the deck; `days_left`
    = study days from today to the day before the deadline;
  - terms still in triage get a separate `deadline_triage_pending` warning;
  - a deadline may raise the quota up to 2 × quota, no more;
  - if the pace exceeds `achievable = min(2Q, cap_budget, cap_anticipation)`, `deadline_unrealistic` gives
    the achievable pace and the projected last day (`today + ⌈remaining / achievable⌉ − 1`; null if 0).
- **Why**: a talk can justify a heavier fortnight, but an unbounded quota would bury the following weeks in
  reviews. The warning lets the user decide (cut the list or move the date).

## D-031 — Read-only planner and `plan today` (M1.b)

- **Decision**:
  - `plan_session` is pure and its output (`SessionPlan`, Pydantic) is serialisable;
  - it writes no `study_session` and no event: M4 records the session when the user starts it;
  - `python -m app plan today [--at ISO] [--json]` sets `PRAGMA query_only = ON` on its connection (SQLite
    itself refuses any write) and rolls back; a naive `--at` is local time in the `timezone` setting; it
    refuses a missing or outdated database.

## D-032 — Faster database tests (M1.b)

- **Decision**: the suite runs the migrations once per session into a template file and copies it for each
  test. The template is itself built from scratch by `alembic upgrade head`, and the downgrade/upgrade test
  still uses its own fresh file.
- **Why**: status and queue tests are parameterised over every transition; the suite went from ~30 s to
  ~8 s, which matters on the Windows CI job.

## D-033 — Demo mode, separate database and demo marker (M1.c, 2026-10-16)

- **Separate file**:
  - `VOCAB_DEMO=1` (or `python -m app --demo`, `start.ps1 -Demo`, `start.sh --demo`) changes the default
    database to `<data_dir>/vocab-coach-demo.sqlite3`; nothing else changes;
  - `VOCAB_DEMO` together with `VOCAB_DATABASE_URL` fails at startup: the target would be ambiguous;
  - `--demo` writes `VOCAB_DEMO=1` into the process environment, so the API's `--reload` subprocess
    inherits it.
- **Marker**: a row of the `setting` table with the reserved key `_demo` and the value
  `{dataset_version, seed, days, anchor}`.
  - The key is not in the settings registry, so `get_setting` / `set_setting` refuse it, `get_all_settings`
    skips it, and it can never produce `setting.changed` (D-017). No migration.
  - `/api/health` returns `demo: true` only when the connected database carries it; the frontend then shows
    a "Demo data" badge.
- **Safety checks** (`app/demo/seed.py`):
  - `demo seed` always targets the demo file, whatever `VOCAB_DATABASE_URL` says; tests pass explicit
    temporary paths, and CI uses `VOCAB_DATA_DIR`;
  - a database that holds rows (outside `alembic_version` and the taxonomy) but no marker is refused, even
    with `--reset`;
  - a marked database is refused without `--reset`; `--reset` rebuilds it without a backup (it can be
    regenerated);
  - `--if-missing` does nothing when the marker is there (used by the launch scripts).
- **Atomic build**: migrations, taxonomy sync, simulation and marker go to `<name>.tmp-<pid>` in the same
  folder; the WAL is checkpointed, the target's old `-wal`/`-shm` are removed (a stale log would be
  replayed into the new file), then `os.replace`. Any failure removes the temporary file and leaves the
  previous database untouched. On Windows, a file held open by the running API raises `PermissionError`,
  reported as "stop the app and run the command again" (checked on the owner's machine).
- **Default anchor**: the current study day (`timezone`, `day_start_hour`). This is the only place the
  seed reads the clock.

## D-034 — Deterministic simulation and learner model (M1.c)

- **Determinism**:
  - one `random.Random(seed)` derives, in a fixed order, the generators of the FSRS engine
    (`FsrsEngine(rng=...)`, D-022), the learner, the calendar, the learner's choices and the productions;
  - the simulation passes its own engine factory to every service; no set is iterated and every query
    that feeds a decision is ordered;
  - same `(seed, days, anchor, dataset_version)` ⇒ same rows. The test fingerprint hashes every table
    sorted by primary key and **excludes only the real-clock columns `created_at`, `updated_at` and
    `recorded_at`** (rows written by services, such as cards, get the insert time).
- **Time**: every service already took explicit instants (M1.b); no clock parameter had to be added and no
  clock is patched.
- **Calendar**: study days anchor − days … anchor − 1; about 85 % worked; a forced break on days −25…−23;
  sessions mostly 18:30–23:30 Douala time, 10 % in the morning, 10 % after midnight (previous study day);
  activities stop 30 min before the end of the study day, so nothing is later than the anchor day's
  start. Dataset days are written for 60 days and scaled for shorter runs (future deadlines are not).
- **Session**: `plan_today` at the start; due reviews in plan order (25 % of days stop at the budget), then
  new terms through `start_discovery` / `complete_discovery` with initial ratings and a log-normal
  `duration_ms`, then a production every 2–4 days. One `study_session` per session.
- **Learner** (`app/demo/learner.py`):
  - p(success) = retrievability (Review cards; 0.85 for learning steps) × term factor (drawn once in
    [0.92, 1.06]) × direction factor (productive 0.96), bounded to [0.05, 0.98];
  - failure → Again; success → Hard/Good/Easy with weights that depend on retrievability; 5 % of proposed
    ratings differ by one step from the final one;
  - response times log-normal (σ 0.35) around the D-028 defaults, × 1.6 after a failure;
  - exercise types: provisional strings in the single constant `DEMO_EXERCISE_TYPES` (by direction and
    maturity, mature = stability ≥ 21 days). M4 owns the real list.
- **New terms**: deadline decks get exactly their pace; spare energy (4–6 a day at first, 0–2 from day
  −45) goes to decks without a deadline. Decks are activated on purpose through the deck service when
  created (dataset `status_events`); the learner never starts a waiting deck: they stop at the first term
  of a deck in `decks_to_activate` (owner's choice at plan approval). This keeps "Presenting results"
  queued.
- **Guaranteed final states** (last session, through the services): one interrupted discovery, one
  discovery without ratings (`new` cards), a lapse if no card is in Relearning; terms with a `fate` in the
  dataset end as draft, triage, known, archived (day −8) or active (`mark_active`, day −5).
- **Errors in productions**: per code, a Poisson count with a rate per 100 words that moves linearly over
  the history (`content/demo/errors.yaml`); review errors come from `confusion` entries on terms (failed
  productive reviews, at most 10, at most 2 per term).
- **Robustness**: seeds 1 to 12 were checked against every coverage criterion of the milestone; the tests
  pin seed 42.
- **Performance** (Windows 11, owner's machine): 2.4–4.4 s for 60 days. Under the 5 s threshold, so the
  coverage tests share one full 60-day seed (module fixture); determinism uses 21 days and the safety and
  CLI tests 7 days (each seed also runs the migrations). The backend suite went from ~8 s to ~27 s on the
  owner's machine. CI also runs the full seed through the CLI on Linux and Windows.

## D-035 — Provisional direct writes, `deck.item_added`, sessions in services (M1.c)

- **Direct writes** (`app/demo/direct_writes.py`), until the owning services exist: deck and term creation
  and triage decisions (M3), productions and errors (M5), `study_session` rows (M4). Each writes its event
  with the backdated `occurred_at`. Status changes always go through the existing services.
- **`study_session` format**: `planned = {format: "demo-provisional-1", plan: SessionPlan}`,
  `summary = {format, reviews, failed_reviews, discoveries_started, discoveries_completed, productions,
  errors, words, stopped_at_budget}`. Marked provisional: M4 owns it.
- **New event `deck.item_added`** (`deck_id`, `lexical_item_id`, `payload_version` 1): written for every
  `deck_item` row, so a term added to a second deck (D-013) leaves a trace. Open set, no migration (D-015).
- **Service change**: `start_discovery`, `complete_discovery` and `set_item_status` accept an optional
  `study_session_id`, passed to their events and to the initial reviews.

## D-036 — Open the browser only when the app answers (M1.c)

- **Script**: `scripts/wait-and-open.mjs` (Node ≥ 22, native `fetch`, no dependency) polls the API's
  `/api/health` until `status: "ok"`, then the Vite page, every 500 ms for at most 90 s, then opens the
  browser (`start` on Windows, `open` on macOS, `xdg-open` on Linux). On timeout it prints a message and
  exits 0. Without `VOCAB_OPEN_BROWSER=1` it exits at once (`-NoBrowser` / `--no-browser`). Vite's own
  `open` option is removed.
- **Addresses**: `frontend/dev-server.json` holds the Vite host and port and the backend URL;
  `vite.config.ts` and the script both read it (`VOCAB_BACKEND_URL` still overrides the backend URL in
  both). Polling the API directly avoids a proxy error trace in the Vite log at every attempt.
- **`concurrently`**: `--kill-others` killed the servers as soon as the opener exited with code 0 (checked
  with concurrently 10.0.6). The dev script now uses `--kill-others-on-fail`: a crashing server still
  stops the other, Ctrl+C stops everything (owner's choice at plan approval).

## D-037 — Error category levels (M1.c)

- **Decision**: in the taxonomy, level 1 is `grammar`, `lexis`, `register`... and the categories of SPEC
  module E (`grammar.preposition`, `grammar.tense`, `lexis.false_friend`...) are level 2. The demo summary
  prints both levels; "prepositions and tenses are the most frequent categories" is checked at level 2
  (approved with the plan). Statistics (M9) will aggregate by code prefix at either level (D-016).

## D-038 — Synchronous gateway and the transaction rule (M2.a, 2026-10-16)

- **Decision**: the gateway is synchronous (services take a `Session`, D-023, and FastAPI runs sync
  routes in a thread pool). `clock`, `sleep` and `rng` are injected so tests never wait.
- **Rule for callers**: call the AI **first**, then write the results in your own short transaction. Never
  keep a write transaction open while waiting for a provider: SQLite allows one writer, and a slow call
  would block the others past `busy_timeout` (5 s).
- **Exception to D-023**: the gateway writes `ai_call_log` in its own short session, committed at once,
  never in the caller's transaction. A caller's rollback would otherwise erase the trace of failed
  calls. A failed journal write is logged (`logging`, masked) and never turns a successful result into
  an error.
- **Expected failures are results, not exceptions**: `AiResult.status` is `ok`, `incomplete` or
  `unavailable` (+ reason). Exceptions (`UnknownTask`, `InputTooLong`, `SchemaMismatch`,
  `UnknownProvider`, `PromptError`, all `ValueError`s) are programming errors raised before any call.

## D-039 — Error policy and constants (M2.a)

- **Constants** (`app/ai/policy.py`, provisional, M2.b may adjust them after reading the real quotas):
  `MAX_ATTEMPTS_PER_PROVIDER=3`, backoff 1 s x2 with +/- 25 % jitter, `MAX_WAIT_S=20`,
  `TOTAL_BUDGET_S=90`, `QUOTA_COOLDOWN=1 h`, `REQUEST_TIMEOUT_S=30` (a task may override it).
- **Per error type**:
  - `rate_limited` / `transient`: retry (`retry_after` when <= 20 s, else backoff), then fallback after
    3 failed attempts;
  - `quota_exhausted`, or `rate_limited` with `retry_after` > 20 s: no retry, fallback, cooldown;
  - `network`, `bad_request`: no retry, fallback;
  - `auth`: no retry, fallback, provider marked misconfigured until `reload()`;
  - `invalid_output`: one repair on the same provider (the validation message is added to the
    prompt), then `incomplete`, never a fallback (SPEC section 7: "to complete", without blocking).
- **Cooldown length** (interpretation of the brief): `QUOTA_COOLDOWN` without indication, else
  `min(retry_after, 1 h)`. A per-minute 429 with `retry_after=25 s` must not block a provider for an
  hour.
- **Counting**: the cap of 3 counts transport failures; the single repair is outside it and its message
  stays in the prompt of later retries. Validation messages list locations and rules only, never the
  output itself.
- **Time budget**, measured with `clock`: a wait that would end past 90 s is not made (next provider, or
  `unavailable(timeout)`); each request's timeout is capped by the budget left. `timeout` means the
  budget only (a request timeout is `transient`).
- **Reason of `unavailable`**: no usable provider -> `no_provider_configured`; budget -> `timeout`;
  otherwise the common class of the final failures (network, quota = `quota_exhausted` or
  `rate_limited`, auth) or `all_failed`. Providers skipped for cooldown / auth count in it.
- An unexpected exception from an adapter is treated as `bad_request` (error code
  `unexpected:<Type>`) and never reaches the caller.
- **Revised in M2.b1**: see D-051 (new `EXHAUSTED_RETRY_COOLDOWN`, provider timeout floor).

## D-040 — Fallback, health, pinning, reload (M2.a)

- **Order** = setting `ai_provider_order`; a provider that is absent is disabled; a provider that is not
  configured is skipped without a log line, as is one in cooldown or marked misconfigured.
- **Health** (`app/ai/health.py`): in memory, one lock (several FastAPI threads), lost on restart on
  purpose. `Gateway.status()` returns configured / enabled / available / `cooldown_until` / last error
  type per provider, never a key.
- **`pin_provider`**: one provider, no fallback, ignores order, cooldown and the misconfigured mark
  (M2.b "test connection"). Unknown name -> `UnknownProvider`; not configured or without the capability
  -> `unavailable(no_provider_configured)`. It is journalled and updates health (a success clears the
  marks).
- **`reload()`** clears health and rebuilds the providers when the gateway was given a factory (M2.b calls
  `get_settings.cache_clear()` then `reload()` after the user changes a key).
- **Seam**: `get_gateway()` exists now with no real provider (`build_providers()` returns `{}`), so every
  call is `unavailable(no_provider_configured)`: degraded mode works before M2.b. M2.b's
  `build_providers()` must include unconfigured providers too (their `is_configured()` is False), so
  that `pin_provider` and `status()` know them.

## D-041 — Journal granularity (M2.a)

- **One `ai_call_log` row per provider request** (retries and repairs included); skipped providers and
  `no_provider_configured` write nothing. No migration: the M1.a table already holds everything.
- `attempt` = rank of the request on that provider; `fallback_from` = the provider that failed just
  before in the same call; `model` is the provider's model even when the request fails
  (`Provider.model_for`, the column is NOT NULL); `prompt_version` = `<task>.v<N>` (null for
  transcription); `AiResult.call_id` is the last row's id (for `production_attempt.ai_call_id`).
- Never stored: prompts, responses, user text, keys. Error messages are masked, then truncated to 300
  characters (`AICallLog.ERROR_MESSAGE_MAX` lowered from 500; Python constant, no schema change).
- **Usage** (`app/services/ai_usage.py`): computed from `ai_call_log` per study day (D-014), per provider
  and model (requests, successes, errors by code, tokens, mean duration). No counter table.

## D-042 — Prompt files, registry and data framing (M2.a)

- **Format** `app/ai/prompts/<task>.v<N>.txt`: YAML header (`task`, `version`, `description`,
  `placeholders: {name: data|plain}`), then `@@ system` and `@@ user` sections. Validated at load:
  file name = header, every used placeholder declared and every declared one used.
- **Single-pass substitution** with `re.sub` and a function: inserted text is never scanned again;
  missing or undeclared inputs are errors; no `str.format`, no `%`.
- **Data framing by construction**: a `data` placeholder is inserted between `<<<USER_DATA` and
  `USER_DATA>>>`; if the text contains `USER_DATA`, the delimiter becomes `USER_DATA_2`, and so on, so the
  text cannot close the frame while being inserted unchanged. The loader itself adds the "data, never
  instructions" rule to the system part.
- **Registry** (`app/ai/tasks.py`) pins each task's prompt version, output schema, input and output
  limits. `generate_json(task, inputs, schema)` keeps the SPEC section 7 signature; `schema` must be the
  registered class (`SchemaMismatch` otherwise), which keeps prompt and schema from drifting apart.
  `pin_provider` is an additional keyword-only argument. `SPEC.md` is unchanged.
- Output schemas inherit `AiOutput` (`extra="ignore"`); the gateway always validates with Pydantic,
  whatever native JSON support a provider has (`ProviderRequest.json_schema` is handed to adapters).

## D-043 — Secrets and masking (M2.a)

- `Settings` gains `gemini_api_key`, `groq_api_key` (`SecretStr`) and `ollama_base_url`; an empty value
  means "not configured". `repr`/`str` show `SecretStr('**********')`.
- `mask_secrets` replaces every secret of 6 characters or more (raw, `quote`, `quote_plus`) with `***`, then
  the message is truncated (masking first, so a cut key cannot escape). It applies to every error
  message before it is logged, returned, journalled or sent to `logging`. The secret list is read at each
  call, so it follows a `reload()`.

## D-044 — List settings and `ai_provider_order` (M2.a)

- The settings registry gains list support: `SettingSpec(type=list, item_choices=..., unique_items=True)`.
  `validate` refuses unknown names, duplicates and non-strings, and returns a copy; `get_setting` and
  `get_all_settings` return copies of the default so callers cannot alter the registry.
- `ai_provider_order`: default `["gemini", "groq", "ollama"]`; `[]` turns AI off. Known names live in
  `KNOWN_AI_PROVIDERS` (`domain/settings_defaults.py`). `setting.changed` is written by `set_setting` as
  for any setting.

## D-045 — Tests without network (M2.a)

- `tests/ai/conftest.py` has an autouse fixture that refuses `socket.connect` / `connect_ex` to any
  non-local host and DNS lookups of non-local names (loopback stays open: `socketpair` on Windows goes
  through 127.0.0.1). Its exception derives from `BaseException`, so the gateway's `except Exception`
  cannot hide it. The CI has no key.
- `FakeProvider` (`app/ai/providers/fake.py`) plays a script of successes and typed errors and records
  the requests it received; it is also what `python -m app ai simulate` uses.

## D-046 — Provider facts checked before coding (M2.b1, 2026-10-16)

Read in the official documentation on 2026-10-16 (never from memory). Where a page does not say, the
cell says so. Re-check what matters at the start of M2.b2 (Gemini) and whenever a provider changes. *Gemini re-checked in M2.b2: D-056.*

| Fact | Value | Source |
|---|---|---|
| **Gemini** stable models | Flash-Lite: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`; Flash: `gemini-3.8-flash`, `gemini-3.6-flash`. `gemini-3-flash-preview` is a preview. `gemini-2.5-flash(-lite)` are kept only for users who already used them; 2.0 models are shut down | <https://ai.google.dev/gemini-api/docs/models> |
| Gemini free tier | "Free of charge" for those six models. **Content is used to improve the products on the free tier, not on the paid tier** | <https://ai.google.dev/gemini-api/docs/pricing> |
| Gemini free quotas | **No public figure**: limits are per project and shown per account in AI Studio; the daily quota resets at midnight Pacific time. Third-party figures disagree and are not used | <https://ai.google.dev/gemini-api/docs/rate-limits> |
| Gemini in Cameroon | Cameroon is in the list of available countries; the page does not split free and paid tiers. **Hypothesis B.11 stays open until the owner's real call** | <https://ai.google.dev/gemini-api/docs/available-regions> |
| Gemini API | `generateContent` (v1beta) is "legacy" but "fully supported"; the Interactions API is the recommended one (breaking changes in May 2026). Key in the `x-goog-api-key` header | <https://ai.google.dev/gemini-api/docs/interactions>, <https://ai.google.dev/api/generate-content> |
| Gemini JSON | `generationConfig.responseFormat.text = {mimeType: "APPLICATION_JSON", schema}`; `responseMimeType` + `responseJsonSchema` are marked deprecated. Accepted schema keywords: `$id $defs $ref $anchor type format title description enum items prefixItems minItems maxItems minimum maximum anyOf oneOf properties additionalProperties required` (+ `propertyOrdering`); next to a `$ref` only `$`-keywords are allowed | <https://ai.google.dev/api/generate-content> (GenerationConfig) |
| Gemini thinking | `thinkingConfig.thinkingLevel` (Gemini 3+; an **error** on older models) or `thinkingBudget`; `maxOutputTokens` **includes** thinking tokens; default `gemini-3.5-flash-lite` = minimal, `gemini-3.8-flash` = medium (no minimal); usage field `thoughtsTokenCount` | same page, <https://ai.google.dev/gemini-api/docs/thinking> |
| Gemini finish | `finishReason`: STOP, MAX_TOKENS, SAFETY, RECITATION, BLOCKLIST, PROHIBITED_CONTENT, SPII, OTHER...; `promptFeedback.blockReason`: SAFETY, OTHER, BLOCKLIST, PROHIBITED_CONTENT | same page |
| Gemini errors | The "API errors" page documents the **Interactions API** (401 `authentication`; 429 `rate_limit_exceeded` = per minute, `quota_exceeded` = per day; 400 `failed_precondition`). Nothing official for `generateContent`. Forum reports: invalid key = **400 `INVALID_ARGUMENT` / `API_KEY_INVALID`**; region = **400 `FAILED_PRECONDITION` "User location is not supported"**; 429 with `QuotaFailure.quotaId` containing `PerDay` or `PerMinute` and `RetryInfo.retryDelay` ("51s", short even for a daily quota). **To confirm with a real call** | <https://ai.google.dev/gemini-api/docs/api-errors>; discuss.ai.google.dev threads "API key not valid" and "User location is not supported" |
| **Groq** base URL | `https://api.groq.com/openai/v1` (`/chat/completions`, `/audio/transcriptions`) | <https://console.groq.com/docs/speech-to-text> |
| Groq free plan limits | `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`: 30 requests/min, 1 K/day, 8 K tokens/min, 200 K/day. `whisper-large-v3` and `-turbo`: 20 requests/min, 2 K/day, 7.2 K audio-s/hour, 28.8 K audio-s/day. `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` are production models but **absent from the free table** | <https://console.groq.com/docs/rate-limits> ("Free Plan Limits" tab, read in the page HTML) |
| Groq models | text: `openai/gpt-oss-20b` (131 072 context, 65 536 output), `openai/gpt-oss-120b`, `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`; speech: `whisper-large-v3` (WER 10.3 %), `whisper-large-v3-turbo` (12 %) | <https://console.groq.com/docs/models>, <https://console.groq.com/docs/speech-to-text> |
| Groq JSON | `response_format: {type: "json_schema", json_schema: {name, strict, schema}}` on `openai/gpt-oss-20b`, `-120b`, `qwen/qwen3.8-27b`, `meta-models/muse-spark-open` (strict or best-effort); other models only `json_object`, where the prompt must mention JSON. Best-effort allows optional fields. A mismatch gives **HTTP 400** "Generated JSON does not match the expected schema" | <https://console.groq.com/docs/structured-outputs> |
| Groq reasoning | gpt-oss: `reasoning_effort` low/medium/high, `include_reasoning`, `max_completion_tokens` (default 1024). **Not documented**: whether reasoning counts against the limit (assumed yes) | <https://console.groq.com/docs/reasoning> |
| Groq 429 | `retry-after` header (seconds, only on 429); `x-ratelimit-*`: requests = per day, tokens = per minute, resets formatted `2m59.56s` / `7.66s`; body `{"error": {"message", "type"}}`. **Not documented**: telling a per-minute from a per-day limit in the body (third-party reports show `code: rate_limit_exceeded` and messages naming `(TPM)`, `(RPD)`, `(TPD)`) | <https://console.groq.com/docs/rate-limits>, <https://console.groq.com/docs/errors> |
| Groq errors | 401 key, 403 permission, 413 request too large, 498 flex tier full, 503 | <https://console.groq.com/docs/errors> |
| Groq audio | **25 MB on the free tier**, 100 MB on the developer tier; flac mp3 mp4 mpeg mpga m4a ogg wav webm; minimum 0.01 s (billed 10 s); `prompt` up to 224 tokens; response `json` has a `text` field | <https://console.groq.com/docs/speech-to-text> |
| **Ollama** chat API | native `POST /api/chat`: `stream` (default **true**), `format` = `"json"` or a JSON Schema, `options.num_predict`, `think`, `keep_alive` (5 min); answer `message.content`, `done_reason`, `prompt_eval_count`, `eval_count`; errors `{"error": "..."}` with 400, 404, 429, 500, 502; listens on `127.0.0.1:11434` by default. The docs advise to put the schema in the prompt as well. The OpenAI-compatibility page documents neither `json_schema` nor errors | <https://docs.ollama.com/api/chat>, <https://docs.ollama.com/capabilities/structured-outputs>, <https://docs.ollama.com/api/errors>, <https://docs.ollama.com/faq> |
| Ollama models | library: `gemma3` (`gemma3:4b`, 3.4 GB, 128 K context), `llama3.2`, `qwen2.5`...; `qwen3`, `gpt-oss`, `gemma4`... are "thinking" models | <https://ollama.com/library>, <https://ollama.com/library/gemma3> |
| Ollama install | `OllamaSetup.exe` runs in the background after install; `ollama pull <model>`, `ollama ls` | <https://docs.ollama.com/windows>, <https://docs.ollama.com/cli> |

**Not verified (so not asserted)**: Ollama's first-load latency; the exact Groq 429/401 bodies (the fixtures are
built from public reports, see `tests/ai/fixtures/README.md`); the real `generateContent` error body; whether
Groq's sign-up asks for a payment method. The owner's real calls settle these.

## D-047 — Groq adapter (M2.b1)

- **Text**: OpenAI-compatible `chat/completions` through a small base class (`openai_compat.py`) that Groq
  extends; a later OpenAI-compatible provider is one more subclass. Defaults: `openai/gpt-oss-20b` (in the free
  table, production, documented for `json_schema`), `whisper-large-v3` (more accurate than turbo for spotting a
  learner's mistakes; same free limits).
- **JSON**: `json_schema` in **best-effort** mode (`strict: false`, name `output`) for the models documented for
  it, with the simplified schema (D-049) and `additionalProperties: false`; any other model gets `json_object`
  and the schema restated in the system prompt (Groq wants JSON mentioned there). Pydantic still validates.
- **gpt-oss**: `reasoning_effort: "low"`, `include_reasoning: false`, and `max_completion_tokens` = the task's limit
  + 1 024 (reasoning may count against it, undocumented). Other models get no reasoning field.
- **Transcription**: multipart upload (`model`, `language`, `response_format=json`, `temperature=0`, `file`),
  a short encoder in `http.py`. The adapter refuses **before any request** an empty clip, one over 25 MB (the
  free-tier limit; constant `MAX_AUDIO_BYTES`), or an extension Groq does not read; the refusal is a
  `bad_request`, which the gateway journals as a request without HTTP status (so it counts in `ai usage`: a
  small, accepted imprecision, no interface change). An empty text (silence) is a valid answer: the caller
  (M6) decides what to tell the user. `Gateway.transcribe` is unchanged.
- **Tokens**: `usage.prompt_tokens` / `completion_tokens` go to `ai_call_log`; a transcription has none.

## D-048 — Ollama adapter (M2.b1)

- **Native API** `/api/chat`, not `/v1`: only the native one documents `format` (a JSON Schema),
  `options.num_predict` and the error body. So Ollama does not share the OpenAI-compatible base (assumed).
- Always `stream: false`, `temperature: 0`; the schema is sent as `format` **and** restated in the system
  prompt (the documentation's advice). `think` is not sent (unknown to some models, its effect on others is
  not documented): the default model `gemma3:4b` does not think; with a thinking model an empty answer is
  reported as such.
- "Configured" = `VOCAB_OLLAMA_BASE_URL` is an http(s) URL (a `file:` or scheme-less value is "not configured").
  `.env.example` suggests `http://127.0.0.1:11434`: on Windows `localhost` may resolve to `::1` first.
- **First request after a pause** loads the model: the adapter declares `min_request_timeout_s = 60`, which
  the gateway honours (D-051) but never beyond the 90 s budget.
- A server that answers 200 without being Ollama (HTML...) is a `bad_request`; a cut-off answer
  (`done_reason: "length"`) or an empty one is `invalid_output`.

## D-049 — HTTP client, schemas and secrets in adapters (M2.b1)

- **Standard-library `urllib`, no SDK, no new dependency.** The three APIs are plain JSON POSTs; an SDK brings
  its own retry loop and error types that would mix with the gateway's policy (D-039), and `google-genai` is
  moving to the Interactions API. `httpx2` (a dev dependency, the `pydantic/httpx2` fork) stays possible: its
  source would be read first (as for `fsrs`, D-022). Consequences: a hand-made multipart encoder, a per-request
  deadline implemented in `http.py`, an explicit `User-Agent` (`vocab-coach/0.1`: some API gateways refuse
  `Python-urllib`; unverified, a real call will tell).
- `http.post` returns a non-2xx answer as a normal `HttpResponse` (the adapter reads its headers and body);
  failures become `ProviderError` with **fixed wording** (never `str(exc)`, which may quote the URL):
  `connection refused`, `DNS lookup failed`, `TLS handshake failed`, `connection closed by the server`
  (`network`); a timeout, connect or read, is `transient`. **Redirects are refused** (a redirect could forward
  the key to another host). Loopback hosts bypass the system proxy. Only `http` and `https` URLs (`urllib`
  would open `file:`).
- **Schemas** (`providers/schema.py`): `Model.model_json_schema()` is simplified, not trusted: `$ref`s are
  inlined (a recursive model is refused), `title`, `default`, `examples` and validation keywords
  (`minLength`, `minItems`, `maximum`, `pattern`, `format`...) are dropped, `const` becomes `enum`, objects get
  `additionalProperties: false`; field names are never mistaken for keywords. Tested on the shape of the M3
  usage sheets (nested models, lists, enums, optionals). The Pydantic model keeps enforcing everything dropped.
- **JSON fences** (a Markdown code fence around the JSON) are removed by every adapter, only when the text
  starts with one.
- **Secrets** (D-043 extended): the key lives in a private attribute, `__repr__` never shows it, it travels only in
  the `Authorization` header; every message is the service's own `error.message` or fixed text, masked by the
  adapter (`mask_secrets`, raw, URL- and form-encoded) and again by the gateway; the 400 `json_validate_failed`
  answer, which quotes the model's output, is replaced by fixed text. No request body is logged.

## D-050 — Error translation per provider (M2.b1; Gemini column for M2.b2)

| Situation | Groq | Ollama | Gemini (M2.b2) |
|---|---|---|---|
| 429, per minute | `rate_limited`; `retry_after` = `retry-after` header, else "try again in 7m12.5s" from the message, else `x-ratelimit-reset-tokens` for a token limit | `rate_limited` (`Retry-After` if present) | `rate_limited`; `RetryInfo.retryDelay` or `Retry-After` |
| 429, per day | `quota_exhausted` when the message says `per day`, `(RPD)`, `(TPD)` or `(ASD)`; `retry_after` as above (cooldown = min(that, 1 h)); an unlabelled 429 stays `rate_limited` (least penalising) | - | `quota_exhausted` when a violated quota is `PerDay` (any one of them); **`retry_after` ignored** (short even for a daily quota), so the cooldown is 1 h |
| 5xx, 408, 498 (flex full), timeout | `transient` | `transient` | `transient` (also 499, 504) |
| Connection refused, DNS, TLS | `network` | `network` | `network` |
| Key refused | 401, 403 -> `auth` | 401, 403 -> `auth` | 401, 403, **400 `API_KEY_INVALID`**, **400 `FAILED_PRECONDITION` / "location is not supported" / "free tier not available"** -> `auth` with an explicit message |
| Other 4xx | `bad_request`; 404 model -> hint to set `VOCAB_GROQ_*_MODEL`; 413 -> "too large for this model's limits"; 3xx (no redirect followed) -> `bad_request` | `bad_request`; **404 -> `bad_request` + "run `ollama pull <model>`"** | `bad_request`; 404 model -> hint `VOCAB_GEMINI_MODEL`; 402 -> `quota_exhausted` |
| Answer unusable | `invalid_output`: 400 "does not match the expected schema" / `json_validate_failed`, `finish_reason` `length` or `content_filter`, empty | `invalid_output`: `done_reason: "length"`, empty | `invalid_output`: `MAX_TOKENS`, `SAFETY`..., `promptFeedback.blockReason`, empty |

- **Blocked content is `invalid_output`** (the owner's brief): one repair, then `incomplete`, never a fallback.
  The comment of `ErrorKind.BAD_REQUEST` ("includes blocked content") was corrected.
- A 400 is never classified before reading what it says (a Gemini 400 can mean "invalid key").

## D-051 — Policy constants revised (M2.b1)

| Constant | M2.a | M2.b1 | Why |
|---|---|---|---|
| `MAX_ATTEMPTS_PER_PROVIDER` | 3 | 3 | unchanged |
| backoff | 1 s x2, +/-25 % | same | unchanged |
| `MAX_WAIT_S` | 20 | 20 | Groq's `retry-after` is in seconds (30 requests/min): waiting up to 20 s pays off; reported Gemini delays (14-57 s) often exceed it and then falling back is better than sleeping. Re-examined in M2.b2: kept, D-060 |
| `TOTAL_BUDGET_S` | 90 | 90 | unchanged |
| `QUOTA_COOLDOWN` | 1 h | 1 h | a daily quota does not free up before its reset; one probe per hour costs one failed request |
| `REQUEST_TIMEOUT_S` | 30 | 30 | unchanged; transcription 60 s; Ollama floor 60 s (below) |
| **`EXHAUSTED_RETRY_COOLDOWN`** | - | **60 s** | closes the point left open in M2.a: a provider that fails 3 times in a row with `rate_limited` or `transient` is set aside for a minute (about one per-minute window) instead of costing three attempts (3 s of waiting) on every call. It also applies to repeated 5xx |

- `health.blocked_by()` now reports the error that started the cooldown (not always "quota"), so repeated
  transient failures end as `unavailable(all_failed)` rather than a misleading `quota`.
- **Provider timeout floor** (the only interface addition to M2.a): the gateway sends each request with
  `min(max(task timeout, provider.min_request_timeout_s), time left in the budget)`, the attribute being optional
  (`getattr`, default 0). Only Ollama sets it (60 s).
- Groq's free limits make a fallback call fit in about 8 000 tokens (input + output) per minute: M3 tasks sent
  to Groq must keep prompts small, or the answer is a 413 (`bad_request`).

## D-052 — Providers built from the settings (M2.b1)

- `build_providers(settings=None)` returns `groq` and `ollama`, configured or not (D-040), so `status()` and
  `pin_provider` know them. **Gemini is not built until M2.b2**: `ai status` shows it as "not available yet",
  `ai test --provider gemini` exits 2, and the gateway skips a name it does not know in `ai_provider_order`.
  *(M2.b2: Gemini is built too, see D-057; these special cases are gone.)*
- New optional settings (empty = default): `VOCAB_GROQ_TEXT_MODEL`, `VOCAB_GROQ_TRANSCRIPTION_MODEL`,
  `VOCAB_OLLAMA_MODEL`; `VOCAB_GEMINI_MODEL` came with the Gemini adapter (M2.b2). Defaults are constants in the adapters.
  Adapters take an optional `base_url` in their constructor for tests only (no variable, as in M2.a).
- The M2.a test that asserted `status() == []` (no provider) now asserts that both providers are known and
  none is configured; it also forces the keys to empty **environment variables** (not `delenv`): an
  environment variable, even empty, wins over the owner's real `.env`, so keys written there can never turn a
  test into a network call.

## D-053 — `ai status`, `ai test`, `ai usage` (M2.b1)

- Same style as `plan today` (module `cli_ai.py`, injectable output). Exit codes: 0 all fine, **1** a test failed,
  **2** nothing configured / bad arguments / database absent or out of date / `--demo`.
- `status`: provider, configured or not, models per capability, rank in `ai_provider_order` (read-only, the
  default order with a note without a database), "AI is turned off" when the order is empty. Never a key (not
  even its last characters) nor a server address. The in-memory health is empty in a new process, so it is not
  shown.
- `test [--provider NAME] [--audio FILE]`: `generate_json("connection_test", ..., pin_provider=...)` per
  configured provider, one line each (status, model, time, tokens; on failure the reason, the last error code
  and HTTP status read from `ai_call_log`, and the masked message). `--audio` (Groq only, up to 200 MB read
  into memory) adds a Whisper request and prints the transcript. The output says these calls use free quota and
  are recorded in `ai_call_log`. **No session is open during a call** (D-038; tested with a second writer taking
  the database lock from inside the fake server).
- `usage [--days N]` (1-90, default 7): `services/ai_usage.py` per study day, provider and model, read-only
  (`PRAGMA query_only`). `test` and `usage` refuse `--demo` (D-033); `status` does not.
- stdout and stderr use `errors="replace"`: a transcript may hold characters the Windows console cannot show.

## D-054 — Tests without the real services (M2.b1)

- **Fake HTTP servers** (`tests/ai/fake_server.py`): a thread on `127.0.0.1` playing scripted answers
  (status, body, headers, delay, dropped connection), keeping every request. The adapters and the gateway run
  over real loopback sockets; the D-045 guard is unchanged (it allows only the loopback interface).
- **Fixtures** (`tests/ai/fixtures/<provider>/*.json`): built from the documentation and public reports, with
  invented identifiers; no real call produced them (`fixtures/README.md`).
- **Secrets**: a hostile server repeats the key in raw, URL- and form-encoded form in its error message, headers
  and path; the key must not appear in any error, repr, log record, `ai_call_log` column, status, traceback or
  CLI output.
- **Live tests** (`tests/live/`, marker `live`): `addopts = "-q -m 'not live'"` deselects them; they need
  `VOCAB_RUN_LIVE=1` **and** a configured provider; one request per provider; a quota or rate limit is a skip;
  Whisper only with `VOCAB_LIVE_AUDIO`. A default-suite test runs them in a subprocess to prove they are all
  skipped without the opt-in, and without keys even with it. Command:
  `VOCAB_RUN_LIVE=1 uv run pytest tests/live -m live -v`. The CI has no key and never selects them.

## D-055 — Gemini adapter design, to build in M2.b2 (decided in M2.b1)

*Built in M2.b2: see D-056 to D-060 for the re-checked facts and what was refined (no `temperature`, the thinking
table, the automatic switch to the older JSON fields).*

- **API**: `generateContent` (v1beta), stateless, key in `x-goog-api-key`; default model `gemini-3.5-flash-lite`
  (stable, Flash-Lite, free of charge); override `VOCAB_GEMINI_MODEL`.
- **JSON**: `generationConfig.responseFormat.text = {mimeType: "APPLICATION_JSON", schema}` with the simplified
  schema (keywords limited to the accepted list of D-046). **Risk n° 1**: documented but untested against the real
  service. The body builder is one isolated function; a 400 on that field gives `bad_request` (fallback to
  Groq); the fallback to try is the older `responseMimeType` + `responseJsonSchema`.
- **Thinking**: a per-model table (`thinkingLevel: "MINIMAL"` for `gemini-3.5-flash-lite`; nothing for an
  unknown model, since `thinkingLevel` is an error on older models) plus 512 tokens added to `maxOutputTokens`;
  `output_tokens` = candidates + `thoughtsTokenCount`.
- **Errors**: D-050 column; parse both error shapes (classic `error.status` / `details[]` and the Interactions
  style `error.code`), ignore `retryDelay` for daily quotas.
- **Privacy**: the README must warn that the free tier may use content to improve the products (SPEC section 7).
- **To confirm by the owner's first real call**: JSON field accepted, error bodies, quota ids, region and free
  tier in Cameroon (hypothesis B.11).

## D-056 — Gemini facts re-checked before coding (M2.b2, 2026-10-16)

D-046 was re-read against the official pages the same day (models, pricing, rate limits, regions, API
errors, troubleshooting, thinking, structured output, the `generateContent` reference and the v1beta
discovery document, which lists the exact field names and enum values). **What changed or was settled:**

| Fact | Result | Consequence |
|---|---|---|
| Models | the six of D-046 are unchanged. New: **`gemini-4-argon`** (stable, **no free tier**); `gemini-3.1-flash-lite-preview` and the 2.0 models are "shut down"; the 2.5 family is "limited to past users". The models page recommends 3.5 Flash-Lite or 3.8 Flash for new projects | the default stays `gemini-3.5-flash-lite`; a model without a free tier is never a default |
| Free tier and privacy | unchanged: free for 3.5/3.1 Flash-Lite and 3.8/3.6 Flash; "used to improve our products": yes on the free tier, no on the paid tier | README warning |
| Quotas, regions | unchanged: not published (AI Studio shows them), per project, RPM / TPM / RPD, reset at midnight Pacific; Cameroon listed, no free / paid split | hypothesis B.11 stays open until the owner's call |
| JSON | **settled in the discovery document**: `generationConfig.responseFormat` is a `ResponseFormatConfig` with `text: TextResponseFormat {mimeType: MIME_TYPE_UNSPECIFIED, APPLICATION_JSON or TEXT_PLAIN; schema}`. `responseSchema` and `responseJsonSchema` are marked deprecated ("use response_format instead"); `responseMimeType` is a plain string (`application/json`). The narrative pages only show the Interactions form (`response_format`, lowercase `mime_type`) | D-058; still not exercised against the real service |
| Schema keywords | the structured-output page (Interactions) lists: types incl. `null` and type arrays, `title description properties required additionalProperties enum format(date-time/date/time) minimum maximum items prefixItems minItems maxItems anyOf $ref`; "not all JSON Schema features are supported", large or deeply nested schemas "may be rejected" | `to_gemini_schema` keeps the four bounds (D-057) |
| Thinking | `ThinkingConfig {thinkingBudget, includeThoughts, thinkingLevel: MINIMAL, LOW, MEDIUM or HIGH}`; "recommended for Gemini 3 or later, earlier models return an error". Per-model table on the thinking page: 3.5-flash-lite default minimal (minimal..high); 3.6-flash default medium (minimal..high); **3.8-flash default medium (low..high, no minimal)**; 4-argon low..high. The same table lists 2.5 models with levels, which **contradicts** the discovery document. `maxOutputTokens` includes thinking tokens | table in D-057; models not in it get no `thinkingConfig` |
| Temperature | "silently ignored on Gemini 3.6 Flash and newer" | `temperature` is not sent |
| Answer | `usageMetadata`: promptTokenCount, candidatesTokenCount, thoughtsTokenCount, totalTokenCount...; `finishReason`: STOP, MAX_TOKENS, SAFETY, RECITATION, LANGUAGE, OTHER, BLOCKLIST, PROHIBITED_CONTENT, SPII, MALFORMED_*, ...; `promptFeedback.blockReason`: SAFETY, OTHER, BLOCKLIST, PROHIBITED_CONTENT, IMAGE_SAFETY | anything but STOP is `invalid_output` |
| Errors | unchanged: the "API errors" page documents **only the Interactions API** (`error.code` snake_case: `authentication`, `rate_limit_exceeded`, `too_many_requests` = per minute, `quota_exceeded` = per day, `failed_precondition`, `payment_required`...). The troubleshooting page says 429 / 503 are retried, 400 / 402 / 403 are not, and mentions "API key was reported as leaked". Forum reports again show the classic shape (`status`, `details[]` with `QuotaFailure.quotaId` containing `PerDay` / `PerMinute`, `RetryInfo.retryDelay` as short as 1 to 14 s even for a daily quota, `limit: 0` for a model without quota, some 429 without `details`) | D-059 |

**Could not be verified (so not asserted)**: the real `generateContent` error body (no official page); that the
live service accepts `responseFormat` and the upper-case `thinkingLevel`; thinking levels of
`gemini-3.1-flash-lite`; the 2.5 contradiction above. The owner's first real call settles them.

## D-057 — Gemini adapter (M2.b2)

- **Request**: `POST {base}/models/{model}:generateContent` (v1beta), key in `x-goog-api-key` only (the URL has no
  query string). Body: `systemInstruction`, one user `contents` entry, `generationConfig` with `maxOutputTokens`
  = the task's limit + **512** (thinking tokens count against it) and the JSON fields (D-058). No `temperature`
  (no-op on recent models), no `safetySettings` (defaults). The model name is validated (`[A-Za-z0-9._-]+`,
  a leading `models/` is accepted) before it enters the URL path: a name from `.env` cannot add a path segment
  or a query string.
- **Default model** `gemini-3.5-flash-lite`; `VOCAB_GEMINI_MODEL` (new `Settings.gemini_model`, empty = default).
  Text only: `transcribe` is a `bad_request`.
- **Thinking table** (`THINKING_LEVELS`, exact model name -> `thinkingLevel`): `gemini-3.5-flash-lite` and
  `gemini-3.6-flash` `MINIMAL`; `gemini-3.8-flash` `LOW` (it has no minimal level). Any other model gets **no
  `thinkingConfig`**: it is an error on models older than Gemini 3 and the levels of `gemini-3.1-flash-lite` are
  undocumented. The 512-token headroom is added whatever the model.
- **Answer**: first candidate; the parts are joined, parts with `thought: true` are left out; a `finishReason`
  other than STOP (MAX_TOKENS = cut off, anything else = stopped by the model, the name being echoed only when
  it looks like an enum name), a prompt blocked with no candidate, or an empty text is `invalid_output` with
  fixed wording (never the content). JSON fences are removed. **Tokens**: `input_tokens = promptTokenCount`,
  `output_tokens = candidatesTokenCount + thoughtsTokenCount` (thinking is billed and counts against the quota),
  `None` when neither is present. The model recorded is `modelVersion` when the answer carries one.
- **Schema** (`to_gemini_schema`): like Groq and Ollama (inlined `$ref`, closed objects, `title`, `default`,
  `format`, `pattern`, string lengths... dropped) **except** that `minimum`, `maximum`, `minItems` and `maxItems`
  are kept: the documentation lists them. `simplify_schema` got an optional `dropped` set; the default is
  unchanged, so the Groq and Ollama schemas are identical to M2.b1's. Pydantic still validates everything.
- `build_providers()` now returns `gemini`, `groq`, `ollama` (D-052 amended: Gemini is built; the "not available
  yet" cases of `ai status` / `ai test` are gone).

## D-058 — Isolating risk n° 1: the `responseFormat` field (M2.b2)

- All the JSON-related fields of the body come from **one function**, `json_generation_fields(schema, mode)`:
  `response_format` mode sends `responseFormat.text = {mimeType: "APPLICATION_JSON", schema}`; `legacy` mode sends
  `responseMimeType: "application/json"` + `responseJsonSchema` (marked deprecated by Google but still listed).
  Both are unit-tested.
- The provider starts in `response_format` mode. If Google answers **400 with "unknown name" / "cannot find
  field" and the field's name** (`responseFormat` or `response_format`), the adapter raises a `bad_request`
  (the gateway falls back to the next provider for that call) and **switches that instance to `legacy` for the
  next requests**. No second request inside `generate_json` (a provider makes one request, the journal counts
  one row per request). The switch is one-way and in memory (a restart tries `response_format` again); a schema
  error that merely mentions the field is not a missing field and does not switch.
- Cost if the field is refused: one request to Google and one fallback call, once per process. The live test
  (`tests/live`) warns when that happened, so D-058 can be updated with the real answer.

## D-059 — Gemini error translation, as implemented (M2.b2)

D-050's Gemini column, with the bodies parsed in both documented shapes (classic: `error.code` is the HTTP
status, `error.status` a name, `details[]` typed messages; Interactions: `error.code` is a snake_case string):

| Situation | Result |
|---|---|
| 429, a violated quota whose id contains `PerDay` (any one of them), the code `quota_exceeded`, or "per day" / "daily" in the message | `quota_exhausted`; **`retry_after` ignored** (reported delays are short even for a daily quota), so the gateway's cooldown is the default hour |
| 429 otherwise (`PerMinute`, `rate_limit_exceeded`, `too_many_requests`, no `details`) | `rate_limited`; `retry_after` = `RetryInfo.retryDelay`, else the `Retry-After` header, else "retry in 33.5s" in the message, else none |
| 402 | `quota_exhausted` (Interactions `payment_required`) |
| 401, 403 (including "API key was reported as leaked") | `auth` |
| 400 with `API_KEY_INVALID`, `UNAUTHENTICATED` / `PERMISSION_DENIED`, `authentication`, or "API key not valid / expired / invalid" | `auth` |
| 400 `FAILED_PRECONDITION` (or `failed_precondition`) whose message says "location is not supported", "not available in your country / region" or "free tier" | `auth`, with an explicit "region not supported or free tier not available here" message |
| Any other 400 (billing precondition, invalid schema, unknown field) | `bad_request` (+ D-058 when it is the `responseFormat` field) |
| 404 | `bad_request` + "check `VOCAB_GEMINI_MODEL`" |
| 408, 499, 5xx | `transient` (`Retry-After` kept) |
| 3xx, other 4xx | `bad_request` |

- A 400 is read before it is classified; every message is the service's own `error.message` (or fixed text),
  masked with the key (raw, URL- and form-encoded) and cut to 300 characters. Fixtures are built from the
  documentation and forum reports (`tests/ai/fixtures/README.md`): the quota ids and delays are reported
  values. Tested end to end through the gateway (`tests/ai/test_gateway_gemini.py`) and with a hostile server
  that repeats the key in every form (`test_provider_secrets.py`).

## D-060 — `MAX_WAIT_S` kept at 20 s with Gemini's delays (M2.b2)

- **Decision**: no change to `policy.py` (`MAX_WAIT_S = 20`, `TOTAL_BUDGET_S = 90`, backoff, cooldowns). The point
  left open by D-051 is closed.
- **Reasoning, from the delays reported for Gemini (14 to 57 s; nothing official)**: a delay up to 20 s is slept
  (three such attempts cost 28 s of the 90 s budget and a successful retry keeps Gemini first); a longer one
  makes the gateway fall back to Groq at once and set Gemini aside for exactly that delay (`min(retry_after, 1 h)`),
  then Gemini is tried first again when its window is over. Raising the limit to about 60 s would let one
  rate-limited provider eat two thirds of the budget for a call the user waits for; lowering it would give up on
  the common short delays. A daily quota never waits (D-059).
- Pinned by tests (14 s and 20 s wait, 21 s and 57 s fall back; three short 429s set Gemini aside for a minute;
  a daily quota with a 14 s delay cools down for an hour).
- **To re-examine** after the owner's real runs: the actual `retryDelay` values and how often the free tier is
  rate limited (`ai usage` shows the errors per provider).

## D-061 — Protecting the API against forged requests (M2.c1)

- **Threat**: the API holds the keys and will write `.env`. It listens on the loopback only, but the owner's
  browser can reach it, so a page opened in another tab could (a) make the browser send a write request
  (CSRF), or (b) use DNS rebinding (a hostile domain resolving to 127.0.0.1) to read answers.
- **Rules** (`app/api/guard.py`, a pure ASGI middleware, added last so it is the outermost layer: even a CORS
  preflight goes through the Host check; it applies to the whole application, `/docs` and `/openapi.json`
  included, and to the frontend served by the same port in M10):
  1. `Host` must be `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>` (case-insensitive; exactly one
     `Host` header) else 403 `forbidden_host`, for every method.
  2. POST / PUT / PATCH / DELETE: `Origin`, when present, must be in `cors_origins` or be the backend's own
     origin, else 403 `forbidden_origin` (`Origin: null` included); `Sec-Fetch-Site: cross-site` is 403
     `cross_site_request`.
  3. POST / PUT / PATCH with a body must be `application/json` (parameters allowed) else 415
     `unsupported_media_type`. FastAPI alone already answers 422 to a form body (tested), but this rule does not
     depend on a FastAPI version, and it makes any request from another site "non simple": the browser sends a
     preflight, which CORS refuses.
- **No CSRF token**: a single-user application on the loopback with no cookie and no session has nothing a token
  would protect further. The browser sets `Origin` / `Sec-Fetch-Site` and a page cannot forge them; the JSON
  rule forces a preflight; the Host rule stops rebinding.
- **Through Vite** (checked with a real Vite 8.3.4 and an echo server): the proxy's `changeOrigin: true` rewrites
  `Host` to the backend's (`127.0.0.1:<backend port>`) and forwards `Origin` unchanged
  (`http://127.0.0.1:5173`), so on port 5173 the Host check is Vite's own (`server.allowedHosts`: it answered
  "Blocked request" to a foreign Host) and the Origin check is ours. A GET without `Origin` is accepted; reads
  from another site are stopped by CORS (no `Access-Control-Allow-Origin`) and by the Host rule.
- Format: `{"detail": {"code", "message"}}` (D-063). Tests: `tests/api/test_guard.py`.

## D-062 — Writing `.env` from the API (M2.c1)

- **Where**: the path is `Settings.model_config["env_file"]` (one source of truth; tests redirect it with
  `monkeypatch.setitem`). **What**: a closed list: `VOCAB_GEMINI_API_KEY`, `VOCAB_GROQ_API_KEY`,
  `VOCAB_OLLAMA_BASE_URL` (`app/services/env_file.py`).
- **Editing** is a pure function on the text (`set_variable`): every active `NAME=` line (also `export NAME=`,
  name matched without regard to case, like pydantic-settings) is replaced in place; otherwise the line is
  appended with the file's own line ending (CRLF or LF; a missing final newline is not added). A commented line
  is left alone; comments, other variables and their order are kept. Removing is `NAME=` (an empty value is "not
  configured"); removing an absent variable, or setting the same value, writes nothing and records no event. A
  missing file gets a two-line comment header.
- **Validation**: a key is 8 to 512 printable characters with no space, quote, backtick, `#`, `=` or `$` (`$`
  because python-dotenv expands `${VAR}` in unquoted values). The Ollama address uses the same rules (`=` allowed,
  1 to 512 characters) then `ollama._normalize` (http or https and a host; stored without the trailing slash).
  Messages never contain the value.
- **A process environment variable wins** over `.env`, so editing would change nothing: refused with 409
  `set_in_environment` (present even if empty, compared without case).
- **Writing**: a module `threading.Lock` held from the read until the settings cache is cleared and the gateway
  reloaded (two edits cannot overwrite each other); a temporary file in the same folder, flushed and fsynced, then
  `os.replace` (atomic); a UTF-8 BOM is dropped. On Windows `os.replace` fails with `PermissionError` while an
  editor or an antivirus holds the file: 3 attempts 100 ms apart, then 409 `env_file_locked`. Another `OSError` is
  500 `env_file_write_failed`. The temporary file is always removed.
- **Limit**: a multi-line quoted value (allowed by python-dotenv) is not handled; unlikely for these variables.
- uvicorn `--reload` only watches `*.py`, so writing `.env` does not restart the server: the API clears
  `get_settings()` and calls `gateway.reload()` itself.

## D-063 — One error format and 422 answers without `input` (M2.c1)

- Every error is `{"detail": {"code", "message", ...}}` (`app/api/errors.py`): `code` is stable (the settings page
  maps it to an i18n key), `message` is English and masked with the configured keys.
- FastAPI's own 422 answers include the received value (`input`), which would send a pasted key straight back to
  the page and into any proxy log. A `RequestValidationError` handler answers 422 `invalid_request` with only
  `errors: [{loc, message}]`; `input` and `ctx` are dropped. Tested with malformed bodies containing a recognisable
  string.
- Codes added by M2.c1: `forbidden_host`, `forbidden_origin`, `cross_site_request` (403), `unsupported_media_type`
  (415), `invalid_request` (422), `invalid_credential` (422), `invalid_setting` (422, with `key`),
  `unknown_provider` (404), `set_in_environment`, `env_file_locked`, `test_in_progress`, `demo_read_only` (409),
  `env_file_write_failed` (500), `database_unavailable` (503). Unknown routes keep FastAPI's plain 404.

## D-064 — AI and settings endpoints (M2.c1)

- `GET /api/ai/status`, `PUT|DELETE /api/ai/providers/{name}/credential`, `POST /api/ai/test`,
  `GET /api/ai/usage?days=`, `GET|PATCH /api/settings`. The gateway comes from `Depends(get_gateway)` (tests
  replace it). `Gateway` got two read-only accessors, `providers` and `provider_order()`.
- **`credential_source`**: `environment` when the variable exists in the process (it blocks editing, even empty),
  else `env_file` when the provider is configured, else `none`. Responses carry no key, no end of key and no
  Ollama address (tested on every response, `/openapi.json`, logs, `event_log` and `repr`).
- **Event after the file**: `ai.credential_changed {provider, action: set | removed}` (new event type, no
  migration: `event_type` is a free string) is written in a short transaction once the file and the gateway are
  up to date. If that write fails (database absent or busy) the file is already changed, so the failure is logged
  (masked) and the answer stays 200.
- **Test endpoint**: a plain `def` route with no database session in its dependencies (D-038); an unconfigured
  provider answers 200 `unavailable` / `no_provider_configured` without any request; 409 `test_in_progress` when
  the same provider is being tested.
- **Usage**: every day of the window is returned, empty ones included (today first), in a read-only session
  (`PRAGMA query_only`, reset to OFF afterwards because the connection returns to the pool).
- **Settings**: `GET` returns an object keyed by setting with `value, default, is_default, type, minimum, maximum,
  choices, item_choices`; `PATCH` is all-or-nothing (one invalid value rolls everything back: 422 `invalid_setting`
  with the key). `_demo` and unknown keys are refused. The provider order is read by the gateway on every call, so a
  PATCH applies at once.
- **Demo**: when the demo marker is present (or `VOCAB_DEMO`), credential writes, the connection test and a PATCH
  of `ai_provider_order` answer 409 `demo_read_only`; other settings stay editable; reads work.
- A `reload()` while a test runs: the running call keeps the old provider object and its success may be noted in
  the new health state. Harmless.

## D-065 — Shared connection-test service (M2.c1)

- `app/services/ai_connection_test.py`: `run_connection_test(gateway, session_factory, provider, secrets)` makes
  the `connection_test` call pinned to the provider and returns a `ConnectionTestReport` (status, reason, model,
  time, tokens, last logged error code and HTTP status, masked message of 300 characters, `detail_kind`). The CLI
  (`ai test`, including the audio check) and `POST /api/ai/test` both use it; the CLI tests passed unchanged.
- A lock per provider (`acquire(blocking=False)`) raises `TestInProgress`: a double click would spend the free
  quota twice. The lock is per process, which is enough for one local backend.
