# vocab-coach — Product specification

> English translation of Part B of the project brief. These decisions are settled.
> If a milestone seems to require departing from them, **stop, explain why, propose the change and wait for
> the owner's approval** — never change them silently. Approved changes are recorded in `docs/DECISIONS.md`
> and reflected here.

Section numbers match the brief (B.1 → section 1, etc.).

---

## 1. User and context

- Master's student (M2, economics and statistics, data science track), French-speaking, based in Cameroon;
  about to enter professional life (job interviews, presentations in English).
- Estimated level: speaking A2–B1, writing B2, reading B2, listening B2–C1. Overall B1.
- Goal 1: speak fluently and spontaneously, with intelligible pronunciation (target accent: American).
  Goal 2: master academic English and the vocabulary of their field for talks and interviews.
- Available time: 30 to 60 minutes a day.
- Known recurring errors: prepositions ("in campus" instead of "on campus", "in university" instead of
  "at university", uses of "by", "for", "at", "on", "in"); tenses (past simple used instead of present perfect).
- Machine: Windows 11, Python 3.13 (to confirm), Git, GitHub account, Claude Code on a Claude Pro subscription.
- Usage: personal tool, run locally on a laptop. Code published in a public GitHub repository for backup and
  possible sharing with classmates. Expected quality: a project another student could install and use.

## 2. Vision

An application that turns the words and expressions the user considers important (met in reading, classes or
daily life) into **active** vocabulary: recognised, recalled, correctly pronounced and reused spontaneously in
speech and writing. It also tracks the user's errors, categorises them, measures their frequency and organises
work on the most frequent ones.

What sets it apart from Anki or Quizlet: the user brings a word and a context, not a flashcard; the app builds
the usage sheet, the discovery session, the reuse exercises, the speaking practice and the statistical
tracking of errors.

## 3. Learning principles (apply to every feature)

1. **Paul Nation's four strands**: meaning-focused input, meaning-focused output, language-focused learning,
   fluency development. Deliberate word study does not replace exposure and production; the app must push
   towards production.
2. **Active recall before reveal**: the user always attempts an answer before seeing the solution. No answer
   is shown before the attempt.
3. **Spaced repetition** with the FSRS algorithm.
4. **Semantic elaboration and context**: every item is learned in real sentences, with its collocations,
   register and pitfalls.
5. **The learning unit is not only the word**: words, collocations ("to draw a conclusion"), expressions
   ("it is worth noting that"), spoken formulas.
6. **Several dimensions of knowledge**: recognition, understanding in context, recall (French/definition →
   English), pronunciation, use in a sentence, collocations, transfer to a new context.
7. **Useful corrective feedback**: a correction gives the wrong form, the correct form, one or two natural
   alternatives, the rule in one sentence, and feeds the error log.
8. **Immersion**: English interface by default; explanations in simple English (B1–B2), with a French
   translation available on demand.

## 4. Full functional scope

The architecture covers all the modules below from the start; they are built in roadmap order (section 9).
No later module may require redoing the data model or the dashboard: this is why the complete data model
(section 6) and the event log are laid down in milestone M1.

### Module A — Vocabulary library and import

- **Markdown import** of a list of terms, with preview and validation before saving. Flexible format:

  ```markdown
  ---
  deck: Causal inference reading
  domain: econometrics
  source: "Angrist & Pischke, Mostly Harmless Econometrics, ch. 3"
  context: "Reading for my M2 report on policy evaluation"
  deadline: 2026-11-20      # optional (talk to prepare)
  ---
  - heteroskedasticity
  - to account for | We account for regional fixed effects in all specifications.
  - shed light on
  ```

  One line = one term, optionally followed by `|` and the original sentence. The YAML header is optional; any
  missing field stays empty. The parser accepts `-`, `*` and numbered bullets and blank lines; it **reports
  ambiguous lines instead of failing**.
