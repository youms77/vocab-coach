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

## D-029 — Planner formula and constants (M1.b; block 3 amended by D-137)

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

## D-035 — Provisional direct writes, `deck.item_added`, sessions in services (M1.c; direct writes closed in M6.a2b)

**Closed (M6.a2b, D-191)**: `app/demo/direct_writes.py` is deleted; the demo writes nothing directly any more.

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

## D-066 — What the settings page shows, and where (M2.c2)

- **One page, `/settings`** (`frontend/src/features/settings/`), in this order: AI providers (one card each), provider
  order, AI usage, study settings. A "Settings" link in the top bar. The language and theme switches stay in the top
  bar.
- **Study settings are built from `GET /api/settings`** (type, bounds, default): the page only decides the groups
  (daily study, study day, consolidation, audio), the labels / hints (i18n, per key) and the spin-button steps of the
  float settings. Each group is its own form and sends only the keys that changed, in one `PATCH`. Bounds and number
  shape are checked before sending; the backend stays the authority (a 422 `invalid_setting` is shown on the field
  its `key` names, with the English reason).
- **`ui_language` is not on the page.** The interface language is the top bar's choice, stored in the browser
  (M0, never derived from the browser language). Showing the backend setting too would give two sources that can
  disagree. Syncing them (so that, e.g., exports or AI prompts know the language) is left for the milestone that
  needs it.
- **`tts_rate` is shown** although speech synthesis comes with M4: SPEC module J lists "audio speed", and the value
  is stored now.
- **Degraded-mode banner on every page** (`components/AiBanner.tsx`) when `GET /api/ai/status` says `degraded`, with
  calmer wording when the owner turned AI off (`ai_off`), and a link to `/settings` (not shown on that page). Nothing
  while loading or when the backend is down (the home page already says so). The status is refetched every 30 s so a
  cooldown that ends clears the banner.

## D-067 — Keys and addresses on the page (M2.c2)

- The key field is `type="password"`, `autocomplete="off"`, no spell check; it is **never pre-filled** (the API
  never returns a key) and is **cleared as soon as the backend accepted it**; on failure the value stays so it can be
  corrected. The Ollama address is `type="url"` (not secret, D-062) but is not returned by the API either, so the
  page says "configured", never the address.
- Empty or blank values are refused on the page, without a request.
- **Remove asks for confirmation inline** (two buttons, no browser `confirm()` dialog): removing a key the owner may
  not have kept elsewhere is the only destructive action here.
- `credential_source: "environment"`: field, Save and Remove disabled, with the variable name and where to change it;
  the connection test stays possible (the key exists).
- **Demo database** (`demo: true`): keys, test and order are disabled with an explanation; study settings stay
  editable (D-064).

## D-068 — Errors on the page (M2.c2)

- `ApiError` (`api/client.ts`) now carries `code` and the whole `detail` (D-063), and `apiSend()` sends JSON bodies
  with `Content-Type: application/json` (the guard refuses anything else, D-061).
- `features/settings/errorMessage.ts` maps the 14 known codes to `errors.<code>` i18n keys; an unknown code gets
  "Unexpected error (HTTP n)"; a failed `fetch` and a 502 / 504 from the Vite proxy mean "cannot reach the local
  server". The English `message` is shown under the translated sentence only for `invalid_credential` and
  `invalid_setting` (it says *why*, never the value); the provider's own message after a failed test is behind a
  "Provider message (English)" disclosure.
- `last_error` kinds and test `reason` values have their own i18n keys (`settings.errorKinds.*`,
  `settings.test.reasons.*`).

## D-069 — The connection test on the page (M2.c2)

- A TanStack Query mutation per provider; the button is disabled while it runs and shows "Testing… n s" (seconds
  counted from the mutation's `submittedAt`, ticking every second) with a hint that it can take up to ~90 s. The
  result (status, model, time, tokens, translated reason, HTTP status) is announced in an `aria-live` region.
- A double click cannot send a second request (disabled button); a test started elsewhere gives 409
  `test_in_progress`, shown as a message.
- After a test, the AI status and usage are refetched (the test changes health and adds call-log rows). Leaving the
  page during a test does not cancel the request; the result is not shown when coming back, but the refreshed status
  reflects it. Accepted for a tool the owner opens rarely.

## D-070 — Frontend tests with a small API router (M2.c2)

- `src/test/mockApi.ts` replaces `fetch` with a router keyed by `"METHOD /path"` (without `/api` and the query),
  records every call (method, path, headers, parsed JSON body) and answers 404 to an unknown route, so a missing mock
  fails visibly. `apiErrorResponse()` builds the backend's error format.
- A `Response` body can be read once: the home page test's single shared response now returns a clone per request
  (the layout makes two requests since the banner exists).

## D-071 — Markdown import parser (M3.a, 2026-10-16)

- `app/domain/markdown_import.py`, pure, no clock (`today` is a parameter: the caller's study day). It never raises
  on user input: everything odd is an `ImportProblem {line, severity: info|warning|ambiguous|error, code, message
  (EN), suggestion?}` with a **stable code** (M3.c turns codes into i18n keys). Line numbers are the file's, 1-based,
  header included. `\r\n`, `\r` and `\n` all end a line (not `str.splitlines`, which also splits on Unicode line
  separators and form feeds and would shift the numbers); a UTF-8 BOM is removed.
- **Header**: only when the first non-blank line is `---` and a later `---` closes it (else `unclosed_header` and the
  file is read as a plain list). Loaded with a subclass of `yaml.SafeLoader` that keeps timestamps as text: PyYAML's
  own date constructor raises `ValueError` on `2026-13-01`, which would break the "never raises" rule and turn a bad
  deadline into `invalid_header`. The deadline must match `YYYY-MM-DD` and be a real date (`invalid_deadline`,
  ignored); a past one is kept with `past_deadline`. Unknown key → `unknown_header_key`; a list or mapping as a value
  → `invalid_header_value`; invalid YAML or a non-mapping → `invalid_header` (warning), header empty, body still read.
- **Body**: bullets `-` `*` `+`, `1.` `1)`, checkboxes, plain lines; `**` `__` `*` `_` and backticks around the term
  are removed. Headings (`#` + space) and horizontal rules are `info` and skipped. The first `|` separates the
  sentence.
  - **Ambiguous** (returned with `include: false`): `multiple_separators`; `looks_like_definition` (` = `, ` : `,
    `word: x`, ` -> `, ` – `, ` - ` without `|`; suggestion `{term, note}`); `looks_like_sentence` (more than 8
    words or 80 characters without `|`); `nested_item` (a bullet indented 2+ columns more than the first item, so a
    uniformly indented list is not "nested"); `empty_term`; `term_too_long` (more than 300, the column size).
  - **Warnings**, imported anyway: `term_not_in_sentence`; `duplicate_in_file` (the kept line is a clear one with a
    sentence, else the first clear one).
- **Limits**: 256 KB (UTF-8 bytes) and 1 000 non-blank body lines, else `too_large` (error) and no rows. The CLI also
  reports `not_utf8`.
- **Type guess**: 1 word → `word`; 2–4 words, or 5 starting with "to" → `collocation`; longer → `phrase`.
  `spoken_formula` is never guessed.
- `check_term()` is shared by the parser and the commit, so the server re-validates rows with the same rules.

## D-072 — Normalised form and naive lemma (M3.a)

- `normalize_term` (`app/domain/normalize.py`): NFKC, casefold, typographic apostrophes / quotes / dashes to ASCII,
  spaces collapsed, final `.,;:!?` and enclosing quotes removed (repeatedly), initial `to ` removed, placeholders
  unified with or without parentheses (`someone`/`somebody`/`sb` → `sb`, `something`/`sth` → `sth`, `one's`,
  `someone's` → `sb's`). `lexical_item.term` keeps the user's spelling. Known limit: `to a large extent` becomes
  `a large extent` (the rule cannot tell an infinitive from a preposition); harmless, since a match is only a proposal.
- `naive_lemma`: **single-word terms only** (None otherwise, so expressions never get "possible" matches). It is a
  *stem*, not a dictionary form: plural `-ies/-es/-s`, `-ed`, `-ing`, undoubled consonant, then a final `-e` dropped and
  `-y` → `-i`, so `study/studies/studied/studying` and `estimate/estimated` meet. Words under 4 letters, words with a
  non-letter, and an exception list (news, series, species, analysis, data, physics, statistics, bias, thing, need...)
  are left alone. No new dependency.
- **Matching**: same normalised form = `exact`; same lemma, different form = `possible`. Compared with every term,
  archived and known included, and answered with the existing term's status and decks. **Nothing is ever merged
  automatically**: the normalised form is not unique in the database (homographs), on purpose.
- `term_in_sentence`: each word of the term (placeholders left out) must appear in order in the sentence, by equal
  stem or as a prefix (4+ letters); irregular forms (`drew` for `draw`) give the warning.

## D-073 — Library services and their errors (M3.a)

- `app/services/library.py`, `importing.py`, `triage.py`, `duplicates.py`, in the caller's transaction (D-023).
  User refusals are `LibraryError` subclasses with `status` and `code`; `app/api/errors.py` turns them (and
  `InvalidItemTransition`, 409 `invalid_transition`) into the D-063 format with their extra fields.
- `create_item` writes the term in `draft` with `item.created`, then moves it to `triage` or `queued` through
  `set_item_status` (D-025 table and events). `add_item_to_deck` writes `deck.item_added` and refuses a second link to
  the same deck. New decks go to the end of the queue (`queued`, D-026).
- **Quick add** goes to `queued` directly (the user typed the term because they want to learn it) and, without a deck,
  to a deck named "Quick adds" created the first time. A duplicate without `on_duplicate` is a 409 `duplicate_term`
  with the candidates; `attach` links the existing term (status untouched), `new` creates another one.
- Editing a term's spelling recomputes `normalized_form` and `lemma` and returns the duplicates without blocking.
- **Search**: `q` matches `lower(term)`, `normalized_form` (with the normalised query) and `lower(origin_sentence)`
  with escaped `LIKE` (`%`, `_`, `\`). SQLite's `lower()` only folds ASCII; the normalised-form branch covers accented
  terms. Deck, domain and source filters go through `deck_item` (a term has no source of its own); archived terms are
  excluded unless asked for.

## D-074 — Import preview and commit (M3.a)

- `preview()` writes nothing (the CLI also sets `PRAGMA query_only`). It adds library problems to each row:
  `duplicate_exact` (info), `duplicate_possible` (warning), `already_in_deck` (info, when a target deck is given),
  `existing_status_kept` (info: attaching a `known` or `archived` term does not change its status).
- `commit()` receives the rows **as validated by the user** (`term, sentence, item_type, include, confirmed,
  on_duplicate: attach|new|skip, attach_to`) and re-checks each. An included row that is still ambiguous needs
  `confirmed: true`, and only `looks_like_definition` / `looks_like_sentence` can be confirmed (an empty or over-long
  term or a stray `|` must be corrected); otherwise 422 `row_rejected` with the row index, line and codes. All rows
  are checked before anything is written.
- **Defaults**: exact duplicate → `attach` (the row's sentence goes to `deck_item.context_sentence`), possible
  duplicate → `new`, a term already in the target deck → skipped, the same term twice in the rows → the first wins.
- **Header mapping**: `source` → `source.title` (+ `context` → `source.context`); without `source`, `context` →
  `deck.description`; `domain` → `deck.domain` and `source.domain`; `deadline` → `deck.deadline`. A new deck takes
  `target.new_deck_name`, else the header's `deck`, else 422 `deck_name_required` (the CLI uses the file name). An
  existing target deck keeps its own fields: the header is ignored.
- One transaction; tested by injecting a failure in the middle (no row, no event left).

## D-075 — Triage semantics (M3.a)

- `learn` and `unsure` → `queued`, `known` → `known`; one `item.triaged` per term (the decision itself is kept, so
  statistics can tell `unsure` from `learn`). **Why `unsure` is queued**: discovery starts with the meaning hidden
  (module B), so an unsure term costs one short discovery at most, and leaving it in limbo would hide it from the
  planner.
- All or nothing: unknown id → 404 `item_not_found`; a term not in `triage` → 409 `not_in_triage` with the ids; the
  same id twice → 422 `duplicate_decision`.
- The triage list shows the term, its type, its decks and a sentence (the deck's context sentence, else the origin
  sentence), **never a usage sheet**, so the self-assessment is not biased.

## D-076 — Deletion rules (M3.a)

- A term with **history** (a card, hence reviews; an error event; a production target; a consolidation target)
  cannot be deleted: 409 `item_has_history` with `suggestion: "archive"`. Otherwise `item.deleted`, then the row
  (deck links follow by cascade).
- A deck cannot be deleted when one of its terms has started discovery (`discovered_at`) or has history, **even
  through another deck** (strict reading, approved with the plan): 409 `deck_has_history` (pause it or mark it done
  instead, M4). Otherwise the terms that belong to no other deck are deleted (`item.deleted` each), then
  `deck.deleted {deck_id, deleted_item_ids}`.

## D-077 — Merge rules (M3.a)

- `merge(source, target)` folds the source into the target and deletes it. Both have cards → 409 `merge_conflict`;
  only the source has cards → the direction is inverted (the term with the review history is kept, `inverted: true`);
  same id → 422 `merge_same_item`.
- Moved to the target: deck links (when both are in the same deck, the target's empty context sentence is filled and
  the source's link dropped); `origin_sentence`, `notes`, `part_of_speech`, `origin_error_event_id` when the target
  has none; error events; production and consolidation targets (a duplicate row for the same attempt or task is
  dropped); the usage sheets and exercise templates **only when the target has none** (otherwise the source's are
  deleted with it). The kept term's status is unchanged. `item.merged` is written.
- Duplicate groups (`GET /duplicates`): exact groups by normalised form, then possible groups by lemma with at least
  two forms; each item says whether it has cards, so the page can show which merges are possible.

## D-078 — New events and the demo (M3.a)

- New event types (open set, no migration, D-015), payloads in `app/domain/events.py`: `deck.updated {deck_id,
  fields}` and `item.edited {lexical_item_id, fields}` (field **names** only, never values), `deck.deleted {deck_id,
  deleted_item_ids}`, `item.deleted {lexical_item_id}`, `import.completed {deck_id, lines_read, imported, attached,
  skipped, ambiguous}`. `item.merged` and `item.triaged` already existed.
- The demo creates sources, decks, terms, deck links and triage decisions through the services (`direct_writes.py`
  keeps productions, errors and sessions until M4/M5). Comparing a 60-day seed (seed 42, anchor 2026-09-01) before
  and after: **every table is identical except `lexical_item`**, where `normalized_form` changed for 27 of 113 terms
  (e.g. `to a large extent` → `a large extent`) and `lemma` is now filled for single words. The event log (types,
  counts, payloads) and every status are the same. The determinism tests compare two runs, so they still pass.
- Library writes are allowed on the demo database (a throwaway sandbox); only AI keys and provider order are
  protected there (D-064).

## D-079 — Validation context for the gateway (M3.b)

- `Gateway.generate_json(..., validation_context=...)` passes a context to Pydantic validation. The enrichment
  schema reads `{"terms": {ref: term}}` from it, so the business rules of `app/domain/exercises.py` (term present in
  every example, gap-fill answer matches the term, ...) run inside the validator. A broken rule is a validation
  error: the gateway asks for one repair, then answers `incomplete`. No second validation layer in the service.

## D-080 — Output budget per call (M3.b)

- `generate_json(..., max_output_tokens=...)` overrides the task's ceiling for one call. A term of the `enrichment`
  task costs about 1 500 output tokens (sheet about 900, exercises about 450), so a batch asks for
  `ENRICHMENT_TOKENS_PER_TERM x terms`. A suggestion of `list_extension` costs about 50 tokens
  (`EXTENSION_TOKENS_PER_SUGGESTION` x count). These are estimates to tune after the owner's first real calls.

## D-081 — One enrichment run is one batch (M3.b)

- Batches of 5 terms (`ENRICHMENT_BATCH_SIZE`, SPEC: 5 to 10, lower end because of the free-tier output limits).
  The AI is called with no session open (D-038); results are written in one short transaction after checking each
  term again (still there, same spelling, no new current sheet).
- `incomplete`, or `all_failed` on several terms: the terms are retried one by one under a time cap; a term that
  still fails alone gets a skeleton sheet (`needs_completion`, no exercise) the user completes by hand. Any other
  `unavailable` reason writes nothing: terms stay pending (degraded mode).
- A process-wide lock refuses a second run (`enrichment_running`, 409); a run from another process (the CLI) is
  caught by the re-check before writing. An AI failure is HTTP 200 with `status` and `reason`, not an error.
- CLI `library enrich` loops over batches until nothing is left or the AI is unavailable (exit 1);
  `--dry-run` lists the waiting terms; `library extend <deck_id> --count 10..30`.

## D-082 — Typed recall follows the user's sheet (M3.b)

- When the user saves a sheet, the "French / definition to English" typed-recall template is refreshed from the
  new translations and definition, so the exercise never contradicts the sheet.

## D-083 — Editing, versions and consent (M3.b)

- A sheet edit creates a new version (`origin = user`); old versions are kept and listed. `base_enrichment_id`
  protects against a stale editor (409 `sheet_changed`). An edited sheet is never regenerated without
  `confirm_overwrite` (409 `sheet_edited`). Regeneration keeps templates the user edited or reviewed. A term
  without a sheet accepts a hand-typed one (manual entry).
- Exercise templates are edited one by one (`PATCH /api/exercises/{id}`), validated by the same rules (422
  `invalid_exercise`), and logged.

## D-084 — Extension suggestions and the deck (M3.b)

- Suggestions are created in triage with origin `extension`, linked to the deck with their example sentence as
  context. Exact duplicates of the library and repeats are dropped; possible duplicates are kept and reported.
- Per SPEC only retained terms stay in the deck: an extension suggestion triaged as `known` leaves the deck
  (`deck_item.removed` event) but stays in the library as `known`, so it is never suggested again. Imported terms
  keep their deck links whatever the decision (D-075).

## D-085 — Library pages: scope and conventions (M3.c1)

- M3.c is delivered in three stacked branches (c1 library, c2 import / triage / duplicates, c3 sheets and
  extension) to keep each review small. No component library: plain components and the existing CSS tokens.
- Library error codes share `describeError` (`features/settings/errorMessage.ts`); a code unknown to the front end
  falls back to the generic message. `apiSend` returns `undefined` for 204 answers (DELETE routes).
- A possible duplicate on quick add is never blocking: the 409 `candidates` are shown and the user chooses
  `attach` (to a candidate) or `new`, as the API contract defines.
- The deck filter can be preset with `/library?deck=ID`; filter changes reset the page to the first one.
- Sheet-content search stays out: `q` searches terms only (backend unchanged); to decide with M3.c3.

## D-086 — Import review: local state sent as is (M3.c2)

- The preview is never written: the review table is local state (`importReview.ts`) and the commit sends every
  row (`include` false for the rows left out), so the backend's `lines_read` and `skipped` match the file.
- Ambiguous rows start unchecked. Only `looks_like_definition` and `looks_like_sentence` offer "Import anyway"
  (`confirmed: true`), as the backend accepts nothing else; other ambiguities must be corrected. A corrected term
  is sent without `confirmed` (the backend checks it again) and without the preview's duplicate choice, since its
  duplicates may differ (`invalid_attach_target` otherwise); the backend default then applies.
- The target and intake are chosen after the preview, so the preview is called without `deck_id`; terms already
  in an existing target deck are skipped by the commit and counted in "skipped".
- The browser reads the file (`File.text()`, D-061) and checks the 300 000-character limit before sending.
  Example files stay outside the bundle: the user picks them with the file field.
- The summary's `ambiguous` count is every row still ambiguous when sent (confirmed or not), so it is worded
  "ambiguous lines in the list", not "left out".

## D-087 — Problem codes and messages (M3.c2)

- Each `ProblemCode` and severity has an i18n key; an unknown code falls back to the backend's English message.
  The `suggestion` object fills placeholders (`key`, `kept_line`). Severity is written as text (and ⚠ for
  ambiguous / error), never shown by colour alone.

## D-088 — Triage page (M3.c2)

- One `POST /api/triage` sends every choice made (terms left undecided stay in triage); the backend is all or
  nothing, so a 409 `not_in_triage` saves nothing, the list is refetched and the remaining choices are kept.
- Keys 1 / 2 / 3 choose for the focused card, else the first undecided term; they are ignored with modifiers and
  inside text inputs, textareas, selects and editable content (radios and checkboxes still work).
- The card shows the term, its type, sentence and decks only: never a usage sheet (active recall).
- The "n to sort" count on the Library page reuses `GET /api/triage` (no new endpoint).

## D-089 — Duplicates page (M3.c2)

- The user picks the term to keep (default: the one with review cards, which the backend would keep anyway) and
  merges each other term into it with the existing `useMergeItem`; the duplicate groups live under the `items`
  query key so a merge refreshes them. An inverted merge is reported in the message.

## D-090 — CSS fixes from the first browser check (M3.c2)

- Text-like inputs are styled by `input:not([type])`, `search`, `date` and `textarea` too (M3.c1 fields had native
  styling). `.library-page` and `.import-review` use `grid-template-columns: minmax(0, 1fr)` so a wide table
  scrolls in its `.table-wrap` instead of widening the page.

## D-091 — Sheet visibility and search (M3.c3, owner's decisions)

- The library search (`q`) stays on terms only: sheet content is not searched. The sheet-state filter covers the
  need for now; a content search would be a backend change to plan later. Closes the open point of D-085.
- On a term's page the usage sheet and its exercises are behind a "Show the usage sheet" button, closed on every
  visit. Before discovery (`draft`, `triage`, `queued`) a warning says the sheet gives away module B's answer.
  Nothing is fetched until the user opens it.

## D-092 — Sheet editor and stale versions (M3.c3)

- The editor works on a draft with every text as a string (`sheetForm.ts`); saving trims, turns empty text into
  `null`, drops rows with an empty required field and sends `schema_version: 1` only with the backend's fields
  (`extra="forbid"`). The client checks the one content rule (a simple definition or a French translation)
  before sending; the backend stays the judge.
- The editor keeps the version it was opened from and sends it as `base_enrichment_id`. On 409 `sheet_changed`
  the edits stay on screen; "Load the latest version" replaces them only after a confirmation. There is no
  automatic merge.
- A term with no sheet gets the same editor with `base_enrichment_id: null` (manual entry, degraded mode).

## D-093 — Regeneration consent (M3.c3)

- "Generate a new version" always sends `confirm_overwrite: false` first. The backend answers 409
  `sheet_edited` before any AI call when the sheet was edited; the page then asks for consent in an inline
  alertdialog, and only "Replace my version" resends with `true`. Refusing sends nothing. A failed regeneration
  (`failed`, `unavailable`) says the existing sheet is kept.
- A sheet to complete (`needs_completion`) offers "Try the AI again" through `POST /enrichment/run {item_ids}`
  instead of regeneration, since it was never the user's.

## D-094 — Exercise template editing (M3.c3)

- One form per known type (fields of `app/domain/exercises.py`), lists typed one entry per line; the whole
  content is sent and validated by the backend (422 `invalid_exercise` shows each field with the backend's English
  message, like `invalid_request`). An unknown type is shown read-only. Answers are visible here: editing is not
  a drill, and the panel is behind the sheet's reveal button anyway.

## D-095 — Batch enrichment loop (M3.c3)

- The page calls `POST /enrichment/run` (one batch of at most 5 terms) again with the same scope while terms
  remain. It stops on: nothing left (`remaining` 0 or an empty batch), any AI failure (`unavailable` or a
  `reason`, shown with the degraded explanation and links for manual entry), a batch that wrote nothing (avoids a
  loop when every term changed meanwhile), an error (409 `enrichment_running` included), or the user's "Stop
  after this batch" (a flag: the running batch always finishes on the server). Leaving the page sets the same
  flag. No client timeout: a batch may take minutes when it is split.
- `aiReasons.*` holds the gateway's reasons worded for any AI task; `settings.test.reasons.*` keeps the
  provider-test wording.

## D-096 — List extension in the decks page (M3.c3)

- "Extend this list" sits on each deck row (number 10 to 30, default 20 as `DEFAULT_COUNT`); the created terms
  wait in triage and "Sort them now" opens the existing triage page filtered on the deck (`/triage?deck=ID`), so
  the I know it / not sure / to learn choice and D-084 apply unchanged. Possible duplicates link to the existing
  terms and to the duplicates page.

## D-097 — Injectable clock for API routes (fix, after M3.c3)

- `GET /api/ai/usage` reads the current time through the `get_now` FastAPI dependency (`app/api/clock.py`,
  `NowDep`) instead of `datetime.now(UTC)`. Behaviour for the user is unchanged (`get_now` returns `utcnow()`).
- The API test fixture overrides `get_now` with the same `FakeClock` the gateway uses, so a call logged by the
  gateway and the route's "today" always agree; the test passed only on 2026-10-16 before.
- Other routes still call `utcnow()` directly; a route whose result depends on "today" in a test should use
  `NowDep` rather than freezing time globally.

## D-098 — Fixes from the pre-merge verification of M2.c2 to M3.c3

- **Source filter on `/library`** (SPEC module A lists deck, field, source, type and status filters; the API had
  `source_id` since M3.a but the page did not offer it). There is no `/api/sources` route: the choices are the
  sources of the decks (`sourcesOf` in `api/library.ts`), once each, sorted by title. A source no deck uses
  cannot hold terms (a term reaches a source only through a deck, D-073), so nothing is missing from the list.
  No backend change.
- **Home page**: the "Import a word list (coming soon)" text was left from M0; it now links to the import and
  the library until today's session arrives in M4.
- **i18n**: the main navigation's `aria-label` was hard-coded ("Main"); it is now `nav.label`.
- Merged as one pull request (the tip, `feat/m3c3-sheets`) rather than one per milestone: the intermediate
  branches contain the date-dependent test fixed by D-097, so their own checks fail on any day but 2026-10-16.

## D-099 — M4.a split in two, owner's choices for the demo (M4.a, 2026-10-17)

- The M4.a plan touched about 24 significant files, so it is cut in two on the same branch
  `feat/m4a-session-backend` (started from `origin/main`, which holds M3.c3 and D-097; the local `main` was
  behind): **M4.a1** (domain, services, every route, tests, this documentation) and **M4.a2** (the planner's
  "usable sheet" filter, the demo sheets, the simulation through the real session service and exercise choice).
  The filter goes with the demo because the current demo has no sheet: with the filter alone, the simulated
  learner could never discover a term.
- **Owner's choices for M4.a2** (plan approval):
  - terms without a full demo sheet get a **minimal hand-typed sheet** (French translation only, no exercise
    template). They can be discovered and still go through `self_assessment` in review. A term with no sheet
    at all could never reach `learning` once the planner skips it, so "no sheet" in the milestone text becomes
    "no template";
  - the simulation completes discoveries **without initial ratings**, like the app (D-104).
- **Note (M4.a2, owner's choice at the plan)**: a minimal sheet saved through `save_sheet` gets the
  `typed_recall` template that the service derives from the French translation (D-082), like any sheet typed
  in the app. So minimal terms use `self_assessment` for their receptive card only; their young productive
  cards use typed recall.

## D-100 — Exercise choice and the maturity threshold (M4.a1)

- `app/domain/exercise_choice.py` replaces `DEMO_EXERCISE_TYPES` (the demo moves to it in M4.a2). A card is
  **mature** when it is in Review state with a stability of at least `MATURE_STABILITY_DAYS = 21` days (the
  demo's threshold, D-034); new, learning and relearning cards are young whatever their stability.
- Receptive: young -> `recognition_in_sentence`; mature -> `listening_comprehension` (even `reps`) /
  `recognition_in_sentence` (odd). Productive: young -> `typed_recall` (even) / `gap_fill` (odd); mature ->
  `sentence_production` (even) / `spoken_answer` (odd). Deterministic, so tests and the demo are reproducible.
- Fallback: the other type of the pair, then any other template of the same direction (in the order of
  `EXERCISE_TYPES`), then `self_assessment` (D-101).
- Several templates of one type: index `(reps // 2) % n` in id order. `reps % n` would always pick the same
  one, because the type itself alternates on the parity of `reps`.
- The client may send another consistent type than the one proposed (for example a self-assessment instead of
  a spoken answer): the server checks the direction and the template, not the choice.

## D-101 — `self_assessment`, the degraded review (M4.a1)

- A new exercise type with no stored template, used when a term has no template of the card's direction (AI
  unavailable, sheet typed by hand). Receptive prompt: the term and its context sentence (the original one,
  else the sheet's first example); the user recalls the meaning. Productive prompt: the sheet's first French
  translation and simple definition, and the context sentence with the term replaced by `___`; the user recalls
  the term. The reveal (`POST /api/reviews/reveal`) gives the term, definition, translations and sentence.
- It is self-graded: no proposed rating (`auto_rating` null), four buttons as SPEC module C says. A productive
  prompt with nothing to show (no sheet, no sentence) carries the warning `no_cue`.
- `sentence_production` and `spoken_answer` are self-graded too until AI correction (M5) and recording (M6):
  a typed sentence is only checked for the term (`term_missing`).
- *Updated in M6.a2a*: `sentence_production` is checked by the AI since M5.a1 (D-129) and `spoken_answer` since
  M6.a2a (D-183): neither is self-graded any more when the check is available. Without it (no key, no network, a
  failed transcription or correction, or the user skipping the check) both stay self-graded exactly as above.
  The "nothing is recorded yet" note of D-123 is for the M6.b screens.

## D-102 — Grading rules (M4.a1)

- **Normalisation**: NFKC, typographic apostrophes to `'`, case folding, single spaces, punctuation removed at
  both ends. For a term that starts with "to", an initial "to" is optional on both sides. Expected forms are
  the template's `answer` and `accepted`.
- **Outcomes**: `exact`; `form` (typed recall only); `typo`; `wrong`; `empty`. Order of the checks: empty,
  exact, confusion (-> wrong), form, typo, wrong.
- **Typo**: Damerau-Levenshtein in its "optimal string alignment" variant (insertions, deletions,
  substitutions, transpositions of two adjacent letters; no substring edited twice), written by hand. The
  threshold depends on the length of the nearest expected form: 0 up to 3 characters, 1 from 4 to 8, 2 beyond.
  The diff shown for a typo is `difflib` on characters (standard library).
- **Confusion**: a typed answer that is, once normalised, another term of the library or a word of the sheet's
  `confusables` or `french_speaker_pitfalls.wrong` is `wrong`, never `typo` ("affect" for "effect"): a
  confusion is not a slip of the finger, and M5 will log it as an error.
- **Form**: the milestone said "per `is_form_of`", but that function (written to check AI output) accepts any
  word with the same first letter as an irregular form, so "cat" would be a form of "confounder". Grading
  accepts **regular inflections only**: same stem, and the given word is longer than the expected one (the
  stemmer maps both "rule" and the typo "rul" to "rul"). Irregular forms count when the template lists them
  in `accepted`. Departure from the milestone text, reported to the owner.
- **Proposed rating**: exact or form -> Good, or Hard when the answer took more than 2 x the estimate of its
  duration class (D-028, observed medians when available); typo -> Hard; wrong or empty -> Again. Easy is never
  proposed. Choice exercises: right -> Good (Hard when slow), wrong -> Again, no choice -> `empty` (Again).

## D-103 — Active recall in the API (M4.a1)

- A review step (`GET /api/session/{id}/next`) carries the prompt only: never `answer`, `accepted`,
  `example_answer`, `meaning`, `meaning_fr`, `distractors` or the index of the right option, and a productive
  card never carries the term. `app/domain/review_steps.py` lists these keys (`SOLUTION_KEYS`). A domain test
  checks every type and direction; an API test walks every step of several months of reviews (every exercise
  type reached) and of discoveries, and fails if one of these keys appears.
- Choice options are shuffled by the server with `random.Random("card:<id>:reps:<reps>")`: the step and the
  grading see the same order without storing it, and the order changes between reviews.
- **Exception**: `listening_comprehension` sends its sentence, because speech synthesis runs in the browser.
  The interface must hide it until the answer (M4.c).
- The solution and the sheet summary are returned only after an attempt: by `POST /api/reviews/grade` (any
  answer, even empty) or `POST /api/reviews/reveal` (self-graded types only; 422 `exercise_mismatch` for a
  graded type). Both write nothing (tested by counting the rows of every table).
- Discovery's immediate exercises are read with `GET /api/discovery/{item_id}/exercises` (prompts only; the
  term must be `discovering`). Added because the existing `/items/{id}/exercises` returns full templates.

## D-104 — Discovery creates the cards without initial ratings (M4.a1)

- `POST /api/discovery/{id}/complete` calls `complete_discovery` without initial ratings: both cards stay `new`,
  due at the start of the next study day (D-025). Discovery is a presentation (the sheet was just read), not a
  retrieval from memory; rating it would schedule the first real review from an answer given with the solution
  in view. The first real review is the next study day.
- `discovery.completed` goes to `payload_version` 2 with `guess` (step 2) and `exercise_results`
  (`[{exercise_type, outcome}]`, step 4). Both fields are optional, so version 1 rows still validate.
- The personal sentence becomes a `production_attempt` (`writing`, `written`, prompt "discovery sentence", the
  term in `production_target` with `used` from `contains_term`, `ai_feedback` null) and `production.recorded`,
  through `app/services/productions.py`, which M5 extends. `term_missing` is returned when the term is absent.
- Start and complete each run in one short transaction. A second `complete` (or a `start`) after success gets
  409 `already_discovered`; `complete` before `start` gets 409 `invalid_transition`.

## D-105 — Usable sheet (M4.a1; planner part in M4.a2)

- A sheet is usable when it is the current one, its status is `complete` (AI or the user's) and it has a simple
  definition or a French translation (the D-092 content rule). A `needs_completion` skeleton is not usable.
  `usage_sheet.is_usable()` is the single rule.
- `POST /api/discovery/{id}/start` on a term without a usable sheet answers 409 `sheet_required` and writes
  nothing. The planner's exclusion and its `items_without_sheet` warning came with M4.a2 (D-109).

## D-106 — Response time capped at 5 minutes (M4.a1)

- `response_time_ms` must be >= 0 (422 otherwise) and is stored as at most 300 000 ms. A coffee break in the
  middle of a card must not move the medians that estimate session length (D-028). The proposed rating uses the
  capped value.

## D-107 — Study session `session-1` and the live next step (M4.a1)

- `study_session.planned = {format: "session-1", plan: SessionPlan}`; `summary = {format, reviews,
  failed_reviews, discoveries_started, discoveries_completed, productions, words, duration_ms,
  planned_minutes}`, counted from `review_log` (by `study_session_id`) and `event_log` (`item.status_changed`
  to `discovering`, `discovery.completed`, `production.recorded` and its `word_count`), never from counters.
  The demo moves from `demo-provisional-1` to this format in M4.a2.
- `start` is idempotent within a study day (200 with the open session, 201 for a new one). A session left open
  on an earlier study day is closed first, at its last event (`ended_at`, summary, and `session.ended` dated
  at that instant).
- `next` is computed live, not from the frozen order: a card is due **now** when its due time has passed, or
  when it is a `new` or `review` card due later in the current study day (whole-day intervals, which the
  planner already counts for today). A learning or relearning card due later today gives `wait {until}`. New
  terms come from the frozen plan, interrupted discoveries first, skipping a queued term whose deck stopped
  supplying (paused or done).
- `practice_info` is shown when the frozen plan has targeted practice or consolidation, until the client asks
  `next?practice_seen=true`; then `done`. This keeps `next` stateless. Targeted practice and consolidation are
  information only in M4.
- A review is refused with 409 `not_due` only when the card's due date is after the current study day.

## D-108 — Codes, decks and voice (M4.a1)

- **Error codes** (D-063 format): those of the milestone (`card_changed`, `review_not_allowed`,
  `sheet_required`, `already_discovered`, `session_not_found`, `session_closed`, `not_due`) and four more:
  `card_not_found` (404), `exercise_mismatch` (422: type not of the card's direction, template of another term
  or type, missing template, choice index out of range, reveal of a graded type), `discovery_not_allowed`
  (409, from `DiscoveryError`: paused or done deck, term not in the deck given) and `invalid_queue` (422). Deck
  transitions reuse `invalid_transition` (409, with `from_status` and `to_status`).
- **Decks**: `POST /api/decks/{id}/status` and `PUT /api/decks/queue` wrap the M1.b services. Every deck
  answer now carries `pace` and `warnings` taken from `plan_today` (no second computation; one plan per
  request).
- **`tts_voice`**: a string setting, default `""` (the first en-US voice), at most 200 characters, no list on
  the server (voices depend on the browser). `SettingSpec` gains `max_length`. No migration (`setting` table).

## D-109 — The planner skips terms without a usable sheet (M4.a2)

- `PlanInputs.items_without_sheet` (frozenset, default empty, so pure tests need no sheet) holds the queued
  terms whose current sheet is missing or not usable (`usage_sheet.is_usable`, D-105).
  `planning.items_without_sheet()` computes it in one query. `plan_session` leaves these terms out of the new
  terms (pace and queue phases) and adds the warning `items_without_sheet {count, deck_ids}`: the number of
  distinct terms left out, and the decks that would have supplied them, in queue order. `GET /api/decks`
  shows the warning on each deck of `deck_ids` (the M4.a1 filter already read `deck_ids`).
- Deadline paces still count these terms in `remaining`: a missing sheet does not move the deadline, and the
  warning tells the user why the pace may not be reached. `decks_to_activate` follows the filtered selection,
  so a queued deck with no usable term is not activated.
- An interrupted discovery (`discovering`) stays proposed whatever its sheet: the term was already started.
- Existing database tests that plan queued terms now give them a hand-typed sheet (`tests/factories.add_sheet`).

## D-110 — Demo sheets (M4.a2)

- `content/demo/sheets.yaml` (fictional, English; `dataset_version` 2 for the four demo files): 68 **full**
  sheets (simple definition, French translation, one academic and one spoken example, pronunciation, a
  confusable or a French-speaker pitfall when relevant, and one template each of gap-fill, recognition with
  three distractors, sentence production and spoken answer) and 41 **minimal** ones (French translation
  only). With seed 42, full sheets cover the 42 terms that end queued, in triage or discovering, and 26
  learning or consolidated terms. Draft and known terms have none.
- Inserted when the simulation creates the term, through the services:
  `enrichment.save_sheet(..., provenance=Provenance("demo", None, "demo-sheets-v1"))` (new keyword; by default
  the provenance is still copied from the edited version) and the new `enrichment.add_templates()` (content
  validated by `validate_content`, nothing deleted, origin `demo`). The gap-fill template is added before the
  sheet so the derived typed recall gets its accepted forms; listening reuses the recognition sentence, like
  the AI path. A demo sheet is a hand-typed sheet: `edited_by_user` and `enrichment.edited`, like a sheet typed
  in the app.
- `tests/test_demo_sheets.py` applies the generated-content rules of `app/domain/exercises.py` (the same checks
  as `EnrichmentEntry.problems`) to every full sheet.

## D-111 — The demo goes through the session service and the exercise choice (M4.a2)

- Sessions: `study_sessions.start_session` / `end_session` (format `session-1`, plan frozen at the start,
  summary computed from the logs). `direct_writes.start_study_session` / `end_study_session` and
  `demo-provisional-1` are removed; `direct_writes` keeps productions and errors (M5).
- Reviews: the type and the template come from `choose_exercise` (templates read once per term, after its
  sheet). `DEMO_EXERCISE_TYPES` and the learner's own maturity threshold are removed. Self-graded types store
  `auto_rating` null. The learner draws its "changed rating" step for every review, so the generator sequence
  does not depend on the templates.
- Discoveries: `begin_discovery` / `finish_discovery` without initial ratings (D-104). The last session still
  leaves one term `discovering`; the only `new` cards left are those of the terms discovered in the last
  session.
- Seed 42 stays reproducible (fingerprint test). Seed time for 60 days: 5.6 s on the owner's machine (5.1 s
  before; the extra time goes to the sheets and the session summaries). The 5 s target is missed by about
  0.6 s; accepted and reported to the owner.
- Test fix on the way: the M4.a1 anti-leak walk (`test_review_steps_never_carry_a_solution`) seeds the
  production FSRS fuzz generator. Unseeded, its cards sometimes stayed below the maturity threshold and the
  mature exercise types were not reached, so the test failed now and then.

## D-112 — Speech synthesis module in `frontend/src/speech/` (M4.b, 2026-10-17)

- Speech synthesis is neither a feature nor a plain UI component: it adapts a browser API, like `api/` adapts
  HTTP, and discovery (M4.b), reviews (M4.c) and speaking (M6) share it. It lives in its own top-level folder,
  mirroring the SPEC's backend `speech/`: `voices.ts` (pure rules, unit-tested), `useSpeech.ts` (a small store
  over `window.speechSynthesis` with `useSyncExternalStore`, the `useSpeech()` hook, `cancelSpeech()` and
  `useCancelSpeechOnLeave()`), `SpeakButton.tsx`.
- `window.speechSynthesis` is read on every call, never cached: without it (jsdom, an old browser) the page
  says so and the buttons are disabled. Voices arrive asynchronously (`voiceschanged`), so the first render can
  have an empty list.
- One utterance at a time: `cancel()` before every `speak()`; `cancel()` when the route changes (in the
  layout) and when the session player unmounts. Each utterance carries a token, so the "interrupted" error of
  a cancelled one does not clear the state of the next.
- Tests use `src/test/fakeSpeech.ts` (configurable voices, `voiceschanged` fired by the test, every utterance
  and `cancel()` recorded); `setup.ts` removes it after each test.

## D-113 — Voice choice, fallback and slow speed (M4.b)

- Voice: the one named by `tts_voice` when this browser has it; else the first `en-US` voice; else the first
  `en-*` voice, with the mention "non-American voice"; else none (buttons disabled, "no English voice").
  `utterance.lang` is always `en-US`. Language tags are compared case-insensitively, `en_US` included.
- Speed: normal = `tts_rate`; slow = `tts_rate × SLOW_FACTOR` (0.7), never below `MIN_RATE` (0.5).
- Settings: a separate "Voice" form under Audio, because `""` (automatic) is a valid value that the generic
  group form refuses. The list comes from the browser (the server has none, D-108): "Automatic (first en-US
  voice)", then English voices, en-US first, with their language. A saved voice that this browser lacks stays
  listed as "(not available here)", with a note that the automatic choice applies. "Test" speaks a fixed
  sentence with the voice selected in the form, before saving.
- Observed in the owner's in-app browser (Chromium 152, Windows 11): Microsoft Mark, Zira and David, all
  `en-US`, local (SPEC assumption B.11).

## D-114 — Today card and session player (M4.b)

- The home card reads `GET /api/session/today`: due reviews, new terms per deck (names from `GET /api/decks`),
  minutes against the budget, targeted practice and consolidation for information. The five plan warnings are
  translated with their data: `items_without_sheet` links each deck (`/library?deck=ID`) and `/enrichment`;
  `deadline_triage_pending` links `/triage?deck=ID` (its deadline comes from the plan's paces). The error
  category of targeted practice is shown as its code: no route gave the taxonomy labels yet (since M5.a1
  `GET /api/error-categories` does, and M5.b2 shows the label with the code as a fallback, D-150).
- `/session` calls `start` once per visit (a ref guards React's development double effect; the route is
  idempotent anyway), then `next`. `next` is a query (`staleTime: Infinity`, no refetch on focus) fetched
  again only when the page asks; `practice_seen` is part of its key. `done` ends the session by itself, once,
  and shows the summary. "End the session" is always visible behind an inline confirmation whose focus goes
  to "Keep going". `session_closed` offers a new session; `session_not_found` goes home; other failures show
  the translated error and "Retry".
- Every new step's title takes the focus (`tabIndex={-1}`); progress is announced politely.

## D-115 — The `wait` timer (M4.b)

- `wait {until}` shows a countdown (minutes, then seconds) and the local time, and checks `next` again at
  `until` plus a one-second margin (so the backend sees the card as due), with the delay capped to what
  `setTimeout` accepts. The timer is armed once per `until`: if the check answers the same `until` (clock skew
  between browser and server), it does not loop; "Check now" stays available. Both timers are cleared when
  the panel goes away.

## D-116 — Provisional review panel (M4.b, replaced in M4.c)

- A `review` step shows only the number of due reviews, "the review player comes with the next version" and
  "End the session": never the term, the prompt or the options (active recall). Its strings
  (`session.reviewPlaceholder.*`) say "Provisional (M4.b)"; M4.c removes them with the panel.

## D-117 — Discovery flow (M4.b)

> M6.b1 (D-199): the spoken repetition now has an optional recording (the "recording comes later" mention is gone). M6.b2.2 (D-206):
> the recorder is now split into `RecorderView` and `Recorder`; the discovery keeps using `Recorder`.

- `features/discovery/DiscoveryFlow.tsx` keyed by the term id, so a `next` that answers the same term does not
  reset it. Steps 1 and 2 share one screen (the sentence stays visible while guessing); then the sheet, the
  immediate exercises (typed recall, then gap-fill, each skipped silently when absent), the spoken repetition,
  the optional personal sentence, then `complete` and the first review date (the earliest `cards[].due`,
  local time).
- Active recall: the sheet query is mounted only after the guess (a test checks that no `/sheet` request goes
  out before, and fails when the sheet is loaded earlier); an exercise component never receives the sheet or
  the solution, which comes only from the `grade` answer (sent even with an empty field, `answer: null`); the
  sheet can be reopened after the answer and folds again at the next exercise; during the exercises no title
  shows the term, since it is the answer.
- `duration_ms` runs from the moment step 1 is shown (the `start` answer) to the sending of `complete`.
  "Finish" and "Skip" are disabled while `complete` is pending.
- A resumed discovery (`resumed: true`) says so and starts again from step 1 (owner's choice in the
  milestone).
- Errors: `already_discovered` (start or complete) asks for `next` without a message; `sheet_required` links
  to the term page and says the other new terms wait (`next` returns the first pending term of the frozen
  plan, so the same term comes back until its sheet is written: a server-side "skip this term" would need a
  backend change, noted for M4.c); `discovery_not_allowed`, `invalid_transition` and other refusals show the
  translated message and "Continue the session".

## D-118 — `SheetView` reused read-only (M4.b)

- Step 3 shows the library's `SheetView` with a new optional `audio` prop (default false) that adds "Listen"
  buttons to the examples. The term and its audio sit above it; the pronunciation (IPA, stress) is the
  sheet's own entry. `SheetPanel` is unchanged.

## D-119 — Small fixes and conventions met on the way (M4.b)

- French strings use "vous" and "paquet", like the existing translation (the milestone text used "tu"); the
  English ones follow the existing tone.
- A bigger `en.json` pushed the typed `t()` past TypeScript's instantiation depth in `ImportRows.tsx` (a `t`
  parameter typed as `ReturnType<typeof useTranslation>['t']`); typing it `TFunction`, like the other files,
  fixes it.
- At 375 px the top navigation (now four links) goes on its own row with tighter padding, and a long
  `<select>` (voice names) no longer widens the settings page.

## D-120 — The life of a review card (M4.c1, 2026-10-17)

- `features/review/reviewMachine.ts` is a pure reducer: `answering` → `checking` (grade or reveal sent) →
  `answered` (result shown, rating buttons) → `recording` (`POST /api/reviews` sent) → `recorded` (the page
  asks `next`). A failed `grade` / `reveal` goes back to `answering` with the typed answer kept; a failed
  record goes back to `answered` so the user can rate again. An action the phase does not allow returns the
  same state object.
- The player keeps the state in a ref as well as in React state and sends a request only when the reducer
  accepted the action, so two key presses handled before React re-renders send one `grade` and one
  `POST /reviews` (tested by dispatching two key events in one `act`; the test fails without the ref).
- The player is keyed by `card_id:expected_reps` in the session page: every card, including a learning card
  that comes back, starts fresh. `expected_reps` is sent back as received; `auto_rating` is never sent.
- Choice cards have an "I don't know" button (`choice_index: null`, outcome `empty`, proposed Again), like
  "I don't know" in discovery: the solution still comes only from `grade`.
- Errors of `POST /reviews`: `card_changed` asks `next` again with a discreet message (the card was rated
  elsewhere); `not_due` and `review_not_allowed` hide the rating buttons (rating again would be refused the
  same way) and offer "Continue the session"; `exercise_mismatch` (from `grade` or the record) offers
  "Retry", which resets the card and asks `next`; `session_closed` and `session_not_found` are passed to the
  page and follow D-114; a network error keeps the rating buttons for another try.
- After a record, the page shows and announces politely, outside the step card: "Saved: the previous card
  comes back on {date}" (or "today at {time}"), plus "{term} is now {status}" when `item_status_changed`. The
  next card is fetched at once; the text says "previous card" because the next one is already on screen.

## D-121 — Response time (M4.c1)

- `response_time_ms` runs from the prompt being shown (an effect at mount, `performance.now()`) to the
  answer: the submission of a typed answer, the choice of an option or the click on "Show". The time spent
  reading the correction and choosing the rating is not counted, and the same value is sent to `grade` and to
  `POST /reviews`. The server caps it at 5 minutes (D-106). Tested on fake timers with `performance` faked.

## D-122 — Keyboard shortcuts by phase (M4.c1)

- `useReviewShortcuts` listens on `document` and receives only the handlers the current phase allows:
  answering a choice → 1–4 choose and check; answering without input → Space or Enter show the answer;
  answered → 1–4 rate, Enter accepts the proposed rating (when there is one); R / Shift+R replay normally /
  slowly whenever there is something to hear. A typed answer is checked by Enter in its field (a form
  submit); in the sentence-production textarea Enter checks and Shift+Enter starts a new line.
- Ignored: Ctrl, Alt or Meta held, auto-repeated presses (`event.repeat`), and key presses in text fields,
  textareas, selects and editable content (the triage guard of D-088, moved to `components/keyboard.ts`; it
  now also reads the `contenteditable` attribute, which jsdom does not reflect in `isContentEditable`). Enter
  and Space on a focused button, link or summary are left to the browser, which activates the element:
  acting as well would do it twice.
- Digits are read from `event.key` **or** from the physical key (`Digit1`–`Digit4`, `Numpad1`–`Numpad4`): on an
  AZERTY keyboard the digit row gives "&", "é"... without Shift.
- A visible hint with `kbd` elements lists the keys of the current phase; every action also has a button, and
  the rating and option buttons show their number.

## D-123 — What is heard and shown before the answer (M4.c1)

> M6.b2.2 (D-206 to D-209): the "nothing is recorded yet" note of `spoken_answer` is replaced by the recorder; the question is shown alone,
> the example answer is never in the page before the answer, and Space and Enter no longer reveal it. The rule that the speech synthesis
> is cut before the recorder opens (D-193) holds.

- Listening comprehension: the sentence is never written in the DOM before the answer (no text, no hidden
  element, no attribute; the "Listen" buttons are labelled "the sentence"). The player speaks it as soon as a
  voice is available and fails silently; "Listen" and "Listen slowly" stay. After the answer the sentence is
  shown ("The sentence you heard").
- R replays, before the answer: the sentence of a receptive card (or the term of a receptive self-assessment
  without a sentence); nothing for a productive card, whose term is the answer. After the answer: the
  solution's sentence, else the term.
- A productive card never shows its term before the answer; the card's title is the exercise type, never the
  term. `sentence_production` shows the backend's `example_answer` as "Example answer (one possibility among
  others)", never as "the correct answer"; `spoken_answer` says that nothing is recorded yet (M6).
