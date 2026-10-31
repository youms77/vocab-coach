# French values changed in M10.c1 (old → new)

Only changes of wording are listed. 687 more values changed only by typography (typographic apostrophe, no-break spaces; see D-322).

The keys are grouped by screen (first part of the key).

## Reworded

### import

- `import.severity.info`: « Info » → « Information »

### stats

- `stats.intro`: « Tout est calculé à partir de tes journaux : révisions, erreurs, productions et appels à l'IA. Aucun compteur n'est tenu à part. » → « Tout est calculé à partir de vos journaux : révisions, erreurs, productions et appels à l’IA. Aucun compteur n’est tenu à part. »
- `stats.period.problem.invalid`: « Saisis deux dates valides. » → « Saisissez deux dates valides. »
- `stats.export.hint`: « Un zip avec un fichier CSV par table, pour tes propres analyses (par exemple avec pandas). » → « Un zip avec un fichier CSV par table, pour vos propres analyses (par exemple avec pandas). »
- `stats.errors.topTitle`: « Tes cinq erreurs les plus récurrentes » → « Vos cinq erreurs les plus récurrentes »
- `stats.memory.intro`: « La tenue des cartes : rétention face à ton objectif, calibrage du planificateur, oublis et stabilité. » → « La tenue des cartes : rétention face à votre objectif, calibrage du planificateur, oublis et stabilité. »
- `stats.memory.calibrationIntro`: « Pour chaque tranche de rappel prévu, ce qui s'est vraiment passé. Plus les deux courbes sont proches, mieux le planificateur te connaît. » → « Pour chaque tranche de rappel prévu, ce qui s’est vraiment passé. Plus les deux courbes sont proches, mieux le planificateur vous connaît. »
- `stats.memory.agreement`: « Notes que tu as changées après la note automatique : » → « Notes que vous avez changées après la note automatique : »
- `stats.progress.intro`: « Où en sont tes termes, comment la bibliothèque a bougé sur la période, tes decks et tes parcours, et les révisions à venir. » → « Où en sont vos termes, comment la bibliothèque a bougé sur la période, vos paquets et vos parcours, et les révisions à venir. »
- `stats.progress.funnelIntro`: « L'entonnoir d'apprentissage, des termes qui attendent dans la file à ceux que tu utilises activement. » → « L’entonnoir d’apprentissage, des termes qui attendent dans la file à ceux que vous utilisez activement. »
- `stats.progress.decksTitle`: « Decks » → « Paquets »
- `stats.progress.decksEmpty`: « Aucun deck pour l'instant. » → « Aucun paquet pour l’instant. »
- `stats.progress.deck`: « Deck » → « Paquet »
- `stats.practice.intro`: « Combien tu as travaillé, à quelle régularité, et combien tu as écrit et dit. » → « Combien vous avez travaillé, à quelle régularité, et combien vous avez écrit et dit. »
- `stats.practice.studyNote`: « Compté d'après tes actions seulement : une longue lecture sans clic n'est pas comptée. La ligne en pointillés est la durée des séances, pour comparer. » → « Compté d’après vos actions seulement : une longue lecture sans clic n’est pas comptée. La ligne en pointillés est la durée des séances, pour comparer. »
- `stats.practice.wordsNote`: « Tes propres mots seulement : une conversation collée compte tes phrases, pas celles de l'autre personne. » → « Vos propres mots seulement : une conversation collée compte vos phrases, pas celles de l’autre personne. »

## Added

### errors

- `errors.card_exists`: « Une carte existe déjà pour ce terme. »
- `errors.not_cardable`: « Cette erreur ne peut pas devenir une carte. »
- `errors.suggestion_not_found`: « Cette suggestion n’existe plus. »
- `errors.duration_required`: « La durée de l’enregistrement est inconnue. »
- `errors.unknown_code`: « Le serveur a refusé cette demande. »
- `errors.unknown_table`: « Cette table n’existe pas. »

### consolidation

- `consolidation.summary.effectActive_one`: « {{count}} terme est devenu actif. »
- `consolidation.summary.effectActive_other`: « {{count}} termes sont devenus actifs. »
- `consolidation.summary.effectReinforced_one`: « {{count}} carte de révision a été renforcée. »
- `consolidation.summary.effectReinforced_other`: « {{count}} cartes de révision ont été renforcées. »

### fieldErrors

- `fieldErrors.missing`: « Ce champ est obligatoire. »
- `fieldErrors.string_type`: « Ce champ doit être du texte. »
- `fieldErrors.string_too_short`: « Ce texte est trop court. »
- `fieldErrors.string_too_long`: « Ce texte est trop long. »
- `fieldErrors.string_pattern_mismatch`: « Ce texte n’a pas la forme attendue. »
- `fieldErrors.too_short`: « Il n’y a pas assez d’éléments. »
- `fieldErrors.too_long`: « Il y a trop d’éléments. »
- `fieldErrors.int_type`: « Ce champ doit être un nombre entier. »
- `fieldErrors.int_parsing`: « Ce champ doit être un nombre entier. »
- `fieldErrors.float_type`: « Ce champ doit être un nombre. »
- `fieldErrors.float_parsing`: « Ce champ doit être un nombre. »
- `fieldErrors.bool_type`: « Ce champ doit être oui ou non. »
- `fieldErrors.bool_parsing`: « Ce champ doit être oui ou non. »
- `fieldErrors.greater_than`: « Ce nombre est trop petit. »
- `fieldErrors.greater_than_equal`: « Ce nombre est trop petit. »
- `fieldErrors.less_than`: « Ce nombre est trop grand. »
- `fieldErrors.less_than_equal`: « Ce nombre est trop grand. »
- `fieldErrors.literal_error`: « Cette valeur ne fait pas partie de celles qui sont acceptées. »
- `fieldErrors.enum`: « Cette valeur ne fait pas partie de celles qui sont acceptées. »
- `fieldErrors.list_type`: « Ce champ doit être une liste. »
- `fieldErrors.dict_type`: « Ce champ doit être un objet. »
- `fieldErrors.extra_forbidden`: « Ce champ n’est pas attendu. »
- `fieldErrors.json_invalid`: « La requête n’est pas du JSON valide. »
- `fieldErrors.value_error`: « Cette valeur n’est pas acceptée. »

## Removed

- `consolidation.summary.effect`
