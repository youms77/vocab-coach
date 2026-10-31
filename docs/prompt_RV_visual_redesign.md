# Jalon RV — Refonte visuelle (frontend uniquement)

> Prompt d'exécution pour Claude Code (Sonnet 5.5). Il fusionne le brouillon « Jalon RV » et le plan de refonte
> validé le 24 octobre 2026 (`docs/DESIGN_PLAN.md`, Design System et maquettes). **Quand les deux divergent,
> ce prompt fait foi** : il reprend les décisions du propriétaire, avec les valeurs corrigées pour le contraste.

## Contexte

Lis d'abord, dans cet ordre :
1. `CLAUDE.md`.
2. `docs/SPEC.md` : section 3 (principes 2 et 8), section 8 « Conventions », section 9.
3. `docs/PROGRESS.md` : « Current state », puis les « Left / known limits » de M5.b1 à M9.b2.
4. `docs/DECISIONS.md`, au moins :
   - D-007 (thème, polices système) ;
   - D-087 (sévérité jamais portée par la seule couleur) ;
   - D-090 et D-157 (`minmax(0, 1fr)`, `min-width: 0`) ;
   - D-119 et D-145 (375 px, barre du haut sur deux lignes) ;
   - D-122 (raccourcis) ;
   - D-279 à D-284 (graphiques sans bibliothèque, « Show the numbers », `insufficient`).
5. `docs/DESIGN_PLAN.md`. Il n'est pas sur `main` : voir « Branche ».

Références visuelles du propriétaire (artefacts privés de son compte) :
- **Design System** : https://claude.ai/artifact/JTXNiqX9PkLFw6HsDYao3S. Lis `project/README.md`, `project/tokens.json`
  et `project/components/*/README.md` avec l'outil Artifact (`action: "read"`, `path`).
- **Maquettes** : https://claude.ai/artifact/BgyHqkEG7CaYvfSnGctsdS. Lis `project/Main.dc.html`, `project/Library.dc.html`
  et `project/Review.dc.html`.

Si tu ne peux pas les lire, travaille avec ce prompt seul : il contient toutes les valeurs nécessaires. Les valeurs
de ce prompt priment sur celles des artefacts (deux couleurs y ont été corrigées, voir « Tokens »).

### Branche et état de départ

