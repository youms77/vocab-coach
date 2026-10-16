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