- A receptive self-assessment's result shows the meaning only (definition, translations): the term and the
  sentence were already in its prompt. The sheet summary links to the full term page in a new tab, so the
  session stays open.

## D-124 — The deck queue order is computed in the page (M4.c2)

- `GET /api/decks` answers in id order, so `features/queue/queueOrder.ts` reproduces D-027 as a pure function:
  decks that are not done, future deadline first (earliest first; "future" is strictly after today, as
  `has_future_deadline`), then `queue_position` (unset last), then id. "Today" is the plan's `study_day`
  (`GET /api/session/today`), else the local date. Paused decks keep their place in the list: they are part of
  the order that `PUT /api/decks/queue` rewrites, although the planner skips them.
- Two groups: decks with a future deadline (ordered by date, no move buttons, "Placed by its deadline") and the
  others (Move up / Move down, no drag and drop). A move swaps two neighbours of the manual group and sends
  **every** deck that is not done, once, in the new order; the backend writes dense positions. A deck whose
  deadline has passed is back in the manual group, at its position (D-027).
- A refused write (422 `invalid_queue`, 409 `invalid_transition`) shows the translated error and "Nothing was
  changed; the list was loaded again": deck writes refetch the decks, the term lists and the Today card on
  success and on failure.

## D-125 — Deck status changes on `/queue` (M4.c2)

- Only the transitions of D-026 are shown: queued → Activate / Pause / Mark as done; active → Pause / Mark as
  done; paused → Resume / Mark as done; done → Reopen. "Activate", "Resume" and "Reopen" all send
  `to: active`. No confirmation (every change can be undone); the result is announced in a polite status
  region; every button is disabled while a write or the refetch runs, then the focus returns to the button
  used (or to the deck's title when the deck changed section or the button became disabled).
- The page says that pause and done stop new terms only: cards already created keep being reviewed (D-026).
- Done decks are in a folded `<details>` section. Warnings reuse the Today card's `PlanWarnings` (its title id
  now comes from `useId`, since the page shows one list per deck). `reviews_over_budget` has no `deck_id`, so
  the backend never attaches it to a deck: it stays on the Today card only.
- `/queue` is linked from the Today card ("Manage the queue") and from `/library/decks`, not from the top bar.

## D-126 — Small conventions met in M4.c

- French counts use a space before the colon ("En file : 2") through a `queue.statusCount` key instead of a
  hard-coded ": ".
- Accessible names: the space between a button's number and its text is its own text node (a leading space
  inside a `span` is dropped by the name computation, which gave "3 GoodSuggested").

## D-127 — `review_log.production_attempt_id` (migration 0002, M5.a1)

- The prompt of M5.a1 planned no migration. One was needed: the server must know which production a review
  rated, to compute the proposed rating from the stored correction and to refuse a production used twice
  (409 `production_mismatch`). Migration `0002_review_log_production` adds `review_log.production_attempt_id`
  (nullable FK, `ON DELETE SET NULL`) and a unique index: a production is checked for at most one review.
  It was added in the first M5.a1 commit and is declared here; `alembic check` finds no difference.
- SQLite cannot add a named foreign key to an existing table, so the migration recreates `review_log` in batch
  mode. Foreign keys are on during migrations, so dropping the old table would run `ON DELETE SET NULL` on
  `error_event.review_log_id`: both directions save those links in a temporary table and put them back.
- **Departure from the prompt (spec 6)**: "the errors of this production receive the `review_log_id`" is not
  possible. `error_event` has a `single_origin` check (an error comes from a production **or** a review, never
  both; `ErrorEvent` in `app/db/models/errors.py`). The errors of a checked sentence therefore keep `production_attempt_id` and source
  `review`; the link goes the other way, `review_log.production_attempt_id`, which is enough to join them.
  Errors from lexical confusions (typed answers) keep `review_log_id` as before.

## D-128 — The `production_correction` task (M5.a1)

- **Task**: `production_correction` v1, `app/ai/{prompts,schemas}/production_correction*`, pinned in `tasks.py`.
  Inputs: `mode` (`sentence` when the text is one sentence, else `paragraph`), the numbered sentences, the prompt
  (cut to 500 characters), up to 15 targets, the active taxonomy codes with a one-line description. The user's
  text, the prompt and the targets are `data` placeholders (D-042); mode and taxonomy are `plain`. The learner's
  list of frequent errors is **not** sent (it would push the model towards false positives).
- **Sentences are numbered from 1** (`split_sentences`), and the validator checks the returned indices equal the
  sent ones exactly.