- `main` contient M1 à M9 (PR #24 et #25). Pas de migration après `0002`. La prochaine décision libre est **D-285**,
  sauf si M10.a a déjà tourné : prends alors le premier numéro libre.
- Crée `feat/rv-visual-redesign` depuis `main`, puis `git cherry-pick 6f8b007`. Ce commit, sur la branche
  `docs/design-overhaul-plan`, ajoute :
  - `docs/DESIGN_PLAN.md` ;
  - `frontend/src/assets/hero/home-hero-p6.jpg` et `home-hero-p2.jpg`.
- Supprime `home-hero-p2.jpg` (photo non retenue) dans le premier commit de RV.a.
- Vérifie que `npm run check` est vert sur `main` et note le nombre de tests Vitest : c'est la référence.
- Si l'état ne correspond pas à ce qui précède, arrête-toi et dis-le.

### Mise à jour de la spec (approuvée par le propriétaire)

Dans `docs/SPEC.md`, deux changements, faits une seule fois dans le premier commit :
1. **§9** : ajoute la ligne « **RV — Visual redesign** », entre M9 et M10. Contenu et critères : ceux de ce prompt,
   en une ligne.
2. **§8**, la ligne « Sober, readable interface, dark mode; daily speed of use matters more than decoration. »
   devient :

   > Section landing pages (home, library, writing, speaking, errors) have a large coloured header with an
   > illustration, and the home page a hero photo. Working screens (review, discovery, drills, forms) stay clean and
   > focused: no images, one main action, nothing that slows daily use. Dark mode.

## Objectif

L'application a une identité visuelle cohérente, celle du Design System :
- indigo vif ;
- police Inter embarquée ;
- barre latérale indigo repliable et barre du haut ;
- pages d'accueil de section illustrées ;
- écrans de travail épurés.

Tout repose sur un seul système de tokens et de composants de base, en clair et en sombre, de 375 px à l'écran
large, en anglais et en français.

Aucun comportement métier, aucune route, aucun appel d'API ne change. Les seuls textes nouveaux sont ceux listés
dans « Textes nouveaux autorisés ».

Le jalon est coupé en deux parties, sur la même branche :
- **RV.a** : fondations (organisation du CSS, tokens, police, icônes, composants de base, coquille et navigation,
  guide de style, test de contraste, graphiques).
- **RV.b** : passe écran par écran (accueil, pages de section avec illustrations, écrans de travail, le reste).

**Arrêt obligatoire après RV.a** : commit, PROGRESS, captures avant/après, rapport. Attends l'accord du propriétaire
avant RV.b.

## Périmètre

Inclus :
- organisation du CSS ;
- tokens (couleurs, typographie, espacements, rayons, élévation, focus, mouvement) ;
- police Inter embarquée ;
- jeu d'icônes SVG maison ;
- composants de base ;
- coquille et navigation ;
- guide de style réservé au développement ;
- test de contraste ;
- graphiques à 375 px ;
- accueil avec photo ;
- en-têtes de section avec illustrations ;
- application du système à tous les écrans ;
- défauts de mise en page connus ;
- captures avant/après ;
- documentation.

Exclu :
- **Tout changement backend** : `git diff --stat <base> -- backend` reste vide.
- **Toute nouvelle dépendance npm**, même de développement. La police et les icônes sont des **fichiers du dépôt**,
  pas des paquets : pas de `@fontsource`, pas de `@tabler/icons-react`. `package.json` et les lockfiles ne changent
  pas.
- Nouvelle fonctionnalité, à une exception : replier et déplier la barre latérale, validé par le propriétaire.
- « Mode concentration » en séance : à proposer dans le rapport, pas à faire.
- Bouton « Se connecter » ou « Tableau de bord » dans la barre du haut : ne pas le faire, ne pas le proposer.
- Traduction complète et captures du README (M10.c), mode un seul port (M10.b).

## Prérequis à vérifier (le propriétaire les fournit)

1. **Police Inter** (licence SIL OFL 1.1). Prends-la à la source officielle : les releases GitHub `rsms/inter`.
   - Cite la version et la date dans DECISIONS.
   - Le téléchargement est un ajout de fichier : demande l'accord du propriétaire avant, en donnant l'URL et la taille.
   - Embarque **uniquement** `InterVariable.woff2` (et l'italique seulement s'il sert), dans `frontend/src/assets/fonts/`,
     avec `OFL.txt` à côté.
   - Déclare-la dans un `@font-face` avec `font-display: swap`, et garde une pile de secours système
     (`"Segoe UI Variable", "Segoe UI", system-ui, sans-serif`).
   - Rapporte la taille ajoutée.
   - L'appli reste hors ligne. Cette décision **remplace la partie « polices système » de D-007** : écris-le dans
     la nouvelle décision.
2. **Illustrations des en-têtes de section** (nécessaires seulement en RV.b). Le propriétaire les exporte depuis Canva :
   - huit fichiers `header-<library|writing|speaking|errors>-<light|dark>.png`, environ 800 px de large ;
   - placés dans `frontend/src/assets/sections/`.

   S'ils manquent au début de RV.b, demande-les. Sans réponse, fais les en-têtes sans illustration et signale-le.
   N'utilise jamais d'images basse définition à leur place.

## Spécifications

### 0. Inventaire (mode plan de RV.a)

- Liste les fichiers CSS, leur taille brute et gzip, le nombre de règles.
- Compte avec `rg` les couleurs, les tailles en px et les ombres écrites en dur hors des tokens.
- Relève les liens de la barre du haut, dans l'ordre, avec leurs clés i18n. Sur `main` : Home, Today, Library,
  Writing, Speaking, Tracks, Consolidation, Errors, Statistics, Settings. Vérifie cette liste.
- Repère les composants qui dupliquent des styles (boutons, cartes, badges, avis, tableaux).
- Prends les **captures « avant »** sur le commit de base, avant toute modification (voir section 10).

### 1. Organisation du CSS

- Remplace le `styles.css` unique (environ 2 800 lignes) par quelques fichiers ordonnés par `@layer` : `tokens`,
  `base`, `components`, `layout`, `features`.
- Un fichier de fonctionnalité ne définit ni couleur ni taille en dur : il utilise les tokens.
- Après RV.b, **zéro** couleur en dur hors de `tokens`. Liste et justifie les exceptions dans DECISIONS : le
  blanc de l'anneau du bouton du bandeau photo, les SVG, etc.

### 2. Tokens

**Mécanisme du thème** :
- D-007 reste valable pour le choix du thème : `prefers-color-scheme`, sinon `data-theme` choisi et stocké
  (`vocab-coach.theme`).
- Les valeurs de chaque thème n'existent qu'à **un seul endroit**. Aujourd'hui, le bloc sombre est dupliqué entre la
  media query et `[data-theme='dark']`.
- Propose dans le plan `light-dark()` avec `color-scheme`, ou une autre solution sans duplication. Vérifie d'abord la
  prise en charge dans Edge et Chrome à jour sur MDN, et cite la date.

**Couleurs** : valeurs imposées. Les noms suivent le Design System. Donne dans DECISIONS la correspondance entre
les anciens noms et les nouveaux (`--text` → `--ink`, `--accent` → `--brand`, `--ok` → `--success`…).

| Token | Clair | Sombre | Usage |
|---|---|---|---|
| `bg` | `#f6f6fb` | `#14132b` | Fond de page |
| `surface` | `#ffffff` | `#1e1d3d` | Cartes, tuiles, champs, boutons secondaires |
| `surface-sunken` | `#efeff7` | `#191834` | Zones en creux dans une carte (zone de réponse, rayures de tableau) |
| `border` | `#e3e3f0` | `#2e2c55` | Filet des cartes et des lignes (décoratif) |
| `border-strong` | **`#8582a8`** | **`#7472ab`** | Bordure des champs et des boutons secondaires. Corrigé : l'ancienne valeur ne faisait que 1,6:1 |
| `ink` | `#1e1b3a` | `#e8e7f5` | Texte |
| `ink-muted` | `#5d5a7a` | `#a3a1c2` | Texte secondaire, libellés |
| `ink-subtle` | `#6f6c8f` | `#8f8db3` | Placeholders et légendes, sur `surface` |
| `brand` | `#4f46e5` | `#a5b4fc` | Bouton principal (un par vue), liens, progression, compteurs |
| `brand-hover` | `#4338ca` | `#b8c3fd` | Survol de `brand` |
| `on-brand` | `#ffffff` | `#14132b` | Texte sur `brand` (jamais blanc en sombre) |
| `brand-strong` | `#312e81` | `#c7ccfb` | Titres de section et de carte, grands chiffres |
| `brand-tint` | `#eef0ff` | `#1e1d3d` | Fond des en-têtes de section, puits d'icônes, avis « info » |
| `brand-tint-border` | `#d9dcfb` | `#2e2c55` | Bordure des en-têtes de section |
| `sidebar` | `#312e81` | `#0f0e24` | Fond de la barre latérale |
| `sidebar-ink` | `#c9ccf5` | `#a3a1c2` | Libellés de la barre latérale |
| `sidebar-ink-active` | `#ffffff` | `#ffffff` | Lien actif |
| `sidebar-active` | `rgba(255,255,255,.12)` | `rgba(255,255,255,.10)` | Fond du lien actif et du survol |
| `focus-ring` | `#4f46e5` | `#a5b4fc` | Contour de focus, 2 px plein, décalé de 2 px |
| `hero-scrim` / `hero-scrim-mid` | `rgba(49,46,129,.95)` / `rgba(49,46,129,.82)` | `rgba(20,19,43,.96)` / `rgba(20,19,43,.85)` | Dégradé du bandeau photo |
| `accent` | **`#a8461f`** | `#f0997b` | Corail : marques d'erreur dans un texte corrigé, petits détails d'illustration. Jamais un bouton. Corrigé pour atteindre 4,5:1 sur `accent-tint` |
| `accent-tint` | `#fbede6` | `#3a2220` | Fond d'un fragment fautif |
| `success` / `success-tint` | `#1e7a4c` / `#e3f4ea` | `#7fd49f` / `#173326` | Bonne réponse, « Bien », succès |
| `warning` / `warning-tint` | `#8a5a00` / `#fbf0da` | `#e3b55a` / `#33280f` | Échéances, termes à trier, « Difficile » |
| `danger` / `danger-tint` | `#b3261e` / `#fce9e7` | `#f2948d` / `#3a1a1e` | Mauvaise réponse, « À revoir », actions destructives |
| `chart-1..5` | `#4f46e5` `#c2552d` `#1e7a4c` `#8a5a00` `#993556` | `#a5b4fc` `#f0997b` `#7fd49f` `#e3b55a` `#ed93b1` | Séries des graphiques (au moins 4,2:1 sur `bg` et `surface`) |
| `illus-blob` `illus-paper` `illus-light` `illus-leaf` | `#dde0fd` `#ffffff` `#a5b4fc` `#1d9e75` | `#2a2856` `#3a3870` `#4f46e5` `#5dcaa5` | Illustrations plates SVG (états vides) |

**Typographie** : Inter, avec la pile de secours ci-dessus. L'échelle est en `rem`, avec une graisse et un
interlignage par niveau :

| Style | Taille | Interligne | Graisse | Usage |
|---|---|---|---|---|
| `display` | 36 px | 42 | 700, −0,02em | Titre du bandeau d'accueil seulement |
| `title-1` | 30 px | 36 | 700, −0,02em | Titre de page et d'en-tête de section, couleur `brand-strong` |
| `term` | 34 px | 40 | 600 | Le terme anglais sur une carte de révision ou de découverte |
| `title-2` | 20 px | 28 | 600 | Titres de carte, couleur `brand-strong` |
| `title-3` | 16 px | 24 | 600 | Sous-titres, titres de tuile |
| `body` | 16 px | 24 | 400 | Texte courant, champs |
| `body-sm` | 14 px | 20 | 400 | Boutons, texte secondaire, cellules |
| `stat` | 26 px | 32 | 700 | Grands chiffres |
| `eyebrow` | 12 px | 16 | 600, majuscules, +0,08em | Petit libellé au-dessus d'un titre de section |
| `caption` | 12 px | 16 | 500 | Indications de touches, notes |

Autres règles de typographie :
- `font-variant-numeric: tabular-nums` pour les chiffres des statistiques et des tableaux ;
- une police à chasse fixe système pour les codes (catégories, `kbd`).

**Autres tokens** :
- **espacements** `space-1..10` (4, 8, 12, 16, 24, 32, 40 px) ;
- **rayons** `radius-sm` 6, `radius-md` 10 (contrôles), `radius-lg` 14 (cartes), `radius-xl` 18 (bandeau et
  en-têtes), `radius-pill` ;
- **ombres** `shadow-card` et `shadow-raised` (valeurs du Design System, plus fortes en sombre) ;
- **durées** de transition, 150 ms, toutes annulées sous `prefers-reduced-motion: reduce` ;
- **largeurs** `sidebar-width` 232 px (72 px repliée), `content-max` 1120 px, `reading-max` 720 px ;
- **hauteur** des contrôles `control-height` 40 px (32 px en petit).

**Points de rupture** : 600 et 960 px. Documente-les comme constantes. Les media queries ne lisent pas de
variables : les valeurs sont donc répétées et citées dans `docs/architecture.md`.

### 3. Icônes

- Pas de bibliothèque. Crée `components/Icon.tsx` : un petit jeu d'icônes SVG en contour (trait 1,75, 24×24,
  `currentColor`), dessinées dans le style des maquettes.
