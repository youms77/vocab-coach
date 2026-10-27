import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { UsageSheet } from '../../api/enrichment'
import { SpeakButton } from '../../speech/SpeakButton'

function Entry({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="sheet-entry">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/**
 * "Shadow this sentence": opens the shadowing page with the sentence and the term in the
 * navigation state (the page reads them once). `what` names the sentence for screen readers.
 */
export function ShadowLink({
  sentence,
  itemId,
  what,
}: {
  sentence: string
  itemId: number
  what: string
}) {
  const { t } = useTranslation()
  return (
    <Link
      to="/speaking/shadowing"
      state={{ target: sentence, itemId }}
      className="button button--small"
    >
      {t('sheet.shadow')}
      {' '}
      <span className="visually-hidden">({what})</span>
    </Link>
  )
}

/**
 * A usage sheet, read-only, in the SPEC order. Empty fields are left out. `audio` adds "Listen"
 * buttons to the examples (discovery, M4.b); the library's sheet panel shows none. `shadowItemId`
 * adds "Shadow this sentence" to the examples (the term's page, M6.b1); discovery gives none.
 */
export function SheetView({
  sheet,
  audio = false,
  shadowItemId,
}: {
  sheet: UsageSheet
  audio?: boolean
  shadowItemId?: number
}) {
  const { t } = useTranslation()
  const p = sheet.pronunciation
  const hasPronunciation = p !== null && (p.ipa_us ?? p.stressed_syllable ?? p.note) !== null

  return (
    <dl className="sheet-view">
      {sheet.meaning_in_context !== null && (
        <Entry label={t('sheet.fields.meaning_in_context')}>{sheet.meaning_in_context}</Entry>
      )}
      {sheet.definition_simple !== null && (
        <Entry label={t('sheet.fields.definition_simple')}>{sheet.definition_simple}</Entry>
      )}
      {sheet.translation_fr.length > 0 && (
        <Entry label={t('sheet.fields.translation_fr')}>
          <span lang="fr">{sheet.translation_fr.join(' · ')}</span>
        </Entry>
      )}
      {(sheet.part_of_speech !== null || sheet.register_level !== null) && (
        <Entry label={t('sheet.fields.grammar')}>
          {[
            sheet.part_of_speech,
            sheet.register_level !== null ? t(`sheet.register.${sheet.register_level}`) : null,
          ]
            .filter((v) => v !== null)
            .join(' · ')}
          {sheet.register_note !== null && <> — {sheet.register_note}</>}
        </Entry>
      )}
      {sheet.usage_notes !== null && (
        <Entry label={t('sheet.fields.usage_notes')}>{sheet.usage_notes}</Entry>
      )}
      {sheet.other_meanings.length > 0 && (
        <Entry label={t('sheet.fields.other_meanings')}>
          <ul>
            {sheet.other_meanings.map((m, i) => (
              <li key={i}>
                {m.definition} — <span lang="fr">{m.translation_fr}</span>
              </li>
            ))}
          </ul>
        </Entry>
      )}
      {sheet.collocations.length > 0 && (
        <Entry label={t('sheet.fields.collocations')}>
          <ul>
            {sheet.collocations.map((c, i) => (
              <li key={i}>
                <strong>{c.pattern}</strong>
                {c.example !== null && <> — “{c.example}”</>}
              </li>
            ))}
          </ul>
        </Entry>
      )}
      {sheet.examples.length > 0 && (
        <Entry label={t('sheet.fields.examples')}>
          <ul>
            {sheet.examples.map((e, i) => (
              <li key={i}>
                <span lang="en">“{e.sentence}”</span>{' '}
                <span className="muted">({t(`sheet.kind.${e.kind}`)})</span>
                {audio && (
                  <>
                    {' '}
                    <SpeakButton
                      text={e.sentence}
                      label={t('sheet.exampleLabel', { index: i + 1 })}
                    />
                  </>
                )}
                {shadowItemId !== undefined && (
                  <>
                    {' '}
                    <ShadowLink
                      sentence={e.sentence}
                      itemId={shadowItemId}
                      what={t('sheet.exampleLabel', { index: i + 1 })}
                    />
                  </>
                )}
              </li>
            ))}
          </ul>
        </Entry>
      )}
      {sheet.word_family.length > 0 && (
        <Entry label={t('sheet.fields.word_family')}>
          {sheet.word_family.map((w) => `${w.form} (${w.part_of_speech})`).join(' · ')}
        </Entry>
      )}
      {hasPronunciation && (
        <Entry label={t('sheet.fields.pronunciation')}>
          {[
            p.ipa_us,
            p.stressed_syllable !== null
              ? t('sheet.stress', { syllable: p.stressed_syllable })
              : null,
          ]
            .filter((v) => v !== null)
            .join(' · ')}
          {p.note !== null && <> — {p.note}</>}
        </Entry>
      )}
      {sheet.french_speaker_pitfalls.length > 0 && (
        <Entry label={t('sheet.fields.french_speaker_pitfalls')}>
          <ul>
            {sheet.french_speaker_pitfalls.map((pit, i) => (
              <li key={i}>
                <span className="visually-hidden">{t('sheet.wrong')} </span>
                <s>{pit.wrong}</s> → <span className="visually-hidden">{t('sheet.right')} </span>
                <strong>{pit.right}</strong> — {pit.explanation}
              </li>
            ))}
          </ul>
        </Entry>
      )}
      {sheet.confusables.length > 0 && (
        <Entry label={t('sheet.fields.confusables')}>
          <ul>
            {sheet.confusables.map((c, i) => (
              <li key={i}>
                <strong>{c.term}</strong> — {c.difference}
              </li>
            ))}
          </ul>
        </Entry>
      )}
    </dl>
  )
}