- **Quick add** of a term (term + optional context) from the interface.
- **AI-generated usage sheet** ("enrichment"): not a dictionary entry but a usage guide. Content: meaning in
  the given context (and other frequent meanings), definition in simple English, French translation, part of
  speech, register (academic, neutral, spoken, informal), when and how to use it, frequent collocations and
  constructions, 3 to 5 varied examples (at least one academic example in the deck's field and one spoken
  example), word family, pronunciation (American IPA and stress), typical errors of French speakers and false
  friends, similar words not to confuse. The sentences used by exercises (gap-fills, production prompts) are
  generated at the same time and stored.
- **Review**: the user can edit any sheet; an edited sheet is flagged as edited and **never regenerated without
  the user's consent**.
- **List extension**: from a deck's terms and context (title, field, goal), the AI suggests 10 to 30 related
  terms (technical terms, general academic terms, spoken formulas useful to present the topic). The user sorts
  each suggestion: "I know it" / "not sure" / "to learn". Only retained terms enter the deck.
- **Intake triage**: the same quick triage is available for an imported list, so no time is spent on words
  already known.
- **Duplicates**: detected on import (normalised form, lemma), with a proposal to merge or to attach the term
  to the new deck.
- Search, filters (deck, field, source, type, mastery status), edit, delete, archive.

### Module B — Discovering a term (first encounter)

A progressive method, once per term:

1. Show a sentence containing the term (the original sentence if there is one, otherwise a generated example).
2. The user types what they think the term means (in English or French).
3. Reveal the usage sheet, with the pronunciation audio; compare with the user's guess.
4. Short series of immediate exercises: French → English recall, gap-fill, spoken repetition of the sentence
   (listen, then optional recording), a personal sentence using the term (corrected by the AI when available).
5. The term then enters spaced repetition.

### Module C — Spaced reviews

- **FSRS algorithm** through a maintained Python library (for example the `fsrs` package from the
  open-spaced-repetition organisation; version to verify). Default target retention: 0.90, adjustable. Access to
  the algorithm goes through an internal interface so it can be replaced.
- **Two FSRS cards per term** to keep the workload under control: a **receptive** card (English → meaning) and a
  **productive** card (meaning or definition → English). The exercise type varies with card maturity:
  - receptive: recognition in a sentence, listening comprehension (hear the sentence, choose or type the
    meaning);
  - productive, young card: typed French → English recall, gap-fill;
  - productive, mature card: produce a sentence for a given situation, spoken answer.
- **Grading**: automatic when possible (typo-tolerant comparison for typed answers; AI correction for free
  productions), converted to an FSRS rating (Again / Hard / Good / Easy); the user can always override the
  proposed rating. Self-graded cards get four buttons.
- A wrong answer caused by a lexical confusion (similar word, false friend, wrong collocation) also creates an
  error event (module E).

### Module D — Daily planning and queue

- **Today's session**, in this order: due reviews first, then new terms within the daily quota, then one
  exercise targeting the most frequent error category, then, if available, a consolidation task.
- **Priority rule**: ongoing reviews always come before a new list. A new list enters the deck **queue**
  (status `queued`); it is activated when the new-term quota allows.
- The user can reorder the queue by hand. A deck with a deadline (talk to prepare) has priority and the app
  computes how many new terms per day are needed to finish discovery before the deadline, warning when this is
  unrealistic.
- **Time budget**: adjustable (default 45 min/day). Default new-term quota: 12 per day, adjustable. The app
  estimates session length from past response times and automatically reduces new terms when the forecast
  review load exceeds the budget.
- Pause a deck, resume it, mark it done.

### Module E — Error log and targeted practice

- **Error sources**: writing exercises, speaking exercises (transcribed), reviews, transcripts of conversations
  pasted by the user (for example a ChatGPT voice session), manual entry.
- **Error event**: original text, wrong form, correction, 1 or 2 natural alternatives, category, subcategory,
  short explanation, source, date, linked term if any.