- **Budgets** (named constants in `tasks.py`, like D-080): input 16 000 characters (text 4 000 + numbered JSON
  about 800 + prompt 500 + 15 targets x about 250 + about 40 taxonomy lines x about 110, 13 000 at most, margin
  for categories the user adds); output ceiling 10 000 tokens (30 errors x about 170, the corrected and natural
  texts about 1 000 each, sentences, notes, targets); a call asks for `800 + 250 x sentences` tokens, never more
  than the ceiling, so one short sentence does not reserve what 40 need (Groq's 8 000 tokens per minute, D-051);
  timeout 60 s.
- **Validators** (validation context, D-079; a violation = one repair, then `incomplete`): indices; `wrong` is a
  substring of its sentence (`find_fragment`: ignores runs of spaces, typographic apostrophes, Unicode
  composition, then case); `wrong` differs from `correction`; `category_code` is an active code; a proposal's
  `parent_code` is an active code and its slug matches `^[a-z][a-z0-9_]{1,40}$`; a `correct` sentence has no
  error; target refs are known and not repeated; notes point at known sentences; at most 30 errors, at most 2
  alternatives. Messages name locations, never the learner's text. `comment` may be empty.
- **Flow** (`app/services/corrections.py`, D-038): short read session, closed; AI call with no session open (a
  test locks the database from another connection during the call); one write transaction that first checks the
  production is still there and not corrected (409 `already_corrected`). `incomplete` and `unavailable` write
  nothing and are results (HTTP 200 with `status`/`reason`, D-081): the production stays uncorrected and can be
  corrected again.
- **Stored feedback** (`production_attempt.ai_feedback`, `format: "correction-1"`): `prompt_version`, `provider`,
  `model`, `output` (the validated output), `spans`, `error_event_ids`, `targets`. `ai_call_id` is a column.
  - `spans`: one per error, in order, `{error, sentence_index, start, end}` as **Unicode code points** into the
    original text (JavaScript counts UTF-16 units: identical except for characters outside the BMP).
  - `error_event_ids` has the order of `output.errors`; the API reads the French explanation through it as long
    as the English explanation is unedited.
  - `targets`: `used` is deterministic (`contains_term`), `used_correctly` comes from the AI (False when the term
    is absent), `ai_used` is the AI's own claim and `disagreement` notes where they differ.
- **Sources**: `ErrorSource` has no `discovery` value and adding one would be a schema change, so the personal
  sentence of a discovery gives errors with source `writing`. A sentence checked in a review gives `review`: the
  source is read from `production.recorded.origin` (`ProductionRecorded` version 2 adds `origin`: `writing`,
  `discovery`, `review`), so a later retry through `/productions/{id}/correct` keeps it.
- **Proposed subcategories** become `<parent>.<slug>` categories with status `proposed`; the error points at the
  proposed category; the same proposal reuses it; a rejected code is never proposed again (errors go to the
  parent). `sync_taxonomy` leaves them alone (tested).
- Fixed along the way: `error_log.french_explanations` built a `dict` from a SQLAlchemy `Result` (it treated the
  result as a mapping and always failed); it had never run because nothing wrote feedback yet.

## D-129 — Sentence production checked by the AI (M5.a1; replaces the `sentence_production` note of D-101)

- D-101 said `sentence_production` is self-graded until M5. Now, when the AI check is available, the client
  calls `POST /api/reviews/check-production` after the attempt (D-103 still holds: the example answer is in the
  response, so only after the attempt) and sends `production_attempt_id` with the final `POST /api/reviews`.
  Without the check, or when it fails, the exercise stays self-graded exactly as before (`auto_rating` null).
- The check records the sentence as a production (prompt = the situation, target = the term, `origin: review`),
  corrects it in `sentence` mode and returns `{production_attempt_id, status, reason, feedback, errors,
  proposed_rating, solution, sheet_summary}`. `proposed_rating` is an addition to the prompt's list: without it
  the client would have to wait for the final call to show "Suggested". An unavailable AI leaves the sentence
  recorded and uncorrected.
- **Proposed rating** (`grading.production_rating`, pure, computed by the server from the stored feedback, never
  sent by the client): term used (deterministic) and judged correct, no error tied to the term (`target_ref`)
  -> Good; term absent, misused, or with an error tied to it -> Again; no usable correction, or the AI gave no
  verdict on a used term -> none. Easy and Hard are never proposed.
- `POST /api/reviews` with `production_attempt_id` refuses (409 `production_mismatch`) a production that does not
  exist, was written in another study session, was not written for this term, or is already linked to a review
  (also enforced by the unique index); with another exercise type: 422 `exercise_mismatch`. Nothing is written
  when it refuses. `response_time_ms` of `check-production` is validated and not stored (the final call times
  the card).

## D-130 — M5 is cut in four sessions (M5.a1, M5.a2, M5.b, M5.c; revised by D-138)

- M5.a1 (backend): correction of written productions, error log, error categories and proposals, errors from
  reviews, AI-checked sentence production, writing topics, CLI.
- M5.a2 (backend): transcript analysis, targeted drills, cards made from errors, suggestions for recurring
  errors, running the demo's errors through the services.
- M5.b and M5.c (screens): the writing screen and the error log screens.
- Why: M5 was too large for one session; the backend contract is fixed first, so the screens are built on a
  documented API.

## D-131 — Error log, categories and writing topics (M5.a1)

- **Sentence splitter** (`domain/sentences.py`, pure): numbered sentences with offsets; line breaks, `!?` runs,
  abbreviations (`e.g.`, `i.e.`, `etc.`, `et al.`, `Dr.`, `vs.`, `p. 12`), decimals, ellipses, closing quotes,
  text without final punctuation. At most 40 sentences (422 `text_too_long`, also checked when the production is
  created, so an uncorrectable text is never stored). The SPEC's "line by line" correction is sentence by
  sentence; stable indices are what lets the AI output be validated.
- **Errors** (`services/error_log.py`, `/api/errors`): manual entry (source `manual`, `erroneous_text` must be in
  `original_text`, active category only); list with category-prefix, source, term, production, date and text
  filters, newest first, pages of at most 100, and a facet of counts by level-2 category on the current filter;
  `PATCH` writes `error.updated` (changed fields, old and new codes); `DELETE` removes the row and writes
  `error.deleted` (the log stays append-only, D-017).
- **Categories** (`/api/error-categories`): the tree with labels, status, origin (`builtin`, `user`, `ai`) and
  counts (total and last 14 days); user categories are active at once; `resolve` accepts (optionally renamed) or
  rejects a proposed category. Rejection moves its errors to the parent (one `error.updated` each, reason
  `category_rejected`) and keeps the category as `rejected`.
- **Errors from reviews**: `grade_typed` exposes the cause of a `wrong` (`confusion`: library term, confusable,
  pitfall). `POST /api/reviews` creates one error for a `typed_recall` or `gap_fill` that is `wrong` with a
  confusion (source `review`, `lexis.collocation` when a multi-word term was answered with one word changed,
  else `lexis.wrong_word`); never for a choice, a typo, an empty or unexplained wrong answer, or self-graded
  types. `grade` and `reveal` still write nothing (the row-count test stays green).
- **Writing topics**: `content/writing_topics.yaml` (EN and FR, tags `academic`, `interview`, `data_science`,
  `everyday`, `campus`); `GET /api/writing/topics` is deterministic per study day and avoids the prompts of the
  last 7 days. No AI call.
- **New events** (open set, D-015; no migration): `production.corrected`, `error.updated`, `error.deleted`,
  `error_category.created`, `error_category.proposed`, `error_category.resolved`.

## D-132 — Tuning the prompt against the real model (M5.a1)

- First live run (`gemini-3.5-flash-lite`): "in campus" was classified `grammar.preposition.place`, and the
  correct paragraph got style remarks as errors (`lexis.collocation`, `register.too_formal`,
  `discourse.cohesion`, a tense false positive). A first failure of the live tests was a test fixture defect (the
  temporary database had no taxonomy), fixed in the fixture. The rest was fixed in the prompt and the taxonomy
  descriptions, not in the tests:
  - prompt: error or naturalness rule (grammatical + clear + a native could say it = note, not error), style
    examples, "choose the specific category" rule with the fixed-expression example;
  - `content/error_taxonomy.yaml` version 2: descriptions of `grammar.preposition.fixed_expression` (with
    examples of set phrases), `grammar.preposition.place` ("when it is not a set phrase") and
    `discourse.cohesion` (repeating a clear noun is style);
  - `content/examples/m5_correct_paragraph.txt` has a repeated-noun sentence (correct, unnatural) instead of
    "I have the intention to...", which the model rightly treated as borderline.
- Result with the final prompt and taxonomy: the example paragraph gave exactly the two expected codes in 3 of 3
  runs, the correct paragraph gave 0 errors and a naturalness note in 7 of 7 runs (counting the two live tests,
  which pass). Earlier versions of the prompt were worse: 3 of 6 clean on the correct paragraph. A lite model is not
  deterministic: one run in several may still flag style as an error. Nothing is hidden: the user sees and can
  edit or delete any error.

## D-133 — Transcript parser (M5.a2, 2026-10-18)

- `app/domain/transcript_import.py`, pure; it never raises on user input. Problems are `{line, severity: info |
  warning | error, code, message}` with stable codes: `empty_text`, `too_large`, `no_speaker_labels`,
  `single_speaker`, `unlabelled_text`, `empty_turn`, `unknown_label`, `no_user_turns`. Line endings and BOM as D-071.
- **Timestamps** at the start of a line are removed: always when bracketed (`[00:12]`, `(12:03 PM)`); otherwise
  when they have seconds or AM/PM, when a label follows, or when they are alone on the line. So "10:30 is fine for
  me" keeps its time. A line that was only a timestamp is dropped and does not separate paragraphs.
- **Labels**: `Name:` at the start of a line (1 to 3 words, at most 30 characters, starting with a letter, a space
  or the end of the line after the colon, so `https://` is not a label) opens a turn; the next lines belong to it.
  Known labels, without case: user `you, user, me, moi, vous`; other `chatgpt, assistant, ai, gpt, tutor`.
  `suggested_user_label` is the user label when exactly one distinct one is present. **Owner's choice (departure
  6)**: the rule is left as the prompt wrote it, so a line such as "Note: ..." inside a turn opens a turn "Note";
  the preview shows it (a label with one turn).
- **Blank lines inside a turn are dropped**: a turn never contains an empty line, so the stored text (the user's
  turns joined by `\n\n`) can be split back into turns exactly (`user_turns_of`). Nothing else has to be stored.
- **Lines before the first label** form a turn without label, never the user's except in `all_mine` mode, with
  `unlabelled_text` (departure 4, approved).
- Without any label, turns are paragraphs (`no_speaker_labels`). The user is designated by `{label}` or `{mode:
  alternating_user_first | alternating_user_second | all_mine}`; without a designation the suggested label is used.
- **Limits**: more than 60 000 pasted characters gives `too_large` and no turn; more than 6 000 characters of the
  user's turns gives `too_large` (error). The other speaker's text does not count.
- **Context of a user turn**: the other speaker's turn just before it, cut to its **last** 300 characters ("…"
  first when cut), because the question sits at the end of a turn. None when the turn before is the user's.
- **Units and chunks** (for the AI): each user turn is a unit; a turn of more than 600 characters is cut on sentence
  ends (`split_sentences`, which gained `max_sentences=None`), whole sentences grouped while they fit, a longer
  sentence on spaces, a longer word where it must. Chunks of at most 2 500 characters of unit text **and at most 20
  units** (the second limit is an addition: 30 short turns would bring 30 contexts of 300 characters).
- `POST /api/transcripts/preview` accepts an optional `user` (departure 3, approved): it shows which turns are the
  user's and checks the 6 000-character limit with that choice. It opens no database session at all.

## D-134 — The `transcript_analysis` task and its storage (M5.a2)

- **Task** `transcript_analysis` v1: inputs `units` (JSON lines `{index, text}`, `data`), `contexts` (JSON lines
  `{before_unit, text}` for the units that open a turn, `data`, introduced as "context, never to be corrected") and
  `taxonomy` (active codes **without `spelling` and `pronunciation.*`**, `plain`). The other speaker's text is sent
  nowhere else.
- **Prompt rules**: real errors of the learner only (D-132 rule "error or naturalness"); punctuation, capitals,
  spelling, hesitations, false starts, self-corrections, contractions and normal spoken style are ignored; a possible
  speech-recognition homophone is not reported; a form the other speaker quotes or corrects is never reported; the
  most specific subcategory. Added after the first live run: a duration said with "since" ("I study here since two
  years", a "depuis" calque) is **one** by/for/since error covering the verb and the time expression (the model had
  reported it as two errors, tense and preposition).
- **Validators** (validation context, D-079; one repair, then `incomplete`): unit indices exactly those sent;
  `wrong` found in its own unit (`find_fragment`, so never in the context); `wrong` differs from `correction`; code
  allowed (active, not spelling or pronunciation); proposed subcategories as D-128; a unit with an error is not
  `correct`; notes on known units; at most 40 errors per call and 2 alternatives. Messages name locations only.
- **Budgets** (`tasks.py`): input 20 000 characters (units 2 500 + JSON 600 + 20 contexts of about 330 + about 33
  taxonomy lines of at most about 230, about 17 300 at most); output `800 + 450 x units`, ceiling 8 000 (a long
  unit needs about 150 tokens of corrected text and up to 4 errors of about 170; 40 errors = 6 800); timeout 60 s.
- **Flow** (`app/services/transcripts.py`, D-038): short read; one call per chunk, in order, with no session open;
  **all or nothing**: one failed chunk and nothing is written (the calls stay in `ai_call_log`); one write
  transaction that checks the production is still there and not analysed (409 `already_corrected`).
- **Storage**: `production_attempt` with `kind = transcript_analysis`, `modality = oral`, `text` = the user's turns
  joined by `\n\n` (the paste and the other speaker are never stored), `word_count` = the user's words,
  `prompt_text` = the title. `production.recorded` **version 3**: origin `transcript`, `turns_total`,
  `turns_user`, `words_user`, `occurred_on` (no text); its `occurred_at` is the start of the conversation's study
  day when the date is given. A date in the future gives 422 `invalid_transcript` (`codes: ["future_date"]`).
- **Feedback** `format: "transcript-1"` with the `correction-1` keys (units as `sentences`, errors with
  `sentence_index`, `targets: []`), so M5.c reuses the highlighted view. Differences: `natural_text` is null (a
  "native" version of speech is of little use and costs output tokens), `corrected_text` joins the corrected units,
  and three keys are added: `units [{index, turn, start, end, opens_turn}]`, `context_sent`, `calls [{ai_call_id,
  provider, model, units: [first, last]}]`. `spans` are Unicode code points into `text`; `ai_call_id` (column) is
  the last call. `french_explanations` works unchanged.
- **Errors**: source `transcript`, `production_attempt_id`, `original_text` = the unit, `occurred_at` = the start of
  the conversation's study day (`occurred_on`), else the time of the analysis.
- **Interlocutor context at `/correct` (departure 1, approved)**: the analysis is a second request, and the other
  speaker's turns are not stored. `POST /api/productions/{id}/correct` therefore accepts an optional body
  `{transcript: {text, user}}`; the server parses it again and requires the same user turns as the stored text
  (409 `transcript_mismatch` otherwise). Without the body the units are checked without context. The CLI always
  sends it; M5.c must keep the pasted text in memory. The same body on another kind gives 422 `invalid_production`.
- `/correct` chooses the task by `kind` (`writing` -> `production_correction`, `transcript_analysis` ->
  `transcript_analysis`, anything else 422 `not_correctable`); `corrections.prepare` now also checks the kind.
- **Taxonomy version 3**: `grammar.preposition.by_for_since` describes the "since + duration" calque; the example
  of `grammar.tense.present_simple_vs_continuous` no longer uses "since" (it pulled answers towards that category).
- Live results (`gemini-3.5-flash-lite`, 2026-10-18): before the "since" rule, the example gave four errors (the
  calque split in two); after it, the example gave exactly the three expected codes in 6 of 6 runs and the clean
  transcript 0 errors in 6 of 6. The two M5.a1 live tests still pass with taxonomy v3.

## D-135 — The `targeted_drill` task and the `drill-1` storage (M5.a2)

- **Drillable categories**: active codes of level 2 or more. Level 1, `pronunciation.*`, `proposed` and `rejected`
  give 422 `not_drillable` (with `reason`); an unknown code 404 `category_not_found`.
- **Inputs**: the category and its active descendants (`code: label - description`, `data`, since user categories
  hold user text), at most 5 recent errors of the user in that prefix **without drill errors** (wrong form and
  correction, `data`), and the count (5 to 15, default 10). Level B1-B2 and the themes are in the prompt.
- **Output**: `{rule_en, rule_fr, items: [{kind: gap_fill | choice, sentence, answer, accepted, options, category_code,
  theme, explanation_en, explanation_fr}]}`. **`theme`** (`campus | data_economics | everyday`) is an addition
  (departure 2, approved): without it, "at least two themes in a batch" could not be checked.
- **Validators**: exact item count; exactly one gap, written `___` (a run of underscores of another length is
  refused); completed sentence of at most 30 words; `answer` not empty and at most 4 words (so are the accepted
  forms); no duplicate sentence; a choice has 2 to 4 different options containing `answer` exactly once; `accepted`
  disjoint from the wrong options; a gap-fill has no options; `category_code` is the requested code or an active
  descendant; explanations not empty; at least two themes; each rule 1 to 3 sentences.
- **Prompt**: added after the live probes: "each item must have ONE clear answer" (the model sometimes offered "at
  the end" and "by the end" together, or left "in lectures" for "during lectures").
- **Budgets**: input 6 000 characters (family about 2 000, 5 errors about 3 000, count); output `400 + 250 x items`,
  ceiling 4 200 (15 items = 4 150); timeout 45 s.
- **Storage**: `production_attempt` with `kind = drill`, `modality = written`, `prompt_text` = the code, `text = ""`,
  `word_count = 0`, `ai_call_id`, and `ai_feedback = {format: "drill-1", prompt_version, provider, model,
  category_code, rule_en, rule_fr, items (with their solutions), answers: []}`. `drill.generated` is written; no
  `production.recorded` (a drill is not free production).
- `POST /api/drills` answers 201 `{status: "ok", reason: null, drill}`; an AI failure is 200 `{status: incomplete
  | unavailable, reason, drill: null}` and writes nothing.
- **Options order**: `random.Random("drill:<id>:<index>")`, deterministic and not stored (like D-103); the index of
  the right option is computed by the server.
- Live results: with the first prompt, 3 of 3 runs gave a valid 10-item drill at the first call; with the final
  prompt, 2 of 2 valid (one after a repair), and the live test passes. An item can still be arguable (for example
  "closed ___ the weekend" expecting the British "at"): the solution shows `expected` and `accepted`, and the user
  can delete the error.

## D-136 — Exact grading of drill items, their errors and active recall (M5.a2)

- **Grading** (`app/domain/drills.py`): `grade_item` normalises as D-102 (NFKC, apostrophes, case, spaces,
  punctuation at both ends) and compares with `answer` and `accepted`. **No typo tolerance, no "form", and no
  optional "to"** (the D-102 rule for to-verbs would turn the preposition "to" into an empty answer). Outcomes
  `exact`, `wrong`, `empty`; "had been" for "has been" is `wrong`.
- A choice item is answered with `choice_index` into the shown options (an empty answer when absent); a text
  answer on a choice, a `choice_index` on a gap-fill, or an index out of range give 422 `exercise_mismatch`.
  Already answered: 409 `already_answered`; unknown drill (or a production that is not a drill): 404
  `drill_not_found`; unknown index: 404 `item_not_found`. `response_time_ms` must be >= 0 and is capped at 5
  minutes (D-106).
- **One transaction per answer**: the answer is appended to `answers` by reassignment (D-020): `{index, given,
  choice_index, outcome, response_time_ms, error_event_id, answered_at}`; `drill.item_answered {drill_id, index,
  category_code, outcome, response_time_ms}`; after the last item, `drill.completed {drill_id, category_code, items,
  correct, wrong, empty}`.
- **Errors**: a `wrong` answer gives an error with source `drill`: `erroneous_text` = the sentence completed with the
  given answer (or chosen option), `correction` = completed with the right answer, `original_text` = the sentence
  with its gap, `alternatives` = completed with at most 2 accepted forms (an addition), the item's category (the
  drill's when the item's is no longer active), `explanation` = the item's English explanation,
  `production_attempt_id`. `empty` creates nothing. `french_explanations` reads the item's French explanation for
  `drill-1` feedback.
- **Active recall** (D-103): an unanswered item carries `index, kind, sentence, options` only, never `answer`,
  `accepted`, `correct_index`, `expected` or the explanations (`SOLUTION_KEYS`; an API test walks every item of
  drills of 5, 10 and 15 items through `POST`, `GET` and the list). The rule is shown from the start: it is the
  explanation of the rule SPEC asks for. **`ProductionOut.feedback` is null for a drill** and `corrected` is false
  (departure 5, approved): `/api/productions` would otherwise return the solutions.

## D-137 — Targeted practice ignores drill errors (amendment of D-029, approved by the owner, M5.a2)

- Block 3 of the planner (the most frequent error code of the last 14 days with at least 2 errors) now counts the
  errors **without those of source `drill`** (`services/planning.py`). A drill's own mistakes must not keep choosing
  the same drill. Tested: 5 drill errors on prepositions and 2 writing errors on tenses propose tenses.
- The demo has no drill error, so its business data are unchanged. Its fingerprint (seed 42, 60 days, anchor
  2026-09-01) still changes, for two expected reasons only: the descriptions of taxonomy v3 (`error_category`) and
  the 17 `production.recorded` rows that are now written as payload version 3 with the new fields null. Every
  other table is identical (checked table by table).

## D-138 — M5 cut revised (amends D-130, M5.a2)

