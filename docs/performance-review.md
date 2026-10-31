# Performance review (M10.b)

Machine: the owner's Windows 11 PC. Measured on 2026-10-27, branch `feat/m10b-use-mode`. Every database is in a
temporary `VOCAB_DATA_DIR`; `data/` was never opened.

## 1. Bundle

Before = `main`-equivalent code (tip of `feat/m10a-backup`, one JS file). After = lazy pages + a `vendor` chunk
(D-314). Raw bytes from the files, gzip level 9 (Vite's own gzip figures differ by about 1 %).

| File | Before raw | Before gzip | After raw | After gzip |
|---|---:|---:|---:|---:|
| `index-*.js` (the application's entry) | 1,028,419 | 281,699 | 226,762 | 72,520 (Vite) |
| `vendor-*.js` (React, router, TanStack Query, i18next) | in `index` | in `index` | 403,461 | 126,520 (Vite) |
| `rolldown-runtime-*.js` | in `index` | in `index` | 599 | ~0.4 k |
| 84 page and shared chunks (`HomePage` 6,576; `SessionPage` 50,010; `DashboardPage` 32,412; `UnitPage` 30,495; ...) | in `index` | in `index` | 2 to 50 kB each | |
| `index-*.css` | 54,199 | 9,856 | 54,235 | 9,840 |
| `InterVariable.woff2` | 352,240 | (already compressed) | 352,240 | |
| `home-hero-p6.jpg` | 355,390 | (already compressed) | 355,390 | |

The gzip figures of `index` and `vendor` are Vite's report; the others are computed. 87 JS files in all.

**JavaScript loaded by the home page** (14 files: entry, runtime, vendor, `HomePage`, `client`, `Icon` and the small
shared modules it imports): **651,426 B raw / 205,382 B gzip, against 1,028,419 / 281,699 before: -37 % raw,
-27 % gzip.** Other pages load their own file (2 to 50 kB) when first opened.

- The Vite warning "chunk larger than 500 kB" is **gone** (`npm run build` prints no size warning). The entry file
  alone was 513,495 B after the page split; the `vendor` chunk (libraries change rarely, so the browser keeps
  it) brings it to 226,762 B.
- **`fr.json` / `en.json`**: 111,473 B (33,301 gzip) and 98,700 B (29,935 gzip) minified, both in the entry/vendor
  graph. Loading `fr.json` only when French is chosen would save about **111 kB raw / 33 kB gzip** for English
  readers, at the cost of a flash of untranslated keys unless the language loads before the first render. **Not
  applied; to be decided by the owner.**
- **Illustrations** (added by a later commit, `c142bfd`): eight PNG headers of 1.3 to 1.4 MB each (about 11 MB
  in all) are built into `dist/assets`; one pair is loaded per section page. They are **by far the heaviest
  files of the application**, heavier than all the JavaScript together. Resizing them (their display size is a
  few hundred pixels wide) or converting to WebP would cut each by an order of magnitude. Not changed here
  (the files are the owner's art).

## 2. Start-up

Process start to the first `200` of `/api/health`, `python -m app --use` on the 365-day demo, 5 starts:
1,763, 2,222, 2,361, 2,228, 2,206 ms; **median 2,222 ms** (includes interpreter start, imports, the startup
hook and the polling loop's own overhead).

## 3. Routes

Demo of 365 days (`demo seed --reset --days 365 --seed 42 --anchor 2026-10-27`, built in **17.0 s**; dataset
version 7), method of D-278: in-process `TestClient`, `now` = the anchor at noon, one first call then the median
of five warm calls. Script: `scripts/measure_performance.py`.

| Route | First call (ms) | Median of 5 (ms) |
|---|---:|---:|
| `GET /api/session/today` | 150.7 | 16.9 |
| `POST /api/session/start` (session already open) | 7.4 | 7.6 |
| `GET /api/session/{id}/next` | 23.1 | 17.5 |
| `POST /api/reviews/grade` | 17.5 | 12.5 |
| `GET /api/items` (first page) | 11.9 | 9.0 |
| `GET /api/items?q=the` (search) | 19.3 | 10.5 |
| `GET /api/stats/overview` | 131.1 | 59.7 |
| `GET /api/stats/errors?granularity=week`, 366 days | 56.8 | 55.0 |
| `GET /api/stats/memory` | 19.4 | 17.2 |
| `GET /api/stats/progress` | 88.8 | 70.3 |
| `GET /api/stats/practice` | 42.5 | 38.9 |
| `POST /api/backup` (4,474 rows, 24 recordings, ~0.4 MB zip) | 764.0 | 1,003.1 |

(`POST /api/session/start` was measured after the first call had created the session, so the figures are for the
"already open" answer; the creation itself happens once a day.)

**No route is over 300 ms in median** (backup excluded, as the brief says). The slowest, `stats/progress`, is 70 ms.
**No index is proposed; no migration.** The first call of `session/today` and `stats/overview` (150 and 131 ms) is
the cold start of the process (imports, statement caches), as in D-278. The backup takes about one second for
this dataset, which is fine for an action the owner starts.

## 4. Page weight, home page

Built-in browser, `http://127.0.0.1:8000/`, nothing compressed (loopback, D-310):

| | Transferred |
|---|---:|
| Cache full (second visit; revalidated files answer 304) | **48,953 B**, of which 31,337 B are `/api/*` answers |
| Cache empty, computed from the files the page requested (HTML 515 + JS 651,426 + CSS 54,410 + font 352,240 + photo 355,390) + the same API answers | about **1.44 MB** (before the split: about 1.79 MB) |

The "cache empty" figure is computed, not measured: the browser's cache could not be emptied from the tool, and
the font and the photo were already cached when the page was measured. The cold figure counts every byte the
home page needs.

## 5. What was not measured

- Gzip of everything served: there is none (no compression on the loopback, no dependency).
- Timings inside a browser (first paint) were not taken; only bytes and requests.
