# vocab-coach

**Turn the words you care about into words you actually use.**

vocab-coach is a free, local web app for French-speaking learners of English. You bring the words and
expressions you meet in your reading, classes or daily life; the app builds a usage sheet for each one,
walks you through a first discovery, schedules spaced reviews (FSRS), makes you produce sentences and speak,
logs your recurring errors (prepositions, tenses…) and shows your progress with real statistics.

> **Status: milestone M2.b2 (AI providers).** The app starts and shows an empty home screen. Behind it
> sit the data model, the review scheduler, demo data and an AI gateway with Gemini, Groq and Ollama
> adapters, usable from the command line (`python -m app ai ...`). Screens arrive milestone
> by milestone — see [`docs/PROGRESS.md`](docs/PROGRESS.md) and the roadmap in
> [`docs/SPEC.md`](docs/SPEC.md#9-roadmap).

![Home screen](docs/screenshots/home.png)

## Principles

- Active recall before any answer is shown; spaced repetition with FSRS.
- Words, collocations and spoken formulas learned in real context, with pitfalls for French speakers.
- Production first: sentences, paragraphs and speaking, with corrections that feed an error log.
- Free to run: only free AI tiers (Gemini, Groq, local Ollama) and the browser's speech synthesis.
  Works without any key in a degraded mode.
- Private: everything stays on your computer. Your data is never committed to the repository.

## Install on Windows 11

You need **Git**, **uv** and **Node.js LTS (≥ 22.22)**. Python is installed for you by uv.

1. Open **PowerShell** and install what is missing (skip what you already have):

   ```powershell
   winget install --id Git.Git -e
   winget install --id astral-sh.uv -e
   winget install --id OpenJS.NodeJS.LTS -e
   ```

   Close and reopen PowerShell afterwards so the new commands are found.

2. Get the code:

   ```powershell
   git clone https://github.com/<your-account>/vocab-coach.git
   cd vocab-coach
   ```

3. Check your environment (it tells you exactly what to install if something is missing):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\check-env.ps1
   ```

4. Start the app:

   ```powershell
   .\start.cmd
   ```

   or double-click `start.cmd` in File Explorer. The first run installs the dependencies (a few minutes),
   then your browser opens on <http://127.0.0.1:5173> as soon as the app answers. Press **Ctrl+C** in
   the terminal to stop. Add `-NoBrowser` to start without opening the browser.

   If you prefer PowerShell directly: `.\start.ps1` (if scripts are blocked, use
   `powershell -ExecutionPolicy Bypass -File .\start.ps1`).

### macOS / Linux

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js LTS, then:

```bash
git clone https://github.com/<your-account>/vocab-coach.git
cd vocab-coach
./start.sh
```

## Try the demo

To see the app with about two months of fictional history (decks, reviews, productions and errors)
without touching your own data:

```powershell
.\start.cmd -Demo
```

(`./start.sh --demo` on macOS / Linux.) The first demo launch generates `data/vocab-coach-demo.sqlite3`
in a few seconds and prints a summary; the top bar then shows a **Demo data** badge. Your own database
(`data/vocab-coach.sqlite3`) is never read or changed in demo mode. Start without `-Demo` to get back
to it.

Other demo commands (run from `backend/`):

| Command | What it does |
|---|---|
| `uv run python -m app --demo plan today` | Today's session plan on the demo database |
| `uv run python -m app demo seed --reset` | Rebuild the demo database (stop the app first) |
| `uv run python -m app demo seed --seed 7 --days 30 --reset` | Another reproducible history |

The same seed always produces the same data. Everything in the demo (`content/demo/`) is invented.

## Configuration

Copy `.env.example` to `.env` (same folder) and fill in what you need. `.env` is ignored by Git, so your
keys never reach the repository. Every variable is optional: without any key the app still starts and
runs in a degraded mode (no AI features).

The AI keys can also be added, replaced and removed from the application itself: open **Settings** in the
top bar. The page writes the three AI variables into `.env` for you (it keeps your comments and other
lines), never shows a saved key again, and has a **Test connection** button per provider (one real request,
up to about a minute and a half). The same page sets the provider order, shows today's AI calls and holds
the study settings (time budget, new terms per day, target retention, study day, audio speed). Editing `.env` by hand stays possible. If one of these variables is **also set
as an environment variable**, the environment wins and the application will not edit that key (remove the
environment variable first).

> **Privacy.** Whatever the app sends to an AI provider leaves your computer. Send nothing confidential.
> On the **free tier of Gemini**, Google's pricing page says the content *may be used to improve its
> products* (it is not on the paid tier). Your words, sentences and corrections are sent to Gemini first
> (it is the first provider tried): if that matters to you, leave the Gemini key empty and the app uses
> Groq or Ollama only.

### Gemini: the main free text model (Google AI Studio)

1. Sign in at <https://aistudio.google.com/apikey> with a Google account and create an API key (Google may ask
   you to accept its terms; check there whether your account and country get the free tier).
2. In `.env`, add `VOCAB_GEMINI_API_KEY=` followed by the key: no quotes, no spaces.
3. Check it from the `backend` folder:

   ```powershell
   cd backend
   uv run python -m app ai test --provider gemini
   ```

   You should see a line like `gemini: ok (gemini-3.5-flash-lite, 700 ms, tokens in/out 88/11)`.

- **Model**: `gemini-3.5-flash-lite` by default (a stable model, free of charge according to
  [Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing), read on 2026-10-16). To use
  another one, set `VOCAB_GEMINI_MODEL` (for instance `gemini-3.8-flash`); leave it empty for the default.
  Some models have no free tier (`gemini-4-argon`, per Google's pricing page): with a free key, a call to one of them is refused.
- **Limits**: Google does not publish the free-tier numbers; they are per project and shown in
  [AI Studio](https://aistudio.google.com/). A per-minute limit is waited for (up to 20 seconds) or the app
  moves on to Groq; a daily limit sets Gemini aside for an hour (the quota resets at midnight Pacific time).
- **Availability**: Cameroon is in Google's list of supported countries. Whether the free tier works for
  your key from there is only confirmed by a real call: if `ai test` reports `auth` with a message about
  the region or the free tier, the app keeps working with Groq and Ollama.

### Groq: free text model and speech-to-text

1. Create an API key at <https://console.groq.com/keys> (sign in or create an account if the console asks).
2. In `.env`, add `VOCAB_GROQ_API_KEY=` followed by the key: no quotes, no spaces.
3. Check it from the `backend` folder:

   ```powershell
   cd backend
   uv run python -m app ai status
   uv run python -m app ai test
   ```

   You should see a line like `groq: ok (openai/gpt-oss-20b, 650 ms, tokens in/out 96/14)`.

The free plan has limits. Approximate values from [Groq's rate-limits page](https://console.groq.com/docs/rate-limits)
(read on 2026-10-16; they change, and your own limits are shown in your Groq console):

| Model used by default | Requests | Tokens / audio | Notes |
|---|---|---|---|
| `openai/gpt-oss-20b` (text) | 30 per minute, 1,000 per day | 8,000 tokens per minute, 200,000 per day | the app falls back or waits when a limit is hit |
| `whisper-large-v3` (speech-to-text) | 20 per minute, 2,000 per day | 7,200 audio seconds per hour, 28,800 per day | clips up to 25 MB |

### Ollama: optional, local and offline

Ollama runs a model on your own computer. It is slower and less accurate than the cloud models; it is
useful offline or as a last fallback.

1. Install Ollama for Windows from <https://ollama.com/download>. It keeps running in the background.
2. Download a model: `ollama pull gemma3:4b` (about 3.4 GB). Prefer a model that does not "think" (`qwen3`,
   `gpt-oss`... spend their token budget reasoning).
3. In `.env`, add `VOCAB_OLLAMA_BASE_URL=http://127.0.0.1:11434`. Write `127.0.0.1`, not `localhost`: on
   Windows `localhost` may resolve to the IPv6 address first, where Ollama does not listen.
4. Check it: `uv run python -m app ai test --provider ollama`. The first request can take a minute while
   the model loads into memory.

To use another model, set `VOCAB_OLLAMA_MODEL` (or `VOCAB_GEMINI_MODEL`, `VOCAB_GROQ_TEXT_MODEL`,
`VOCAB_GROQ_TRANSCRIPTION_MODEL`); leave them empty to keep the defaults.

### Checking your setup

Run these from the `backend` folder:

| Command | What it does |
|---|---|
| `uv run python -m app ai status` | providers, configured or not, models and order. Never prints a key. |
| `uv run python -m app ai test` | one real request per configured provider: status, model, time, tokens. Exit code 0 = all fine, 1 = a test failed, 2 = nothing configured or a usage error. |
| `uv run python -m app ai test --provider gemini` | tests only one provider (`gemini`, `groq` or `ollama`). |
| `uv run python -m app ai test --provider groq --audio my_clip.wav` | also transcribes a short clip (Groq Whisper) and prints the text. |
| `uv run python -m app ai usage --days 7` | requests and tokens per study day, provider and model (read-only). |

`ai test` and `ai usage` work on your personal database (not `--demo`): the test requests use a little of
your free quota and are recorded in it.

If a test fails, the message says why: `auth` means the key is wrong or refused, or Gemini does not serve your region on the free tier (nothing
is retried);
`quota` means a limit was reached (wait, or let the app use the next provider); `network` means the
provider cannot be reached (for Ollama: is it running, and is the address right?).

## Daily use

Coming with milestones M3–M4 (import a word list, discover new terms, review).

## Backup

Your data lives in the `data/` folder (database and audio recordings), which is never committed.
Export/restore and automatic copies to a synced folder arrive in milestone M10.
Until then, back up `data/` yourself if it matters to you.

## Development

| Task | Command |
|---|---|
| Start backend + frontend | `.\start.ps1` / `./start.sh` (or `npm run dev` after `npm run setup`) |
| Run every check (lint, types, tests) | `npm run check` |
| Backend tests only | `uv --directory backend run pytest` |
| Real-provider tests (optional, your own keys) | `$env:VOCAB_RUN_LIVE=1; uv --directory backend run pytest tests/live -m live -v` |
| Frontend tests only | `npm --prefix frontend test` |

- API docs (development): <http://127.0.0.1:8000/docs>
- The backend only listens on `127.0.0.1`.
- CI (GitHub Actions) runs lint, type checks, tests and builds on Linux and Windows for every push.

### Repository layout

```
backend/    FastAPI app (Python 3.13, uv): api/, domain/, db/, ai/, speech/
frontend/   React + TypeScript + Vite: features/, components/, i18n/, api/
content/    error taxonomy, fictional demo dataset (demo/), later the track syllabus
docs/       SPEC.md (specification), PROGRESS.md, DECISIONS.md, architecture.md
scripts/    environment check, browser opener (wait-and-open.mjs)
```

See [`docs/architecture.md`](docs/architecture.md) for details. Contributors using Claude Code: start with
[`CLAUDE.md`](CLAUDE.md).

## Licence

[MIT](LICENSE).