- Icônes nécessaires : accueil, carte (Today), livres, crayon, micro, parcours, consolidation, alerte, statistiques,
  réglages, plus, import, filtre, étincelles, copie, flèche, cible, haut-parleur, historique, info, coche, répétition,
  menu, repli de la barre latérale.
- Une icône décorative porte `aria-hidden="true"`. Un bouton qui n'a qu'une icône porte un `aria-label`.
- Tailles : 20 px en navigation et dans les tuiles, 18 px dans les boutons, 16 px dans les petits boutons.
- Corrige la ligne « Iconography » de `DESIGN_PLAN.md`, qui prévoyait Tabler.

### 4. Composants de base

Classes CSS, et les petits composants React existants adaptés **sans changer leur API**. Pour chacun, reprends le
`README.md` du composant dans le Design System.

- **Boutons** : principal, secondaire (par défaut), discret, danger, « bandeau » (blanc, sur la photo d'accueil
  seulement), icône seule ; tailles petite, normale et grande ; états désactivé et occupé ; compteur `vc-count`
  intégré.
- **Champs** : texte, select, zone de texte, case à cocher, radio, avec aide et erreur.
- **Carte** (titre en `title-2` `brand-strong`), en-tête de page (titre + actions), titre de section.
- **En-tête de section** (`SectionHeader`) : bloc `brand-tint`, `eyebrow`, titre, une phrase, boutons d'actions,
  illustration optionnelle choisie selon le thème actif.
