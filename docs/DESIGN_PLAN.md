# Design overhaul plan

Status: **implemented in part**: RV.a (foundations: layers, tokens, Inter, icons, base components, sidebar shell,
style guide, contrast test, charts) is done; RV.b (screen by screen) comes next. Corrections made while
implementing (see D-285 to D-294 in `docs/DECISIONS.md`): **icons are home-made SVG, not Tabler** (no new
dependency); `border-strong` is `#8582a8` / `#7472ab` (3.65:1 on surface, the first values were 1.6:1) and
`accent` is `#a8461f` in light (5.16:1 on its tint); the sidebar group "Library" is named "Vocabulary".
Original text: visual decisions are made now; implementation starts **after M9** (before or as
part of M10). Nothing in this file changes `docs/SPEC.md` until the owner approves the amendment below.

## Why

Review of the current frontend (2026-10-24, demo database, light and dark themes):

- **Navigation**: seven links plus language and theme selectors in one top bar; it wraps onto two or
  three lines on narrow windows. Sub-pages (import, triage, duplicates, decks, history...) are hidden
  behind rows of underlined text links.
- **No hierarchy**: every block is the same grey card with the same weight. Nothing says what to do
  first. The home page is a bulleted list of text and feels empty.
- **Looks like a form**: numbers buried in sentences ("Reviews: 0 done, 48 left"), large stacked
  forms (quick add fills the first screen of the library), section titles that are only bold text.
- **Colours and type**: dull palette, system font, small contrast between headings (1.15rem) and
  body text (1rem).

What is already good and stays: colours go through CSS tokens in `frontend/src/styles.css`, no
inline styles in components, light and dark themes, focus styles, keyboard shortcuts.

## Decisions taken (owner, 2026-10-24)

| Topic | Decision |
|---|---|
| Overall direction | **A, "calm and focused"**: left sidebar, one main action per screen, generous spacing |
| Navigation | Left sidebar in the **brand colour**, **expanded by default and collapsible** to an icon rail (fold / unfold button, choice remembered per browser); section titles use the same colour |
| Top bar | A **top bar stays** above the page: fold / unfold button on the left; demo badge, **Language** and **Theme** selectors on the right (they do not move to Settings) |
| Screens | PC only (wide screen); no dedicated mobile layout |
| Themes | Light and dark get the same care |
| Font | **Inter** everywhere (bundled locally, no runtime download) |
| Home page | A real home: large full-bleed hero with a **real photo** (free licence, bundled) and today's session as the main action; below it three key numbers and "Continue" tiles |
| Section pages | Large coloured header block with an **illustration** per section (library: books, speaking: microphone...) |
| Sub-actions | The underlined links under section titles become **buttons** with icon and counter ("Sort new terms (9)") |
| Brand colour | **Bright indigo** (chosen from four proposals: bright indigo, deep violet, terracotta, terracotta with teal-blue). Starting values, to be finalised in the Design System: brand `#4F46E5`, sidebar `#312E81`, header tint `#EEF0FF`, tinted border `#C7CCFB`; dark theme page `#14132B`, surface `#1E1D3D`, accent `#A5B4FC` |
| Images | Home hero: photo P6. Section headers: 3D clay illustrations in both themes (one series per theme). Other illustrations: flat SVG. Details below |

## Home hero photo candidates (Unsplash licence, free tier)

Previewed by hotlinking only; the chosen file is downloaded and bundled at implementation time.

| Id | Description | Source |
|---|---|---|
| P1 | Smiling learner with headphones, colourful room | https://unsplash.com/photos/jeune-femme-portant-des-ecouteurs-travaille-sur-un-ordinateur-portable-D6maLgY8nPk |
| P2 | Smiling learner at a desk with headphones | https://unsplash.com/photos/une-femme-travaille-joyeusement-sur-son-ordinateur-portable-3yVKi6aWddk |
| P3 | Laughing woman at a table, black and white | https://unsplash.com/photos/deux-femmes-souriantes-et-parlant-a-une-table-LXJ5RfH73ls |
| P4 | Headphones and laptop in a café, evening | https://unsplash.com/photos/femme-utilisant-un-ordinateur-portable-dans-un-espace-de-travail-au-cafe-7QVUTtvcIGI |
| P5 | Large library, no face | https://unsplash.com/photos/un-etudiant-etudie-dans-une-grande-et-ancienne-bibliotheque-qfrth-FyHio |
| P6 | Headphones, thoughtful look | https://unsplash.com/photos/une-femme-assise-a-une-table-un-ordinateur-portable-et-des-ecouteurs-r3gxTlf46a4 |

Two hero layouts were proposed: **1, full-bleed photo** with an indigo gradient behind the text, and
**2, split**: text on a solid indigo block, photo on the right without overlay.

**Chosen: layout 1 (full-bleed photo) with photo P6** (confirmed 2026-10-24); P2 was the alternative. Both are
downloaded (2026-10-24, 2400 px wide, JPEG) to `frontend/src/assets/hero/home-hero-p6.jpg`
(2400x1600, 355 KB) and `home-hero-p2.jpg` (2400x1350, 520 KB). P6 sits best with
`background-position: right 35%`. The one not kept is deleted at implementation time.

## Section header illustrations (proposals, 2026-10-24)

Section header layout, shared by all styles: tinted indigo block, small "Section" eyebrow, large
title in deep indigo, one-line description, one primary button plus secondary buttons with counters
(for example "Sort new terms 9"), illustration on the right.

