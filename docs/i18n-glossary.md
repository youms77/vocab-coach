# French glossary of the interface

The wording of `frontend/src/i18n/locales/fr.json`. English is the reference; French uses **vous**
everywhere (D-119). Learning content (terms, example sentences, sentences to repeat, corrected texts,
dialogues) stays in English: that is the point of the application.

Typography (tested in `locales.test.ts`): a no-break space (U+00A0) before `: ; ! ?`, inside `« »` and
before a unit (`5 s`, `10 Mo`, `12 %`); the typographic apostrophe `’` only; `…` instead of three dots.
Numbers, dates, percentages and plurals come from `Intl` and i18next (`src/i18n/format.ts`), never
from the text: `2 983`, `12,5 %`, `27 octobre 2026`, "0 terme" (0 is singular in French).

| English | French | Why | Where it appears |
|---|---|---|---|
| deck | paquet | The word the owner chose (D-119). "Deck" is anglicised and unclear to a French reader. | Queue, library filters, statistics "Paquets", plan warnings |
| deck queue | file des paquets | "File" is the waiting line of decks that feed new terms. | Queue page |
| term | terme | Neutral for a word, a collocation or a phrase. | Everywhere |
| card | carte | A review card (FSRS), one per direction. | Review, statistics |
| review | révision | The act of recalling a card. "Revue" would mean a magazine or an inspection. | Navigation of the session, home tiles, statistics |
| reviews due | révisions dues | A review that is due today. | Home tiles |
| usage sheet | fiche d’usage | The AI sheet that shows how a term is used. | Library, review summary, enrichment |
| exercises | exercices | The practice items of a sheet. | Sheet page |
| targeted drill | exercice ciblé | A drill is an exercise aimed at one error category. | Drills page, error log source |
| triage | tri | "To sort" = "à trier": the choice between learn / not sure / known. | Triage page, library status "À trier" |
| discovery | découverte | The first meeting with a new term, before its cards exist. | Session, library status "En découverte" |
| shadowing | shadowing | Established technique name, no French equivalent in use. Kept in English, in the interface too. | Speaking, statistics |
| free speaking | prise de parole libre | Speaking on a topic without a model. Short title: "Oral". | Speaking page, navigation |
| writing | écriture | The writing exercise. | Navigation, error log source |
| consolidation | consolidation | Same word in French. | Navigation, home, statistics |
| consolidation task | tâche de consolidation | A talk that uses the terms of one deck. | Consolidation pages |
| track | parcours | A general English track (word list or scenarios). | Navigation, statistics |
| unit | unité | One step of a track. | Tracks |
| study day | jour d’étude | A calendar day that can start at a chosen hour (D-266); never the browser clock. | Settings, plan, statistics |
| session | séance | One sitting of study. "Session" is used for a sign-in in French. | Today, summary |
| plan | plan | The day plan. | Home, session |
| budget (time) | budget de temps | The minutes the owner gives to the day. | Settings, plan |
| error log | journal d’erreurs | A log of mistakes, kept to learn from them. | Navigation, statistics |
| error category | catégorie d’erreur | Taxonomy of mistakes. | Error log |
| lapse | oubli | A card the learner forgot. | Statistics |
| retention | rétention | The share of cards remembered. | Statistics, settings |
| stability | stabilité | FSRS term: how long a card holds. | Statistics |
| rating (Again, Hard, Good, Easy) | note (À revoir, Difficile, Bien, Facile) | A grade given to a card. | Review |
| transcript | transcription (d’une conversation) | The pasted text of a conversation. | Transcripts |
| transcription (speech to text) | transcription | Same word; the context tells them apart. | Speaking, shadowing |
| pronunciation | prononciation | Azure pronunciation assessment. | Pronunciation |
| provider | fournisseur | An AI service (Gemini, Groq, Ollama, Azure). | Settings, statistics |
| key (API) | clé | The secret kept in `.env`. | Settings |
| token | jeton | The unit counted by AI providers. | Settings, statistics |
| quota / rate limit | quota / limite de débit | Free-tier limits. | Settings, statistics |
| degraded mode | mode dégradé | The application without AI. | Banner, settings |
| demo data | données de démonstration | Fictional database. | Badge |
| backup | sauvegarde | Full backup and restore. | Settings |
| settings | réglages | Used for the whole page, not "paramètres". | Navigation, settings |
| library | bibliothèque | The list of terms. | Navigation |
| import | importer | Import a list. | Library |
| duplicate | doublon | A term already in the library. | Library |
| queued / active / paused / done | en file / actif / en pause / terminé | Status of a deck. | Queue |
| draft / archived / known | brouillon / archivé / connu | Status of a term. | Library |

## Notes for the proof-reader

- A word kept in English on purpose: *shadowing*, product names (Gemini, Groq, Azure, Ollama).
- Words that look English but are French: *Source, Type, Date, Notes, Actions, Pages, Version, Audio,
  Collocation, Situation, Question, Correction, Score, Export, Suggestions, Structure, Stable,
  Production, Campus, Dialogue, Consolidation*. They are the only French values identical to the
  English ones, and `untranslated.test.ts` lists them one by one.
- The learning content of an error category (`label_fr`, `description_fr`) comes from the database,
  not from `fr.json`.