- **Bandeau d'accueil** (`HomeHero`) : photo en fond, dégradé `hero-scrim`, date, titre, phrase, un bouton.
- **Tuile de chiffre** (`StatTile`), avec barre de progression optionnelle. **Tuile d'action** (`ActionTile`).
- **Badge de statut** : toujours un texte, jamais la couleur seule.
- **Avis** info, avertissement, erreur, succès (icône + texte).
- **Tableau** : en-tête, nombres alignés à droite, `.table-wrap` qui défile seul.
- Divulgation (`details`), `kbd`, **état vide** avec illustration plate SVG (style A, classes `ia-*`).
- **Cibles tactiles** : au moins 40 px de haut pour les boutons et les liens de navigation sous 600 px.

### 5. Coquille et navigation

Maquette de référence : une barre latérale indigo à gauche et, au-dessus de la page, une barre du haut.

```
≥ 960 px (dépliée, par défaut)               ≥ 960 px (repliée)
┌──────────────┬──────────────────────────┐  ┌────┬────────────────────────────────┐
│ ▣ vocab-coach│ [⇤]   [Demo] Langue Thème│  │ ▣  │ [⇥]       [Demo] Langue Thème  │
│ Home         ├──────────────────────────┤  │ ⌂  ├────────────────────────────────┤
│ Today        │                          │  │ ▤  │                                │
│ LIBRARY      │        page              │  │ ▥9 │          page                  │
│ Library   9  │                          │  │ ✎  │                                │
│ PRACTICE     │                          │  │ …  │                                │
│ Writing …    │                          │  │    │                                │
│ ⚙ Settings   │                          │  │ ⚙  │                                │
└──────────────┴──────────────────────────┘  └────┴────────────────────────────────┘

< 960 px                                     < 960 px, menu ouvert
┌────────────────────────────────────────┐  ┌──────────────┬─────────────────────┐
│ [☰ Menu] ▣      [Demo] Langue Thème    │  │ ▣ vocab-coach│░░░░░░░░░░░░░░░░░░░░░│
├────────────────────────────────────────┤  │ Home         │░░ page en dessous ░░│
│                page                    │  │ Today …      │░░░░░░░░░░░░░░░░░░░░░│
└────────────────────────────────────────┘  └──────────────┴─────────────────────┘
```