- M5.a2 (this session): transcript analysis and targeted drills.
- M5.a3: cards made from errors, suggestions for recurring errors, the demo's errors through the services.
- M5.b and M5.c: the screens (writing, transcripts, drills, error log).
- The `practice_info` step of the session stays informative; M5.c links it to a drill through `category_code`.
- **Amendment (M5.b1, owner's decision): the order is M5.b, then M5.a3, then M5.c.** The screens of writing and of the
  error log come first, because they need no new backend; the backend of M5.a3 (cards made from errors, suggestions
  for recurring errors, the demo's errors) follows; M5.c (transcripts, drills, the `practice_info` link) comes last,
  on the complete API. M5.b itself is two parts on one branch: M5.b1 (writing and corrections) and M5.b2 (error log
  and categories).
- **Second amendment (M5.c1, owner's decision): M5.c comes before M5.a3**, see D-151.

## D-139 — Small conventions met in M5.a2

- **CLI**: `transcript analyse --file <txt> [--speaker LABEL | --mode alternating-user-first |
  alternating-user-second | all-mine] [--preview]` (the preview needs no database; the title is the file name) and
  `drill new <code> [--count N]`, `drill list`. Exit codes as D-053 (0, 1 AI failed, 2 usage). `transcript analyse`
  (without `--preview`) and `drill new` refuse `--demo`, as the prompt asked; note that `write correct` and
  `library enrich` accept it (M3.b, M5.a1): a later milestone may align them.
- The API on the demo database behaves as for `/api/productions`: the demo database is a sandbox (D-064), so the
  routes are not refused there (the plan said they would go through a demo guard; there is none for productions).
- `corrections.category_for` and `corrections.Written` are public (shared with the transcript service).
- The live tests of M5.a2 (`test_live_transcript.py`, `test_live_drill.py`) follow D-054: deselected by default,
  `VOCAB_RUN_LIVE=1` and a configured provider required, a quota is a skip.

## D-140 — Error spans and the correction model (M5.b1, 2026-10-18)

- The backend counts spans in Unicode code points (D-128), JavaScript in UTF-16 units. `features/writing/spans.ts`
  (pure) converts once: `Array.from(text)`, then the running sum of the lengths. A span that is out of bounds, not
  made of integers or with `start >= end` is ignored and reported with `console.warn` in development only: a wrong
  highlight is better than a crash.
- **Overlaps**: spans that overlap (a nested one included) are merged into one mark that carries every error number;
  spans that only touch stay two marks. `segment()` then cuts the text into plain and marked segments.
- `features/writing/correction.ts` is the only place that knows the stored format: `readFeedback()` switches on
  `feedback.format` and returns a neutral model (segments, ranges, entries grouped by sentence, naturalness notes,
  the corrected and natural texts, target checks). `correction-1` is the only branch today; M5.c adds
  `transcript-1` (the same keys plus `units`) as a second branch, without touching the view. An unknown format, a
  missing feedback or a `correction-1` without `output` gives `null`: the view shows the plain text and "Not
  corrected yet".
- The logged errors (`ErrorOut`) are matched to `output.errors` through `feedback.error_event_ids`. The logged
  explanation wins over the stored one (the user may have edited it) and its French goes with it (null once edited,
  so no stale translation is offered).

## D-141 — The correction view (M5.b1)

- `CorrectionView` takes `{text, feedback, errors?, targets?, proposedCategories?, compact?, level?}`. The first
  three are the milestone's; `targets` (the production's targets, for the term names) and `proposedCategories` are
  additions, because `feedback.targets` carries item ids but no term, and the proposals only come with `/correct`.
- **Marks are never colour alone**: a wavy underline, a tinted background and the error number in superscript, each
  number a link to its entry; each entry has a "Back to the text" link. The links move the focus (`getElementById`
  + `focus()`) instead of changing the URL hash, so `/writing/:id` stays clean.
- Entries: `wrong` → `correction` (with visually hidden "Incorrect" / "Correct" labels and `del` / `ins`), the
  alternatives, the category (label in the interface language, then the code in small type), the English
  explanation, "Show in French" per error (never open by default, whatever the interface language; absent when the
  French is null) and the linked target term.
- **Category labels**: the logged row first; else the tree of `GET /api/error-categories` (queried only when some
  error has no logged row, e.g. a reloaded `/writing/:id`, which does not return the errors); else the code alone.
- **Compact** (a review sentence, the personal sentence of a discovery): marks, the list, the naturalness notes and
  the corrected version, without the natural version, the Copy buttons and the target terms; the page around it
  already deals with the term. Section headings take a `level` (2 on a page, 3 inside a step).
- Naturalness notes are presented as correct but unusual and "not logged", never as errors. A proposed category is
  announced with a link to `/errors/categories` (the page itself arrives in M5.b2; until then the link shows the
  404 page).
- "No errors found." for a text, "Your sentence is correct." for a single sentence.

## D-142 — The writing flow (M5.b1)

- `/writing` creates the production (`POST /api/productions`), clears the draft and goes to `/writing/{id}` with
  `replace: true` and the router state `{autoCorrect: true}`. The detail page starts `/correct` by itself once, clears
  the state at once, and shows the correction or the reason. Two consequences: a reload never creates a second
  production (the URL is the production's) and never starts a correction by itself (the flag is gone); "Try again"
  only calls `/correct`. Departure from the prompt's wording ("Checking… n s" on the writing page): the counter is on
  the detail page, where the saved text is visible while the AI works.
- `409 already_corrected` invalidates the production's query, so the stored correction is shown.
- **Length**: counted in code points (as Python's `len`), words as runs of non-space characters. Over 4 000 the
  button is disabled with a visible message and nothing is sent; no `maxLength` attribute, which would silently cut
  a paste. The server stays the judge of the 40 sentences (`text_too_long`, shown, text and draft kept).
- **Draft**: `localStorage` key `vocab-coach.writing-draft`, every access in `try/catch`, cleared when the production
  is created. It is a per-viewer convenience: the page works without storage.
- Topics: `GET /api/writing/topics?count=3&tag=` (the theme selector is labelled "Topic theme" so it is not confused
  with the theme switcher of the top bar); the prompt sent is the English text of the topic or what the user typed
  (500 characters at most).
- **History** (`/writing/history`, 20 per page, the page in the URL): `ProductionOut` does not expose `origin`, so the
  list also holds the personal sentences of discoveries and the sentences written in reviews. The topic column
  (`prompt_text`) tells them apart, and the page says so. Not fixed here (it would need a backend field).
- The AI failure is a 200 answer: `unavailable` gives the translated reason (`aiReasons.*`, D-095 — through
  `aiReasonText`, which maps an unknown reason to "the providers failed"), `incomplete` its own sentence.

## D-143 — Sentence production checked by the AI in the review player (M5.b1; builds on D-120, D-129)

- A new phase `checking_production` in `reviewMachine`. A typed, non-empty sentence on a `sentence_production` card
  with a template calls `POST /api/reviews/check-production` (a plain function, not a mutation, so an
  `AbortController` can stop the wait). An empty sentence stays the self-graded path of M4.c.
- `status: ok`: the correction in compact mode, `term_missing` derived from the stored `feedback.targets`, the
  example answer, the sheet summary, the proposed rating (1 or 3 marked "Suggested", Enter accepts; null gives four
  buttons without a suggestion). `POST /reviews` carries `production_attempt_id` and never `auto_rating`.
- **Fallback = `grade`, not `reveal`** (departure from the prompt, approved in the plan): `unavailable`, `incomplete`,
  a network error or "Skip the check" go back to the exact M4.c path, which for this type is `grade` (it keeps the
  `term_missing` warning that `reveal` does not give; `grade` writes nothing). `POST /reviews` then carries no
  `production_attempt_id`. A notice says why. Refusals that a fallback would not fix (`exercise_mismatch`,
  `not_due`, `review_not_allowed`, `session_closed`, `session_not_found`) are handled as for `grade`.
- **Waiting**: "Checking your sentence… n s" (hidden from screen readers; a static polite status says it once);
  after 5 s a "Skip the check and rate myself" button aborts the request. The sentence stays recorded on the server
  and the user rates it themselves, as accepted in the prompt. The reducer refuses an AI answer that arrives after
  the skip (same state object, tested), so no `Date` or flag is needed for the race. Shortcuts are only armed in
  `answering` and `answered`, so keys are ignored while waiting.
- **Active recall (D-103)**: the example answer is only in the answer of `check-production` (or of `grade`), so
  nothing of it is in the DOM before. A test fails if it is: breaking check (b) in PROGRESS.
- `409 production_mismatch` on `POST /reviews`: a discreet message, then **one** automatic resend without
  `production_attempt_id` (`productionDropped` empties it, so a second refusal is shown like any other error).
- **`error_event_id`** (a lexical confusion in a typed answer): the polite announcement of the session page, now a
  `ReactNode`, adds "Added to your error log." and a link to `/errors/{id}` (the final route of M5.b2).
- The hint under the sentence field no longer says that AI correction comes in a later version.

## D-144 — The AI check of the personal sentence in discovery (M5.b1; builds on D-104, D-128)

- On the last screen, when `complete` answered a `production_attempt_id` and a sentence was written, a "Check my
  sentence with AI" button sits next to "Continue". It only calls `POST /api/productions/{id}/correct`, shows the
  compact correction, and a failure (reason, network, refusal) is said without blocking "Continue"; the button can be
  used again after a failure. `409 already_corrected` reads the stored production.
- The sheet is neither reloaded nor shown on this path (a test counts the sheet requests). The sentence shown is the
  one that was sent (kept in the flow's state). Its errors have the source `writing` (D-128).

## D-145 — Small conventions met in M5.b1

- `apiSend` takes an optional `AbortSignal`; `mockApi` rejects with an `AbortError` when the signal fires, like
  `fetch`. `renderApp` also returns the router and the query client (to check the URL and the history action).
- `useElapsedSeconds` moved to `components/` (the settings page and the new pages share it); the review panel counts
  its own ticks instead, because the lint rule on impure calls refuses `Date.now()` in an event handler.
- `PageTitle` (a focusable `h1`) for the new screens: focus goes to the title on arrival.
- `errorMessage.ts`: six new codes; `invalid_production` shows the English detail like `invalid_setting` (D-068).
- i18n: `review.check` was already a string (the button label), so the new keys are `review.aiCheck.*`.
- **Navigation**: "Writing" is a fifth link. At 375 px the five links fit on one row in English; in French
  ("Aujourd'hui", "Bibliothèque") the last one wraps to a second row, with no horizontal scroll (D-119 asked for
  no scroll; wrapping was already the design). "Errors" arrives with M5.b2.
- Found in the browser: a grid track without `minmax(0, 1fr)` let the history table widen the page to 1 661 px;
  `.writing-page` now has it, like the library page.

## D-146 — The error log page: state in the URL, dates, links (M5.b2)

- `/errors` keeps every filter in the URL (`category`, `source`, `q`, `from`, `to`, `item_id`, `page`; empty values and
  page 1 are left out), so Back, reload and sharing work. The form holds a draft and "Apply" writes the URL; the form
  is remounted (`key`) when the URL changes, so it always shows the applied filters. A facet button writes `category`
  at once; clicking the pressed one clears it (`aria-pressed`). 25 rows per page (the backend allows 100).
- **Dates**: "From" and "To" are calendar days in the browser's time zone, sent as local midnights in UTC
  (`occurred_from` = the start of the first day, `occurred_to` = the start of the day after the last day, because the
  backend's bound is exclusive). The planner's study day (`day_start_hour`) is not used here: it is a scheduling
  notion, and this is a log of what happened on a calendar day.
- Rows link to `/errors/{id}` with the current search in the router state; the detail page's back link and the
  redirect after a deletion use it, so the filters survive the round trip. Without state they fall back to `/errors`.
- **Production link**: `ErrorOut` carries no production kind. A row links to `/writing/{production_attempt_id}` for the
  sources `writing` and `review` (both are written productions) and has no link for `transcript`, `drill`,
  `speaking` or `consolidation` (their screens arrive with M5.c).
- The term chip of `item_id` shows the term's name (`GET /api/items/{id}`), "Term {id}" while it is unknown, and a
  button that removes the filter.

## D-147 — Category selectors (M5.b2)

- A native `<select>` with the tree flattened and indented (recursively: the demo taxonomy has three levels, for
  instance `grammar.preposition.time`). **Filter**: active and proposed categories (a rejected one holds no error);
  a top-level category reads "X (all)" because the backend filters by code prefix; a proposed one is marked
  "(proposed)". **Assign** (edit, manual entry, parent of a new category): active categories only, which is what the
  backend accepts (`unknown_category` otherwise); in the edit form the error's current category stays selectable even
  when it is only proposed. Any active category may be chosen, level 1 included (the backend allows it).
- A category that is not in the list (not loaded yet) stays as an option with its label or its code, so the control
  never shows a wrong value.

## D-148 — Editing, deleting and entering errors by hand (M5.b2)

- The edit form sends **only the changed fields** (`PATCH`); with nothing changed it says so and sends nothing.
  `lexical_item_id: null` unlinks the term. Editing the explanation drops the stored French translation (a backend
  rule), and the form says so while a French version is shown.
- The edit form is not remounted after a save (a `mutate` callback of an unmounted component never runs): the "Saved."
  state lives in the page, and the form compares against the refreshed error.
- **Deletion** asks inline; focus goes to "Keep it" (D-067). `useDeleteError` invalidates the lists and the category
  counts but not the error's own query, which is still mounted and would answer 404 before the navigation.
- **Manual entry**: client checks that mirror the backend (`fragment.ts` is a look-alike of `find_fragment`: runs of
  spaces, typographic apostrophes, NFC / NFD and, as a second try, case): the incorrect form must be in the sentence
  when one is given, and must differ from the correction. The server stays the judge: `invalid_error` (with its
  English detail), `unknown_category` and the others are shown. After a success the form empties and a link opens
  the new error. An exotic case difference (such as "ß") could make the client check stricter than the server's; the
  client check is a convenience and the message names the rule.
- The term picker searches `GET /api/items?q=`, shows at most 8 results as buttons and lets the user unlink.

## D-149 — The categories page (M5.b2)

- The AI's proposals come first. Accept sends a rename only when a label differs from the proposal's. Reject is
  explained before it is done ("its errors move to the parent category", focus on "Cancel"), then reports how many
  errors moved. The result and the refusals are shown **at page level**, not inside the card: the reloaded tree
  removes the card, and `category_not_proposed` (decided elsewhere) reloads the tree by itself.
- `useResolveCategory` does not await its invalidation (so the card's own `mutate` callbacks still run), and
  invalidates the Today plan when errors moved (targeted practice reads the counts).
- The tree shows the label in the interface language, the code, the status and the origin **as text**, and the counts
  (total and last 14 days) with a link to the filtered list. Rejected categories are folded in a `<details>`.
- Creation: the parent defaults to the first active top-level category (a top-level category is an explicit choice
  "None"); the code name follows the backend rule (`^[a-z][a-z0-9_]{1,40}$`), checked while typing; both labels are
  required, descriptions optional; `category_exists` is shown.

## D-150 — Labels, links and small conventions of M5.b2

- `useCategoryName()` gives the label of a code in the interface language and falls back to the code (tree loading,
  request failed, unknown code). The Today card and the `practice_info` step use it; `categoryLabels` returns an
  empty map for anything that is not a list, so a label lookup cannot take a page down.
- The term's page has a card "Errors linked to this term" that opens `/errors?item_id=ID`.
- **Error codes**: six new ones in `errorMessage.ts` (`error_not_found`, `category_not_found`,
  `category_not_proposed`, `unknown_category`, `invalid_error`, `category_exists`). The prompt counted nine and
  listed five; `category_exists` was missing from it. `invalid_error` shows the English detail like `invalid_setting`.
- The page strings live in `errorLog.*`: `errors.*` already holds the messages by code.
- **Navigation**: "Errors" is the sixth top link; the links wrap to two rows at 375 px in English and in French, with
  no horizontal scroll (measured: `scrollWidth` 375 on every new page).
- Page layouts use `grid-template-columns: minmax(0, 1fr)`, so a wide table scrolls in its frame (D-145).

## D-151 — M5.c before M5.a3, and M5.c in two parts (amends D-138, M5.c1, 2026-10-18)

- **Owner's decision**: the order is M5.b (done), then **M5.c, then M5.a3**. The transcript and drill screens need no
  new backend, and the real analyses of the owner's conversations are worth having before the backend of M5.a3.
  M5.a3 keeps its content (cards made from errors, suggestions for recurring errors, the demo's errors through the
  services); nothing of it enters M5.c.
- M5.c is two parts on one branch (`feat/m5c-transcripts-drills`): **M5.c1** transcripts (`/transcripts`,
  `/transcripts/:id`, `/transcripts/history`, `transcript-1` in the correction view, the error log's transcript link),
  **M5.c2** drills (`/drills`, `/drills/:id`, "Practise now", "Practise this category", the error log's drill link).
- No backend change in M5.c (`git diff --stat main -- backend` is empty); a need found on the way stops the session.

## D-152 — The pasted conversation lives in memory only (M5.c1)

- The server stores your turns, not the other speaker's, so `/correct` needs the paste again to give the AI the
  context (D-134). `features/transcripts/transcriptMemory.ts` is a module-level `Map<productionId, {text, user}>`:
  `remember` after saving, `recall` for the analysis, `forget` after success. It is **never** in `localStorage`,
  `sessionStorage`, the router state (react-router writes it to `history.state`) or the URL, and there is no draft.
- Saving navigates to `/transcripts/{id}` with `replace: true` and the state `{autoAnalyse: true}` only. The detail
  page clears it at once (a ref guard makes this safe in StrictMode) and starts `/correct` once, with `{transcript}`
  when the memory has it, without a body otherwise. A reload therefore never creates a production and never starts an
  analysis by itself.
- `useAnalyseTranscript(onDone)` forgets in the **hook's** callbacks (`ok`, or `409 already_corrected`): the
  callbacks of `mutate()` are dropped when the page is left, and a long analysis can outlive it. An AI failure
  (`unavailable`, `incomplete`) keeps the paste: "Try again" calls only `/correct`, with the same body.
- After a reload the memory is empty. The page then offers **"Analyse without the other speaker's context"** (no body,
  `context_sent: false`) and **"Paste the conversation again"** (the same paste, preview and choice as the first page;
  the body is `{transcript: {text, user}}`). `409 transcript_mismatch` shows a sentence and keeps the pasted text.
- The privacy test uses a `createBrowserRouter` variant (`renderAppInBrowser`), because the memory router never writes
  `history.state` and the test would prove nothing. It records `window.history.state`, the router state and the URL at
  **every** navigation (the state that carries the flag is cleared a moment later, so a final check would miss it),
  then the two storages. Breaking check (a) in PROGRESS.

## D-153 — Preview and choice of your turns (M5.c1)

- The preview belongs to the text it was made from: editing the text hides the preview and the choice and disables
  saving until "Preview" is run again, so what is saved is what was previewed. The latest answer wins when two
  previews overlap.
- "Preview" sends `{text}`; the parser's suggestion (`suggested_user_label`, echoed as `designation`) pre-chooses the
  label. Changing the choice reads the text again with `{text, user}`. **Without labels no mode is pre-chosen** (the
  prompt only listed the three modes): the parser already warns that each paragraph is a turn, and a wrong guess would
  silently analyse the other speaker's sentences.
- Limits as the server's: 60 000 pasted characters, counted in code points. Over it: a visible message, "Preview" and
  saving disabled, no request, **no `maxLength`** (it would cut a paste without saying so). The 6 000 characters of
  your turns come back from the parser as a `too_large` error problem.
- Problems: one i18n key per code (`transcripts.problems.*`); an unknown code falls back to the backend's English
  message; the severity is written (Note, Warning, Error), never by colour alone (D-087). A label with one turn and no
  known role gets the D-133 explanation ("Note:" opens a turn).
- Your turns are marked "You" in words and by a border; the others "Other speaker". The pasted text is shown with
  `white-space: pre-wrap`.

## D-154 — Date and title (M5.c1)

- The server refuses `occurred_on` after the **study day** (`study_today()`: the `timezone` and `day_start_hour`
  settings), not after the browser's calendar day. The date field's `max` and the client check use the plan's
  `study_day` (`GET /api/session/today`), with `localDay()` while it loads. The comparison is on `YYYY-MM-DD`
  strings. The server stays the judge (`invalid_transcript` with `future_date`).
- The title is optional, at most 200 code points (a counter and a disabled button; no `maxLength`). Empty fields are
  sent as `null`; `study_session_id` is `null` (transcripts are not part of a study session in M5.c1).

## D-155 — `transcript-1` in the correction model and the view (M5.c1; amends D-140 and D-141)

- `readFeedback` has a second branch. Both formats go through one function; the model gained `kind` (`text` or
  `transcript`), `numberOf(sentenceIndex)` and `contextSent` (null for a text, `false` when the flag is missing).
- Units play the part of sentences (the entries keep the unit index in `sentenceIndex`), but errors and naturalness
  notes are **grouped by your turn**: `units[].turn + 1`, "Your turn k" with k the position among your turns. Two units
  of one long turn are one group; an unknown unit keeps its own index rather than disappearing.
- The spans are in the stored text (your turns joined by a blank line), in code points, converted as before
  (`toUtf16Ranges`); the text is shown with `pre-wrap` so the turns stay apart.
- There is no natural version (`natural_text` is null) and no target term, so those sections are already hidden. The
  view shows "Your turns, with the errors marked", the mention "Analysed with / without the other speaker's context"
  from `context_sent`, and "No errors found in your turns".
- **Departure from D-140** ("without touching the view"): these three labels and the group headings needed a small change in
  `CorrectionView`; the stored-format knowledge stays in `correction.ts`.

## D-156 — Error codes and the transcript reasons (M5.c1)

- `errorMessage.ts` knows `transcript_mismatch` (409) and `invalid_transcript` (422). `not_correctable` was known.
- `invalid_transcript` and `text_too_long` carry `codes` (the parser's codes, `future_date`, `title_too_long`).
  `describeError` returns them as translated `reasons` (`transcripts.reasons.*`, then `transcripts.problems.*`, then
  the code itself), shown as a list under the sentence by `ErrorText`.
- `text_too_long` **with** `codes` is a transcript (60 000 and 6 000 characters); without, it is a written text (4 000
  characters and 40 sentences): two sentences for one code (`errors.text_too_long_transcript`).
- The codes of the drills (`drill_not_found`, `already_answered`, `not_drillable`...) arrive with M5.c2.

## D-157 — Small conventions met in M5.c1

- `productionLink` (D-146): the source `transcript` links to `/transcripts/{production_attempt_id}`; `drill` follows in
  M5.c2 (the drill id must be checked against the production id in the service then).
- `applyCorrection` and `applyCorrectionError` (in `api/productions.ts`) are the invalidations shared by the two
  correction hooks.
- `context` is a reserved option of i18next: the privacy sentence uses `{{chars}}`.
- Found in the browser: a fieldset keeps its content's minimum width, so a 28 rem title field made the page 481 px wide
  at 375 px. `.transcript-meta` and `.transcript-picker` have `min-width: 0` and the field is `min(28rem, 100%)` wide
  (like D-145's table).
- No new link in the top bar: the pages are reached from `/writing` ("Analyse a conversation transcript"), and the
  history, the detail and the error log link to each other.

## D-158 — The drills pages and `?category=` (M5.c2)

- `/drills` is the list and the creation form; `/drills/:id` is the player. No new link in the top bar (D-157's rule):
  the pages are reached from `/errors` ("Targeted drills"), `/errors/categories` ("Practise this category"), the Today
  card and the session's `practice_info` step ("Practise now").
- **One `?category=` parameter with two roles** (proposed in the plan, accepted): it filters the list by code prefix
  and, on arrival, preselects the form's category when it can be drilled and scrolls to the form. Changing the filter
  later does not move the form; nothing starts without a click. The page (`?page=`) is in the URL too (20 per page).
- **Eligible categories** (`drillRules.ts`, same rule as `drillable_category`): active, a code with a dot (level 2 or
  more), not `pronunciation`. `CategorySelect` got a mode `drill`: eligible nodes are selectable, their level-1
  ancestors stay as greyed options so the tree stays readable, everything else is left out. A preset that the loaded
  tree refuses (proposed, unknown) is not preselected; before the tree is loaded the code alone decides. The server
  stays the judge (`not_drillable`).
- **Creation**: number 5 to 15 (default 10) checked in the page; a ref guard so two clicks send one request; "Preparing
  your exercises… n s" in the button, with a polite status; 201 opens the drill; `incomplete` / `unavailable` (HTTP
  200) show the reason with `aiReasonText` and keep the form filled. `{fromSession}` in the navigation state becomes
  `study_session_id` and is passed on to `/drills/{id}`.

## D-159 — The drill player (M5.c2; builds on D-120, D-121, D-122)

- `drillMachine.ts` is a pure reducer per item (`answering` → `sending` → `answered`, `failed` back to `answering` with
  the typed answer kept; an action the phase refuses returns the same object). `DrillItemPlayer` keeps the state in a ref
  as well and sends a request only when the reducer accepted the action: two Enter before React re-renders send one
  answer (tested; removing the guard makes two tests fail, see PROGRESS).
- **The page owns the index** (`DrillRun`, mounted once the drill is loaded, `useState(() => firstUnanswered(drill))`):
  the answer replaces the cached drill, but the result stays in front of the user until "Next". Leaving an item is
  guarded twice (a ref in the player, and a relative `setIndex`), so a double Enter or a double click cannot skip one.
- Bodies: a gap-fill sends `{answer, response_time_ms}` (empty string for "I don't know"), a choice sends
  `{choice_index, response_time_ms}` (`null` for "I don't know"); the server refuses the other field. The time runs from
  the item being shown to the answer (D-121).
- Keys: 1 to 4 choose (read from `key` or `Digit1`-`Digit4` / `Numpad1`-`Numpad4`, D-122), Enter goes to the next item
  once the result is shown; ignored in fields, with Ctrl/Alt/Meta, on repeat, and Enter on a focused button or link.
  `useDrillShortcuts` reuses `digitOf` and `activatesItself` (now exported from `useReviewShortcuts.ts`); `KeyHints`
  moved to `components/KeyHints.tsx`. One hint line per phase.
- **Enter does not send an empty gap-fill** (the "Check" button is disabled until something is typed): a held Enter that
  reaches the next item's focused field must not answer it as "I don't know". After the first item the field of a
  gap-fill takes the focus (keyboard flow); on the first item the page title keeps it.
- Errors: `409 already_answered` reads the drill again and moves to its first item not answered; `exercise_mismatch`,
  `item_not_found` and `drill_not_found` show the translated message and "Retry" (reads the drill again, the item starts
  fresh); anything else (network) keeps the answer typed for another try.
- The result shows a sign **and** a word (never colour alone), what was given, the right answer, the accepted forms, the
  English explanation (French on request) and, when `error_event_id` is set, "Added to your error log" with a link and the
  sentence "The correction is exact. If you think your answer was correct, you can delete this error." The recap of the
  finished drill has no error link (`DrillOut` carries no `error_event_id`): "See these errors" covers it.

## D-160 — Active recall in the drill screens (M5.c2; D-103, D-136)

- Before the answer the page renders `index`, `kind`, the sentence (gap as a line plus the word "blank" for screen
  readers) and the options in the order received. The rule is shown from the start (it is the rule SPEC asks for).
  Nothing else comes from the server earlier: the player reads items from the `DrillOut`, which has no solution for an
  unanswered item, and makes no request but `GET /drills/{id}` and the answer.
- The recap and the results of the other items are only rendered on the final screen. Tested against `innerHTML` as a
  whole with unguessable solution tokens (`ANSWER-TOKEN`...), for a gap-fill and a choice, and against the list of
  requests.

## D-161 — The links (M5.c2; amends D-107 / D-114 and D-146)

- `productionLink`: a `drill` error opens `/drills/{production_attempt_id}`; `answer_item` gives the error the drill's own
  id, checked in `services/drills.py`. The error log and the error detail say "Open the drill" / "Open the drill it comes
  from" for it (`errorLog.list.openDrill`, `errorLog.detail.openDrill`).
- **"Practise now"** (`session.practice.now`) in the `practice_info` step and on the Today card: shown when
  `category_code` exists and passes `isDrillableCode` (the code alone, so the card does not wait for the tree). The step
  passes `{fromSession: step.session_id}`; the card passes the open session's id, and nothing when none is open.
  "Continue" is unchanged. Two texts changed because they said the exercises were not available:
  `session.practice.later` now speaks of the consolidation task only and is shown only when there is one;
  `today.targeted` lost "for information only".
- Back to the session: `/session` resumes the open session, and the `practice_info` step is shown again (`practiceSeen`
  is local to the page): "Continue" is enough. Not changed here (known issue).
- `/errors/categories`: "Practise this category" on every active category of level 2 or more outside pronunciation, with
  the accessible name "Practise this category: {label}" (the visible text is contained in it).

## D-162 — Error codes and test helpers (M5.c2; follows D-156)

- `errorMessage.ts` knows `drill_not_found` (404), `already_answered` (409) and `not_drillable` (422). The `reason` of
  `not_drillable` (`level`, `pronunciation`, `proposed`, `rejected`) is shown as a translated line (`drills.reasons.*`),
  falling back to the backend's English sentence for any other reason. The other codes the drills can answer were already
  known (`category_not_found`, `item_not_found`, `exercise_mismatch`, `invalid_request`, `session_not_found`...).
- Test helpers: `renderApp` takes a router entry (so a test can start with a navigation state), `node` of
  `writingFixtures.ts` is exported, `test/drillFixtures.ts` has a small fake server that grades like `domain/drills.py`
  and never shows a solution before an answer.
- Run Vitest from `frontend/` (`npx vitest run ...`) or through `npm run check`: `npm --prefix frontend exec -- vitest`
  from the repository root gave a jsdom setup error in this session.

## D-163 — Cards made from errors (M5.a3; departure from "two cards per term" approved with the plan)

- **One error, one term, one productive card.** `POST /api/errors/{id}/card` (`services/error_cards.py`,
  `domain/error_cards.py`) creates a `lexical_item` (`origin_error_event_id` = the error, `item.created` origin `error`,
  `discovered_at` set), links it to the deck "Error cards" (`kind = error_drill`, created and activated with the first
  card), writes a small usage sheet, one `gap_fill` template and **one productive card** due at the start of the next
  study day (like a discovery). Events: `item.created`, `deck.item_added`, `item.status_changed`, `card.created` and the
  new `error.card_created {error_event_id, lexical_item_id, card_id, deck_id, category_code, source, recurrence}`.
  No receptive card (the departure from SPEC module C, approved by the owner and written in SPEC module E): a grammar
  rule has no recognition exercise without an AI and a receptive self-assessment would only add workload.
- **No AI**, so the card exists in degraded mode. The term is the correction; for a long correction (a sentence, from a
  drill error) it is the changed words with one word of context on each side, and `term` in the request overrides it
  (at most 6 words and 60 characters). The exercise is the sentence the error came from with the wrong form replaced
  by the correction and **only the changed words blanked** ("live ___ campus"): blanking the whole term would leave
  nothing to guess from. When the correction only removes words, the whole fragment is blanked.
- **A card always has its sentence**: an error without an original sentence (a manual one) is refused with 422
  `not_cardable` `reason: no_context` unless the request gives a `sentence` that contains the correction
  (`invalid_sentence` otherwise). Other reasons: `no_correction`, `too_long`, `invalid_term`. 409 `card_exists` (+
  `item_id`) when the error already has a card or the term is already in the library; 404 `error_not_found`.
- **The wrong form is a pitfall of the sheet.** `grade_typed` tolerates one edit from four characters on, so "in campus"
  typed for "on campus" would be a typo (Hard). The sheet lists the wrong fragment and the wrong changed words as
  `french_speaker_pitfalls`, which makes them `wrong` answers (tested: "in" for "on" is `wrong`, never `typo`).
  `review_flow._origin_category`: when a review falls into such a pitfall, the review error keeps the **category of the
  origin error** (a preposition stays a preposition) instead of `lexis.wrong_word` / `lexis.collocation`.
- The sheet's definition is the error's explanation (or "Say X, not Y"), saved by the new
  `enrichment.store_generated_sheet` (provider `error`, prompt version `error-card-v1`), **not** by `save_sheet`: that one
  derives a typed-recall template whose cue would be the rule, which contains the answer. Templates have origin `user`.
- New transition kind `FROM_ERROR` (`draft -> learning`) in `ITEM_TRANSITIONS`: the term skips discovery (the user met the
  error and its correction already) and does not use the daily quota of new terms.
- The error row is not changed (no `lexical_item_id` written on it); `ErrorOut.card = {id, term} | null` is read from
  `origin_error_event_id` (additive field).

## D-164 — Suggestions for recurring errors (M5.a3)

- **Recurring** = the same wrong form corrected the same way at least twice (default `min_count` 2): the key is
  `"<wrong> => <correction>"` once lower-cased, with one apostrophe and words only (`pair_key`). Errors of source `drill`
  are left out (D-137: a drill's mistakes are the generator's sentences, not habits). Deterministic, no AI.
- `GET /api/errors/suggestions?min_count=&limit=` (1 to 50, default 20): `{suggestions: [{key, erroneous_text,
  correction, category, count, first_at, last_at, error_id, sample_error_ids (5, newest first), term, cardable,
  reason}]}`, the most frequent first, then the most recent, then the key. `error_id` is the newest error of the group
  that can become a card (the one to send to `POST /errors/{id}/card`); a group none of whose errors can (no sentence)
  is shown with `cardable: false` and its `reason`. Declared before `/errors/{error_id}` so the path is not read as an id.
- A suggestion disappears when one of its errors has a card, when its term is already in the library, or when the user
  dismissed it: `POST /api/errors/suggestions/dismiss {key}` writes `error.suggestion_dismissed {error_event_id, key,
  count}` (no table, no migration; the event log is the memory). Idempotent (`{dismissed: false}` the second time); 404
  `suggestion_not_found` for a key that is not a current suggestion. A dismissal stays: a new occurrence does not bring the
  suggestion back (the owner's "no"). There is no way to undo it yet.
- CLI: `errors card <id> [--term] [--sentence]`, `errors suggestions [--min-count] [--limit]`, `errors dismiss <key>`.

## D-165 — `store_correction`, `store_analysis`, `store_drill` (M5.a3)

- The write transaction of each AI task was a private `_write` that opened its own session. Each body is now a public
  function that writes **in the caller's transaction, without committing**: `corrections.store_correction`,
  `transcripts.store_analysis`, `drills.store_drill`. The AI paths call them from a short `with session_factory()` block
  and commit exactly as before (behaviour unchanged: the whole test suite is the proof); the demo calls them inside its one
  transaction. The rule "no write transaction during an AI call" is unchanged: the AI call still happens before.

## D-166 — The demo goes through the services (M5.a3; narrows D-035)

- **Dataset v3** (`content/demo/`): `explanation_fr` on the 59 error templates, `tutor_lines` (the other speaker of the
  simulated conversations), `drills.yaml` (six drills of five items for six categories, with the learner's wrong answer
  `wrong` for each gap-fill), and a full sheet for `tweak` (the term the last session leaves half discovered must have one).
- `app/demo/fictional_ai.py` builds the outputs the AI tasks would have returned (correction, transcript chunk, drill) and
  **validates them with the real Pydantic output models and validation contexts**, so a template that does not fit raises.
  Provenance: provider `demo`, prompt versions `demo-correction-v1`, `demo-transcript-v1`, `demo-drill-v1`.
- Written productions: `record_written_production` then `corrections.prepare` + `store_correction` (spans, `error_event_ids`,
  `production.corrected`). Transcripts: `You:` / `Tutor:` conversations through `record_transcript`, `prepare` (with the
  context) and `store_analysis`; spelling is left out as the real task does. Drills: `store_drill`, then `answer_item` for each
  item (the learner's score rises from 50 % to 85 %); a drill every 6 to 10 worked days, the plan's targeted category when a
  drill exists for it, never the same drill twice in a row; **the last session leaves one drill half answered**. Review
  errors: `error_log.record_error`. Spoken productions: no service before M6, so `direct_writes.record_oral_production` is
  the only direct write left (its errors still go through `error_log`).
- **Cards from errors in the demo**: at about days -30 and -12 the learner makes up to two cards from the suggestions, and
  dismisses one at day -12; the simulation reviews them with the other cards (their templates are registered).
- The new random generator (`_drills`) is derived after the others, but the reviews of the new cards and the longer
  sessions shift the older generators' draws: **the demo fingerprint changes** (D-137 already warned); determinism (same
  seed, same fingerprint) and the other seeds' difference are still tested. Result for seed 42, 60 days, anchor 2026-09-01:
  7 drills (6 finished, 1 open), 14 drill errors, 4 analysed transcripts, 8 corrected writings, 4 cards from errors, 1
  dismissal.

## D-167 — Small conventions met in M5.a3

- The terms made from tense errors are the corrected fragment ("I haven't decided yet"): usable, but the cards fit fixed
  expressions better. The user can give `term` and `sentence`. A smarter choice would need an AI and is left out.
- If the user later edits the sheet of an error card with `save_sheet`, the derived typed-recall cue is the rule, which
  contains the answer (known issue, D-163). Not handled here: the editing screens are not planned for these items.
- The deck "Error cards" is an ordinary deck for the queue (it takes a queue position like the others); the screens show it
  with `kind: error_drill`, which the frontend does not special-case yet.
- `ErrorOut.card` is additive; the frontend types are untouched in this milestone.

## D-168 — M6 is cut in five (M6.a1, 2026-10-18)

- **M6.a1** (backend): local recordings, Groq Whisper transcription through the gateway, word-by-word comparison
  with a target sentence, playback, events, CLI. **M6.a2** (backend): corrected free speaking, spoken answers in
  reviews (`spoken_answer`), the demo through the services (removes `app/demo/direct_writes.py`). **M6.b1** and
  **M6.b2**: the frontend (`MediaRecorder` recorder, screens). **M6.c**: Azure AI Speech, optional.
- Out of M6.a1 on purpose: local transcription (faster-whisper, to propose later), any error created from the
  comparison (D-174), backup and export of the audio (M10).

## D-169 — Recordings are files under `data/audio/` (M6.a1)

- **Folder**: `<resolved_data_dir>/audio/`, and `<resolved_data_dir>/audio-demo/` when `settings.demo` is on, so no
  demo file mixes with the owner's recordings; `demo seed` empties `audio-demo/` once the new database is in place
  (a refused or failed seed leaves it). *Since M6.a2b (D-188), `demo seed` replaces `audio-demo/` with the clips it
  wrote, together with the database.* The demo folder follows `settings.demo` (`VOCAB_DEMO`, `--demo`), not the
  demo marker of the database: `VOCAB_DATABASE_URL` and the demo mode exclude each other (D-033).
- **Names** are the server's: `YYYY/MM/<uuid4 hex>.<ext>`, never the client's. `production_attempt.audio_path` holds
  that path relative to the folder. Reading checks the stored path against this exact pattern and that the resolved
  path stays inside the folder (no traversal, no absolute path, no backslash).
- **Formats** (media type, parameters such as `;codecs=opus` ignored -> extension): `audio/webm` webm, `audio/ogg`
  ogg, `audio/mp4` and `audio/x-m4a` m4a, `audio/wav` and `audio/x-wav` wav, `audio/mpeg` mp3. Groq reads every one
  (`groq.AUDIO_EXTENSIONS`, tested). The served type follows from the extension: no column was added.
- **Limits** (`domain/speech_rules.py`): 10 MB (`MAX_AUDIO_BYTES`, well below Groq's 25 MB), an empty file refused,
  and duration bounds per production kind (shadowing 0.5 to 30 s; M6.a2 adds free speaking, about 180 s). The
  client sends `duration_s` (a `MediaRecorder` webm often has no duration in its metadata): it is checked before
  anything is written and is the only measure in degraded mode.
- **Writing**: a temporary file in the same folder, flushed and fsynced, then `os.replace`; done **before** the
  database transaction, and deleted if that transaction fails (tested by a failing event write and by an unknown
  term). `clear()` uses `shutil.rmtree(ignore_errors=True)`: on Windows a file another program holds open stays.
- **Playback** `GET /api/productions/{id}/audio` is Starlette's `FileResponse`. Checked on 2026-10-18: Starlette
  **1.8.0** is installed; `FileResponse` answers HTTP `Range` requests since 0.39.0 ("Add support for HTTP Range to
  FileResponse", #2697) with fixes up to 1.8.0 (weak `If-Range`, several ranges, client disconnect), confirmed in the
  installed code (`accept-ranges: bytes`, 206, 416) and by a test (`Range: bytes=4-11` -> 206). Nothing to write.
  `audio_url` is given whenever `audio_path` is set; a file deleted by hand gives 404 `no_audio` on playback.

## D-170 — The upload is the raw body, and the guard lets `audio/*` through on `/api/speech/` (M6.a1)

- `POST /api/speech/shadowing`: the body **is** the recording (`Content-Type` = its media type), everything else is a
  query parameter (`target_text`, `duration_s`, `item_id`, `origin` = `shadowing` | `discovery`, `study_session_id`).
  No multipart, so no `python-multipart` dependency, and `/docs` still offers a file picker (`openapi_extra`
  describes a binary body for each accepted type).
- An **async dependency** reads `request.stream()`: 415 `unsupported_audio` for a media type that is not accepted, 413
  `audio_too_large` from `Content-Length` before reading, or as soon as the streamed (chunked) body passes 10 MB.
  The routes are plain `def` with no database session in their dependencies (D-038).
- **The guard** (D-061, rule 3) refused every body that is not `application/json` (415). It now also accepts an
  `audio/*` body, on paths under `/api/speech/` only. No `audio/*` type is "CORS-safelisted" (only
  `application/x-www-form-urlencoded`, `multipart/form-data` and `text/plain` are), so a request from another site is
  still "non simple": the browser sends a preflight, which CORS refuses (tested). Host, Origin and
  `Sec-Fetch-Site` rules are unchanged, and apply to these routes too.
- The target sentence is a query parameter, so it appears in uvicorn's access log (console only, never a file). It
  is the learner's practice sentence, not a secret: accepted.
- Codes: 413 `audio_too_large` (+ `max_bytes`), 415 `unsupported_audio`, 422 `audio_empty`, `audio_too_short` /
  `audio_too_long` (+ `min_s`, `max_s`), `invalid_target` (empty, no word, over 400 characters: checked by the
  service, so the query parameter has no length constraint), `invalid_request` (missing parameter, NaN or infinite
  `duration_s`), 404 `item_not_found`, `session_not_found`, 409 `session_closed`.

## D-171 — `verbose_json`: the provider's duration and silence detection (M6.a1)

- **Checked on 2026-10-18** in Groq's API reference (the OpenAPI specification embedded in console.groq.com/docs):
  `response_format` accepts `json`, `text` and `verbose_json`; `CreateTranscriptionResponseVerboseJson` **requires
  `language`, `duration` ("the duration of the input audio", typed as a string) and `text`**; each
  `TranscriptionSegment` requires `id`, `seek`, `start`, `end`, `text`, `tokens`, with `no_speech_prob` and
  `avg_logprob` optional. Its description of `no_speech_prob` says "higher than 1.0 and avg_logprob below -1": 1.0
  is impossible for a probability, a typo copied from OpenAI's.
- **Whisper's own rule** (openai/whisper, `transcribe.py`): defaults `no_speech_threshold=0.6`,
  `logprob_threshold=-1.0`; a segment is skipped as silence when `no_speech_prob > 0.6` and `avg_logprob` is not
  above -1.0. That is the threshold used.
- **Groq free limits** (rate-limits page, "Free Plan Limits" tab; speech-to-text page) are unchanged from D-046:
  `whisper-large-v3` and `-turbo` 20 requests per minute, 2 000 per day, 7 200 audio seconds per hour, 28 800 per
  day, 25 MB per file. Only the date of the check in `groq.py` changed.
- **Gateway**: `Gateway.transcribe(audio, language=, pin_provider=)` keeps its signature. `ProviderResponse` gains an
  optional `transcription` (duration and segments as numbers); internally `parse` receives the whole response
  instead of its text. `TranscriptionOutput` gains `duration_s` and `segments` (optional). The fake provider can play
  them (`Success.transcription`).
- **Groq adapter**: asks for `verbose_json`, read tolerantly because it was never called live before: `duration` as a
  string or a number (negative, NaN, infinite or unreadable -> None), segments that are not objects ignored, numbers
  that are not numbers -> None, only `text` required (the plain `json` answer still reads). The live test
  `tests/live/test_live_speech.py` checks a real answer carries a duration.
- **Duration**: the API keeps the client's `duration_s` mandatory (bounds checked before any write). After a
  successful transcription, Groq's `duration`, when present, replaces `production_attempt.audio_seconds` and goes in
  `production.transcribed.audio_seconds`; `production.recorded` keeps the recorder's value. Rule for M9: the last
  measure wins. No new setting.
- **Silence**: `silence` when the transcription has no word, or when **every** segment is silence by Whisper's rule
  (a segment without the two numbers is not). The invented text ("Thank you.") is not stored (`text = ""`), and
  nothing is compared.

## D-172 — The target sentence is never a prompt for Whisper (M6.a1)

- Whisper accepts a `prompt` that biases the recognition towards its words. Sending the target sentence would pull
  the transcription towards what the learner was expected to say and hide exactly the intelligibility problems the
  comparison looks for. So `Gateway.transcribe` has no prompt parameter, the Groq request has no `prompt` field
  (tested), and the clip goes under its generated name (`<uuid4>.<ext>`, or `recording.<ext>` when the CLI
  transcribes before storing), never the client's file name or the target. The service test checks the recorded
  `TranscriptionRequest` holds the audio, the language and the timeout only.

## D-173 — The word-by-word comparator (`domain/speech_compare.py`, version `speech-compare-1`) (M6.a1)

- **Words**: `clean_typography` (made public in `normalize.py`: NFKC, typographic apostrophes, quotes and dashes),
  en and em dashes as separators, then tokens `\d+(?:[.,]\d+)+%?` (grouped or decimal numbers), words of letters or
  digits with inner apostrophes or hyphens, a final apostrophe and an optional `%`, or a lone `%`. The comparison
  key is case-folded, a final apostrophe dropped ("students'" = "students"). Punctuation is ignored, as in D-102.
- **Canonical forms** (a word may have several; two runs are equivalent when their sets meet): `%` = percent,
  `50%` = 50 percent; a hyphenated word = its parts **and** the joined form ("e-mail" = "email"); "1,000" = 1000;
  cannot / can't = can not, won't = will not, shan't = shall not, X n't = X not; 're are, 'm am, 've have, 'll will,
  'd would or had; let's = let us; 's after he, she, it, that, this, there, here and the wh-words = is or has (it's
  also = its); another word's 's = is, has, or the plural sound ("John's" = "Johns"). Then on the whole run: "per
  cent" = percent, numbers in words from zero to a hundred = digits ("twenty-one" = 21, "a hundred" = 100).
- **Alignment**: dynamic programming with backtracking over target and heard words. Costs: match 0, merge k:l
  (k, l <= 3, tried in the order 1:2, 2:1, 1:3, 3:1, 2:2, 2:3, 3:2, 3:3; "it's" = "it is") 0, close 1, substitution
  2, missing 2, extra 2. One generator of options serves both the filling and the backtracking, in a fixed
  priority (match 1:1, merges, close, substitution, missing, extra), so the result is minimal and deterministic.
  `difflib` was not used: it does not give a minimal alignment. Every step carries `[target_start, target_end)` and
  `[heard_start, heard_end)`: each word of both sides appears exactly once, in order (property tested on 500 random
  pairs). Cost: O(target x heard); 0.17 s for 400 and 2 000 characters.
- **Close** (the owner's choice, 2026-10-18): both words alphabetic, and either a British / American variant two
  edits apart by a spelling key (`-ogue` / `-og`, `-mme` / `-m`, grey / gray), or one Damerau edit (D-102) on a
  target word of **five letters or more**, **except** on the first letter or for a final -s or -d added or removed
  ("effects" / "effect" stays a substitution: it is a real difference for the listener). Known limits: these /
  those and quite / quiet are one edit apart and count as close; homophones (their / there), numbers above a hundred
  in words and ordinals are different.
- **Output**: the steps, `unrecognized` (target words substituted or missing, with their position and what was
  heard), counts and `word_accuracy` = (match + close) / target words. `pronunciation_result` stores the target, the
  transcript and `unrecognized_words`, `scores = null` (reserved for M6.c) and the provider; **the alignment is
  computed again on every read** (pure and fast), so a better comparator improves the old attempts. The version
  goes into `pronunciation.checked`.
- Limits: a target of at most 400 characters; `speech compare` accepts at most 2 000 characters heard.

## D-174 — No error is created from the comparison (M6.a1)

- A word the recogniser did not find is a *possible* intelligibility issue, never an error: speech recognition is not
  a pronunciation judge (an accent it knows less well, a noisy room, a homophone), and automatic errors would skew
  the normalised rates of module I. Nothing in M6.a1 writes `error_event`. The user can record a flagged word as a
  `pronunciation.intelligibility` error through the existing manual entry (a screen comes in M6.b). The CLI says so
  (`NOT_A_JUDGE`); the screens will (M6.b).

## D-175 — Events and the transcription state (M6.a1)

- `production.recorded` **version 4**: the new origin `shadowing`, and `discovery` on a spoken production (step 4 of a
  discovery); `audio_seconds` = the recorder's measure. `ProductionOrigin`'s docstring now covers written and spoken
  productions. A shadowing has `word_count = 0`: a repeated sentence holds none of the learner's own words, and
  `word_count` is the denominator of the error rates.
- New `production.transcribed` {`production_attempt_id`, `kind`, `provider`, `model`, `ai_call_id`, `status` `ok` |
  `silence`, `heard_word_count`, `audio_seconds`} and `pronunciation.checked` {`production_attempt_id`,
  `target_word_count`, `recognized_count`, `unrecognized_count`, `word_accuracy` (4 decimals),
  `comparator_version`, `provider`}. No text in the payloads (as for the transcripts of M5.a2). `model` and
  `ai_call_id` were added to the milestone's list, as in `production.corrected`. For module I: minutes of speech,
  intelligibility over time.
- **"Already transcribed"** = a `production.transcribed` event exists for the production (the event log as memory, as
  in D-164), checked before the call and again in the write transaction (409 `already_transcribed`; a concurrent
  transcription loses, tested). `production_attempt.ai_call_id` is **not** used: it designates the correction call,
  which M6.a2 will add for free speaking.
- `ProductionOut` gains (additions only) `audio_url`, `audio_seconds`, `transcription_status` (`pending` | `ok` |
  `silence`, null without a recording; without it the M6.b1 screen could not tell "to transcribe again" from
  "silence") and `comparison` (a transcribed shadowing). `GET /api/productions?kind=shadowing` lists them.
- Origin `discovery`: `item_id` stays optional (no new error). `item_id`, when given, becomes a `production_target`
  with `used = null`.
- An AI failure writes nothing: the answer is 201 (or 200 for a retry) with `transcription.status = unavailable` and
  `reason` (an `UnavailableReason`, or `incomplete` when the provider answered without a usable text).

## D-176 — `speech` commands (M6.a1)

- `speech shadow --file <clip> --target "<sentence>" [--item <id>] [--duration <s>]`, `speech transcribe <id>`,
  `speech compare "<target>" "<heard>"` (no AI, no database). The media type comes from the extension (`.webm`,
  `.ogg`, `.m4a`, `.mp4`, `.wav`, `.mp3`). With `--demo` the recordings go to `data/audio-demo/`.
- **Without `--duration`** the CLI calls the gateway first (no session open), takes Groq's `duration`, then stores the
  production and that transcription without a second call (`record_shadowing(transcription=...)`). Without a
  provider, or without a duration in the answer, it refuses (exit 2) and stores nothing: the manual scenario
  without a key passes `--duration`. The service raises `duration_required` (422) in that case; the API never meets
  it, since `duration_s` is mandatory there.
- Exit codes (D-053): 0 done (silence included), 1 the transcription is unavailable (the recording is kept; the
  message gives `speech transcribe <id>`), 2 usage (no database, unreadable or refused clip, invalid sentence,
  unknown term or production, already transcribed). Everything is refused before any AI call when possible. Output
  goes through `_console_safe()` and is plain ASCII apart from the learner's own words.

## D-177 — Small conventions met in M6.a1

- `.env.example` and the README say that recordings sent to Groq's free tier leave the machine, and that they stay
  in `data/`, never in Git. The CI list of refused files gains `flac`, `opus`, `aac` and `mp4` (`wav`, `webm`, `mp3`,
  `m4a`, `ogg` were already there). No audio file is in the repository: the tests build their WAV clips in memory
  with `wave`, or use a few fake bytes when the provider is fake.
- No migration (the schema already had `audio_path`, `audio_seconds`, `pronunciation_result`), no new dependency, no
  new setting, no frontend change.

## D-178 — M6.a2 is cut in two; facts checked (M6.a2a, 2026-10-19)

- **M6.a2a** (this milestone, backend): corrected free speaking, spoken answers in reviews checked by
  transcription and the AI, the CLI. **M6.a2b** (next, same branch): the demo through the services (injectable audio
  names, atomic `audio-demo/`, short WAV clips, fictional `speaking_correction` outputs and transcriptions in
  `fictional_ai.py`, dataset v4), which removes `direct_writes.py` and closes D-035. The services of M6.a2a already
  take an injected `AudioStore` and a given transcription (`transcription=`) for that.
- Branch `feat/m6a2-speaking-correction`, cut from `feat/m6a1-recordings-transcription` (M6.a1 is not merged into
  `main` yet: PR #21). No migration, no new dependency, no new setting, no frontend change.
- **Checked on 2026-10-19** on the official models page (ai.google.dev/gemini-api/docs/models): `gemini-3.5-flash-lite`
  is listed under Gemini 3, "Stable". Groq's limits were not read again: nothing surprising happened.

## D-179 — Recording kinds, their bounds and the units of a spoken text (M6.a2a)

- `domain/speech_rules.py`: `RecordingKind` = `shadowing` / `speaking` / `spoken_answer`; `DURATION_BOUNDS` is keyed
  by it, and since `shadowing` and `speaking` have the values of `ProductionKind`,
  `DURATION_BOUNDS[ProductionKind.SHADOWING]` still reads the M6.a1 bounds (its tests are unchanged). Bounds:
  shadowing 0.5 to 30 s; free speaking 5 to 180 s (the screen asks for 1 to 2 minutes: 180 s is a technical ceiling
  so a take that runs over is not lost; SPEC module F says "up to 3 accepted", **approved by the owner** with the
  plan); spoken answer 1 to 90 s.
- `MAX_SPEAKING_CHARS = 4000`, as a written text: about three minutes of a learner's speech is 2 500 characters.
- `speech_units(text)`: the sentences of `split_sentences(max_sentences=None)`; beyond 40 they are grouped into 40
  units of consecutive whole sentences, balanced (the first `n % 40` units hold one sentence more). A unit is the
  original text from the start of its first sentence to the end of its last, so `spans` stay exact. Tested on 200
  random texts (every sentence in exactly one unit, in order, positions exact, sizes balanced).
- `grading.production_rating` also reads `speaking-1`: Good when the term was heard and judged correct with no error
  tied to it; Again when it is misused or an error concerns it; **none when it was not heard** (the learner may have
  left it out, or the recogniser may have missed it: speech recognition is not a pronunciation judge, D-174), with
  `production_warnings` giving `term_not_heard`. A written sentence without the term is still Again (D-129). Easy and
  Hard are never proposed.
- Topics: `domain/topics.py` holds the file format and the daily pick, shared by `writing_topics.py` (same names and
  behaviour, its tests unchanged) and `speaking_topics.py` (`SpeakingTag` adds `presenting`).

## D-180 — The `speaking_correction` task (M6.a2a)

- **Task** `speaking_correction` v1. Inputs as `production_correction` (D-128): `mode` (`answer` | `monologue`) and
  `taxonomy` are `plain`; the units (sent as numbered `sentences`), the task (cut to 500 characters) and at most 15
  targets are `data`. The taxonomy is `transcripts.allowed_taxonomy`: active codes **without `spelling` and
  `pronunciation.*`** (the recogniser wrote the spelling; pronunciation cannot be judged from a transcription).
- **Prompt rules**: real errors only (D-132); the recogniser's punctuation, capitals, spelling and homophones,
  hesitations, repetitions, false starts and self-corrections (only the final version counts), contractions and
  normal spoken style are ignored; register is an error only when it is clearly wrong for the task (an interview, a
  presentation), otherwise a note; `discourse.*` only for a connector that says the wrong thing or a clear break in
  logic, everything else about organisation goes in `structure`; the most specific subcategory ("at university"; a
  duration with "since" is one by/for/since error, D-134). Tuned once against the real model (D-185).
- **Schema**: `SpeakingCorrectionOutput` **inherits** `ProductionCorrectionOutput`, so every validator of D-128 runs
  (indices, `wrong` in its unit, codes, proposals, targets, notes, 30 errors). Changes: a unit's `corrected` may hold
  4 500 characters (a spoken unit without punctuation can be long); `structure` (nullable) = `comment_en`,
  `comment_fr` (1 to 3 sentences, at most 600 characters each), `connectors_used` (at most 10, each found in the
  transcription with `find_fragment`), `suggestions` (at most 3 `{text_en, text_fr}`); `structure` is required in
  `monologue` mode. Validation context: `speaking_context(units, codes, refs, mode, text)`. `production_correction`,
  its schema and its tests are untouched.
- **Budgets** (`tasks.py`): input 20 000 characters (text 4 000, 40 units as JSON about 800, task 500, 15 targets of
  about 250, about 33 taxonomy lines of at most about 230: about 16 600); output `1 200 + 250 x units`, ceiling
  10 000 (the base is 400 tokens above D-128, for `structure`); timeout 60 s. As in D-128, 10 000 tokens are more
  than Groq's 8 000 per minute in a fallback: accepted.

## D-181 — One store for written and spoken corrections; `production.corrected` v2 (M6.a2a)

- `corrections.store_correction`'s body is now a private `_store`, set by the feedback format and the date of the
  errors; `store_correction` calls it unchanged (the whole suite is the proof). `store_speaking_correction` (D-165:
  the caller's transaction, no commit) writes `format: "speaking-1"` with **exactly the keys of `correction-1`**
  (`prompt_version`, `provider`, `model`, `output`, `spans`, `error_event_ids`, `targets`), so the M6.b screens reuse
  the highlighted view; `output` keeps `structure`.
- Spoken errors: `original_text` = the unit, `occurred_at` = **the time of the recording** (`attempt.created_at`),
  since a correction can come days later; `spans` are code points into the transcription.
- `production.corrected` **version 2** adds `kind` (optional, so version 1 reads), written by written corrections,
  transcripts and spoken corrections: M9 can count corrected speech apart.
- `recorded_origin`, `targets_for`, `prompt_line` and `task_inputs` of `corrections.py` are shared with the spoken
  correction.

## D-182 — Free speaking (M6.a2a)

- **Recording core** (`speech.record`, a `Recording` = kind, bounds, prompt, targets, origin, study session): used
  by the shadowing (`record_shadowing` keeps its signature), free speaking and the spoken answer. Order: the upload
  and its duration, then a short read that checks the terms, the session and the caller's own checks (`check`),
  **before the file is written**; the same checks again in the creating transaction; the file is deleted if that
  transaction fails (D-169). The shadowing gains the early read too: same results, but a refused term no longer
  writes and deletes a file (approved with the plan).
- `services/speaking.py`: `record_speaking` creates `kind = speaking`, `modality = oral`, `prompt_text` = the topic,
  targets with `used = null`, `production.recorded` **version 5** (new origin `speaking`). The topic is never a
  Whisper prompt (D-172; tested). After the transcription, a spoken production's `word_count` = the words heard
  (`speech_compare.words`), the denominator of the error rates; a shadowing keeps 0 (D-175).
- `prepare_speaking` refuses before any AI call, in this order: 422 `not_correctable` (not a speaking production; a
  shadowing is compared, never corrected), 409 `already_corrected`, 409 `not_transcribed` (no
  `production.transcribed`: transcribe it first), 422 `nothing_to_correct` (silence), 422 `text_too_long` (over 4 000
  characters). `correct_speaking`: short read, the AI with no session open, one short write that checks again (D-038;
  tested with a second writer taking `BEGIN IMMEDIATE` during both calls). A failure writes nothing and can be retried.
- **Mode and source come from the origin** of `production.recorded`: `review` gives `answer` and the source `review`,
  anything else `monologue` and `speaking`. A retry of a spoken answer through `/correct` keeps them.
- API: `POST /api/speech/speaking` (raw body, the shadowing's dependency, D-170; query `duration_s`, `prompt_text?`,
  `target_item_ids?` repeated, `study_session_id?`; lengths checked by the service, 422 `invalid_production`) answers
  201 `SpeechOut` with `comparison: null`; nothing is corrected until `POST /api/productions/{id}/correct`, which now
  sends a speaking production to `speaking_correction`.
- **Topics**: `content/speaking_topics.yaml` (26 fictional topics, EN and FR, tags `interview`, `presenting`,
  `academic`, `data_science`, `everyday`, `campus`; 7 interview questions and 7 presentation topics, results among
  them). `GET /api/speaking/topics?count=3&tag=` (in `api/speech.py`, the module F router): deterministic per study
  day, skipping the **spoken** prompts of the last 7 days (`recent_prompts(modality=oral)`); the writing topics keep
  skipping every prompt, as before.

## D-183 — Spoken answers in reviews (M6.a2a; extends D-129)

- `POST /api/speech/review-answer` (under `/api/speech/`, the only paths that take `audio/*`, D-170; never under
  `/api/reviews/`). Query: `card_id`, `session_id`, `exercise_template_id`, `duration_s` (1 to 90), `response_time_ms`
  (>= 0, validated, not stored: the final call times the card).
- `spoken_review.check_spoken_answer`: every refusal **before any write and any AI call**, in this order:
  `card_context(..., "spoken_answer", template)` (404 `card_not_found`, 422 `exercise_mismatch` for the type, the
  template or the card's direction), `review_flow.require_due` (extracted from `record`, 409 `not_due`), a reviewable
  term (409 `review_not_allowed`), `require_open` (404 `session_not_found`, 409 `session_closed`), then the recording
  (422 `audio_empty`, `audio_too_short`, `audio_too_long`; 413 and 415 even earlier, while reading the body). Tested
  by counting the rows, the files and the provider calls.
- Then **three short transactions**, none open during the two AI calls: the recording (prompt = the question,
  target = the term, origin `review`, its checks run again), the transcription, the correction in `answer` mode.
  Neither the question nor the example answer reaches Whisper (tested).
- Answer 200: `{production_attempt_id, transcription: {status, text, reason}, status, reason, feedback|null, errors,
  proposed_rating: 1|3|null, warnings, solution: {example_answer}, sheet_summary}`. A failed transcription:
  `status: unavailable` with its reason, the recording kept; silence: `unavailable` / `silence`; a transcription over
  4 000 characters: `unavailable` / `text_too_long` (kept, not corrected); a failed correction: the transcription is
  returned, no rating; `term_not_heard`: a warning and no rating. The solution and the sheet summary come in every
  case, since the recording is the attempt (D-103; the anti-leak walk of `test_session_api` now calls this route on
  every `spoken_answer` step and finds `example_answer` in `solution` only).
- `POST /api/reviews` with `production_attempt_id` (`_checked_production`): the exercise types checked by the AI and
  the kind of their production (`CHECKED_TYPES`: `sentence_production` -> `writing`, `spoken_answer` -> `speaking`);
  409 `production_mismatch` for a production of another kind (so a sentence production now refuses a spoken one, and
  the reverse, approved with the plan), a spoken production whose origin is not `review` (a free speech), another
  term, another session, or one already used; other exercise types keep 422 `exercise_mismatch`. `auto_rating` is
  computed again from the stored feedback (the client cannot send it); `review_log.audio_path` gets the production's
  recording (the column exists since M1 for this). Errors keep the source `review` and `production_attempt_id`,
  never `review_log_id` (D-127).
- Two AI calls in one request: the M6.b client must allow about a minute and a half.

## D-184 — `speech speak` and `speech correct` (M6.a2a; extends D-176)

- `speech speak --file <clip> [--prompt TEXT] [--duration S] [--no-correct]`: without `--duration`, Groq measures
  the clip first and that transcription is stored without a second call (D-176); then the bounds 5 to 180 s are
  checked. `speech correct <id>` corrects a stored spoken production (refused before any gateway is built when it is
  not correctable). `--demo` writes into `data/audio-demo/`.
- Output: the transcription, the errors (`#id date source code`, `wrong -> correction`, the unit, the rule), the
  notes, the corrected and natural versions, the structure (comment, connectors used, suggestions) and the sentence
  saying that **the correction is about what speech recognition heard**. The written renderer is shared
  (`cli_write.render_correction`).
- Exit codes (D-053): 0 done (silence and `--no-correct` included), 1 the transcription or the correction is
  unavailable (the production is kept; the message gives `speech transcribe <id>` and `speech correct <id>`), 2
  usage (unreadable or refused clip, bounds, topic over 500 characters, unknown production, not transcribed yet,
  already corrected, no duration without a provider).

## D-185 — Tuning `speaking_correction` against the real model (M6.a2a)

- Live runs with the owner's keys on 2026-10-20 (`gemini-3.5-flash-lite`; Groq `whisper-large-v3`). The example
  (`content/examples/m6_speaking.txt`: hesitations, a self-correction "I present— I presented", "I live in campus",
  "I study here since two years", "I never presented in English before") must give exactly
  `grammar.preposition.fixed_expression`, `grammar.preposition.by_for_since` and
  `grammar.tense.past_simple_vs_present_perfect`; the clean one (`m6_speaking_clean.txt`) no error.
- **First prompt**: the example was right in 0 of 3 runs: the past simple was missed twice (taken for "normal spoken
  style"), and once reported under the parent `grammar.tense`. The clean text gave 0 errors.
- **Fix** (in the prompt, not in the tests, D-132; v1 was never released, so it was edited in place as D-132 did):
  "spoken style never excuses a grammar mistake", with the past simple of an experience up to now as the example
  (other sentences than the test's: "I never worked with R before", "I already sent the file"; the past simple stays
  right with a finished time), and "a tense error never takes the parent tense code alone". The taxonomy was not
  touched (still version 3).
- **Result**: the example gave exactly the three codes in **9 of 9 runs** (3 probes, 3 passes of
  `test_live_speaking.py`, the audio pass, 2 runs of the CLI on the transcribed clip); the clean text **0 errors in 7
  of 7** (4 probes, with no naturalness note either, and 3 passes). No wrong form was a hesitation or a false start.
  The two M5.a1 live tests still pass (`production_correction` untouched). A lite model is not deterministic: a run
  may still miss or over-report; the user sees, edits and deletes any error.
- **First real `verbose_json` answer** (D-171): a synthetic clip of the example (Windows System.Speech, voice
  "Microsoft Zira Desktop", 33 s, made in a temporary folder and never committed) came back with `duration`
  33.079437312 s; Whisper kept "Um", "uh" and the self-correction (as "I present I presented", the dash dropped), and
  did not smooth over the three mistakes on this clear synthetic voice. A human voice may differ: the audio test only
  requires `ok`.

## D-186 — Small conventions and departures met in M6.a2a

- Departures from the prompt and the plan, beyond those approved with the plan (180 s and the SPEC sentence,
  `/correct` in `answer` mode for a review origin, silence as `unavailable` / `silence`, `review_log.audio_path`, the
  symmetric refusal of `sentence_production`, the early checks for the shadowing, 4 500 characters per unit,
  `production.corrected` v2 for every kind, the demo fingerprint):
  - `review-answer` returns `solution` and `sheet_summary` in every case once the recording exists, as
    `check-production` does (D-129);
  - a spoken answer whose transcription is over 4 000 characters gives `unavailable` / `text_too_long` (not planned);
  - the review checks of a spoken answer run three times (once to order the refusals and read the question and the
    solution, once before the file is written, once in the creating transaction), through `speech.Check`;
  - `review_flow` keeps a private `_recorded_origin`: importing `corrections.recorded_origin` would be an import cycle
    through `study_sessions`;
  - a spoken production's `word_count` counts words as the comparator does (`speech_compare.words`), a written one
    as `len(text.split())`; they agree on ordinary speech.
- The example files are fictional ("Alex"); `content/speaking_topics.yaml` quotes the values that hold `: `.
- In `--demo`, the hint printed after a failure omits `--demo` (as in M6.a1).
- The demo fingerprint changes (payload versions 2 and 5, `kind`); determinism is still tested. The demo's spoken
  productions are still direct writes until M6.a2b.

## D-187 — M6.a2b: the demo through the speech services; injectable file names (2026-10-21)

- **M6.a2b** (second part of M6.a2, D-178), same branch `feat/m6a2-speaking-correction`: the demo's spoken
  productions, shadowings and spoken answers go through the speech services; `direct_writes.py` is deleted and D-035
  closed. No migration, no new dependency (`wave`, `struct`, `math` are in the standard library), no new setting, no
  frontend change.
- **Names**: `AudioStore(root, names=...)` takes a factory of file names, `random_name` (`uuid4().hex`) by default; a
  name must be 32 lowercase hexadecimal characters (the pattern `resolve` accepts), else `save` raises `ValueError`
  before anything is written. The demo derives its names from its seed (`f"{rng.getrandbits(128):032x}"`, a generator
  taken after the others), so `audio_path`, which the fingerprint reads (D-034 leaves out only the clock columns), is
  the same for the same seed.

## D-188 — `audio-demo/` is replaced together with the demo database (M6.a2b; supersedes part of D-169)

- The trap of D-169: `demo seed` emptied `audio-demo/` after the database was replaced, which would delete the clips it
  had just written. Now the simulation writes them into `<data_dir>/audio-demo.tmp-<pid>/`, then (`seed._swap`):
  1. the previous `audio-demo/` is renamed `audio-demo.old-<pid>`;
  2. the database is moved over the target (`os.replace`, D-033);
  3. the temporary folder is renamed `audio-demo/`, and `.old-<pid>` is deleted (`rmtree(ignore_errors=True)`).
- **Order** (approved with the plan, against the prompt's "after the database"): the old folder is set aside
  **before** the database is replaced. A recording held open on Windows refuses the rename of its folder (checked on
  the owner's machine: `PermissionError`, WinError 5), and then nothing has changed yet: "a recording is in use, close
  the program playing it, or stop the app" (exit 2). A database held open by the app refuses step 2, and the old
  folder is put back. In the prompt's order a locked folder would have left the new database with the old clips.
- If step 3 fails (the folder locked between two renames: rare), the old folder is put back and the message says the
  new database is in place and to run `demo seed --reset` again.
- Any failure while building removes the temporary file and folder and leaves the previous database and recordings
  intact (tested as D-033: a failing simulation that wrote a clip; on Windows, a recording and the database held open).
  `audio_path` is relative to the folder, so it stays valid after the rename.
- `seed_demo(audio_dir=...)` replaces `audio_store=` (default: `audio-demo/` next to the database; the CLI passes
  `AudioStore.demo(settings).root`, the same folder). `AudioStore.clear()` has no caller left and is removed. The
  summary prints "Recordings: N files in <folder>".

## D-189 — The speech flows in the caller's transaction (M6.a2b; as D-165)

- The demo builds its history in **one** transaction (D-033). `record_shadowing`, `record_speaking`,
  `check_spoken_answer` and `correct_speaking` open and commit their own sessions, and roll back to close their reads:
  inside the demo that rollback would undo the whole simulation. So, as D-165 did for module E, each flow has a variant
  that writes in the caller's transaction, without committing and without any AI call:
  - `speech.store_recording(session, store, recording, *, data, content_type, duration_s, transcription, check, at)`:
    the same validation and checks as `record` before the file is written, then the production, then the given
    transcription (`store_transcription`); a failed transcription leaves it `pending`; if a write raises, the file is
    deleted;
  - `speaking.store_speaking(...)`: free speaking through `store_recording`; `prepare_speaking` and
    `corrections.store_speaking_correction` then correct it;
  - `spoken_review.store_spoken_answer(..., transcription, correct, provenance, at)`: the checks of
    `check_spoken_answer` (`answer_context`), the recording, then the output of an **injected corrector** (the demo's
    fictional AI) stored in `answer` mode with the source `review`; it returns the same `SpokenCheck`.
- Shared with the AI paths (behaviour unchanged, the whole suite is the proof): `speech.shadowing_recording`,
  `speaking.speaking_recording`, `spoken_review.answer_context`, and the result builders of `spoken_review`.

## D-190 — Fictional transcriptions, spoken corrections and clips (M6.a2b; extends D-166)

- `fictional_ai.transcription(text, duration_s)` is a `TranscriptionOutput` validated by the real schema: the text,
  the duration and one segment per sentence, timed by its share of the words, with confident scores; an empty text is a
  silent take (one segment with Whisper's silence scores, D-171). Provenance: provider `demo`, model
  `demo-transcription-v1`. A transcription stores no prompt version (`production.transcribed` has `provider` and
  `model`): the version goes in the model, where it can be seen (approved with the plan).
- `fictional_ai.misheard(sentence, rng, count)`: `count` words (0 to 2) lost, a plural heard as a singular
  ("effects" -> "effect", "studies" -> "study") or the word missed. Both are words the comparator does not recognise (a final -s is never "close",
  D-173); tested on every sentence of the dataset: exactly `count` unrecognised words.
- `fictional_ai.speaking_output(prepared, made, structure=, connectors=, term_used=)` is a `SpeakingCorrectionOutput`
  validated with `speaking_context` (units, codes without spelling and pronunciation, targets, mode, text). A free
  speech gets a structure comment from the dataset and the connectors actually said (whole words); a spoken answer
  (`answer` mode) has no structure and every target `used` / `used_correctly` = `term_used`. Provenance
  `("demo", None, "demo-speaking-v1")`.
- `app/demo/clips.py`: one-second mono 16-bit WAV clips at 8 kHz made with `wave` (a soft 330 Hz tone with fades, and
  a silent one), about 16 KB each. **Limit**: the declared durations are realistic (free speech: its words at 2 a
  second, from 5 to 178 s; a shadowing at 2.5 words a second; a spoken answer at 2 words a second, 1.5 to 90 s; the
  silent take 6 s), but every clip plays for one second. The demo shows that recording and playback work, not what was
  said. No audio file is in the repository.

## D-191 — Dataset v4 and the spoken history of the demo (M6.a2b; closes D-035)

- **Dataset v4** (`content/demo/`, fictional): the five files move to version 4; `prompts.yaml` gains `speech`
  (`connectors`, three `structure` comments with suggestions, three `forgotten_answers`).
- **Free speaking** (a production of kind `speaking`, as before, every 2 to 4 days among the three kinds):
  `store_speaking` with a tone clip and the fictional transcription of its text, then `prepare_speaking` and
  `store_speaking_correction`. Its errors have the source `speaking`, the production's id and the unit as their
  original text, and are dated at the recording. Speech leaves out the `spelling` and `pronunciation` templates, as
  the real task does (and as the transcripts already did).
- **Shadowing**: every 7 to 11 days (a generator `_speech` taken after the others), on the original sentence of a
  term already discovered (`learning`, `consolidated`, `active`), with the term as its target; the recogniser misses 0,
  1 or 2 words (weights 1, 2, 2). Through `store_recording` and the real comparator: `pronunciation_result` holds the
  unrecognised words. Seed 42 over 60 days: 6 shadowings, 8 unrecognised words; seeds 1 to 12: 5 or 6 each, at least 3
  unrecognised words.
- **Spoken answers in reviews**: when `choose_exercise` gives `spoken_answer`, the review goes through
  `store_spoken_answer` (a success says the template's example answer; a failure says one of the `forgotten_answers`,
  so the term is not heard: no proposed rating, `term_not_heard`), then `review_flow.record(production_attempt_id=...)`,
  which links the production, copies its `audio_path` and computes `auto_rating` again from the stored feedback. A
  spoken answer no longer gives a confusion error (D-034): its errors come from its correction, as in the app.
  The forced lapse of the last session skips a card whose exercise would be a spoken answer, since the spoken check
  refuses a card that is not due. Seed 42: 3 spoken answers, all linked (one failed). Seed 2 of 1 to 12 has none (no
  mature productive card reaches that exercise); the tests pin seed 42.
- **The last session** leaves a silent take (6 s, `silence`) and a free speech of four sentences transcribed but not
  corrected yet, so the M6.b screens have both cases.
- A pasted transcript keeps `modality = oral` without a recording: "every oral production has a file" means every
  `speaking` and `shadowing` production (tested, approved with the plan).
- **Fingerprint**: it changes, for these reasons: the marker's `dataset_version` 4; the new rows (shadowings and
  their targets, `pronunciation_result`, spoken answers, the silent take and the uncorrected speech) and events
  (`production.transcribed`, `pronunciation.checked`, `production.corrected` v2 with `kind: speaking`); spoken errors
  written by the store (unit, French explanation, spans); spoken answers with `production_attempt_id`, `audio_path`
  and an `auto_rating`, without confusion errors; speech without spelling errors; and the time the new activities take
  in a session, which moves the later reviews (the learner's success depends on retrievability at that time). The new
  generators are taken after the others, so the older ones draw the same sequence. Determinism (same seed, same
  fingerprint) and another seed's difference are still tested.
- **Time** (owner's machine, Windows 11, 60 days, seed 42, three runs of `seed_demo` in a fresh process each): 4.4 to
  4.6 s, against 4.3 s for the same measure before M6.a2b (D-111 measured 5.6 s on an earlier version and another
  load). The 7 s target is met. Through the CLI, `demo seed` prints about 5.5 s (it includes the summary queries, and
  was measured while the test suite ran).

## D-192 — Small conventions and departures met in M6.a2b

- Approved with the plan: the speech flows in the caller's transaction (D-189); the old folder set aside before the
  database is replaced (D-188); `audio_dir` instead of `audio_store` and `AudioStore.clear()` removed; the transcription
  version in `model` (D-190); "every oral production" read as every recording (D-191); a failed spoken answer leaves the
  term out (D-191); the last session's two cases (D-191); one-second clips with realistic declared durations (D-190).
- Not in the plan: `demo seed` prints the number of recordings; `test_demo_data` reads the proposed rating of a
  spoken answer from its check (it was always null before) and counts a spoken production's words as the comparator
  does (D-186).

## D-193 — The voice recorder (M6.b1, 2026-10-21)

- `frontend/src/speech/` gets the recorder next to the speech synthesis (D-112): `recorder.ts` (pure rules, unit-tested),
  `useRecorder.ts` (the hook), `activeRecording.ts` (who holds the microphone), `RecorderPanel.tsx` (the `Recorder`
  component). The component's file is **not** `Recorder.tsx`: on Windows' case-insensitive file system `./Recorder` resolves
  to `recorder.ts` (the import gave `undefined`).
- `navigator.mediaDevices` and `MediaRecorder` are read at every call, never cached: without them the recorder reports
  `unsupported` (jsdom, an old browser). Failure reasons from the error name: `NotAllowedError` / `SecurityError` →
  `denied`, `NotFoundError` / `OverconstrainedError` → `no_device`, `NotReadableError` / `AbortError` → `busy`, anything
  else `failed`.
- **Type**: the first accepted by `isTypeSupported` in the order `audio/webm;codecs=opus`, `audio/webm`,
  `audio/ogg;codecs=opus`, `audio/mp4`; none accepted → the browser's default. The blob's type is its first chunk's, else the
  recorder's `mimeType`. The backend ignores the parameters (D-169). `start(1000)` gives chunks as it goes.
- **Duration**: measured by the client, `performance.now()` from the recorder's start to the click on stop (a
  `MediaRecorder` webm often has no duration), sent as `duration_s`, rounded to 2 decimals and **capped at the maximum** (a
  timer fires a few milliseconds late, and the server would refuse 30.04 s for a shadowing). The clock is read through one
  function (`now()`), so the tests move it by hand.
- **Bounds** (the backend's, D-179), with the automatic stop at the maximum: shadowing 0.5 to 30 s; free speaking 5 to 180 s
  with a visible warning from 120 s (ready for M6.b2); spoken answer 1 to 90 s. A take that is too short is not sent (message,
  "Send" off); over 10 MB is refused before sending. The server stays the judge (`audio_too_short`, `audio_too_long`).
- **The microphone is released** (`track.stop()` on every track) when the recorder ends, when the take is cancelled, when
  the component unmounts, on a route change (a `useEffect` in the layout, like the speech's), when `getUserMedia` or the
  recorder fails, and when the user cancels while the browser is still asking (a late stream is stopped as it arrives).
  Tracks are stopped at the click on stop as well as at the recorder's `stop` event, so the indicator goes out at once.
- **One recording at a time** in the whole app (`claimRecording`), and **the speech synthesis is cut before the microphone
  opens** (`cancelSpeech()`), or the synthetic voice would be recorded. While the microphone is open "Listen" is disabled
  with a reason and `speak()` refuses to speak.
- The local clip is listened to through a `blob:` URL, revoked when replaced, on "Record again" and on unmount. Nothing is
  written to `localStorage`, `sessionStorage`, the URL or the router state (tested).
- The state is said in words: a red dot **and** "Recording… 0:42"; a polite status says "Recording started" and
  "Recording stopped: 0:12" once; the timer itself is not a live region.

## D-194 — Upload layer, error codes and the spoken fields (M6.b1)

- `apiUpload(path, blob, query, {signal})` (`api/client.ts`): a POST whose body is the `Blob` and whose `Content-Type` is its
  type; the other values go through `URLSearchParams` (undefined ones left out); the errors are `apiSend`'s. The guard accepts
  `audio/*` only under `/api/speech/` (D-170): audio is sent nowhere else.
- `api/speech.ts` holds the types read from `app/api/speech.py` (`ComparisonStep`, `Comparison`, `SpeechOut`,
  `ReviewAnswerOut`, `SpeakingTopic`) and the hooks (`useShadowing`, `useTranscribe`, `useSpeaking`, `useSpeakingTopics`;
  the last two are used by M6.b2). `Production` gains `audio_url`, `audio_seconds`, `transcription_status`, `comparison`.
- Ten codes join `errorMessage.ts`: `audio_too_large`, `unsupported_audio`, `audio_empty`, `audio_too_short`,
  `audio_too_long`, `invalid_target`, `no_audio`, `already_transcribed`, `not_transcribed`, `nothing_to_correct` (the others
  of the milestone were known). The bounds in the answer (`min_s`, `max_s`, `max_bytes`) go into the sentence. The reason of
  an unavailable transcription goes through `aiReasonText`, which learns `incomplete`; `silence` has its own sentence.

## D-195 — "Play both" and the end of an utterance (M6.b1; builds on D-112)

- `useSpeech().speak` returns whether it started and takes `onDone(completed)`: called **once** per utterance, `true` at its
  end, `false` when it was cancelled, replaced or failed. It is called even for a superseded utterance (the browsers fire
  `error` for it after the next `speak`), which the speaking state itself ignores through its token.
- "Play both" says the sentence, then plays the recording on `onDone(true)`; a run number makes a late end of a cancelled run
  do nothing; "Stop" cancels the voice and pauses the audio; without speech synthesis or an English voice the recording
  plays alone. It drives the page's own `<audio>` element. Seen working in the in-app browser: the voice, then the clip to its
  end, the button back to "Play both".

## D-196 — The shadowing pages and the router state read once (M6.b1; builds on D-142, D-152)

- `/speaking/shadowing` (new take), `/speaking/shadowing/:id`, `/speaking/shadowing/history` (20 per page, the page in the
  URL, `GET /api/productions?kind=shadowing`). The top bar's "Speaking" link points to the first for now (M6.b2: `/speaking`).
- The sentence and the term of "Shadow this sentence" come in the navigation state `{target, itemId}`: read once into the
  page's state, then the state is **cleared at once** (`navigate(..., {replace: true, state: null})`, a ref guard for
  StrictMode), because the browser keeps the router state in `history.state` across a reload. A reload shows an empty field
  (tested with the real history). The sentence is counted in code points (400), with no `maxLength`.
- Sending goes to `/speaking/shadowing/{id}` with the history replaced. When the transcription is unavailable the reason (a
  code, nothing else) goes along in the state, read once and cleared, so the next page says why without an extra request.
- The detail page starts nothing by itself: "Transcribe" / "Try again" call `POST /productions/{id}/transcribe`;
  `409 already_transcribed` reads the production again with no message; the focus goes to the result after a transcription.
  A production that is not a shadowing gets a message and a link to the error log (the redirects are M6.b2's).
- The history page repeats the page and the table of the written history; no recording text reaches any storage (tested at
  every navigation, as in D-152).

## D-197 — The comparison view (M6.b1)

- `ComparisonView` is built only from the backend's `steps` (`speech-compare-1`); `comparison.ts` cuts them into the marks of
  the two rows. "Target": `match` plain, `close` with "≈" (counted as recognised, with a hidden sentence), `substituted`
  underlined with "(heard: X)", `missing` struck through with "(not heard)"; "Heard": the transcription with `extra` marked.
  Every mark has a visible or hidden text, never the colour alone. The summary is in words ("5 of 6 words recognised"), with
  no grade and no percentage. The list of unrecognised words comes from `unrecognized`.
- **The warning is always shown**, compact or not, even when everything was recognised: speech recognition is not a
  pronunciation judge. `compact` (discovery) leaves out the log buttons; the same component serves M6.b2.

## D-198 — A misheard word logged by hand (M6.b1; builds on D-174)

- For each `substituted` word the detail page has "Log as an intelligibility error", which opens `/errors/new` with the
  state `{original_text: the transcription, erroneous_text: the word heard, correction: the target word, category_code:
  pronunciation.intelligibility, explanation}`. No button for a `missing` word (no wrong form to quote). Nothing is created
  without the user's click on "Add to my log" (tested: no `POST /errors` before it).
- `ManualErrorPage` reads the state once, clears it, fills **the first form only** (the one after a successful add is empty)
  and says it was filled in. `readPrefill` ignores any other state. The category label resolves once the tree is loaded.

## D-199 — The optional recording of the discovery's step 4 (M6.b1; builds on D-117, D-144)

- "Say it aloud" gets an optional `Recorder`: the take is sent as a shadowing of the sentence on screen (`origin=discovery`,
  `item_id`, `study_session_id`), with a compact comparison. A refusal of the server, an unavailable transcription, silence and
  a refused microphone are said and **never block** the way on. The recorder is mounted again after each take (empty), so the
  same clip is not sent twice by mistake; the sheet is neither loaded nor shown (a test counts the `/sheet` requests).
- The existing button "Done, I repeated it" stays the one way on, with or without a take (it is both "Continue" and "Skip"),
  so the older tests and wording hold. This replaces "recording comes later" (D-117).

## D-200 — "Shadow this sentence" on the term page (M6.b1; builds on D-091, D-118)

- `SheetView` takes `shadowItemId`: each example gets a link to `/speaking/shadowing` with `{target, itemId}` (a `Link` styled
  as a small button: it navigates). The discovery's `SheetView` and the versions list pass none.
- The original sentence of a term was only shown in the edit form. It now also appears in the revealed sheet ("Original
  sentence", with its link), so the whole feature stays behind the reveal button (D-091). Accessible names end with the
  sentence they act on ("Shadow this sentence (example 1)").

## D-201 — Small conventions and departures met in M6.b1

- `fakeRecorder.ts` (the microphone, `MediaRecorder`, `URL.createObjectURL`, `play()`/`pause()`, and the clock of
  `performance.now()` through `kit.advance`) and the shared `recordTake` helper; `setup.ts` removes it after each test, like the
  fake speech. `mockApi` keeps a non-JSON body (a `Blob`) as it was sent.
- The speech tests fake only the timers they need (`setTimeout`, `setInterval`): faking every timer made `findBy*` wait forever.
- The recorder is not wired to a "choose the microphone" setting (excluded from the milestone).
- Departures from the prompt: the component's file is `RecorderPanel.tsx` (D-193); the reason of an unavailable first
  transcription travels in the router state (D-196); the original sentence is displayed in the revealed sheet (D-200); the one
  "Done, I repeated it" button covers "Continue" and "Skip" (D-199).

## D-202 — `speaking-1` in the correction model and the view (M6.b2.1; builds on D-140, D-141, D-155, D-181)

- `readFeedback` gets a third branch next to `correction-1` and `transcript-1`: `speaking-1` gives `kind: 'speaking'`, the same
  fields, and `structure` (`output.structure`, null for a missing key or in answer mode). The other two formats read exactly as
  before (their tests are untouched). The model's `kind` is now `'text' | 'transcript' | 'speaking'`.
- The units are numbered as they are (a unit may hold several sentences, D-179) and shown under "Part n" ("Passage n" in French).
- `CorrectionView`: for a speech the text section is "What the speech recognition heard", followed by the note that the correction is
  about what was heard (a mistake the recogniser smoothed over is not reported, a misheard word may be). A speech without error says
  "No errors found." (never "Your sentence is correct"). The **Structure** section (comment, "Connectors you used" with a sentence
  when there are none, suggestions) comes after the versions; the French of the comment and of each suggestion is on demand, with the
  button of the explanations. It is absent when `structure` is null (answer mode) and in the compact view.

## D-203 — The free speaking pages (M6.b2.1; builds on D-142, D-193, D-196)

- `/speaking`: the subjects come from `GET /api/speaking/topics` (`count=3`, a "Topic theme" filter with "Presenting"), the prompt sent is
  the English text of the subject or what the user typed (500 characters). A subject is **optional**: the recorder is never locked by its
  absence (the server takes no `prompt_text`). The recorder is the 5 to 180 s one (warning at 120 s). Sending goes to `/speaking/{id}` with
  the history replaced and the state `{autoCorrect: true}` (plus the reason of an unavailable first transcription, read once as in D-196).
- `/speaking/:id` is keyed by the production, so moving from one to another starts afresh. The state is read into the page's state at
  the first render and **cleared at once**, with a `ref` guard for StrictMode (tested in StrictMode): a reload never starts anything.
  Order: a transcribed, not corrected speech with `autoCorrect` runs `POST /correct` once ("Correcting… n s", a polite status once);
  `pending` shows "Transcribe", and a click on it (the user's own action) goes on to the correction when the transcription is `ok`; a speech
  opened without the flag only shows what is stored and offers "Correct my speech".
- Refusals: `silence` or `422 nothing_to_correct` say "No speech was heard" with a link to record again; `409 not_transcribed` reads the
  production again (`applyCorrectionError` now handles it with `already_corrected`) and "Transcribe" appears; `409 already_corrected`
  reads the stored correction, silently; `422 text_too_long` has its own sentence and no retry; an AI failure (HTTP 200) says its reason
  (`aiReasonText`) or "could not be used" and offers "Try again"; another error is shown with "Try again". The transcription stays visible.
- Not-corrected speeches show the heard text, the note and the status in a polite region; a corrected one shows `CorrectionView`
  (marks, errors, versions, structure). The topic label is "Topic or question" (a spoken answer of a review has the question as prompt).
- `/speaking/history` (`GET /api/productions?kind=speaking`, 20 per page, the page in the URL): date, topic, words heard, status; it says
  that spoken answers of reviews are in the list.

## D-204 — Redirects between the written and the spoken pages; the Speaking link (M6.b2.1)

- `ErrorOut` has no production kind: a `review` error leads to `/writing/{id}` as before, and **both pages decide by the production's
  `kind`**: `/writing/:id` of a `speaking` production and `/speaking/:id` of a `writing` one use `<Navigate replace>` once the production is
  read (the same query, so no second request). Another kind on `/speaking/:id` gets a message and a link to the error log (`/writing/:id`
  keeps its old behaviour for the other kinds, to keep its tests as they were).
- `productionLink`: the source `speaking` leads to `/speaking/{id}` (it was `null`); its test changed accordingly.
- The top bar's "Speaking" points to `/speaking` (it was `/speaking/shadowing`); the section stays marked on `/speaking/shadowing`.

## D-205 — Small conventions met in M6.b2.1

- `TopicPicker` takes a `source` (`topicSource.ts`: the strings' namespace, the themes, the label of a theme, the hook that fetches the
  subjects); the writing page's source is the default, `features/speaking/topics.ts` has the speaking one. The strings of both
  namespaces have the same keys (`writing.topics.*`, `speaking.topics.*`).
- `speechFixtures.ts` gets `speakingFeedback`, `speech` / `correctedSpeech`, `speakingCorrection`, `speakingOut` (fictional data).
- Departure from the prompt: decisions start at D-202 (D-201 was taken); the milestone is cut in two sessions (b2.1, b2.2), approved.

## D-206 — The recorder in two parts and the spoken phases of the review machine (M6.b2.2; builds on D-120, D-143, D-193)

- `RecorderPanel.tsx` exports `RecorderView` (presentation: it takes the object `useRecorder` returns, `RecorderApi`) and `Recorder` (the view and
  the hook, for the pages that only need a recorder). The review player calls `useRecorder('spoken_answer')` itself because Space and Enter must drive
  the recorder (bounds 1 to 90 s). `useClipSender` (own file: oxlint's fast-refresh rule) holds the 10 MB check, shared by the Send button and Enter.
- `reviewMachine` gets `capturing` (microphone open), `captured` (clip ready) and `checking_spoken` (`review-answer` running). `recording` keeps
  its meaning (the rating is being saved, D-120). Actions: `startCapture`, `captured` (fixes `responseTimeMs`: the answer ends with the recording,
  D-121), `discardCapture` ("Record again", a cancelled or failed microphone), `submitSpoken`, `spokenChecked`, `spokenFailed`, `spokenFallback`.
  Every action outside its phase returns the **same state object**; `spokenChecked` outside `checking_spoken` is how a late answer, after the way
  out, changes nothing (tested on the reducer).
- The machine follows the hook: an effect turns `stopped` into `captured` and `idle` / `error` (Cancel, Record again, a refused microphone, a route
  change) into `discardCapture`. The Start button goes through `startCapture` too, so the reducer is the one guard for "one microphone per take".
- The result is still a `GradeResult` (`outcome` null, `proposed_rating` kept only when the correction is `ok`, `term_not_heard` in `warnings`,
  `solution`, `sheet_summary`), so `ReviewResult` and `RatingButtons` are reused; the heard text and its status live in `state.spoken`.

## D-207 — Keys of the spoken answer (M6.b2.2; builds on D-122)

- Space starts the take (phase `answering`) and stops it (`capturing`); Enter sends it (`captured`). Space does nothing in `captured`, Enter
  nothing in `capturing`, no key at all in `checking_spoken`. The same exclusions as D-122 (fields, Ctrl/Alt/Meta, Shift, auto-repeat, a focused
  button or link). `useReviewShortcuts` gets `record` and `send` (Space and Enter are matched to their own handler, `reveal` stays for the other
  types). On a spoken card Space and Enter **no longer reveal** the example: it is revealed by "Answer without recording".
- A double Space opens the microphone once (`startCapture` is refused the second time and the recorder's own guard backs it up); a double Enter
  sends one recording (`submitSpoken` is refused the second time: the guard is the player's `ref`, as in D-120). `KeyHints` follows the phase and
  promises no key when the browser cannot record.

## D-208 — The way out, the fallback and the refusals of a spoken answer (M6.b2.2; builds on D-142, D-143, D-183)

- `reviewAnswer()` (`api/speech.ts`) is a plain function over `apiUpload`, under an `AbortController`, like `checkProduction`. The query holds
  `card_id`, `session_id`, `exercise_template_id`, `duration_s`, `response_time_ms` (the end of the recording, the same value as `POST /reviews`).
- While waiting: "Checking your answer… n s" (the status is said once, the counter is hidden from screen readers) and the sentence about two AI
  steps; after 5 s "Skip the check and rate myself" aborts and takes the fallback.
- **The fallback is the `reveal` path of M4.c, without `production_attempt_id`**: the way out, a network error or any unexpected error
  (notice `spoken_skipped` / `spoken_failed`), a refused, absent or unsupported microphone, "Answer without recording" (always visible, the main
  button when the microphone failed; no notice: the user chose it). A spoken card without a template shows no recorder, only that button.
- Refusals of the recording (`audio_too_short`, `audio_too_long`, `audio_empty`, `unsupported_audio`, `audio_too_large`) go back to `captured`
  with the message: nothing was stored (D-183), the same take can be sent again. `not_due`, `review_not_allowed`, `exercise_mismatch`,
  `session_closed`, `session_not_found` are handled as for `grade` (`checkFailed` now also leaves `checking_spoken`; the recorder is reset).
- Transcription unavailable or silent, or a failed correction, are **not** a fallback: the solution came with the answer (D-186), so the card is
  rated without another request and `POST /reviews` keeps `production_attempt_id` (the server accepts a spoken answer without correction).
  `auto_rating` is never sent. `409 production_mismatch` is the existing single resend (D-143).

## D-209 — What is shown before and after a spoken answer (M6.b2.2; builds on D-103, D-123, D-202)

- The prompt of a spoken card is the question alone: the example answer is **never in the page before the answer**, in none of the phases (a test
  checks `document.body.innerHTML` in `answering`, `capturing`, `captured` and `checking_spoken`, and fails when the example is rendered earlier).
  "Show an example" and the "nothing is recorded yet" sentence (D-123) are gone.
- The result: the compact `CorrectionView` of what was heard (its title already says "What the speech recognition heard" and that the correction is
  about what was heard, D-202), `term_not_heard` translated (forgotten or missed by the recogniser: rate yourself), the example "one possibility
  among others", the sheet summary, the proposed rating 1 or 3 marked "Suggested" (Enter accepts it) or four plain buttons. Silence, an
  unavailable transcription and a failed correction have their own sentence; the sentence "Compare with your own answer" is shown only when no
  rating is proposed.
- One sentence says that two AI steps may take up to about 90 seconds, under Send and during the wait, on every spoken card.

## D-210 — Small conventions and departures met in M6.b2.2

- Fixtures: `reviewAnswerOut` (a correction with one error, Again proposed), `untranscribedAnswer`, `heardFeedback`, `HEARD_ANSWER`, `SPOKEN_EXAMPLE`
  in `speechFixtures.ts`.
- Departures from the prompt: no second "What was heard" heading (the correction view's own title serves); `spokenFallback` takes a nullable notice
  instead of a `declined` kind; "Start recording" and "Answer without recording" are both primary when the microphone failed; the break check
  (e) is caught by the reducer test and not by the player test (the abort already drops the late answer there).

## D-211 — Azure Speech: the facts read, their sources and what is not verified (M6.c1, 2026-10-24)

Read on Microsoft Learn on 2026-10-24 (the "updated" dates are those printed on the pages). Nothing below was observed live: the live test
(`tests/live/test_live_azure.py`) is the proof.

| Point | Finding | Source |
|---|---|---|
| Endpoint | `https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1`, the regional host of Microsoft's REST sample. The current page shows the resource-name host (`{resource}.cognitiveservices.azure.com/stt/...`) and says the key header "works with all endpoint formats". The regional host is kept, as the milestone asked. | `rest-speech-to-text-short` (ms.date 2025-11-21, updated 2026-06-05); `Azure-Samples/Cognitive-Speech-TTS`, `PronunciationAssessment/Python/sample.py` |
| Query | `language=en-US` (required, else a 4xx), `format=detailed` | same |
| Key | `Ocp-Apim-Subscription-Key` header (no token exchange) | same |
| Assessment header | `Pronunciation-Assessment` = base64 of a UTF-8 JSON: `ReferenceText` (required), `GradingSystem` (FivePoint, HundredMark), `Granularity` (Phoneme, Word, FullText), `Dimension` (Basic, Comprehensive), `EnableMiscue`, `EnableProsodyAssessment`, `ScenarioId`. `PhonemeAlphabet` is not in the REST table but Microsoft's sample sends it; the PA page says phoneme names exist in en-US with IPA (default SAPI). | same + `how-to-pronunciation-assessment` (updated 2026-07-03) |
| What is sent | `{"ReferenceText": target, "GradingSystem": "HundredMark", "Granularity": "Phoneme", "Dimension": "Comprehensive", "EnableMiscue": "True", "PhonemeAlphabet": "IPA"}`; no prosody. | |
| Answer | `RecognitionStatus`: Success, NoMatch, InitialSilenceTimeout, BabbleTimeout, Error. `Offset` / `Duration` in 100 ns. In `NBest[0]` the REST page puts the scores flat (`AccuracyScore`, `FluencyScore`, `CompletenessScore`, `PronScore`, `Words[]{Word, Offset, Duration, AccuracyScore, ErrorType}`); the SDK JSON of the PA page nests them under `PronunciationAssessment` with `Phonemes[]`. **The parser accepts both.** | both pages |
| `ErrorType` | REST page: None, Omission, Insertion, Mispronunciation; the PA page adds UnexpectedBreak, MissingBreak, Monotone (prosody). Unknown values are stored as they come and counted in none of the three counters. | both pages |
| Duration | 60 s per request, **30 s when pronunciation assessment is on** (`pa.MAX_ASSESSMENT_SECONDS`). Shadowing is already 0.5 to 30 s (D-179). | REST page |
| Formats | **WAV PCM 16 kHz mono** and **OGG Opus** only. webm, m4a and mp3 are not accepted. | REST page |
| HTTP errors | 400 (language, unsupported or invalid audio), 401 (key invalid for this region/endpoint), 403 (key missing); 429 is described as throttling while autoscaling. **No body or code is documented for "the monthly F0 hours are used up": not verified.** | REST page + `speech-services-quotas-and-limits` (updated 2026-10-23) |
| F0 limits | 5 audio hours a month of real-time STT, shared between Standard and Custom; **one concurrent request**, not adjustable. `pa.F0_MONTHLY_AUDIO_SECONDS = 18_000`, `F0_LIMIT_CHECKED_ON = "2026-10-24"`. | pricing page + quotas page |
| Regions | Real-time STT is in the 33 listed regions. The PA page links to a "pronunciation assessment" region tab that the regions page no longer has: **PA availability per region not verified**. | `regions` (updated 2026-10-18) |
| Card at sign-up | Not stated on the free-services page: **not verified**. | free-services page |

**Is pronunciation assessment free on F0? Not confirmed.** The pricing page lists "Pronunciation Assessment (prosody)" among the enhanced add-on
features (billed per hour) with no add-on line for F0; an unofficial Q&A answer (2025-11-04) says it is billed as plain STT. An F0 resource cannot
bill, so the risk is an S0 resource created by mistake. The owner decided on 2026-10-24: go on, F0 only, document it as unverified. Consequences:
SPEC section 7 no longer says "includes pronunciation assessment" (it says "not confirmed by the pricing page (2026-10-24)"); README and
`.env.example` say "F0 only, never S0" and "the audio goes to Microsoft"; the live test is the proof.

**webm is refused by Azure, and Chrome and Edge record webm.** Same codec (Opus), different container. M6.c2 must send WAV 16 kHz mono
(`OfflineAudioContext` decode and resample is the simplest path) or an OGG Opus take as it is (a Firefox take, if it is 16 kHz mono). The backend
refuses a webm with `unsupported_for_assessment` before any request.

## D-212 — A gateway capability outside `ai_provider_order` (M6.c1)

- New `Capability.PRONUNCIATION_ASSESSMENT`, a task `pronunciation_assessment` (no prompt: `prompt_version` null in `ai_call_log`, timeout 30 s), and
  `Gateway.assess_pronunciation(audio, *, reference_text, language="en-US", pin_provider=None)`, which goes through `_run` like every other call:
  retries, cooldown, the 90 s budget, one `ai_call_log` row per request.
- **`ai_provider_order` does not apply to it**: `_select` takes every provider that holds the capability (`ORDERLESS_CAPABILITIES`), with health
  respected. This is not `pin_provider`, which ignores cooldowns. `status().enabled` is true for a provider whose capabilities are all orderless.
  The real switch is the `pronunciation_assessment` setting, checked by the service. Azure can never be put in the order (`KNOWN_SPEECH_PROVIDERS`
  is a separate tuple) and a text call never picks it (it has no `TEXT` capability).
- The `Provider` Protocol is unchanged; a second Protocol, `PronunciationProvider`, carries `assess_pronunciation`. Gemini, Groq and Ollama are
  untouched; `FakeProvider` gained a scripted `assessment`. `ProviderResponse.assessment` carries the validated
  `PronunciationAssessmentOutput` (`status` ok|silence, four 0-100 scores, `words[]` with `phonemes[]`, `duration_s`).
- `ReferenceText` is required here. D-172 (the target is never sent to Whisper) is about transcription and does not apply: assessing against the
  target is the point.

## D-213 — The Azure adapter and the Azure column of the D-050 table (M6.c1)

- `app/ai/providers/azure_speech.py`, `urllib` through `app/ai/http.py`, no SDK and no new dependency (D-049). Model name `pa-rest-v1` (ours: the
  REST API has no model). The key goes in the header only; messages are masked (D-043); `repr` shows the region, never the key.
- The region is checked against `^[a-z0-9]{2,40}$` before the URL is built (as D-057), else `bad_request` "VOCAB_AZURE_SPEECH_REGION is not a valid
  region"; the language against a BCP-47-like pattern. `base_url` is injectable for the tests (the default URL is unit-tested from the region).
- Refused **before any request** (`bad_request`): a clip that is not WAV 16 kHz mono PCM or OGG Opus mono (the content decides, the file name must
  agree), a clip over 30 s (read from the headers), an empty reference text. The service refuses earlier with stable codes (D-215).
- Parsing is tolerant: both score shapes, numbers that are strings are read, scores outside 0-100 become null, unreadable words and phonemes are
  skipped. `Success` without `NBest[0]` is `invalid_output`. NoMatch, InitialSilenceTimeout and BabbleTimeout give a `silence` result (not an
  error). `Error` is `transient`.

| Situation | Category |
|---|---|
| 401, or 403 without "quota" in the message | `auth` |
| 403 or 429 whose message says "quota" | `quota_exhausted` (**an unverified heuristic**: the F0 wording is not documented) |
| other 429 | `rate_limited` (`Retry-After` when present) |
| 5xx, 408, timeout | `transient` |
| other 4xx, 3xx | `bad_request` |
| unusable body | `invalid_output` |

The worst case of a wrong guess is a one-hour cooldown, or an `auth` mark cleared by `reload()` (D-040).

## D-214 — `.env`, routes and the setting (M6.c1)

- `Settings.azure_speech_key` (secret) and `azure_speech_region`; both are "empty means not configured". The key is in `secret_values()`.
- `env_file.EDITABLE` plus `REGION_VARIABLES` make **five** editable variables. `update_credential(provider, value, region=...)` writes the key and
  the region in **one** atomic write under the same lock; removing the key removes both; `set_in_environment` (409) applies if either variable is in
  the process environment. The region is lower-cased and validated (`invalid_region`, 422).
- `PUT /api/ai/providers/azure/credential` takes `{value, region?}`; 422 `region_required` when no region is stored and none is given, 422
  `invalid_request` for a region sent to another provider. `DELETE` clears both. The event `ai.credential_changed` accepts `azure`.
- **`GET /api/ai/status` lists Azure in a new field `speech_providers`, not in `providers`** (a departure from the plan, found while reading the
  Settings screen: it draws a card and an order entry for every item of `providers`, and the frontend does not change in M6.c1). `ProviderState`
  gained `region` (null for the others, never the key). `degraded` ignores Azure (it means "no text provider").
- Setting `pronunciation_assessment` (`off` | `azure`, default `off`). The demo guard refuses its `PATCH` and the Azure credential routes (409
  `demo_read_only`), as for `ai_provider_order`.
- `POST /api/ai/test {provider: "azure"}` and `ai test --provider azure` send one second of silent WAV (built in memory) with the reference
  "Hello."; a 200 answer, even `silence`, is a success. A plain `ai test` never calls Azure (it would spend free minutes).
- `GET /api/ai/usage` already groups `ai_call_log` by provider: Azure appears with no change (a test checks it).

## D-215 — Storage: the scores live with the comparison, whichever comes first (M6.c1b)

- `pronunciation_result.scores` holds the `azure-pa-1` document (`format`, `provider`, `model`, `assessed_at`, `status`, `overall{accuracy,
  fluency, completeness, pronunciation}`, `words[]`, `duration_s`). No migration.
- `pronunciation.store_assessment(session, attempt_id, result, *, at)` works in the caller's transaction, no commit (D-165, D-189). It fills `scores`
  on the latest row; **when there is none** (no Groq key, transcription not done yet, or a transcription that heard silence) **it creates the row**
  with `transcript=""`, `unrecognized_words=[]` and `provider=""` (the column means the transcription's provider and nothing was transcribed). The
  model allows it: both columns are NOT NULL but accept the empty string, and `production_attempt_id` is not unique.
- `speech.store_transcription` now **updates** the existing row (transcript, unrecognised words, provider; it keeps `scores`) instead of always
  inserting; every other path is unchanged. `speech.comparison_of` returns None while `transcript == ""`, otherwise a row created by the assessment
  would show every target word as missing.
- `pronunciation.assess` refuses, before any call and in this order: 404 `production_not_found`, 422 `not_assessable` (not a shadowing, or no target),
  404 `no_audio`, 409 `assessment_disabled`, 409 `already_assessed`, 422 `unsupported_for_assessment` (the WAV/OGG header of the bytes read), 422
  `audio_too_long` (over 30 s). Then: a short read (the session is closed), the call with no session open, a short write that checks 1, 2 and 5 again
  (D-038). An AI failure is a 200 `unavailable` / `incomplete` (D-081) that writes only the gateway's `ai_call_log` row and can be repeated. No
  `error_event` is ever created (D-174, tested).
- **Known limit, no migration**: two concurrent writers of the same production have a microsecond window between the last check and the insert (as
  for transcription today). A unique index would need migration `0003`; it is not proposed. The test "second writer during the call" covers a writer
  that commits during the AI call.
- `assessable_reason` (on `ProductionOut` and `SpeechOut`, with `assessable` and `pronunciation`): `not_shadowing`, `no_target`, `no_audio`,
  `disabled`, `not_configured`, `already_assessed`, `unsupported_format` (by the extension only, so a list reads no file), `too_long`.

## D-216 — The event and the monthly use (M6.c1b)

- `pronunciation.assessed` (payload v1): `production_attempt_id`, `provider`, `model`, `ai_call_id`, `status` ok|silence, `audio_seconds`, the four
  scores (null on silence), `word_count`, `mispronounced`, `omitted`, `inserted`. No text.
- `GET /api/speech/pronunciation/usage` sums this calendar month's (UTC) events: `{month, audio_seconds, assessments, limit_seconds: 18000,
  limit_checked_on, note}`. Silence counts (Azure bills the audio); failed requests do not (no event). It is what **this app** sent, not what
  Microsoft counts (another tool on the same resource would not show). Read-only session (`query_only`, then restored).

## D-217 — Demo dataset v5 (M6.c1b)

- The five `content/demo/*.yaml` files move to version 5. The last 3 shadowings that have unrecognised words are scored at the end of the run,
  through `store_assessment` (the real service), with `fictional_ai.pronunciation_result`: provider `demo`, model `demo-pa-v1`, no `ai_call_log`
  row, `ai_call_id` null.
- **No new random draw**: the scores come from the words (a CRC of the word), so every other generator draws the same sequence as in v4. A word the
  recogniser missed is `Mispronunciation` (something else heard) or `Omission` (nothing heard); the others score 84 to 98. Phonemes are a fixed
  fictional split of the letters (one IPA symbol per letter), one clearly weak phoneme in a mispronounced word. Validated by the real schema.
- The `pronunciation_assessment` setting stays `off`; the scores are shown anyway (the demo database is read-only for it). The demo clips are
  8 kHz WAV, which Azure would refuse: nothing can send them, the setting is locked.
- The fingerprint changes (version 5, `scores`, `pronunciation.assessed` events), as in D-191. Seed time on 2026-10-24: 14 to 16 s here, against 4.4 to
  4.6 s at M6.a2b with the same command; 0 or 3 assessments make no measurable difference, and the profile is dominated by SQLite writes of the
  reviews (code not touched by this milestone). The cause on this machine is not established.

## D-218 — Small conventions and departures met in M6.c1

- `as_number` moved from `groq.py` to `providers/common.py` (shared by the two parsers).
- `pa.audio_kind` requires the file name to agree with the content (a `.webm` name over WAV bytes is refused).
- Tests: Azure fixtures in `tests/ai/fixtures/azure/` are built from the documentation (the README of the folder says the error bodies are guesses);
  `tests/audio_support.py` makes tiny WAV/OGG clips in memory (no audio file is committed).
- `tests/live/test_live_azure.py` (`VOCAB_RUN_LIVE=1`, a key and a region, `VOCAB_LIVE_AZURE_AUDIO`): one request, a quota error is a skip.
- The frontend does not change; the `speech_providers` field is additive.

## D-219 — Recording for the assessment: WAV at the moment of recording (M6.c2, 2026-10-24; builds on D-211, D-215)

- The backend assesses the **stored file** (`POST /api/productions/{id}/pronunciation` has no body), and Azure refuses webm (D-211). So the
  conversion happens **before the upload of a new shadowing**, in `ShadowingPage`, not at assessment time.
- `frontend/src/speech/wav.ts`: `convertToWav(blob)` decodes with `AudioContext.decodeAudioData`, resamples and mixes down to 1 channel at
  16 kHz with an `OfflineAudioContext`, and encodes WAV PCM 16-bit with the pure `encodeWav`. It returns `null` when the browser cannot (no Web
  Audio, undecodable data); the page then sends the original and the detail page explains `unsupported_format`.
- It runs **only** when the `pronunciation_assessment` setting is `azure` **and** Azure is configured (`useAssessmentReady`). Otherwise the
  recorder, the stored format and the upload are exactly what they were (D-193 is untouched). A 30 s take is about 960 KB, under the 10 MB limit.
- **A Firefox ogg/opus take is converted too**, not sent as it is: one path, testable, no dependence on the sample rate Firefox records at.
- Checked in the built-in browser (Chromium): a real `MediaRecorder` webm/opus take of a 440 Hz tone gave `RIFF`, 16000 Hz, 1 channel, 16 bits,
  1.08 s decoded (the take lasted about 1.5 s), non-silent samples.
  Not checked: a real microphone, Firefox, and the file being accepted by Azure.
- Recordings made before the setting was on stay webm and cannot be assessed; the button is greyed with the reason. The discovery step 4 and
  free speaking are not converted (out of scope).

## D-220 — The Azure card and the way the setting is turned on (M6.c2)

- `AzureCard` is its own card in Settings (between the providers and the usage), drawn from `speech_providers` (D-214), so Azure is never in
  the provider order. It shows: the warning that the recording goes to Microsoft, F0 only (never S0) and that F0 inclusion is not confirmed;
  key + region saved together (`PUT .../azure/credential` with `{value, region}`, the key field emptied after saving); the standard connection
  test (`POST /api/ai/test {provider: "azure"}`); a checkbox for the `pronunciation_assessment` setting (`off`/`azure`), disabled until a key is
  saved; the month's use from `GET /api/speech/pronunciation/usage` with its note ("what this app sent, not what Microsoft counts").
- Locked on the demo database (as the other cards). Absent when the backend sends no `speech_providers`.
- The new error codes (`region_required`, `invalid_region`, `not_assessable`, `assessment_disabled`, `already_assessed`,
  `unsupported_for_assessment`) are in `errorMessage.ts` and in both locales.

## D-221 — The scores view and the button (M6.c2; builds on D-215, D-174)

- `AssessmentSection` on the shadowing page, after the transcription card. **Nothing is sent by itself**: one button, with the sentence "sends the
  recording to Microsoft Azure". The button is greyed from `assessable` and the reason from `assessable_reason` is written under it (with a link
  to the settings for `disabled` / `not_configured`). `not_shadowing` and `no_audio` show no section. A backend without the fields shows nothing.
- `unavailable` / `incomplete` are said with the reason (`aiReasonText`), nothing is stored, the button becomes "Try again". A 409
  `already_assessed` just refreshes the production.
- `PronunciationView`: the sentence "An automatic estimate, not a teacher's judgment" first; four overall scores; every word with its score and
  its error type **in words** (colour is never the only signal; a wavy underline marks words with an error type or a score under 60); the
  weakest sounds (computed in the browser from the stored phonemes: below 80, worst five); date and provider; "Demo scores are fictional" for
  `provider: "demo"`. An unknown `error_type` reads "to check". `silence` says that nothing was heard.
- Active recall holds: the section exists only on a recorded take that was already compared, and the target sentence was shown before.
- No errors are created from the scores (D-174).

## D-222 — Small conventions and departures met in M6.c2

- Backend unchanged, no migration, no new dependency. `ProviderName` stays the text providers; `SpeechProviderName` (`'azure'`) is separate.
- Departure from the plan: `useAssessmentReady` reads two requests (settings and AI status); a take sent in the first instants of a page load
  could be sent without conversion; then it just cannot be assessed (the button says why).
- Tests: 25 new Vitest tests, 644 in all (wav 6, Azure card 6, scores and button 10, recording 3); the "assessment off" test
  fails when the conversion is made unconditional (checked by breaking the code).


## D-223 — M7.a1 starts from M6.c2; no migration; the schema holds the task (module G)

- `main` (`7904aa3`) has no M6, so `feat/m7-consolidation` is cut from `7ffbec6` (tip of `feat/m6c2-pronunciation-screens`). Nothing after
  migration `0002`; `alembic check` stays empty.
- The existing tables are enough. Task types map to the enum at the service/API boundary: `talk` <-> `presentation`, `speech`,
  `interview_answer`; statuses `completed` <-> `done` (`completed_at` is set). `consolidation_task.topic` holds the English title (readable in
  SQL); everything else is in `suggested_structure` (`format: "consolidation-task-1"`: task type, source `ai`|`template`, reason, provider, model,
  prompt version, AI call id, title / prompt / audience in both languages, target minutes, sections with their `item_ids`, study session id).
- The order of the terms is the insertion order of the `consolidation_task_item` rows (id ascending = selection order, most fragile first).
- Pure rules in `app/domain/consolidation.py`: `MIN_TERMS = 8`, `MAX_TERMS = 15` (the target limit of the two correction tasks, D-128, D-180),
  `DEFAULT_TERMS = 12`.

## D-224 — The ratio setting is `consolidation_share`, bounds narrowed to 0.5..1.0

- The registry already had `consolidation_share` (default 0.80), shown in the "consolidation" group of the settings page and unused until now.
  It is reused instead of adding `consolidation_ready_ratio`. Bounds go from 0..1 to 0.5..1.0 (the milestone's bounds). The frontend reads the
  bounds from the API, so no frontend change; the domain also clamps a stored out-of-range value when reading (`clamp_ratio`).
- Readiness: denominator = productive cards of the deck terms that are neither `archived` nor `known`; numerator = those with a stability of at
  least `consolidation_min_stability_days`. The comparison is `stable / total >= threshold` on exact fractions (79.9 % is below 80 %).
  Candidates are the terms at `consolidated` status (not `active`), lowest stability first, then lowest id.

## D-225 — One more reason, `deck_done`, and the order of the reasons

- The milestone excludes `done` decks without naming a reason; the reason is `deck_done`. Order of evaluation: `excluded_kind` (an `error_drill`
  deck), `deck_done`, `task_open`, `no_productive_cards`, `below_ratio`, `not_enough_candidates`. A `paused` deck stays eligible: the pause
  only stops new terms (D-026). `ratio` is 0 when there is no productive card.
- 409 `task_closed` is reserved for M7.a2 (an attempt on a `completed` or `dismissed` task).

## D-226 — The `consolidation_task` AI task and the template fallback

- Prompt `consolidation_task.v1.txt` (`deck` and `terms` are `data`, `task_type` and `term_count` `plain`); the output schema validates by
  context (D-079): known references, every reference exactly once, 3 to 6 sections, `target_minutes` 1 to 6, non-empty texts, bounded lengths
  (named constants), the requested `task_type`. Messages never quote the AI text. The model gets the terms as `t1..tN` references with the
  English simple definition only (no French translation: immersion); the prompt forbids sample sentences containing a term.
- Budgets (`app/ai/tasks.py`): input 8 000 characters (deck about 1 200 + 15 terms x about 300 + keys), output 3 000 tokens (titles, prompts
  and audience in two languages about 500, 6 sections x about 250, JSON frame), timeout 45 s.
- Fallback: `content/consolidation_templates.yaml` (one template per type, 4 or 5 sections, `{deck}` / `{domain}` interpolation, terms spread in turn in
  selection order). Used for any `unavailable` reason and for `incomplete`; the task is created anyway with `source: "template"` and the
  `reason` is the AI reason (`no_provider_configured`, `quota`, `auth`, ..., or `incomplete`). The template result goes through the same schema.

## D-227 — Creation never holds a transaction during the AI call (D-038)

- `create_task`: a short read session (readiness, selection, sheets) is rolled back; the AI is called with no session; then one short write
  transaction re-checks readiness (409 `task_open` with `task_id` if another task appeared, 409 `not_ready` with `reason` otherwise, and
  `not_ready` / `candidates_changed` if a selected term left the candidates) and calls `store_task`. `store_task` works in the caller's
  transaction so the demo can use it. Tested with a second writer taking `BEGIN IMMEDIATE` during the call.
- Statuses: `proposed -> accepted | dismissed`, `accepted -> completed | dismissed`; anything else is 409 `invalid_transition`. A closed task frees the deck.
- Events (open set, no migration): `consolidation.task_created` `{task_id, deck_id, task_type, source, term_count}` and
  `consolidation.task_status_changed` `{task_id, from_status, to_status}` (field names as `deck.status_changed`); no free text.
  `consolidation.attempt_checked` and `production.recorded` v6 come with M7.a2.
- The planner (D-029, block 4) already reads proposed or accepted tasks: unchanged, tested through `/api/session/today` and `practice_info`.

## D-228 — API, export and CLI of M7.a1

- Routes under `/api/consolidation` (decks, tasks create / list / get, status, export), format D-063. `POST /tasks` is a plain `def` with no session
  dependency; `term_count` is validated 8..15 (422 `invalid_request`). The task carries both languages everywhere; `targets` come without the sheet;
  `used_correctly_count` counts `production_target.used_correctly` of the task attempts (0 until M7.a2).
- Export: `content/consolidation_export.yaml` (tutor role, task, structure, terms with simple definitions, what the tutor does: listen, three
  follow-up questions, say which terms were used well / badly / forgotten); the tutor always speaks English, `lang=fr` translates the framing.
  `text/markdown; charset=utf-8`, `Content-Disposition: attachment; filename="consolidation-task-<id>-<lang>.md"`. No personal data.
- CLI `consolidation status | new <deck_id> [--type] [--count 8..15] | show <id> | export <id> [--lang] [--out FILE]`; exit 0 done, 2 usage or refusal.
  Like `write correct`, `new` accepts `--demo` (an AI failure is not an exit code: a template takes over).

## D-229 — Applying the result of a consolidation production (M7.a2; builds on D-025, D-127)

- Per target term, from `production_target.used` (deterministic, `contains_term`), `used_correctly` (the AI) and the errors of the production tied to the term
  by `target_ref` (`classify_target`, pure): **correct** = used, judged correct, no tied error; **misused** = used and judged wrong, or with a tied error;
  **absent** = not in the text (not heard, for a talk); **unknown** = no verdict.
- Correct: `learning` or `consolidated` becomes `active` (`mark_active`); `active` stays; `archived` and `known` are ignored. Misused: a FSRS Again on the productive
  card through `record_review` (`exercise_type = "consolidation_misuse"`, `auto_rating = final_rating = 1`, **no** `production_attempt_id`: the unique index of D-127 allows
  one review per production, the link is the event); `archived` and `known` are ignored, an `active` term stays `active`, a `consolidated` one may fall back to `learning`
  by the usual rule. Absent and unknown: nothing. The error itself already exists (created by the correction, source `consolidation`).
- It runs **in the transaction that stores the correction** (`after_store` of `correct_production` / `correct_speaking`, called after `store_*correction` and before the commit),
  so a correction that fails or is not stored changes no status and a retry applies the result once. `/correct` already refuses a second correction (409 `already_corrected`, in
  `prepare` and again in the write transaction); `apply_result` also looks for an existing `consolidation.attempt_checked` for the production and does nothing if there is one.
  Both layers were removed in turn to check that the tests notice (see the report).
- A term used correctly but with an unrelated error tied to it counts as misused: the prompt of the correction tasks tells the AI to set `target_ref` when a mistake concerns a target term,
  and the milestone's rule is "no error tied to the term". The live pass where the AI tied a tense error to "run a regression" showed the cost; the example text avoids that ambiguity.
- Event `consolidation.attempt_checked` `{task_id, production_attempt_id, modality, targets, used, used_correctly, misused, absent, activated_item_ids, reinforced_card_ids}`: counts and ids only.

## D-230 — Productions of a task: kind, origin, bounds (M7.a2; builds on D-170, D-182)

- A written text is a `production_attempt` `kind=consolidation`, `modality=written`, `prompt_text` = the English prompt of the task, targets = the terms of the task in selection order
  (so the AI `ref` of a term is its position), `consolidation_task_id` set; same limits as free writing (4 000 characters, 40 sentences). A talk is the same kind with `modality=oral`
  (`RecordingKind.CONSOLIDATION`, 20 to 240 s: a 2 to 4 minute talk for 8 to 15 terms, 240 s are about 3 800 characters, under `MAX_SPEAKING_CHARS`); `speech.py` counts the words of a
  `consolidation` production like those of free speaking (the learner's own words). Checks before the file is written and again in the creating transaction; the task prompt is never sent to the recogniser (D-172).
- `production.recorded` is version 6 (origin `consolidation`); `ProductionOrigin.CONSOLIDATION` decides the error source (`source_of`, `mode_and_source`): `consolidation`, so a retry through `/correct` keeps it.
- The first attempt makes a `proposed` task `accepted` in the creating transaction (`note_attempt`); an attempt on a `completed` or `dismissed` task is 409 `task_closed` (`task_status` in the details).
- `corrections.prepare` and `speaking.prepare_speaking` take the accepted kinds as a keyword (defaults unchanged); `prepare_speaking` also requires the oral modality. A written consolidation text is corrected
  in `paragraph` mode even with one sentence.

## D-231 — API additions of M7.a2

- `POST /consolidation/tasks/{id}/attempts/written`, `POST /speech/consolidation` (under `/api/speech/` for the guard of D-170), `CorrectionOut.consolidation` (additive, null otherwise),
  `task.targets[].used_correctly_count` (the `production_target.used_correctly` rows of the task attempts). Nothing completes a task by itself: the owner does (`POST .../status`).
  The feedback formats `correction-1` and `speaking-1` are unchanged, so M7.b reuses the correction views.

## D-232 — Demo v6 (M7.a2; builds on D-163, D-191)

- `dataset_version` 6 in the five files (only the number changes). The simulation makes the task **through the services**: from day -10 (scaled) until the deck is ready, never after day -5, it takes the
  15 most fragile terms with `select_terms`, stores a task from the deck template (`fictional_ai.consolidation_task`, validated by the real schema, provenance `demo`), records a text built from the
  dataset sentences (a fallback sentence for the terms the dataset gives none for), one term used wrongly (`it make` -> `it makes`, `grammar.agreement`, tied to the term) and one forgotten, corrects it
  (`store_correction`, source `consolidation`), applies the result with `apply_result`, and completes the task.
- Terms with `fate: active` are spared from the "misused" and "forgotten" draw, so the task activates them when it selects them; the direct switch at day -5 stays only for the ones it did not reach
  (measured on seeds 1 to 12 in PROGRESS). A new generator `_consolidation` is derived **last** from the root generator (D-191): the numbers of the others do not move.
- The fingerprint changes for these reasons only: the version number, the consolidation rows (task, 15 items, production, correction, error, review, events), the statuses and `item.status_changed` events of the
  terms the task activated (about 13 instead of 5 `active` terms in the causal deck), and the cards of the term reinforced. Existing demo tests changed in two places: the causal deck has 12 to 15 active terms,
  and the replay of the exercise choice skips the `consolidation_misuse` reviews (it checks their ratings instead). New: `tests/test_demo_consolidation.py`.
- The seed takes 5 to 6.5 s here.

## D-233 — Example text and live test (M7.a2; builds on D-054, D-132)

- `content/examples/m7_consolidation.txt`: one paragraph on eight terms of the demo's causal deck (the ten selected at the anchor with seed 42 and `--count 10`): six used well, `noisy estimate` used as a verb
  (wrong), `underpowered` forgotten (two more selected terms are not used either). `tests/live/test_live_consolidation.py` makes a real task (schema-valid, every term in one section) and corrects the example.
- Passes with `gemini-3.5-flash-lite` (Stable on 2026-10-26): the task was written by the AI every time. First text (an agreement slip): the AI called the term correct (rightly: the slip is not about the
  term) - the text was changed, not the test. Second text: failures on "run a regression" (a tense error tied to the term) and once on `noisy estimate` judged correct. Final text (infinitive, a clearly wrong
  use): 6 passes out of 7. The prompts of `production_correction` and `speaking_correction` are shared with M5 and M6, so they were not changed for this (a v2 would be its own change).

## D-234 — CLI `consolidation write | speak` (M7.a2)

- `write <task_id> --file <txt>` and `speak <task_id> --file <clip> [--duration S]` (in `app/cli_consolidation_attempts.py`) print the correction as `write correct` does, then what happened to the terms
  (now active / reinforced / not used / unchanged). Exit codes as D-053: 0, 1 AI unavailable (production kept, no term changed, the message gives `POST /api/productions/<id>/correct`), 2 usage (unknown or closed task,
  refused file, duration outside 20-240 s). `--demo` is accepted.

## D-235 — Routes and structure of the consolidation screens (M7.b; builds on D-229, D-231)

- Three routes under `features/consolidation/`: `/consolidation` (ready decks with the creation form, decks not ready with the reason in words, the tasks with a status filter and paging in the URL),
  `/consolidation/tasks/:id` (brief, structure, terms, status actions, written and spoken production, attempts, export) and `/consolidation/attempts/:id` (correction and summary of the terms).
- A consolidation production opened as `/writing/:id` or `/speaking/:id` redirects to its attempt page (as writing and speaking already redirect to each other), and a consolidation error of the error log
  links to it (`logRules.productionLink`). Any other kind opened on the attempt page redirects to `/writing/:id`.
- The task id is **not** on a production (`ProductionOut` has no `consolidation_task_id`; no backend change was asked for). The attempt page gets it from the query string (`?task=ID`, kept when the page
  clears its router state). Without it the page still works; only "Back to the task" and "Mark as completed" are missing (the link falls back to the task list). Adding the field to `ProductionOut` would remove this.

## D-236 — Task statuses and the user's decision (M7.b; builds on D-229)

- The buttons follow the backend transitions: proposed -> Accept or Dismiss, accepted -> Mark as completed or Dismiss, closed -> none. Dismiss and Complete ask an inline confirmation (`role="alertdialog"`,
  no `window.confirm`); Accept does not (it is harmless, and the first attempt does it anyway).
- Nothing completes a task by itself. After a corrected attempt on an `accepted` task, the attempt page offers "Yes, mark as completed" next to "Make another attempt"; the user decides.
- A closed task shows neither the writing form nor the recorder (the backend would refuse with `task_closed`).

## D-237 — Active recall on a task and what is shown after the attempt (M7.b; builds on the SPEC principles)

- The task page lists the terms to use (that is the exercise, not an answer); no meaning, sheet or example is shown before the attempt. After the correction, the summary groups the terms: used correctly
  (with the "now active" mark and the counts only right after the correction, from `CorrectionOut.consolidation`), used wrongly, not used, not checked. After a reload the groups come from the stored
  `production.targets`; the marks are lost, because the API gives `activated_item_ids` and `reinforced_card_ids` only in the answer of the correction call.
- The text of the task (prompt, audience, structure) is shown in the interface language, with a button to show the other one under it (`lang` attributes set).
- A task made from a template says so on its page, with the reason (`aiReasonText`), passed through the router state from the creation page (the reason is not stored on the task): it is not shown when the
  task is opened from the list.

## D-238 — Recording use `consolidation` (M7.b; builds on D-193, D-179)

- `RecordingUse` gets `consolidation`: min 20 s, max 240 s (the backend's bounds for `POST /speech/consolidation`), a warning from 200 s. The existing `Recorder` is reused as is; the take is sent with
  `apiUpload('/speech/consolidation', blob, {task_id, duration_s})`. Transcription and correction use the same retry buttons as free speaking (`useTranscribe`, `useCorrectProduction`).
- The correction starts by itself on arrival from the task page (router state `autoCorrect`, cleared at once: D-142) and never after a reload.

## D-239 — Export, creation and links (M7.b)

- The Markdown export is downloaded by `apiDownload` (fetch, blob, temporary `<a download>`, file name from `Content-Disposition`): one button per language, no new endpoint.
- The number of terms is limited to 8 up to `min(15, candidates)` in the form; the backend stays the judge (`not_ready` and `task_open` conflicts are shown, the latter with a link to the open task). The
  creation button is disabled while the AI works and shows the elapsed seconds (as the other AI buttons).
- A writing draft is kept in the browser per task (`vocab-coach.consolidation-draft.<id>`, convenience only, cleared on send).
- The Today card and the session's `practice_info` step now link to the open task ("Open the task"); the sentence "available in a later version" is gone. The top bar has a `Consolidation` entry.
- `consolidation_share` was already in the Settings group "Consolidation". Its bounds (0.5 to 1.0, D-224) come from the API, so the form follows them; only a test fixture still said 0 to 1.

## D-240 — NGSL and NAWL are redistributed unchanged, under CC BY-SA 4.0 (M8.a1)

- Checked on 2026-10-26 on the official site (https://www.newgeneralservicelist.com/new-general-service-list and `/new-academic-word-list`): both lists are "licensed under a Creative Commons
  Attribution-ShareAlike 4.0 International License", authors Browne, C., Culligan, B., and Phillips, J.; "permissions beyond the scope of this license may be available at www.charlie-browne.com".
  Redistribution is therefore allowed with attribution and the same licence (SPEC module H asked for this check).
- The files are downloaded again from the official URLs and committed **byte for byte** (`NGSL_12_stats.csv`: ASCII; `NAWL_12_lemmatized_for_teaching.csv`: ISO-8859-1, CRLF) in `content/wordlists/`.
  `.gitattributes` marks them `-text` so that `* text=auto` never rewrites their line endings. `content/wordlists/NOTICE` holds the licence, the authors, the source URLs, the download date and the
  citation; the README (licence section) and SPEC section 8 mention them. Every adjustment is made by the loader: `TRUE` / `FALSE` (spreadsheet artefacts for `true` / `false`) are lowercased, the
  NAWL is decoded as ISO-8859-1, `I` is kept as written. The CI hygiene guard rejects `data/`, `.env`, databases and audio only, so the `.csv` files pass.
- Anything derived from the lists and redistributed carries the same licence; the rest of the repository stays MIT.

## D-241 — A track is linked to its deck through `source`, no migration (M8.a1)

- `curriculum_track` has no `deck_id` and none is added. Starting a word-list track creates a `source` (title "New General Service List 1.2" / "New Academic Word List 1.2", author
  "Browne, Culligan, Phillips", domain `general` / `academic`, `reference = "curriculum:<track_code>"`) and a deck `kind = curriculum`, `queued`, at the end of the queue.
  The deck is found again by `kind = curriculum` + `source.reference`, so a second start returns the same deck (idempotent). If the deck was deleted, a new start makes a new deck and source
  (the previous source stays, harmless).
- `curriculum_track` rows are upserted by `code` when a track is started (title and description in English, `syllabus_version` = the YAML `version`). A scenario track gets its row on start and no deck
  (its units arrive in M8.a2). Known limit: units opened under a deck that was later deleted keep `deck_id = NULL`; reopening them returns them as they are.

## D-242 — Units are computed from the files and created on opening (M8.a1)

- Unit `n` of a word-list track holds ranks `(n-1)*unit_size+1 .. n*unit_size`, computed from the file at each call (NGSL 2809 words: 113 units, the last with 9; NAWL 959 words: 39 units).
  The syllabus only gives `unit_size` (10 to 50). The file is cached by path, modification time and size, so a replaced file is read again.
- Nothing is written for a unit until the user opens it. Opening creates the `curriculum_unit` row (`code` `ngsl_001` / `nawl_001`, title "Words 1–25" with an en dash, `position = n`,
  `deck_id`, `progress = in_progress`, `content_status = generated`: the unit content, a word slice, exists and needs no AI) with
  `content = {format: "wordlist-unit-1", source, source_version: "1.2", first_rank, last_rank, item_ids}`. `item_ids` holds the terms put in the deck (new or attached), in rank order.
  Reopening creates nothing. No usage sheet is generated on opening (the learner chooses which words to learn after triage).

## D-243 — The unit's terms go through the import core, with their own event (M8.a1; builds on D-013, D-015, D-017)

- `importing.commit` takes `origin` (default `ItemOrigin.IMPORT`) and `record_completed` (default true). The curriculum calls it with `origin = ItemOrigin.CURRICULUM`, `intake = triage` and
  `record_completed = False`: an exact duplicate is attached to the deck (a `known` or `archived` status is kept), a possible duplicate creates a new term, the type is guessed as in the import.
- Two events, both `extra="forbid"`: `curriculum.track_started` (`track_code`, `deck_id`, `created`) and `curriculum.unit_opened` (`track_code`, `unit_code`, `unit_id`, `deck_id`, `imported`,
  `attached`, `skipped`). `import.completed` is not written, so M9 statistics count user imports only; the new terms still have their `item.created` events (origin `curriculum`).

## D-244 — NAWL units follow the official alphabetical order (M8.a1; owner's decision)

- The NAWL has no official frequency rank (only the file order, alphabetical, one row per headword followed by its inflected forms). The rank of a NAWL word is its row number; units are
  consecutive slices of 25 headwords. Frequency order was not invented. The inflected forms are read but not imported (the headword is the term).

## D-245 — Unit state is computed, never stored; availability and errors (M8.a1)

- A unit is `not_opened` (no row), `opened` (at least one of its `item_ids` is still in `triage`) or `triaged` (none is). The state is computed at each call; `curriculum_unit.progress` is not used for
  it (it will carry the M8.a2 steps). Terms deleted later count as triaged.
- A track is `available: false, reason: "wordlist_missing"` when its file is absent or unreadable; starting it gives 409 `wordlist_missing`. Opening a unit of a track that is not started gives
  409 `track_not_started` (with `track`); a scenario track has no word units to open (422 `not_a_wordlist_track`); unknown track / unit give 404; an unreadable syllabus gives 503 `syllabus_unavailable`.
- API tests must override `get_session` as well as `get_engine`: with `get_engine` only, routes that commit write into the real database (found and fixed in this milestone, see PROGRESS).

## D-246 — Scenario units: zero migration, the row exists only once its content does; the model check (M8.a2)

- No migration: `curriculum_unit` already has `content` (JSON), `content_status`, `provider`, `model`, `prompt_version`, `deck_id` and the closed `progress` enum; `production_attempt.curriculum_unit_id`
  already exists. `alembic check` reports no operation.
- Generation follows D-038: a short read (the track is started, the unit exists in the syllabus, no content yet), the AI call with no session open, then a short write that checks again (409
  `unit_generated` if another generation wrote in the meantime). The `curriculum_unit` row is created by that write, never before: an AI failure is a result (HTTP 200, `status` `incomplete` or
  `unavailable`, `reason`, `detail`) that writes nothing, and the same command can be run again. A unit with a row and `content_status = pending` is treated as not generated.
- A generated scenario unit is `opened` while none of its formulas is in the library (D-245 computes `opened` / `triaged` from the terms; a scenario unit with no terms yet is simply `opened`).
  Scenario units are listed from the YAML as before (`not_opened` until generated).
- Prior check, 2026-10-26: https://ai.google.dev/gemini-api/docs/models lists `gemini-3.5-flash-lite` as "Stable" (page "Last updated 2026-10-22 UTC"; the page gives no release or deprecation
  date for it). The live test (`tests/live/test_live_curriculum_unit.py`, 1 to 2 requests) wrote the "Job interview" unit with the owner's Gemini key on the first attempt.

## D-247 — Stored format of a scenario unit, `curriculum-unit-1` (M8.a2)

- `curriculum_unit.content` (replaced as a whole dict on every write, D-020): `format: "curriculum-unit-1"`, `prompt_version` (`curriculum_unit.v1`), `provider`, `model`, `ai_call_id`, `edited`,
  `revision` (1 at generation, +1 per edit), `level` (from the syllabus), `formulas [{text, item_type, function_en, function_fr, register}]`, `dialogue {setting_en, setting_fr, speakers[2], lines
  [{speaker, text}]}`, `shadowing [line index]`, `final_task {prompt_en, prompt_fr, minutes 1|2, formula_refs [formula index]}`, `progress {steps {<step>: {done, at}}}`, `item_ids [...]` and
  `formula_item_ids {"<formula index>": item id}` (the last two are empty until the learner adds formulas to the library, D-251). `provider`, `model` and `prompt_version` are copied to the
  columns. `content_status`: `generated` after the AI, `edited` after the first edit (never back).
- Stored positions are **0-based** (line and formula indices). The AI numbers the dialogue lines from 1 and the formulas `f1`, `f2`...: `CurriculumUnitOutput.stored_*` convert them once.
  `register` is the JSON key of a formula; the Python attribute is `style` because `BaseModel.register` exists.
- The shapes and every rule live in `app/domain/curriculum_unit.py` (pure), shared by the AI schema, the edit and the demo dataset.

## D-248 — Progress by four steps; two are marked, two are derived (M8.a2; the owner's brief was cut off here, approved in the plan)

- Steps, in this order but not enforced: `formulas` (read) and `dialogue` (listened to) are **marked** by the learner (`POST /units/{id}/steps/{step}`; the browser's speech synthesis cannot be
  observed); `shadowing` is complete when every line of `shadowing` has at least one transcribed, non-silent shadowing take linked to the unit whose target sentence equals the line (no accuracy
  threshold: speech recognition is not a pronunciation judge, SPEC module F); `final_task` is complete when a free-speaking production linked to the unit has been corrected by
  `speaking_correction` (no new correction task). The two derived steps are computed from `production_attempt.curriculum_unit_id`, so a take never needs a second write and cannot drift.
- `progress` keeps its closed values: `not_started` (no step), `in_progress` (at least one), `done` (all four). `refresh_progress` stores the derived steps in `content.progress.steps`, writes
  the events and moves the enum; it runs after a mark, an edit, a stored transcription and a stored speaking correction that is linked to a unit (late imports in `speech.store_transcription` and
  `corrections.store_speaking_correction`, as the consolidation does). A step lost by an edit (a new line without take, a new prompt) is recomputed; `done` can go back to `in_progress`.
- Events (counts only, no text): `curriculum.unit_generated`, `curriculum.unit_edited` (`parts`, `revision`), `curriculum.unit_step_completed` (`step`, once per step until lost),
  `curriculum.unit_completed`, `curriculum.unit_terms_added`. Statistics (M9) can count units from them.

## D-249 — The `curriculum_unit` task, its validators and its budgets (M8.a2; builds on D-079, D-128, D-226)

- `curriculum_unit.v1`: inputs `title`, `level`, `goals`, `situations` (all `data`: syllabus text). Output: 8 to 15 formulas, a dialogue of two fictional speakers with 8 to 16 lines, 5 to 8 lines to
  shadow, a final task of 1 or 2 minutes that uses at least 3 formulas. The shape limits are named constants of `app/domain/curriculum_unit.py`.
- One model validator runs `problems()` (D-079: one repair, then `incomplete`): formulas unique after `normalize_term`; at least half of them found in the dialogue (`contains_term`); shadowing
  numbers real and unique; shadowing lines of 4 to 25 words; references known and unique; no empty text; the lines' speakers are the two names, which differ. Every message names a
  location, never the generated text; all problems are reported at once so one repair can fix them. There is no request-dependent context (every rule reads the output only).
- Budgets (`app/ai/tasks.py`): input at most 6 000 characters (title, level 500 each, 4 goals and 6 situations of at most 500: the `Text` limit of the syllabus), 6 500 allowed; output about 2 700
  tokens at most (15 formulas of about 110, 16 lines of about 36, settings, task and frame), ceiling 4 000 because French costs more tokens; timeout 60 s.

## D-250 — Editing a unit: whole parts under a revision (M8.a2)

- `PUT /curriculum/units/{id}/content` with `expected_revision` and any of `formulas`, `dialogue`, `shadowing`, `final_task` (0-based positions) replaces those parts. The same rules as the AI
  run (`problems()` plus the counts of the shapes), so an edited unit is as valid as a generated one. 409 `unit_changed` (with the current `revision`) when the revision is stale; 422
  `invalid_content` (with `problems`, locations only) when a rule breaks; an edit with no part is refused. Nothing is written when it fails.
- Replacing `formulas` without `final_task` keeps the references that survive, found again by normalised text; fewer than 3 left is refused. The library terms already added follow their
  formulas the same way (`formula_item_ids`). Editing never calls the AI.
- No regeneration over an existing unit in M8.a2: a second `generate` is 409 `unit_generated`, an edited unit is never overwritten. A `replace` option can come later if the owner wants it.

## D-251 — Formulas enter the library only when the learner asks (M8.a2)

- Generating a unit does not touch the library. `POST /units/{id}/terms` (`indices`, all by default) puts the chosen formulas in intake triage through `importing.commit` (origin `curriculum`,
  `record_completed = False`, the formula's type, `confirmed` because a formula may look like a sentence), in the track's `curriculum` deck, made on first use like D-241 (source
  `curriculum:speaking_scenarios`, deck "Speaking scenarios", end of the queue). It stores `formula_item_ids`, `item_ids` and `deck_id`, and records `curriculum.unit_terms_added`.
- A formula already added is skipped, so calling it again writes nothing; an exact duplicate already in the library is attached (D-243). The terms of the final task (`target_item_ids`) are
  the added formulas among its references: they become the targets of the final speaking take.

## D-252 — Takes of a unit reuse M6 without a new kind or origin (M8.a2)

- `speech.Recording` gains `curriculum_unit_id`; `speech.record_shadowing`, `speaking.record_speaking` and `speaking.store_speaking` take it, the routes `POST /speech/shadowing` and
  `POST /speech/speaking` take `unit_id`, the CLI `speech shadow|speak --unit <id>`. The unit is checked before the file is written and again in the creating transaction (404
  `unit_not_found`, 422 `not_a_scenario_unit`). A take is an ordinary `shadowing` or `speaking` production (origin `shadowing` / `speaking`, errors with the source `speaking`): reviews, the
  error log and the comparison work unchanged.
- With `unit_id`, free speaking defaults its topic to the English prompt of the final task and its targets to the unit's library terms; a caller's own topic or targets win.

## D-253 — Demo dataset v7: a sixth file and three units (M8.a2)

- `content/demo/units.yaml` (`dataset_version: 7`, all six files bumped together) holds three fictional units written as the AI would return them (validated by `CurriculumUnitOutput` when the
  file is read) and what the learner did: `job_interview_1` done (marked, 6 lines shadowed, a 62-second talk corrected), `presenting_data_1` in progress (marked, 2 of 6 lines shadowed),
  `meetings_1` written only. Days are scaled like the others; the track is started the first time a unit is written; no term, deck or library event is added for them.
- The simulation writes them through `curriculum_units.store_generated`, `mark_step`, `speech.store_recording` and `speaking.store_speaking` + `corrections.store_speaking_correction`. A new
  random generator is drawn **after** the existing ones, so the other sequences keep their numbers. Provenance `("demo", None, "demo-unit-v1")`.
- `test_shadowings_compare_the_sentence_of_a_term` now ignores the takes of units (their target is a dialogue line, not the sentence of a term).

## D-254 — The unit page takes its French title and its next unit from the track (M8.b1; owner-approved plan)

- `UnitOut` has no `title_fr` and no neighbour. The scenario unit page calls `GET /curriculum/tracks/{code}?limit=2&offset=number-1` (a slice that starts at the unit: rows `number` and `number + 1`) and
  reads `title_fr` and the next unit's row (`unit_id`, `title`) from it. No backend change (`git diff --stat a68e04c -- backend` is empty). Until the slice arrives, the page shows `unit.title`.
- The next-unit link goes to `/curriculum/units/{id}` when that unit is written, else to the track page. `unitRules.neighbours` is the pure part.

## D-255 — A unit travels to the shadowing and speaking pages in the router state, read once and cleared; `?unit=` is the way back (M8.b1; builds on D-142, D-196, D-203)

- "Shadow this line" links to `/speaking/shadowing` with the state `{target: line, unitId}`; "Record my talk" to `/speaking` with `{unitId}`. Both pages read it once into their own state and clear it
  at once (`navigate(pathname + search, { replace: true, state: null })`), so a reload finds an empty state: a reloaded `/speaking` is free speaking and a reloaded shadowing has an empty field, and
  nothing is sent (D-196). The shadowed line is the unit's own text, not a transcription; the tests look at `history.state` at every navigation and at the storages.
- With a unit the shadowing sentence is read-only (the server only accepts a line of the unit), and `POST /speech/shadowing` gets `unit_id`; free speaking sends `unit_id` and no `prompt_text`
  (the server takes the unit's prompt, D-252). The next page is `/speaking/shadowing/:id?unit=ID` or `/speaking/:id?unit=ID`.
- `ShadowingDetailPage` and `SpeakingDetailPage` cleared their state with `navigate(location.pathname, ...)`, which would drop `?unit=`: they now keep `pathname + search`. `?unit=` is only a link
  target (a validated positive integer), never read as data.
- A take, a transcription retry and a correction invalidate the curriculum queries (the unit page is read again on return: `take_count`, steps, `corrected`).

## D-256 — The dialogue is played line after line with a run token, two voices chosen by a pure rule, and the text starts collapsed (M8.b1; builds on D-195)

- `useDialoguePlayer` says one line at a time through `useSpeech().speak(text, { voiceName, slow, onDone })` and goes on when `onDone(true)`; each run has a token, so the late end of a cancelled run
  does nothing ("Stop", a new run, leaving the page). One line alone ("Listen" of an expanded text) uses the speaker's voice too and ends any run.
- `dialogueVoices(voices, preferred)` in `speech/voices.ts` (pure, unit-tested): two different en-US voices when the browser has two (the learner's chosen voice stays the first speaker's), else the same
  voice for both, else the first English voice, else none. Which speaker is which comes from `dialogue.speakers` (an unknown name reads as the first).
- "Listen first": the lines are not in the page until "Show the text" (`aria-expanded`, `aria-controls`). The shadowing step lists its own lines (they are dialogue lines): they are needed to repeat
  them and step 3 comes after the listening in the advised order, which is not enforced.
- No voice, no synthesis or an open microphone disable the buttons and say why, with the existing `speech.*` sentences.

## D-257 — "Write this unit with the AI": one request, answers in words, nothing hidden (M8.b1; builds on D-079, D-095, D-148)

- The button stays focusable while it works (`aria-disabled`, not `disabled`) and a `ref` guard drops a second click, so a double click sends one request (broken-code check: without the guard the test fails).
  The counter "Writing the unit… n s" uses `useElapsedSeconds`; a polite status says once that the AI is writing.
- `incomplete` and `unavailable` are HTTP 200 answers: the page says why (`aiReasonText`), says nothing was written, offers "Try again", and on `unavailable` a "Configure the AI" link to `/settings`.
  `409 unit_generated` (written in another tab) refreshes the track and says nothing. Any other refusal goes through `ErrorText`. On `ok` the page goes to the unit.
- Nothing starts by itself: opening or reloading a page only reads (no generation, no step mark, no upload).

## D-258 — Every curriculum write refreshes tracks, units, library, triage and Today (M8.b1)

- `useStartTrack`, `useOpenUnit`, `useGenerateUnit` (on `ok` or `409 unit_generated`), `useMarkStep` and `useAddUnitTerms` invalidate the `curriculum`, `items`, `decks`, `triage` and `session/today` keys;
  the unit returned by an answer is also put straight into the unit's query. Pagination of a track is the URL's `?page=` (1-based, 25 units per request).

## D-259 — Small screen decisions of M8.b1

- Word units: no content status and no usage sheet or definition (D-075: triage without a sheet); the words are links to the library with their status in words; "Triage these words" shows the number
  still in triage and goes to `/triage?deck=<deck_id>`.
- Scenario track card: "units written" is `opened_units` (no "done" count: it would need the backend); the deck link of a track appears from the summary's `deck_id`, the unit page's link from `unit.deck_id`
  (formulas added, D-251). A track whose word list is missing says so and its Start button is disabled.
- Formulas and the final task are shown in English with the French on demand; the dialogue setting is in the interface language with the English on demand in French. Formulas already in the library
  link to their term and are not checkable; the others are checked by default and "Add these formulas to my library" sends the exact `{indices}`.
- "Unit completed" is always shown for a `done` unit; the polite announcement fires once, when the page sees `progress` become `done` (not on a plain visit).
- The corrected state of the final task is the unit's (`final_task.corrected`), not per take (the API has no per-take flag). A transcribed take counts for shadowing: the page says that speech recognition
  is not a pronunciation judge.
- `invalid_content` shows the backend's `problems[]` (English, they name a location, never the text) under the translated sentence. The licence line of the two word lists is under the track cards, with the link to
  https://www.newgeneralservicelist.com. The Today card suggests a track when the plan's limit is `nothing_to_learn`.
