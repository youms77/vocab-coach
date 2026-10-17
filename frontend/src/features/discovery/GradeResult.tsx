import { useTranslation } from 'react-i18next'

import type { DiffPart, GradeResult as Result } from '../../api/reviews'
import { SpeakButton } from '../../speech/SpeakButton'

// A sign next to the outcome's text, so the outcome is never carried by colour alone.
const SIGNS = { exact: '✓', form: '✓', typo: '≈', wrong: '✗', empty: '–' } as const

function Diff({ parts }: { parts: DiffPart[] }) {
  const { t } = useTranslation()
  return (
    <p className="grade-diff">
      <span>{t('grading.diff')}</span>{' '}
      <span lang="en" className="grade-diff__text">
        {parts.map((part, i) => {
          if (part.op === 'equal') return <span key={i}>{part.given}</span>
          return (
            <span key={i}>
              {part.given !== '' && (
                <del>
                  <span className="visually-hidden">{t('grading.removed')}: </span>
                  {part.given}
                </del>
              )}
              {part.expected !== '' && (
                <ins>
                  <span className="visually-hidden">{t('grading.added')}: </span>
                  {part.expected}
                </ins>
              )}
            </span>
          )
        })}
      </span>
    </p>
  )
}

/** What `POST /reviews/grade` answered: the outcome, the expected answer, variants and diff. */
export function GradeResult({ result }: { result: Result }) {
  const { t } = useTranslation()
  const outcome = result.outcome
  return (
    <div className={`grade-result grade-result--${outcome ?? 'none'}`} role="status">
      {outcome !== null && (
        <p className="grade-result__outcome">
          <span aria-hidden="true">{SIGNS[outcome]} </span>
          {t(`grading.outcomes.${outcome}`)}
        </p>
      )}
      {result.expected !== null && (
        <p>
          <span lang="en">{t('grading.expected', { answer: result.expected })}</span>{' '}
          <SpeakButton text={result.expected} label={t('discovery.exercises.answerAudioLabel')} />
        </p>
      )}
      {result.accepted.length > 0 && (
        <p className="muted">{t('grading.accepted', { list: result.accepted.join(', ') })}</p>
      )}
      {outcome === 'typo' && result.diff !== null && <Diff parts={result.diff} />}
    </div>
  )
}