**Barre latérale** (≥ 960 px) :
- dépliée par défaut (232 px), repliable en rail d'icônes (72 px) ;
- en position repliée, les libellés restent dans le DOM en texte masqué visuellement, avec un `title`, et le
  compteur devient une pastille ;
- le bouton de repli est à gauche de la barre du haut, avec `aria-expanded` et un libellé qui dit l'action
  (« Collapse the menu » / « Expand the menu ») ;
- le choix est mémorisé dans `localStorage` (`vocab-coach.sidebar`), lu et écrit dans un `try/catch`.

**Groupes**, à adapter à la liste réelle des liens et à confirmer dans le plan :
- Home, Today ;
- « Library » : Library ;
- « Practice » : Writing, Speaking, Tracks, Consolidation ;
- « Progress » : Errors, Statistics ;
- puis Settings, seul en bas.

Les titres de groupe sont masqués en position repliée.

**Barre du haut**, toujours présente :
- le bouton de repli (ou « Menu » sous 960 px) ;
- à droite, le badge « Demo data », puis les sélecteurs **Langue** et **Thème**, qui gardent leur rôle actuel ;
- le bandeau du mode dégradé (`AiBanner`) reste sous la barre du haut, visible.

**Sous 960 px** :
- la barre latérale disparaît ;
- le bouton « Menu » ouvre un panneau avec la même navigation dépliée ;
- règles du panneau :
  - `aria-expanded` et `aria-controls` ;
  - Échap le ferme et rend le focus au bouton ;
  - il se ferme au changement de route ;
  - aucun piège de focus inattendu.

**Règles communes** :
- `aria-current="page"` sur le lien actif ;
- routes, cibles et libellés des liens inchangés ;
- plus de barre sur deux lignes en français à 375 px.

### 6. Textes nouveaux autorisés

Clés EN et FR, avec les mêmes clés. Français au vouvoiement (D-119), formulé de façon neutre en genre.
- titres des groupes de navigation ;
- libellés du bouton de repli et du bouton Menu ;
- bandeau d'accueil : date, salutation avec la durée prévue, phrase avec le nombre de révisions et de nouveaux termes ;
- libellés des tuiles de chiffres et des tuiles « Continue » de l'accueil ;
- le mot « Section » de l'`eyebrow`.

