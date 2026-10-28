import { useTranslation } from 'react-i18next'

import type { PronunciationScores } from '../../api/speech'
import { formatNumber } from '../../i18n/format'
import { formatDateTime } from '../session/format'
import { errorTypeKey, needsAttention, weakestPhonemes } from './pronunciation'
import { Notice } from '../../components/Notice'

function ScoreValue({ value }: { value: number | null }) {
  const { t, i18n } = useTranslation()
  return (
    <>
      {value === null
        ? t('pronunciation.noScore')
        : t('pronunciation.scoreValue', {
            value: formatNumber(i18n.language, value, 0),
          })}
    </>
  )
}

/**
 * The stored `azure-pa-1` scores of a shadowing (D-215): four overall scores, every word with its
 * score and error type, the weakest sounds. Always framed as an automatic estimate. Shown only for
 * a take that was recorded and assessed, so nothing here comes before the attempt.
 */
export function PronunciationView({
  scores,
  demo = false,
}: {
  scores: PronunciationScores
  demo?: boolean
}) {
  const { t, i18n } = useTranslation()

  if (scores.status === 'silence') {
    return <Notice tone="warning">{t('pronunciation.silence')}</Notice>
  }
  const weakest = weakestPhonemes(scores)
  const overall = [
    ['accuracy', scores.overall.accuracy],
    ['fluency', scores.overall.fluency],
    ['completeness', scores.overall.completeness],
    ['pronunciation', scores.overall.pronunciation],
  ] as const

  return (
    <div className="pronunciation">
      <p className="muted">{t('pronunciation.estimate')}</p>

      <h3>{t('pronunciation.overall')}</h3>
      <dl className="pronunciation__overall">
        {overall.map(([key, value]) => (
          <div key={key} className="pronunciation__score">
            <dt>{t(`pronunciation.${key}`)}</dt>
            <dd>
              <ScoreValue value={value} />
            </dd>
          </div>
        ))}
      </dl>

      <h3>{t('pronunciation.words')}</h3>
      <p className="muted field-hint">{t('pronunciation.wordsHint')}</p>
      <ul className="pronunciation__words" lang="en">
        {scores.words.map((word, index) => {
          const type = errorTypeKey(word.error_type)
          const attention = needsAttention(word)
          return (
            <li
              key={`${index}-${word.word}`}
              className={`pronunciation__word${attention ? ' pronunciation__word--attention' : ''}`}
            >
              <span className="pronunciation__text">{word.word}</span>{' '}
              <span lang={i18n.language}>
                {t('pronunciation.wordLine', {
                  score:
                    word.accuracy === null
                      ? t('pronunciation.noScore')
                      : t('pronunciation.scoreValue', { value: Math.round(word.accuracy) }),
                  type: t(`pronunciation.errorTypes.${type}`),
                })}
              </span>
            </li>
          )
        })}
      </ul>

      <h3>{t('pronunciation.weakest')}</h3>
      {weakest.length === 0 ? (
        <p className="muted">{t('pronunciation.weakestEmpty')}</p>
      ) : (
        <ul className="pronunciation__phonemes">
          {weakest.map((p, index) => (
            <li key={`${index}-${p.phoneme}-${p.word}`}>
              {t('pronunciation.weakestLine', {
                phoneme: p.phoneme,
                word: p.word,
                score: t('pronunciation.scoreValue', { value: Math.round(p.accuracy) }),
              })}
            </li>
          ))}
        </ul>
      )}

      <p className="muted field-hint">
        {t('pronunciation.assessedAt', {
          date: formatDateTime(scores.assessed_at, i18n.language),
          provider: scores.provider,
        })}
        {demo || scores.provider === 'demo' ? ` ${t('pronunciation.demoNote')}` : ''}
      </p>
    </div>
  )
}