| Style | What | Pros | Cons |
|---|---|---|---|
| A, flat | Hand-made SVG objects (books, notebook, microphone, magnifier) in the palette | Tiny, sharp at any size, colours follow the theme through CSS variables | Simpler, less "wow" |
| B, geometric | Stacked rounded shapes around the section icon | Most sober and consistent, nothing to maintain | Least warm |
| C, 3D clay | AI images generated with Canva (originals 1680x944, kept in the owner's Canva account) | Warmest, most "learning app" | Heavier files; light background baked in, so dark theme needs a tile or dark versions |

**Chosen (2026-10-24): combine C and A.**

- **Light theme, section headers**: style C (3D clay). At implementation, export the four originals
  (1680x944) from Canva, compress them (WebP), bundle them, and fade their edges into the header tint.
- **Dark theme, section headers**: style A (flat SVG). The 3D images have a light background baked in
  and look like a pasted tile on dark surfaces.
- **Everywhere else** (empty states, onboarding, small spot illustrations): style A, drawn in the
  same flat SVG language with colours from CSS variables.

The header component therefore picks its illustration from the active theme.

**Superseded (2026-10-24): 3D clay in both themes.** A second Canva series was generated on the
dark header colour (`#1E1D3D`) with lighter indigo objects and rim light, one image per section.
With the edges faded into the header it blends well, so the owner chose:

- **Section headers, both themes**: style C (3D clay), one image per section and theme
  (8 images; originals 1680x944 in the owner's Canva account, exported and compressed at
  implementation time).
- **Everywhere else**: style A (flat SVG).

The light/dark split described just above no longer applies.

## Proposed SPEC amendment (needs approval before implementation)

`docs/SPEC.md` currently says: "Sober, readable interface, dark mode; daily speed of use matters more
than decoration." Proposed replacement:

> Section landing pages (home, library, writing, speaking, errors) have a large coloured header with
> an illustration, and the home page a hero photo. Working screens (review, discovery, drills, forms)
> stay clean and focused: no images, one main action, nothing that slows daily use. Dark mode.

Constraints that do not change: active recall (no answer shown before an attempt), every string
through i18n, no runtime network call for assets (images and fonts are bundled in the repository),
image licences must allow redistribution in a public repository (Unsplash, unDraw or generated).

## Steps

1. **Decisions** (done above).
2. **Visual proposals**: brand palette, hero photo, illustration styles (done, 2026-10-24).
   **Design System v1 published** (2026-10-24): https://claude.ai/artifact/JTXNiqX9PkLFw6HsDYao3S
   (private to the owner). Tokens for both themes, Inter type scale, spacing, radii, shadows, and
   13 components with previews: Sidebar, HomeHero, SectionHeader, Button, Badge, StatTile,
   ActionTile, Card, Field, Notice, ReviewCard, CorrectionMark, EmptyState. Icons: ~~Tabler outline~~ home-made outline SVG set (D-289)
   (to add at implementation, version checked then).
3. **Design System** reference (link above). Owner comments; revisions go to the same artifact.
   **Approved** (2026-10-24).
4. **Mock-ups** of three key screens: home, library (section hub), review session. Iterate.
   **v1 published** (2026-10-24): https://claude.ai/artifact/BgyHqkEG7CaYvfSnGctsdS (private to the
   owner), French copy, demo-database figures, a light/dark switch on each screen (Tweaks); the
   review screen is clickable (check, show answer, rate, next card).
   **v2** (2026-10-24, owner feedback): collapsible sidebar and a top bar with Language and Theme
   on every screen (the Theme selector switches the mockup); Design System gained the `TopBar`
   component and the collapsed `Sidebar` variant. **Approved** (2026-10-24).
5. **Before implementation** (after M9):
   - Owner approves the SPEC amendment above; it is applied to `docs/SPEC.md` in the first commit.
   - Export the 8 section illustrations at full size (1680x944) from Canva, compress to WebP
     (about 800 px wide), and delete the unused `home-hero-p2.jpg`.
   - Check and pin versions (`npm view <pkg> version`) for the Inter font package (bundled, no
     runtime download) and Tabler Icons.
   - Screens of M7 to M9 are built with the current styles; they are restyled with the rest.
6. **Implementation**, on a branch `design-overhaul`, one step per commit, `npm run check` after each:
   1. Tokens: replace the colour, type, spacing and radius tokens in `frontend/src/styles.css` with
      the Design System's (light and dark), bundle Inter.
   2. Shell: `Sidebar` (collapsible, state in localStorage) and `TopBar` (Language, Theme, demo
      badge) replace the current top navigation; i18n keys in `en.json` and `fr.json`.
   3. Base components: Button, Badge, Card, Field, Notice, StatTile, ActionTile, EmptyState, icons.
   4. Home: `HomeHero` with the P6 photo, stat tiles, "Continue" tiles, plan warnings card.
   5. Section hubs: `SectionHeader` with its 3D illustrations on Library, Writing, Speaking, Errors;
      underlined links become buttons with counters.
   6. Working screens: review, discovery and drills on `ReviewCard`; corrections on `CorrectionMark`.
   7. Remaining pages (Settings, history and detail pages, import, triage), then a full pass in
      both themes, keyboard and contrast checks, and updated frontend tests.
7. Update `docs/DECISIONS.md` and `docs/PROGRESS.md` as implementation goes.