Tout autre texte existant est conservé tel quel. Il peut être déplacé : par exemple, les liens « Import a list »,
« Sort new terms (9 to sort) » deviennent des boutons de l'en-tête de section, avec le même libellé.

### 7. Guide de style (développement seulement)

- Une route `/styleguide`, montée **uniquement** quand `import.meta.env.DEV` est vrai. Elle montre :
  - les tokens des deux thèmes ;
  - l'échelle typographique ;
  - les icônes ;
  - chaque composant dans chacun de ses états ;
  - la barre latérale dépliée et repliée ;
  - un graphique ;
  - un avis de chaque sévérité.
- Vérifie après `npm --prefix frontend run build` que ni la route ni son code ne sont dans le bundle (recherche d'une
  chaîne témoin).
- Ses textes peuvent rester en anglais en dur. Note cette exception dans DECISIONS.

### 8. Contraste (test automatisé)

- Une fonction pure `contrast.ts` (luminance relative WCAG 2.x) et un test Vitest. Le test lit les tokens des deux
  thèmes depuis le fichier source et vérifie :
  - `ink`, `ink-muted` et `brand-strong` sur `bg`, `surface`, `surface-sunken` et `brand-tint` : au moins 4,5:1 ;
  - `on-brand` sur `brand`, et `sidebar-ink` sur `sidebar` : au moins 4,5:1 ;
  - `success`, `warning`, `danger` sur leur `-tint`, et `accent` sur `accent-tint` : au moins 4,5:1 ;
  - `border-strong` et `focus-ring` sur `bg` et `surface` : au moins 3:1 ;
  - `chart-1..5` sur `surface` : au moins 3:1.
- Valeurs déjà calculées pour ce prompt, à retrouver par le test : `border-strong` 3,65:1 sur `surface` dans les
  deux thèmes, `accent` 5,16:1 sur `accent-tint` en clair.
- **Vérification par code cassé** : applique-la puis annule-la. Un `ink-muted` trop clair en sombre doit faire
  échouer le test. Cite le test qui échoue dans PROGRESS.

### 9. Graphiques à 375 px

- Aujourd'hui, les étiquettes d'axe mesurent environ 8 px, car le SVG est réduit.
- À 375 px, aucune étiquette d'axe ou de légende ne fait moins de 11 px **rendus**. Mesure-le dans le navigateur avec
  `getBoundingClientRect`.
- Méthode libre : étiquettes HTML hors du SVG, `viewBox` plus étroit sous 600 px, moins de graduations… Pas de mesure
  JS dans jsdom, pas de dépendance.
- On garde « Show the numbers », les trous pour `insufficient`, `role="img"`, et les couleurs `chart-1..5`.

### 10. Passe écran par écran (RV.b)

Dans l'ordre de l'usage quotidien :

1. **Accueil** (maquette `Main.dc.html`) :
   - `HomeHero` avec `home-hero-p6.jpg`, cadrée `right 35%`. Sous 600 px, le dégradé couvre toute la largeur ;
   - trois `StatTile` (révisions dues, nouveaux termes, minutes prévues sur le budget) ;
   - tuiles « Continue » ;
   - carte des avertissements du plan ;
   - l'état du système reste présent, plus bas.

   N'affiche que des données que l'accueil charge déjà (aucun nouvel appel d'API).
2. **Today et la séance** (maquette `Review.dc.html`) : lecteur de révision, découverte, attente, résumé.
   - colonne `reading-max`, sans image ;
   - progression en chiffres et en barre ;
   - consigne lisible d'un coup d'œil ;
   - zone de réponse évidente ;
   - boutons de note 1 à 4 colorés (À revoir `danger`, Difficile `warning`, Bien `success`, Facile `brand`), stables,
     sans saut de mise en page entre la question et le résultat ;
   - indications de touches discrètes en `kbd`.
3. **Pages de section** avec `SectionHeader` et illustration 3D : Library (maquette `Library.dc.html`), Writing,
   Speaking, Errors.
   - Les rangées de liens soulignés sous le titre deviennent des boutons de l'en-tête, avec un seul bouton principal.
   - Tracks, Consolidation et Statistics reçoivent le même en-tête **sans** illustration.
4. **Le reste de la bibliothèque** : page du terme et fiche, import, tri, doublons, paquets, file, enrichissement.
5. **Écriture et correction**, transcriptions, entraînements ciblés, journal d'erreurs (liste, détail, catégories,
   saisie manuelle). Les corrections utilisent `CorrectionMark` : fragment fautif sur `accent-tint` avec soulignement
   ondulé `accent`, puis la correction sur `success-tint`.
