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
