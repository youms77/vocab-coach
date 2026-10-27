# Brief du projet « vocab-coach » (nom de code provisoire)

Ce document a deux parties.

- **Partie A** : instructions pour les conversations du Project Claude dans lequel ce document est placé. Elles servent à rédiger, jalon par jalon, les sous-prompts à coller dans Claude Code.
- **Partie B** : la spécification complète du produit. Elle sera aussi copiée (traduite en anglais) dans le dépôt sous `docs/SPEC.md`, pour que Claude Code la relise à chaque session.

Les décisions de la partie B sont prises. Une conversation du Project ne les modifie pas en silence : si une décision lui paraît mauvaise ou si un jalon l'oblige à s'en écarter, elle le signale, explique pourquoi, propose la modification et attend mon accord.

---

## PARTIE A — Comment utiliser ce Project

### A.1 Ton rôle dans chaque conversation

Dans chaque nouvelle conversation de ce Project, je te demanderai le sous-prompt d'un jalon (« écris le sous-prompt du jalon M3 »). Ton travail :

1. Vérifier que tu as l'état réel du dépôt. Si je ne t'ai pas collé le contenu à jour de `docs/PROGRESS.md` (et, s'il existe, `docs/DECISIONS.md`), demande-le-moi avant d'écrire, sauf pour le jalon M0.
2. Relire la section du jalon dans la feuille de route (B.9) et les modules de la spécification qu'il touche.
3. Signaler, en tête de réponse, les ambiguïtés ou dépendances non résolues de ce jalon (3 à 5 points au plus), avec la valeur par défaut que tu retiens si je ne réponds pas.
4. Rédiger le sous-prompt selon le gabarit A.3, dans un seul bloc de code (quatre apostrophes inversées s'il contient lui-même du code).
5. Terminer par trois lignes : modèle conseillé dans Claude Code, risques principaux du jalon, ce que je dois vérifier à la main après la session.

Un sous-prompt ne recopie pas toute la spécification : Claude Code la lira dans `docs/SPEC.md`. Il précise ce qui est propre au jalon : périmètre exact, détails d'implémentation, critères d'acceptation, pièges.

Si un jalon est trop gros pour une session Claude Code (plus d'environ 15 fichiers significatifs à créer ou modifier, ou plusieurs sous-systèmes indépendants), découpe-le en Mx.a, Mx.b et dis-le.

### A.2 Ce que tu ne fais pas

- Tu ne rédiges pas le code de l'application dans ce chat : c'est le travail de Claude Code.
- Tu n'ajoutes pas de fonctionnalité absente de la partie B sans me la proposer explicitement.
- Tu n'inventes pas de version de bibliothèque, de quota ou de prix : quand c'est volatil, le sous-prompt demande à Claude Code de vérifier (documentation officielle, `pip index versions`, `npm view`).

### A.3 Gabarit d'un sous-prompt Claude Code

```
# Jalon Mx — [titre]

## Contexte
Lis d'abord CLAUDE.md, docs/SPEC.md (sections : [liste]) et docs/PROGRESS.md.
État attendu au départ : [ce qui doit déjà exister ; si ce n'est pas le cas, arrête-toi et dis-le].

## Objectif
[1 à 3 phrases : ce qui marche à la fin de la session, du point de vue de l'utilisateur.]

## Périmètre
Inclus : [...]
Exclu (jalons ultérieurs) : [...]

## Spécifications détaillées
[Modèles, endpoints, écrans, règles métier, formats, cas limites, avec le pourquoi des choix non évidents.]

## Critères d'acceptation
- [Tests automatisés qui doivent passer]
- [Scénario manuel que je pourrai rejouer en 2 minutes]

## Démarche
1. Commence en mode plan : propose ton plan (fichiers touchés, migrations, risques) et attends ma validation.
2. Implémente par petites étapes ; lance les tests et le linter après chaque étape et montre la sortie réelle.
3. Ne modifie pas le schéma de données hors de ce qui est prévu ici sans me le signaler.
4. En fin de session : mets à jour docs/PROGRESS.md (fait / reste / bugs connus / prochaine étape) et docs/DECISIONS.md (toute décision technique prise et sa raison), puis fais un commit au format Conventional Commits.
5. Termine par un rapport court : ce qui fonctionne, ce qui ne fonctionne pas encore, comment le tester.
```

### A.4 Relais entre sessions

La mémoire du projet vit dans le dépôt, pas dans les conversations : `CLAUDE.md` (règles permanentes pour Claude Code), `docs/SPEC.md` (spécification), `docs/PROGRESS.md` (état), `docs/DECISIONS.md` (journal des décisions). Après chaque session Claude Code, je copie `PROGRESS.md` dans la conversation suivante de ce Project.

---

## PARTIE B — Spécification du produit

### B.1 Utilisateur et contexte

- Étudiant en Master 2 (économie, statistique, spécialisation data science), francophone, au Cameroun ; entrée prochaine dans le monde professionnel (entretiens, présentations en anglais).
- Niveau estimé : speaking A2–B1, writing B2, reading B2, listening B2–C1. Niveau global B1.
- Objectif n°1 : parler couramment et spontanément, avec une prononciation intelligible (accent cible : américain). Objectif n°2 : maîtriser l'anglais académique et le vocabulaire de son domaine pour les exposés et les entretiens.
- Temps disponible : 30 à 60 minutes par jour.
- Erreurs récurrentes connues : prépositions (« in campus » au lieu de « on campus », « in university » au lieu de « at university », usages de « by », « for », « at », « on », « in ») ; temps verbaux (past simple employé à la place du present perfect).
- Machine : Windows 11, Python 3.13 (à confirmer), Git, compte GitHub, Claude Code connecté à un abonnement Claude Pro.
- Usage : outil personnel, en local sur un ordinateur portable. Code publié dans un dépôt GitHub public, pour la sauvegarde et le partage éventuel avec des camarades. Qualité attendue : celle d'un projet qu'un autre étudiant pourrait installer et utiliser.

### B.2 Vision

Une application qui transforme les mots et expressions que l'utilisateur juge importants (rencontrés dans ses lectures, ses cours ou la vie courante) en vocabulaire **actif** : reconnu, rappelé, bien prononcé et réutilisé spontanément à l'oral et à l'écrit. Elle suit aussi les erreurs de l'utilisateur, les catégorise, mesure leur fréquence et organise le travail sur les plus fréquentes.

Ce qui la distingue d'Anki ou Quizlet : l'utilisateur apporte un mot et un contexte, pas une fiche ; l'application construit la fiche d'usage, la séance de découverte, les exercices de réemploi, le travail oral et le suivi statistique des erreurs.

### B.3 Principes pédagogiques (à respecter dans toutes les fonctionnalités)

1. **Les quatre volets de Paul Nation** : compréhension de contenus (input), production orientée sens (output), étude ciblée de la langue, développement de la fluidité. L'étude délibérée des mots ne remplace pas l'exposition et la production ; l'application doit pousser vers la production.
2. **Rappel actif avant révélation** : l'utilisateur tente toujours de répondre avant de voir la solution. Aucune réponse affichée avant la tentative.
3. **Répétition espacée** par l'algorithme FSRS.
4. **Élaboration sémantique et contexte** : chaque unité est apprise dans des phrases réelles, avec ses collocations, son registre, ses pièges.
5. **L'unité d'apprentissage n'est pas seulement le mot** : mots, collocations (« to draw a conclusion »), expressions (« it is worth noting that »), formules orales.
6. **Plusieurs dimensions de connaissance** : reconnaissance, compréhension en contexte, rappel FR/définition → EN, prononciation, emploi dans une phrase, collocations, transfert dans un nouveau contexte.
7. **Retour correctif utile** : une correction donne la forme fautive, la forme correcte, une ou deux alternatives naturelles, la règle en une phrase, et alimente le journal d'erreurs.
8. **Immersion** : interface en anglais par défaut ; explications en anglais simple (niveau B1–B2), avec traduction française disponible à la demande.

### B.4 Périmètre fonctionnel complet

L'architecture couvre dès le départ tous les modules ci-dessous ; ils sont construits dans l'ordre de la feuille de route (B.9). Aucun module ultérieur ne doit exiger de refaire le schéma de données ou le tableau de bord : c'est pour cela que le modèle de données complet (B.6) et le journal d'événements sont posés au jalon M1.

#### Module A — Bibliothèque de vocabulaire et import

- **Import Markdown** d'une liste de termes, avec aperçu et validation avant enregistrement. Format souple :

  ```markdown
  ---
  deck: Causal inference reading
  domain: econometrics
  source: "Angrist & Pischke, Mostly Harmless Econometrics, ch. 3"
  context: "Reading for my M2 report on policy evaluation"
  deadline: 2026-11-20      # facultatif (exposé à préparer)
  ---
  - heteroskedasticity
  - to account for | We account for regional fixed effects in all specifications.
  - shed light on
  ```

  Une ligne = un terme, suivi facultativement de `|` et de la phrase d'origine. L'en-tête YAML est facultatif ; tout champ manquant reste vide. Le parseur tolère les puces `-`, `*`, numérotées, et les lignes vides ; il signale les lignes ambiguës au lieu d'échouer.
- **Saisie rapide** d'un terme (terme + contexte facultatif) depuis l'interface.
- **Fiche d'usage générée par l'IA** (« enrichissement ») : ce n'est pas une entrée de dictionnaire, c'est un guide d'emploi. Contenu : sens dans le contexte fourni (et autres sens fréquents), définition en anglais simple, traduction française, catégorie grammaticale, registre (académique, neutre, oral, familier), quand et comment l'utiliser, collocations et constructions fréquentes, 3 à 5 exemples variés (dont au moins un académique dans le domaine du deck et un oral), famille de mots, prononciation (API américaine et accentuation), erreurs typiques d'un francophone et faux amis, mots proches à ne pas confondre. Les phrases servant aux exercices (textes à trous, consignes de production) sont générées en même temps et stockées.
- **Relecture** : l'utilisateur peut modifier toute fiche ; une fiche modifiée est marquée comme éditée et n'est jamais régénérée sans son accord.
- **Extension de liste** : à partir des termes d'un deck et de son contexte (titre, domaine, objectif), l'IA propose 10 à 30 termes liés (techniques, académiques généraux, formules orales utiles pour présenter ce sujet). L'utilisateur trie chaque suggestion : « je connais » / « pas sûr » / « à apprendre ». Seuls les termes retenus entrent dans le deck.
- **Tri d'entrée** : même triage rapide possible pour une liste importée, pour ne pas dépenser de temps sur des mots déjà connus.
- **Doublons** : détection à l'import (forme normalisée, lemme) avec proposition de fusion ou de rattachement à un nouveau deck.
- Recherche, filtres (deck, domaine, source, type, statut de maîtrise), édition, suppression, archivage.

#### Module B — Découverte d'un terme (première rencontre)

Méthode progressive, une seule fois par terme :

1. Affichage d'une phrase contenant le terme (la phrase d'origine si elle existe, sinon un exemple généré).
2. L'utilisateur tape ce qu'il pense que le terme signifie (en anglais ou en français).
3. Révélation de la fiche d'usage, avec écoute de la prononciation ; comparaison avec sa supposition.
4. Mini-série d'exercices immédiats : rappel FR → EN, texte à trous, répétition orale de la phrase (écoute puis enregistrement facultatif), une phrase personnelle avec le terme (corrigée par l'IA si disponible).
5. Le terme entre ensuite dans la répétition espacée.

#### Module C — Révisions espacées

- **Algorithme FSRS** via une bibliothèque Python maintenue (par exemple le paquet `fsrs` de l'organisation open-spaced-repetition ; version à vérifier). Rétention cible par défaut : 0,90, réglable. L'accès à l'algorithme passe par une interface interne pour pouvoir le remplacer.
- **Deux cartes FSRS par terme** pour contenir la charge : une carte **réceptive** (anglais → sens) et une carte **productive** (sens ou définition → anglais). Le type d'exercice varie selon la maturité de la carte :
  - réceptive : reconnaissance en phrase, compréhension orale (écouter la phrase, choisir ou taper le sens) ;
  - productive, carte jeune : rappel FR → EN tapé, texte à trous ;
  - productive, carte mûre : production d'une phrase dans une situation donnée, réponse orale.
- **Notation** : correction automatique quand c'est possible (comparaison tolérante aux fautes de frappe pour les réponses tapées ; correction IA pour les productions), convertie en note FSRS (Again / Hard / Good / Easy) ; l'utilisateur peut toujours corriger la note proposée. Pour les cartes à auto-évaluation, quatre boutons.
- Une réponse fausse sur une confusion lexicale (mot proche, faux ami, mauvaise collocation) crée aussi un événement d'erreur (module E).

#### Module D — Planification quotidienne et file d'attente

- **Séance du jour** dans cet ordre : révisions dues d'abord, puis nouveaux termes dans la limite du quota journalier, puis un exercice ciblé sur la catégorie d'erreurs la plus fréquente, puis, si disponible, une tâche de consolidation.
- **Règle de priorité** : les révisions en cours passent toujours avant une nouvelle liste. Une nouvelle liste entre dans la **file d'attente** des decks (statut `queued`) ; elle est activée quand le quota de nouveaux termes le permet.
- L'utilisateur peut réordonner la file à la main. Un deck avec échéance (exposé à préparer) est prioritaire et l'application calcule le nombre de nouveaux termes par jour nécessaire pour finir la découverte avant l'échéance, en signalant si c'est irréaliste.
- **Budget de temps** : réglable (défaut : 45 min/jour). Quota de nouveaux termes par défaut : 12 par jour, réglable. L'application estime la durée de la séance à partir des temps de réponse passés et réduit automatiquement les nouveaux termes quand la charge de révisions prévue dépasse le budget.
- Mettre un deck en pause, le reprendre, le terminer.

#### Module E — Journal d'erreurs et entraînement ciblé

- **Sources d'erreurs** : exercices d'écriture, exercices oraux (transcrits), révisions, transcriptions de conversations collées par l'utilisateur (par exemple une session vocale ChatGPT), saisie manuelle.
- **Événement d'erreur** : texte d'origine, forme fautive, correction, 1 ou 2 alternatives naturelles, catégorie, sous-catégorie, explication courte, source, date, terme lié éventuel.
- **Taxonomie initiale** (extensible ; l'IA choisit dans cette liste et peut proposer une nouvelle sous-catégorie que l'utilisateur valide) :
  - grammar.preposition : time, place, movement, dependent preposition (« depend on »), fixed expression (« at university », « on campus »), by/for/since ;
  - grammar.tense : past simple vs present perfect, present simple vs continuous, future forms, sequence of tenses ;
  - grammar.article, grammar.agreement (3e personne -s, accord sujet-verbe), grammar.word_order, grammar.question_form, grammar.countability, grammar.modal, grammar.other ;
  - lexis.false_friend (« actually », « eventually »…), lexis.wrong_word, lexis.collocation, lexis.word_form ;
  - register (trop familier, trop formel) ; discourse (connecteurs, cohésion) ; spelling ;
  - pronunciation : sound, word_stress, intelligibility (module F).
- **Exercice d'écriture libre** : l'utilisateur écrit un paragraphe sur un sujet proposé (ou le sien) ; correction IA ligne par ligne, version corrigée, version plus naturelle, liste d'erreurs enregistrées.
- **Analyse de transcription** : coller un texte (ses propres phrases) ; extraction des erreurs de l'utilisateur uniquement, pas de celles de l'interlocuteur.
- **Entraînement ciblé** : exercices générés pour une catégorie précise (par exemple 10 phrases à trous sur at/on/in avec lieux), avec explication de la règle ; résultats eux aussi enregistrés.
- Les règles et paires piégeuses que l'utilisateur rate souvent peuvent devenir des cartes FSRS (« at university »).

#### Module F — Oral

- **Écoute** : synthèse vocale de chaque terme et de chaque phrase, voix anglaise américaine, vitesse normale et ralentie.
- **Shadowing** : écouter une phrase, l'enregistrer, réécouter les deux versions l'une après l'autre.
- **Transcription** de l'enregistrement par reconnaissance vocale ; comparaison mot à mot avec la phrase cible. Les mots non reconnus sont signalés comme problèmes d'intelligibilité possibles, avec la mention que la reconnaissance vocale n'est pas un juge de prononciation.
- **Évaluation fine de la prononciation** (score par mot et par phonème) : module optionnel, désactivé par défaut, branché sur un service spécialisé (voir B.7).
- **Réponses orales** dans les révisions (cartes productives mûres) et **prise de parole libre** : un sujet, 1 à 2 minutes d'enregistrement, transcription, correction IA (grammaire, lexique, structure, connecteurs), erreurs enregistrées dans le module E, réécoute.
- La conversation vocale en temps réel avec un tuteur reste hors de l'application : l'utilisateur continue avec ChatGPT en mode vocal et colle ensuite la transcription dans le module E.

#### Module G — Consolidation (exposés et discours)

- Quand une part suffisante d'un deck est consolidée (défaut : 80 % des cartes productives avec une stabilité d'au moins 7 jours), l'application propose une tâche : un sujet d'exposé, de discours ou de réponse d'entretien qui impose d'utiliser 8 à 15 termes du deck, avec une structure suggérée.
- Mode écrit (l'utilisateur rédige, correction IA) et mode oral (l'utilisateur enregistre, transcription puis correction). L'application vérifie quels termes cibles ont été employés, et correctement.
- Un terme employé correctement dans une production libre passe au statut « actif » ; un emploi fautif crée une erreur et renforce sa carte.
- Export du sujet et de la liste de termes pour s'entraîner ensuite avec ChatGPT en vocal.

#### Module H — Parcours d'anglais général

- Parcours intégrés, utilisables quand l'utilisateur n'a pas de liste personnelle en cours :
  1. **General everyday English** : vocabulaire fréquent, à partir de la New General Service List (NGSL) ;
  2. **Academic English** : vocabulaire académique général, à partir de la New Academic Word List (NAWL) ;
  3. **Speaking scenarios** : unités thématiques orientées oral, par exemple job interview, presenting data and results, meetings and discussions, small talk and networking, agreeing and disagreeing in a debate, describing a project, everyday situations (campus, transport, shopping, health), phone and video calls.
- Chaque unité de scénario contient : des formules orales et collocations clés, un dialogue modèle à écouter, des exercices de shadowing et une prise de parole finale. Le contenu des unités est généré une fois par l'IA à partir d'un syllabus fixe versionné dans le dépôt (`content/curriculum.yaml`), puis stocké et modifiable.
- Les termes des parcours passent par le même tri d'entrée (« je connais / pas sûr / à apprendre ») avant d'entrer dans la file.
- Licence des listes NGSL/NAWL à vérifier avant de les inclure dans le dépôt public ; sinon, script de téléchargement documenté.

#### Module I — Statistiques et tableau de bord

Les statistiques sont une fonctionnalité centrale (l'utilisateur est statisticien). Toutes sont calculées à partir du journal d'événements et des journaux de révision, jamais à partir de compteurs ad hoc.

- **Erreurs** : fréquence par catégorie et sous-catégorie, **normalisée** (erreurs pour 100 mots produits, pour éviter qu'un jour de forte production ressemble à une régression), évolution dans le temps, top 5 des erreurs récurrentes avec exemples, part des erreurs « corrigées » (catégories en baisse durable).
- **Mémorisation** : courbe de rétention observée vs rétention cible, taux de réussite par type d'exercice, oublis (lapses), distribution de la stabilité, temps (et nombre de révisions) avant consolidation d'un terme.
- **Progression** : entonnoir des statuts (en attente → en découverte → en apprentissage → consolidé → actif), vocabulaire actif, avancement des decks et des parcours, prévision de charge des 14 prochains jours.
- **Pratique** : temps d'étude quotidien, régularité, mots produits à l'écrit et à l'oral, minutes d'oral enregistrées.
- **IA** : appels par fournisseur, erreurs et quotas atteints.
- **Export CSV** de toutes les tables d'événements, pour analyse dans pandas.

#### Module J — Réglages, données, internationalisation

- Réglages : budget de temps, quota de nouveaux termes, rétention cible, fournisseurs d'IA et clés, voix, vitesse audio, langue de l'interface.
- **Interface en anglais par défaut**, avec bascule anglais/français (toutes les chaînes passent par l'internationalisation dès le premier écran).
- **Sauvegarde** : export/import complet (JSON + fichiers audio en archive zip) et option de copie automatique vers un dossier choisi (par exemple un dossier synchronisé OneDrive ou Google Drive). Les données personnelles ne vont **jamais** dans le dépôt public.

### B.5 Architecture

| Couche | Choix | Pourquoi |
|---|---|---|
| Frontend | React + TypeScript + Vite ; React Router ; TanStack Query ; bibliothèque de graphiques (Recharts ou équivalent) ; react-i18next ; Vitest | Choix de l'utilisateur ; interface riche (cartes, audio, enregistrements, tableau de bord) ; partage possible plus tard |
| Backend | Python + FastAPI ; Pydantic v2 ; SQLAlchemy 2 ; Alembic ; pytest ; ruff | L'utilisateur maîtrise Python ; SDK d'IA et bibliothèque FSRS en Python ; calculs statistiques avec pandas |
| Base de données | SQLite (fichier local dans `data/`, ignoré par Git) | Application locale mono-utilisateur, aucune installation de serveur ; migrations Alembic pour faire évoluer le schéma sans tout casser |
| Audio | Fichiers dans `data/audio/`, ignorés par Git | Les enregistrements sont personnels |
| Environnement Python | `uv` (ou `venv` + `pip` si `uv` pose problème sous Windows) | Installation rapide et reproductible |
| Lancement | Une commande (`start.ps1` ou script npm) qui lance backend et frontend en développement ; en mode « utilisation », le backend sert le frontend compilé sur un seul port | L'utilisateur doit pouvoir réviser sans ouvrir deux terminaux |
| Qualité | Tests unitaires du domaine (FSRS, planification, parseur Markdown, statistiques), tests d'API, linters ; GitHub Actions pour lancer tests et linters à chaque push | Dépôt public, projet qui doit tenir dans la durée |

Organisation du code :

```
backend/app/
  api/            # routes FastAPI, une par module
  domain/         # logique métier pure, testable sans base ni réseau (srs, scheduler, import, errors, stats)
  db/             # modèles SQLAlchemy, migrations
  ai/             # passerelle IA : fournisseurs, prompts versionnés, schémas de sortie
  speech/         # transcription, évaluation de prononciation (optionnelle)
frontend/src/
  features/       # un dossier par module (library, discovery, review, planner, errors, speaking, consolidation, curriculum, dashboard, settings)
  components/ i18n/ api/
content/          # syllabus des parcours, listes de mots (si licence compatible)
docs/             # SPEC.md, PROGRESS.md, DECISIONS.md, architecture.md
```

Règle structurante : chaque module écrit des **événements** dans un journal commun (`event_log`) en plus de ses tables propres. Le tableau de bord lit ce journal et les journaux de révision ; ajouter un module revient à ajouter des types d'événements, sans refaire le tableau de bord.

### B.6 Modèle de données (posé intégralement au jalon M1)

Entités principales (noms indicatifs, à affiner par Claude Code en gardant cette couverture) :

- `source` : titre, auteur, domaine, contexte, URL ou référence, date.
- `deck` : nom, domaine, type (`custom` | `curriculum` | `error_drill`), source, échéance, priorité, statut (`queued` | `active` | `paused` | `done`), position dans la file.
- `lexical_item` : terme, forme normalisée, type (`word` | `collocation` | `phrase` | `spoken_formula`), catégorie grammaticale, deck, phrase d'origine, statut (`draft` | `triage` | `queued` | `discovering` | `learning` | `consolidated` | `active` | `known` | `archived`), dates.
- `enrichment` : terme, contenu structuré (JSON validé), fournisseur, modèle, version du prompt, édité par l'utilisateur (booléen), date.
- `exercise_template` : terme, type d'exercice, contenu (phrase à trous, consigne, réponse attendue, variantes acceptées).
- `card` : terme, sens (`receptive` | `productive`), état FSRS (stabilité, difficulté, échéance, état, répétitions, oublis, dernière révision).
- `review_log` : carte, date, type d'exercice, réponse donnée, note automatique, note finale, temps de réponse.
- `production_attempt` : type (`writing` | `speaking` | `consolidation` | `transcript_analysis` | `drill`), consigne, texte ou transcription, chemin audio, termes cibles, nombre de mots, retour IA (JSON), date.
- `error_category` : code, parent, libellé, description, exemples (table de taxonomie, initialisée au départ).
- `error_event` : tentative ou révision d'origine, texte fautif, correction, alternatives, catégorie, explication, terme lié, source, date.
- `pronunciation_result` : tentative, cible, transcription, mots non reconnus, scores éventuels (module optionnel).
- `consolidation_task` : deck, sujet, structure proposée, termes cibles, statut, tentatives liées.
- `curriculum_track` et `curriculum_unit` : parcours, unités, contenu généré, progression.
- `study_session` : début, fin, plan prévu, réalisé.
- `event_log` : date, type d'événement, entité, charge utile JSON (journal commun pour les statistiques).
- `ai_call_log` : date, fournisseur, modèle, tâche, jetons, durée, succès ou erreur.
- `setting` : clé, valeur.

### B.7 Stratégie IA

**Contrainte** : gratuit ou presque. L'abonnement Claude Pro sert à construire l'application, pas à la faire tourner : l'application ne doit pas dépendre d'une API payante.

**Passerelle d'IA** : une interface unique (`generate_json(task, inputs, schema)` et `transcribe(audio)`) avec plusieurs fournisseurs interchangeables configurés dans `.env` :

| Rôle | Fournisseur par défaut | Remarques |
|---|---|---|
| Texte principal (enrichissement, corrections, génération d'exercices) | API Gemini, offre gratuite, modèle Flash ou Flash-Lite (nom exact à vérifier dans la documentation au moment du jalon) | Offre gratuite limitée en requêtes par minute et par jour ; les données envoyées sur l'offre gratuite peuvent servir à améliorer les modèles : ne rien envoyer de confidentiel. Disponibilité de l'offre gratuite au Cameroun à vérifier |
| Texte, secours | Groq (modèles ouverts, dont Llama), API compatible OpenAI, offre gratuite sans carte bancaire | Bascule automatique si le fournisseur principal renvoie une erreur de quota |
| Transcription vocale | Groq, modèle Whisper (offre gratuite) | Option locale : faster-whisper sur processeur, pour les clips courts |
| Synthèse vocale | Synthèse vocale du navigateur (Web Speech API), voix en-US de Windows | Gratuite et hors ligne |
| Évaluation de prononciation (optionnelle) | Azure AI Speech, offre gratuite F0 (environ 5 h d'audio par mois, inclut l'évaluation de prononciation) | Désactivée par défaut ; nécessite un compte Azure |
| Local (optionnel) | Ollama (API compatible OpenAI) | Pour travailler hors ligne si la machine le permet |

Le point d'accès compatible OpenAI permet d'ajouter d'autres fournisseurs (OpenRouter, API Llama de Meta si elle devient accessible) sans changer le code métier.

**Règles d'économie** (pour rester dans les quotas gratuits) :

- Une fiche d'usage et ses exercices sont générés **une fois** par terme, puis stockés. Les révisions ordinaires n'appellent pas l'IA.
- L'IA n'est appelée en direct que pour corriger une production libre (phrase, paragraphe, prise de parole) et pour générer une extension de liste, une tâche de consolidation ou une unité de parcours.
- Regrouper plusieurs termes dans un même appel d'enrichissement quand c'est possible (lots de 5 à 10).
- File d'attente avec reprise et attente exponentielle en cas d'erreur 429 ; journal `ai_call_log` ; compteur journalier visible dans les réglages.
- Ordre de grandeur attendu : quelques dizaines d'appels par jour.

**Fiabilité** :

- Toutes les sorties de l'IA sont du JSON validé par un schéma Pydantic ; en cas d'échec, une nouvelle tentative avec le message d'erreur, puis un statut « à compléter » sans bloquer l'utilisateur.
- Prompts versionnés dans `backend/app/ai/prompts/` (fichiers texte, avec numéro de version stocké dans chaque résultat).
- Les prompts de correction demandent de ne relever que les erreurs réelles, de ne pas réécrire le style quand la phrase est correcte, d'indiquer quand une formulation est correcte mais peu naturelle, et de classer chaque erreur dans la taxonomie.
- **Mode dégradé** : sans clé ou sans réseau, l'application reste utilisable : saisie manuelle des fiches, révisions, auto-évaluation, journal d'erreurs manuel, statistiques.

**Sécurité** : clés dans `.env` (jamais commité), `.env.example` documenté ; la clé n'est jamais envoyée au frontend ; le backend n'écoute que sur `127.0.0.1`.

### B.8 Conventions

- Langue : code, commentaires, messages de commit, README et documentation du dépôt en anglais. Interface en anglais, traduction française via i18n.
- README en anglais : présentation, captures d'écran, installation sous Windows (et notes pour macOS/Linux), configuration des clés gratuites pas à pas, utilisation quotidienne, sauvegarde, architecture, licence.
- Licence : MIT (sauf contrainte d'une liste de mots incluse).
- Dépôt public : `.gitignore` couvre `data/`, `.env`, exports et audio. Un jeu de données de démonstration fictif (quelques decks et erreurs inventés) permet de tester l'application sans données personnelles.
- Conventional Commits ; une branche par jalon fusionnée dans `main` quand les tests passent.
- Accessibilité de base et raccourcis clavier pour les révisions (révéler, noter 1 à 4, rejouer l'audio).
- Interface sobre et lisible, mode sombre ; priorité à la vitesse d'usage quotidienne plutôt qu'à la décoration.

### B.9 Feuille de route

Chaque jalon laisse une application qui démarre et dont les tests passent. Les critères ci-dessous sont des minimums.

| Jalon | Contenu | Critères d'acceptation principaux |
|---|---|---|
| **M0 — Socle** | Vérification de l'environnement (Python, Node.js LTS, Git, uv) avec instructions d'installation si quelque chose manque ; dépôt GitHub public ; monorepo backend/frontend ; `CLAUDE.md` ; `docs/SPEC.md` (traduction anglaise de la partie B de ce brief) ; `PROGRESS.md`, `DECISIONS.md` ; lancement en une commande ; i18n en place ; écran d'accueil vide ; CI GitHub Actions | `start.ps1` ouvre l'application ; tests et linters verts en local et en CI ; aucun fichier sensible commité |
| **M1 — Modèle de données et domaine** | Schéma complet (B.6) avec migrations ; taxonomie d'erreurs initialisée ; service FSRS derrière une interface ; planificateur de séance et file d'attente (module D, logique seulement) ; journal d'événements ; données de démonstration | Tests unitaires : planificateur (révisions avant nouveaux, quota, échéance, budget), FSRS (notation → échéance), file d'attente ; base créée de zéro par les migrations |
| **M2 — Passerelle IA** | Fournisseurs Gemini, Groq, Ollama ; schémas de sortie ; prompts versionnés ; reprise et bascule ; journal d'appels ; mode dégradé ; page de réglages pour les clés et un bouton « tester la connexion » | Tests avec faux fournisseur ; un appel réel de test réussi avec la clé de l'utilisateur ; erreur 429 simulée → bascule |
| **M3 — Bibliothèque et import** | Module A complet : import Markdown avec aperçu, saisie rapide, enrichissement par lots, relecture et édition, tri d'entrée, extension de liste, doublons, recherche et filtres | Import d'un fichier exemple avec en-tête et sans en-tête ; lignes ambiguës signalées ; fiche éditée jamais écrasée |
| **M4 — Découverte et révisions** | Modules B et C ; séance du jour (module D côté interface) ; synthèse vocale ; raccourcis clavier | Un terme importé passe par la découverte puis apparaît en révision à la bonne date ; notation automatique tolérante aux fautes de frappe ; note modifiable |
| **M5 — Erreurs et écriture** | Module E complet : écriture libre corrigée, analyse de transcription collée, saisie manuelle, entraînement ciblé, cartes issues d'erreurs | Paragraphe test contenant « in campus » et un past simple fautif → deux erreurs classées dans les bonnes sous-catégories |
| **M6 — Oral** | Module F : enregistrement, transcription Groq, shadowing, comparaison mot à mot, réponses orales en révision, prise de parole libre corrigée ; branchement optionnel Azure | Enregistrement → transcription → correction → erreurs enregistrées ; fonctionne sans Azure |
| **M7 — Consolidation** | Module G : déclenchement, sujets, modes écrit et oral, détection d'emploi des termes cibles, statut « actif » | Deck de démonstration consolidé → tâche proposée → production → statuts mis à jour |
| **M8 — Parcours d'anglais général** | Module H : syllabus, import des listes (selon licence), unités de scénarios générées et stockées | Un parcours démarrable de bout en bout ; tri d'entrée appliqué |
| **M9 — Tableau de bord** | Module I complet ; export CSV | Indicateurs calculés sur les données de démonstration, vérifiés par des tests sur des cas construits à la main (taux normalisés, rétention) |
| **M10 — Finitions** | Traduction française complète ; sauvegarde et restauration ; README avec captures ; mode « utilisation » sur un seul port ; revue de sécurité et de performance | Restauration d'une sauvegarde sur une base vide ; installation de zéro en suivant le README |

Le tableau de bord vient tard dans l'ordre de construction, mais les événements qu'il exploite sont enregistrés dès M1 : quand il arrive, l'historique existe déjà.

### B.10 Hors périmètre (pour cette version)

- Comptes utilisateurs, serveur en ligne, synchronisation multi-appareils, application mobile.
- Conversation vocale en temps réel avec un tuteur IA (ChatGPT vocal reste l'outil pour cela).
- Analyse automatique de PDF et extraction de vocabulaire d'un article complet (l'utilisateur fournit sa liste ; on pourra l'ajouter plus tard en réutilisant le module A).
- Gamification élaborée (badges, classements) : une simple série de jours suffit.

### B.11 Hypothèses à vérifier pendant le développement

- Version exacte de Python installée (3.13 attendu) et présence de Node.js (non confirmée).
- Noms des modèles gratuits et quotas actuels de Gemini et de Groq ; disponibilité de l'offre gratuite Gemini depuis le Cameroun.
- Version et API de la bibliothèque `fsrs`.
- Licence des listes NGSL/NAWL.
- Qualité des voix en-US disponibles dans Windows 11 et dans le navigateur utilisé.
- Création d'un compte Azure (moyen de paiement éventuellement exigé à l'inscription) si le module de prononciation est activé.