6. **L'oral** : shadowing, prise de parole, historiques, prononciation.
7. **Consolidation, parcours, statistiques, réglages**. Les listes vides utilisent `EmptyState` (illustration plate).

Défauts connus à corriger :
- barre du haut sur deux lignes en français ;
- codes de catégorie coupés au milieu d'un mot. Ils doivent se couper aux points, par exemple avec un petit composant
  qui insère `<wbr>` après chaque point ;
- `<fieldset>` dans un `<p>` à l'étape dialogue d'une unité (avertissement React) ;
- tableau d'import à sept colonnes : sous 600 px, une carte par ligne, avec les mêmes contrôles et le même ordre de
  tabulation ;
- étiquettes des graphiques (section 9).

### 11. Règles qui ne bougent pas

- **Rappel actif** : aucune solution dans le DOM avant la tentative. Ne masque jamais une réponse par le CSS. Les
  tests anti-fuite existants restent tels quels.
- **Clavier et couleur** :
  - raccourcis clavier inchangés (D-122) ;
  - ordre de focus logique, focus visible partout ;
  - aucune information portée par la couleur seule.
- **Largeur et zoom** :
  - pas de défilement horizontal de la page à 375 px, en anglais comme en français, sauf dans un `.table-wrap` ;
  - zoom à 200 % à 1280 px sans perte de contenu.
- **Tests** : tous les tests Vitest existants passent.
  - Un test ne peut être modifié que s'il vérifiait une structure que la refonte change (la navigation, par exemple).
    Liste-le dans le plan, avec la raison.
  - Aucun test n'est supprimé.
  - Ajoute des tests pour la barre latérale (repli, mémorisation) et le menu (ouverture, Échap, focus rendu,
    fermeture au changement de route).
- **Données et IA** :
  - ne touche jamais `data/` ni `.env` ;
  - pour les vérifications, utilise une démo dans un `VOCAB_DATA_DIR` temporaire, avec l'ancre d'aujourd'hui ;
  - pour vider une variable, utilise Git Bash (incident M5.c2) ;
  - n'appelle aucune IA réelle.

### 12. Captures

- **Écrans** :
  - l'accueil ;
  - Today ;
  - une carte de révision (consigne, puis résultat) ;
  - une étape de découverte après la supposition ;
  - la bibliothèque ;
  - la page d'un terme avec sa fiche ouverte ;
  - l'aperçu d'import ;
  - une correction d'écriture ;
  - une prise de shadowing avec comparaison ;
  - le journal d'erreurs ;
  - une unité de scénario ;
  - les statistiques ;
  - les réglages ;
  - la barre latérale repliée (1280 px) ;
  - le menu ouvert (375 px).
- **Formats** :
  - 1280×800 en clair et en sombre ;
  - 375×812 en clair, en anglais ;
  - 375×812 en français pour l'accueil, Today, la carte de révision et le menu.