- **Initial taxonomy** (extensible; the AI chooses from this list and may propose a new subcategory that the
  user approves):
  - `grammar.preposition`: time, place, movement, dependent preposition ("depend on"), fixed expression
    ("at university", "on campus"), by/for/since;
  - `grammar.tense`: past simple vs present perfect, present simple vs continuous, future forms, sequence of
    tenses;
  - `grammar.article`, `grammar.agreement` (3rd person -s, subject–verb agreement), `grammar.word_order`,
    `grammar.question_form`, `grammar.countability`, `grammar.modal`, `grammar.other`;
  - `lexis.false_friend` ("actually", "eventually"…), `lexis.wrong_word`, `lexis.collocation`,
    `lexis.word_form`;
  - `register` (too informal, too formal); `discourse` (connectors, cohesion); `spelling`;
  - `pronunciation`: sound, word_stress, intelligibility (module F).
- **Free writing**: the user writes a paragraph on a suggested topic (or their own); line-by-line AI correction,
  corrected version, more natural version, list of logged errors.
- **Transcript analysis**: paste a text (the user's own sentences); extract **only the user's errors**, not the
  other speaker's.
- **Targeted practice**: exercises generated for a specific category (for example 10 gap-fill sentences on
  at/on/in with places), with an explanation of the rule; results are logged too.
- Rules and tricky pairs the user often gets wrong can become FSRS cards ("at university").

### Module F — Speaking

- **Listening**: speech synthesis of every term and every sentence, American English voice, normal and slow
  speed.
- **Shadowing**: listen to a sentence, record it, play both versions back to back.
- **Transcription** of the recording by speech recognition; word-by-word comparison with the target sentence.
  Unrecognised words are flagged as possible intelligibility issues, with a note that speech recognition is not
  a pronunciation judge.
- **Fine-grained pronunciation assessment** (per-word and per-phoneme scores): optional module, **disabled by
  default**, plugged into a specialised service (see section 7).
- **Spoken answers** in reviews (mature productive cards) and **free speaking**: a topic, 1 to 2 minutes of
  recording, transcription, AI correction (grammar, vocabulary, structure, connectors), errors logged in
  module E, playback.
- Real-time voice conversation with a tutor stays outside the app: the user keeps using ChatGPT voice mode and
  then pastes the transcript into module E.

### Module G — Consolidation (talks and speeches)

- When enough of a deck is consolidated (default: 80 % of productive cards with a stability of at least 7 days),
  the app proposes a task: a talk, speech or interview-answer topic that requires using 8 to 15 terms from the
  deck, with a suggested structure.
- Written mode (the user writes, AI correction) and spoken mode (the user records, transcription then
  correction). The app checks which target terms were used, and whether correctly.
- A term used correctly in a free production moves to status **active**; a wrong use creates an error and
  reinforces its card.
- Export of the topic and the term list to practise afterwards with ChatGPT voice.

### Module H — General English tracks

- Built-in tracks, usable when the user has no personal list in progress:
  1. **General everyday English**: frequent vocabulary, from the New General Service List (NGSL);
  2. **Academic English**: general academic vocabulary, from the New Academic Word List (NAWL);
  3. **Speaking scenarios**: speaking-oriented thematic units, for example job interview, presenting data and
     results, meetings and discussions, small talk and networking, agreeing and disagreeing in a debate,
     describing a project, everyday situations (campus, transport, shopping, health), phone and video calls.
- Each scenario unit contains: key spoken formulas and collocations, a model dialogue to listen to, shadowing
  exercises and a final speaking task. Unit content is generated once by the AI from a fixed syllabus versioned
  in the repository (`content/curriculum.yaml`), then stored and editable.
- Track terms go through the same intake triage ("I know it / not sure / to learn") before entering the queue.
- The licence of the NGSL/NAWL lists must be checked before including them in the public repository; otherwise,
  provide a documented download script.

### Module I — Statistics and dashboard

Statistics are a core feature (the user is a statistician). All of them are computed from the event log and the
review logs, **never from ad hoc counters**.

- **Errors**: frequency by category and subcategory, **normalised** (errors per 100 words produced, so that a
  day of heavy production does not look like a regression), trend over time, top 5 recurring errors with
  examples, share of "fixed" errors (categories in lasting decline).
- **Memory**: observed retention curve vs target retention, success rate by exercise type, lapses, stability
  distribution, time (and number of reviews) before a term is consolidated.
- **Progress**: status funnel (queued → discovering → learning → consolidated → active), active vocabulary,
  progress of decks and tracks, workload forecast for the next 14 days.
- **Practice**: daily study time, regularity, words produced in writing and speaking, minutes of recorded speech.
- **AI**: calls per provider, errors and quotas reached.
- **CSV export** of all event tables, for analysis in pandas.

### Module J — Settings, data, internationalisation

- Settings: time budget, new-term quota, target retention, AI providers and keys, voice, audio speed, interface
  language.
- **English interface by default**, with an English/French switch (every string goes through i18n from the very
  first screen).
- **Backup**: full export/import (JSON + audio files in a zip archive) and an option to copy automatically to a
  chosen folder (for example a OneDrive or Google Drive synced folder). Personal data **never** goes into the
  public repository.

## 5. Architecture

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + TypeScript + Vite; React Router; TanStack Query; a charting library (Recharts or equivalent); react-i18next; Vitest | Owner's choice; rich interface (cards, audio, recordings, dashboard); possible sharing later |
| Backend | Python + FastAPI; Pydantic v2; SQLAlchemy 2; Alembic; pytest; ruff | The owner knows Python; AI SDKs and the FSRS library are in Python; statistics with pandas |
| Database | SQLite (local file in `data/`, ignored by Git) | Local single-user app, no server to install; Alembic migrations to evolve the schema without breaking everything |
| Audio | Files in `data/audio/`, ignored by Git | Recordings are personal |
| Python environment | `uv` (or `venv` + `pip` if `uv` causes trouble on Windows) | Fast, reproducible installation |
| Launch | One command (`start.ps1` or an npm script) runs backend and frontend in development; in "use" mode the backend serves the built frontend on a single port | The user must be able to review without opening two terminals |
| Quality | Unit tests of the domain (FSRS, scheduling, Markdown parser, statistics), API tests, linters; GitHub Actions runs tests and linters on every push | Public repository, project meant to last |

Code layout:

```
backend/app/
  api/            # FastAPI routes, one per module
  domain/         # pure business logic, testable without database or network (srs, scheduler, import, errors, stats)
  db/             # SQLAlchemy models, migrations
  ai/             # AI gateway: providers, versioned prompts, output schemas
  speech/         # transcription, pronunciation assessment (optional)
frontend/src/
  features/       # one folder per module (library, discovery, review, planner, errors, speaking, consolidation, curriculum, dashboard, settings)
  components/ i18n/ api/
content/          # track syllabus, word lists (if the licence allows)
docs/             # SPEC.md, PROGRESS.md, DECISIONS.md, architecture.md
```

Structural rule: every module writes **events** to a shared log (`event_log`) in addition to its own tables. The
dashboard reads this log and the review logs; adding a module means adding event types, without rebuilding the
dashboard.

## 6. Data model (laid down in full in milestone M1)

Main entities (indicative names, to be refined while keeping this coverage):

- `source`: title, author, field, context, URL or reference, date.
- `deck`: name, field, type (`custom` | `curriculum` | `error_drill`), source, deadline, priority, status
  (`queued` | `active` | `paused` | `done`), position in the queue.
- `lexical_item`: term, normalised form, type (`word` | `collocation` | `phrase` | `spoken_formula`), part of
  speech, deck, original sentence, status (`draft` | `triage` | `queued` | `discovering` | `learning` |
  `consolidated` | `active` | `known` | `archived`), dates.
- `enrichment`: term, structured content (validated JSON), provider, model, prompt version, edited by the user
  (boolean), date.
- `exercise_template`: term, exercise type, content (gapped sentence, prompt, expected answer, accepted variants).
- `card`: term, direction (`receptive` | `productive`), FSRS state (stability, difficulty, due date, state,
  repetitions, lapses, last review).
- `review_log`: card, date, exercise type, answer given, automatic rating, final rating, response time.
- `production_attempt`: type (`writing` | `speaking` | `consolidation` | `transcript_analysis` | `drill`), prompt,
  text or transcript, audio path, target terms, word count, AI feedback (JSON), date.
- `error_category`: code, parent, label, description, examples (taxonomy table, seeded at start).
- `error_event`: originating attempt or review, wrong text, correction, alternatives, category, explanation,
  linked term, source, date.
- `pronunciation_result`: attempt, target, transcript, unrecognised words, optional scores (optional module).
- `consolidation_task`: deck, topic, suggested structure, target terms, status, linked attempts.
- `curriculum_track` and `curriculum_unit`: tracks, units, generated content, progress.
- `study_session`: start, end, planned content, actual content.
- `event_log`: date, event type, entity, JSON payload (shared log for statistics).
- `ai_call_log`: date, provider, model, task, tokens, duration, success or error.
- `setting`: key, value.

## 7. AI strategy

**Constraint**: free or nearly free. The Claude Pro subscription is used to **build** the app, not to run it: the
app must not depend on a paid API.

**AI gateway**: a single interface (`generate_json(task, inputs, schema)` and `transcribe(audio)`) with several
interchangeable providers configured in `.env`:

| Role | Default provider | Notes |
|---|---|---|
| Main text (enrichment, corrections, exercise generation) | Gemini API, free tier, Flash or Flash-Lite model (exact name to check in the docs at milestone time) | Free tier limited in requests per minute and per day; data sent on the free tier may be used to improve the models: send nothing confidential. Availability of the free tier in Cameroon to be checked |
| Text, fallback | Groq (open models, including Llama), OpenAI-compatible API, free tier without a credit card | Automatic switch if the main provider returns a quota error |
| Speech-to-text | Groq, Whisper model (free tier) | Local option: faster-whisper on CPU, for short clips |
| Text-to-speech | Browser speech synthesis (Web Speech API), Windows en-US voices | Free and offline |
| Pronunciation assessment (optional) | Azure AI Speech, free F0 tier (about 5 h of audio per month, includes pronunciation assessment) | Disabled by default; requires an Azure account |
| Local (optional) | Ollama (OpenAI-compatible API) | To work offline if the machine allows |

The OpenAI-compatible endpoint makes it possible to add other providers (OpenRouter, Meta's Llama API if it
becomes accessible) without changing business code.

**Saving rules** (to stay within free quotas):

- A usage sheet and its exercises are generated **once** per term, then stored. Ordinary reviews do not call the AI.
- The AI is called live only to correct a free production (sentence, paragraph, speech) and to generate a list
  extension, a consolidation task or a track unit.
- Group several terms in one enrichment call when possible (batches of 5 to 10).
- Queue with retry and exponential backoff on HTTP 429; `ai_call_log`; daily counter visible in settings.
- Expected order of magnitude: a few dozen calls per day.

**Reliability**:

- All AI outputs are JSON validated by a Pydantic schema; on failure, one retry including the error message,
  then a "to complete" status that does not block the user.
- Prompts versioned in `backend/app/ai/prompts/` (text files, with a version number stored in every result).
- Correction prompts ask to flag only real errors, not to rewrite style when the sentence is correct, to say
  when a phrasing is correct but unnatural, and to classify every error in the taxonomy.
- **Degraded mode**: without a key or network, the app stays usable: manual sheet entry, reviews,
  self-grading, manual error log, statistics.

**Security**: keys in `.env` (never committed), documented `.env.example`; the key is never sent to the frontend;
the backend listens only on `127.0.0.1`.

## 8. Conventions

- Language: code, comments, commit messages, README and repository documentation in English. Interface in
  English, French translation via i18n.
- English README: overview, screenshots, Windows installation (with notes for macOS/Linux), step-by-step setup of
  the free keys, daily use, backup, architecture, licence.
- Licence: MIT (unless an included word list imposes otherwise).
- Public repository: `.gitignore` covers `data/`, `.env`, exports and audio. A fictional demo dataset (a few
  invented decks and errors) makes it possible to try the app without personal data.
- Conventional Commits; one branch per milestone, merged into `main` when tests pass.
- Basic accessibility and keyboard shortcuts for reviews (reveal, rate 1 to 4, replay audio).
- Sober, readable interface, dark mode; daily speed of use matters more than decoration.

## 9. Roadmap

Every milestone leaves an app that starts and whose tests pass. The criteria below are minimums.

| Milestone | Content | Main acceptance criteria |
|---|---|---|
| **M0 — Foundation** | Environment check (Python, Node.js LTS, Git, uv) with install instructions when something is missing; public GitHub repository; backend/frontend monorepo; `CLAUDE.md`; `docs/SPEC.md` (English translation of Part B of the brief); `PROGRESS.md`, `DECISIONS.md`; one-command launch; i18n in place; empty home screen; GitHub Actions CI | `start.ps1` opens the app; tests and linters green locally and in CI; no sensitive file committed |
| **M1 — Data model and domain** | Complete schema (section 6) with migrations; initial error taxonomy seeded; FSRS service behind an interface; session planner and queue (module D, logic only); event log; demo data | Unit tests: planner (reviews before new, quota, deadline, budget), FSRS (rating → due date), queue; database created from scratch by migrations |
| **M2 — AI gateway** | Gemini, Groq, Ollama providers; output schemas; versioned prompts; retry and fallback; call log; degraded mode; settings page for keys with a "test connection" button | Tests with a fake provider; one real test call succeeds with the user's key; simulated 429 → fallback |
| **M3 — Library and import** | Full module A: Markdown import with preview, quick add, batch enrichment, review and editing, intake triage, list extension, duplicates, search and filters | Import of a sample file with and without header; ambiguous lines reported; edited sheet never overwritten |
| **M4 — Discovery and reviews** | Modules B and C; today's session (module D interface); speech synthesis; keyboard shortcuts | An imported term goes through discovery then appears in review on the right date; typo-tolerant automatic grading; rating can be changed |
| **M5 — Errors and writing** | Full module E: corrected free writing, pasted transcript analysis, manual entry, targeted practice, cards from errors | Test paragraph containing "in campus" and a wrong past simple → two errors in the right subcategories |
| **M6 — Speaking** | Module F: recording, Groq transcription, shadowing, word-by-word comparison, spoken answers in reviews, corrected free speaking; optional Azure hook | Recording → transcription → correction → errors logged; works without Azure |
| **M7 — Consolidation** | Module G: trigger, topics, written and spoken modes, detection of target-term use, "active" status | Consolidated demo deck → task proposed → production → statuses updated |
| **M8 — General English tracks** | Module H: syllabus, word-list import (licence permitting), scenario units generated and stored | One track runnable end to end; intake triage applied |
| **M9 — Dashboard** | Full module I; CSV export | Indicators computed on demo data, checked by tests on hand-built cases (normalised rates, retention) |
| **M10 — Polish** | Complete French translation; backup and restore; README with screenshots; single-port "use" mode; security and performance review | Restore of a backup into an empty database; installation from scratch following the README |

The dashboard comes late in the build order, but the events it uses are recorded from M1: when it arrives, the
history already exists.

## 10. Out of scope (this version)

- User accounts, online server, multi-device sync, mobile app.
- Real-time voice conversation with an AI tutor (ChatGPT voice remains the tool for that).
- Automatic PDF analysis and vocabulary extraction from a full article (the user provides the list; this can be
  added later by reusing module A).
- Elaborate gamification (badges, leaderboards): a simple day streak is enough.

## 11. Assumptions to verify during development

- Exact installed Python version (3.13 expected) and presence of Node.js (not confirmed).
- Names of the free models and current quotas of Gemini and Groq; availability of the Gemini free tier from
  Cameroon.
- Version and API of the `fsrs` library.
- Licence of the NGSL/NAWL lists.
- Quality of the en-US voices available in Windows 11 and in the browser used.
- Creating an Azure account (a payment method may be required at sign-up) if the pronunciation module is enabled.
