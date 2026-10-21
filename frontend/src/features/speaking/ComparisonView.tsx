import { useTranslation } from 'react-i18next'

import type { Comparison, UnrecognizedWord } from '../../api/speech'
import { heardMarks, isSubstitution, targetMarks, type WordMark } from './comparison'

/** What the user can do with a word the recogniser did not find: log it by hand. */
export interface LoggedWord {
  /** The word of the target sentence. */
  target: string
  /** What the recogniser wrote instead. */
  heard: string
}

function Word({ mark, row }: { mark: WordMark; row: 'target' | 'heard' }) {
  const { t } = useTranslation()
  // Every mark has a text, visible or for screen readers: the colour is never the only signal.
  let note: React.ReactNode = null
  if (mark.op === 'close') {
    note = (
      <>
        <span aria-hidden="true"> ≈</span>
        <span className="visually-hidden"> ({t('speaking.comparison.closeHidden')})</span>
      </>
    )
  } else if (mark.op === 'substituted' && row === 'target') {
    note = (
      <span className="cmp-word__note">
        {' '}
        ({t('speaking.comparison.heardAs', { word: mark.other ?? '' })})
      </span>
    )
  } else if (mark.op === 'missing') {
    note = <span className="cmp-word__note"> ({t('speaking.comparison.notHeard')})</span>
  } else if (mark.op === 'extra') {
    note = <span className="cmp-word__note"> ({t('speaking.comparison.extra')})</span>
  }
  return (
    <span className={`cmp-word cmp-word--${mark.op}`}>
      <span className="cmp-word__text">{mark.text}</span>
      {note}
    </span>
  )
}

function Row({
  label,
  marks,
  row,
}: {
  label: string
  marks: WordMark[]
  row: 'target' | 'heard'
}) {
  const { t } = useTranslation()
  return (
    <p className="comparison__row">
      <span className="comparison__label">{label}</span>{' '}
      <span lang="en" className="comparison__words">
        {marks.length === 0 ? (
          <span className="muted">{t('speaking.comparison.nothing')}</span>
        ) : (
          marks.map((mark) => (
            <span key={mark.key}>
              <Word mark={mark} row={row} />{' '}
            </span>
          ))
        )}
      </span>
    </p>
  )
}

function Unrecognized({
  words,
  onLog,
}: {
  words: UnrecognizedWord[]
  onLog?: (word: LoggedWord) => void
}) {
  const { t } = useTranslation()
  return (
    <>
      <h3 className="comparison__title">{t('speaking.comparison.unrecognized')}</h3>
      <ul className="comparison__list">
        {words.map((word) => (
          <li key={word.position}>
            <span lang="en">
              <strong>{word.word}</strong>
            </span>{' '}
            {word.heard !== null ? (
              <span>
                — {t('speaking.comparison.heardAs', { word: word.heard })}
              </span>
            ) : (
              <span>— {t('speaking.comparison.notHeard')}</span>
            )}
            {/* No button for a word that was not heard: there is no wrong form to quote. */}
            {onLog !== undefined && isSubstitution(word) && word.heard !== null && (
              <>
                {' '}
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onLog({ target: word.word, heard: word.heard as string })}
                >
                  {t('speaking.comparison.log')}
                  <span className="visually-hidden"> — “{word.word}”</span>
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

/**
 * The target sentence and what the recogniser heard, word by word, built from the backend's
 * `steps` (D-197). The summary is in words, with no grade or percentage; the warning that speech
 * recognition is not a pronunciation judge is always shown. `onLog` adds, for each substituted
 * word, a button that opens the manual error form already filled in.
 */
export function ComparisonView({
  comparison,
  compact = false,
  onLog,
}: {
  comparison: Comparison
  compact?: boolean
  onLog?: (word: LoggedWord) => void
}) {
  const { t } = useTranslation()
  return (
    <div className={`comparison${compact ? ' comparison--compact' : ''}`}>
      {comparison.target_word_count > 0 && (
        <p className="comparison__summary">
          <strong>
            {t('speaking.comparison.summary', {
              count: comparison.target_word_count,
              recognized: comparison.recognized_count,
            })}
          </strong>
        </p>
      )}
      <Row label={t('speaking.comparison.target')} marks={targetMarks(comparison)} row="target" />
      <Row label={t('speaking.comparison.heard')} marks={heardMarks(comparison)} row="heard" />
      {comparison.unrecognized.length > 0 && (
        <Unrecognized words={comparison.unrecognized} onLog={compact ? undefined : onLog} />
      )}
      <p className="form-message form-message--warn comparison__warning">
        {t('speaking.comparison.warning')}
      </p>
    </div>
  )
}