- **Rangement** :
  - hors du dépôt, dans `%TEMP%\vc-rv-shots\before\` et `...\after\` ;
  - noms au format `<écran>-<largeur>-<thème>-<langue>.png` ;
  - un `index.html` qui les montre côte à côte (avant | après). Donne son chemin dans le rapport.
- **Si les captures du navigateur intégré expirent** (fenêtre cachée, vu en M8 et M9) :
  - garde la fenêtre visible ;
  - pour les écrans atteignables par URL, utilise Edge sans interface :
    `msedge --headless=new --window-size=375,812 --screenshot=<fichier> <url>` ;
  - pour les écrans qui demandent une interaction, utilise le navigateur intégré.
- Ne déclare jamais un écran « vérifié visuellement » d'après le DOM seul. Liste ceux que tu n'as pas vus.

## Critères d'acceptation

**Build et dépôt**
- `npm run check` est vert et `npm --prefix frontend run build` passe.
- `git diff --stat <base> -- backend` est vide. `package.json` et les lockfiles sont inchangés.
- Les seuls fichiers binaires ajoutés sont la police, sa licence, la photo P6 et les huit illustrations. Leurs tailles
  sont rapportées.

**Tests**
- Le test de contraste passe dans les deux thèmes, et la vérification par code cassé est faite.
- Tous les tests existants passent. Les tests modifiés sont listés et justifiés. Les tests de la barre latérale et du
  menu sont ajoutés.

**CSS**
- Zéro couleur en dur hors des tokens après RV.b : la commande `rg` et sa sortie figurent dans PROGRESS.
- La taille du CSS avant et après (brute et gzip) est rapportée. Toute hausse de plus de 20 % est justifiée.
- `/styleguide` est absent du build de production.

**Affichage**
- À 375 px, en anglais et en français, en clair et en sombre : `scrollWidth` égal à 375 sur chaque écran de la liste.
- Les étiquettes des graphiques font au moins 11 px rendus.
- La barre du haut tient sur une ligne.
- La barre latérale se replie, se déplie et retient son état. Le menu se pilote au clavier.
- Les captures avant/après sont livrées avec leur `index.html`.

**Scénario manuel du propriétaire** (3 minutes, sans clé), à écrire dans PROGRESS. Préparation :
`demo seed --reset --anchor <aujourd'hui>`, puis `.\start.ps1 -Demo`.
1. Regarder l'accueil (photo, chiffres, tuiles), puis faire une séance de 3 cartes au clavier.
2. Ouvrir la bibliothèque (en-tête illustré, boutons), puis un terme.
3. Ouvrir les statistiques en semaine.
4. Replier puis déplier la barre latérale, puis recharger : l'état est gardé.
5. Basculer en sombre (l'illustration de la bibliothèque change), puis en français, puis réduire à la largeur d'un
   téléphone et ouvrir le menu.
6. Ouvrir `http://127.0.0.1:5173/styleguide`.

## Démarche

1. **Mode plan pour RV.a seulement.** Donne :
   - l'inventaire (section 0) ;
   - la correspondance entre les anciens et les nouveaux tokens ;
   - le tableau des tokens avec les ratios calculés ;
   - la solution de thème sans duplication ;
   - le croquis confirmé de la navigation et ses groupes ;
   - la police (URL, version, taille) ;
   - les tests qui changeront ;
   - les fichiers touchés et les risques.

   Attends la validation du propriétaire.
2. **Implémente par petites étapes.** Lance `npm --prefix frontend run check` après chaque étape et montre la sortie
   réelle.
3. **Fin de RV.a** :
   - captures « après » des écrans de la liste (le système s'applique déjà en partie partout) et du guide de style ;
   - mise à jour de PROGRESS et DECISIONS ;
   - commit, puis rapport ;
   - **arrête-toi**.
4. **RV.b** :
   - nouveau plan : ordre des écrans, défauts traités, estimation par écran, et présence des illustrations ;
   - validation ;
   - implémentation écran par écran, un commit par groupe d'écrans ;
   - captures finales.
5. **En fin de chaque partie** :
   - `docs/PROGRESS.md` : section RV.a ou RV.b (fait / vérifié / reste / limites connues / prochaine étape, scénario
     manuel), et « Current state » ;
   - `docs/DECISIONS.md`, à partir de D-285 : organisation en couches, tokens et thème, police Inter (remplace la
     partie polices de D-007), icônes maison, navigation repliable, images, guide de style, contraste, graphiques,
     exceptions ;
   - `docs/architecture.md` : CSS, points de rupture ;
   - `docs/DESIGN_PLAN.md` : statut « implemented », icônes maison au lieu de Tabler, valeurs corrigées de
     `border-strong` et `accent` ;
   - `CLAUDE.md` : la ligne « UI » renvoie aux tokens et aux classes de base, et interdit les couleurs en dur ;
   - `docs/SPEC.md` : §9 et §8, une seule fois ;
   - commits au format Conventional Commits (`style:`, `refactor:`, `feat(frontend):`, `docs:`), sans pousser.
6. **Termine par un rapport court** :
   - ce qui fonctionne, ce qui ne fonctionne pas encore, comment le tester ;
   - le chemin de l'`index.html` des captures ;
   - les écarts par rapport à ce prompt ;
   - tes propositions non faites (mode concentration en séance, illustrations pour Tracks, Consolidation et
     Statistics, autres).

## Effet sur le prompt M10.a

Le jalon RV passe avant M10.a. Dans le prompt M10.a, deux lignes changent :
- la branche part de la pointe de `feat/rv-visual-redesign` ;
- les décisions partent du premier numéro libre après RV, au lieu de D-285.
