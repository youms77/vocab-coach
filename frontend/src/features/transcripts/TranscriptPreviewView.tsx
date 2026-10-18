import { useTranslation } from 'react-i18next'

import {
  MAX_USER_CHARS,
  type TranscriptPreview,
  type TranscriptProblem,
  USER_MODES,
  type UserDesignation,
} from '../../api/transcripts'

const severityMark = { info: '', warning: '⚠ ', error: '⚠ ' } as const

/** One problem of the parser: the severity is written in words, never by colour alone (D-087). */
function Problem({ problem }: { problem: TranscriptProblem }) {
  const { t } = useTranslation()
  const key = `transcripts.problems.${problem.code}`
  // An unknown code falls back to the backend's English message.
  const message = t(key, { defaultValue: problem.message })
  const severity = problem.severity in severityMark ? problem.severity : 'info'
  return (
    <li className={`transcript-problem transcript-problem--${severity}`}>
      <strong>
        {severityMark[severity]}
        {t(`transcripts.preview.severity.${severity}`)}
      </strong>
      : {message}
      {problem.line !== null && (
        <span className="muted"> ({t('transcripts.preview.line', { line: problem.line })})</span>
      )}
    </li>
  )
}

function sameDesignation(a: UserDesignation | null, b: UserDesignation): boolean {
  if (a === null) return false
  if ('label' in a && 'label' in b) return a.label.toLowerCase() === b.label.toLowerCase()
  if ('mode' in a && 'mode' in b) return a.mode === b.mode
  return false
}

/** "Which turns are yours?": a label, or a mode when the text has no speaker labels (D-151). */
function UserPicker({
  preview,
  user,
  disabled,
  onChoose,
}: {
  preview: TranscriptPreview
  user: UserDesignation | null
  disabled: boolean
  onChoose: (designation: UserDesignation) => void
}) {
  const { t } = useTranslation()
  const labelled = preview.labelled && preview.labels.length > 0
  const lonelyUnknown = preview.labels.filter((label) => label.turns === 1 && label.known === null)
  return (
    <fieldset className="transcript-picker">
      <legend>{t('transcripts.picker.legend')}</legend>
      <p className="muted">{labelled ? t('transcripts.picker.labelsHint') : t('transcripts.picker.modesHint')}</p>
      <div className="transcript-picker__options">
        {labelled
          ? preview.labels.map((label) => (
              <label key={label.label} className="transcript-picker__option">
                <input
                  type="radio"
                  name="transcript-user"
                  checked={sameDesignation(user, { label: label.label })}
                  disabled={disabled}
                  onChange={() => onChoose({ label: label.label })}
                />
                <span>
                  <strong lang="en">{label.label}</strong>{' '}
                  <span className="muted">
                    {t('transcripts.picker.labelMeta', { count: label.turns, words: label.words })}
                    {label.known !== null && <> · {t(`transcripts.picker.known.${label.known}`)}</>}
                  </span>
                </span>
              </label>
            ))
          : USER_MODES.map((mode) => (
              <label key={mode} className="transcript-picker__option">
                <input
                  type="radio"
                  name="transcript-user"
                  checked={sameDesignation(user, { mode })}
                  disabled={disabled}
                  onChange={() => onChoose({ mode })}
                />
                <span>{t(`transcripts.picker.modes.${mode}`)}</span>
              </label>
            ))}
      </div>
      {user === null && <p className="field-hint">{t('transcripts.picker.choose')}</p>}
      {lonelyUnknown.map((label) => (
        <p key={label.label} className="field-hint muted">
          {t('transcripts.picker.single', { label: label.label })}
        </p>
      ))}
    </fieldset>
  )
}

/**
 * What the parser found: the problems, the choice of your turns, the numbered turns (yours marked
 * in words and by a border) and the size of your part against the 6 000-character limit.
 */
export function TranscriptPreviewView({
  preview,
  user,
  pending,
  onChoose,
}: {
  preview: TranscriptPreview
  user: UserDesignation | null
  pending: boolean
  onChoose: (designation: UserDesignation) => void
}) {
  const { t } = useTranslation()
  const over = preview.user !== null && preview.user.chars > MAX_USER_CHARS
  return (
    <div className="transcript-preview">
      {preview.problems.length > 0 && (
        <section aria-label={t('transcripts.preview.problemsTitle')}>
          <h2 className="transcript-preview__title">{t('transcripts.preview.problemsTitle')}</h2>
          <ul className="transcript-problems">
            {preview.problems.map((problem, index) => (
              <Problem key={index} problem={problem} />
            ))}
          </ul>
        </section>
      )}

      {preview.turns.length > 0 && (
        <UserPicker preview={preview} user={user} disabled={pending} onChoose={onChoose} />
      )}

      {preview.user !== null && (
        <p className={`field-hint${over ? ' field-hint--error' : ''}`} role="status">
          {t('transcripts.preview.yours', {
            turns: preview.user.turns,
            words: preview.user.words,
            chars: preview.user.chars,
            max: MAX_USER_CHARS,
          })}
        </p>
      )}

      {preview.turns.length > 0 && (
        <section aria-label={t('transcripts.preview.turnsTitle')}>
          <h2 className="transcript-preview__title">{t('transcripts.preview.turnsTitle')}</h2>
          <ol className="transcript-turns">
            {preview.turns.map((turn) => (
              <li
                key={turn.index}
                value={turn.index}
                className={`transcript-turn${turn.is_user === true ? ' transcript-turn--user' : ''}`}
              >
                <p className="transcript-turn__head">
                  <strong>{t('transcripts.preview.turn', { n: turn.index })}</strong>
                  {turn.is_user === true && (
                    <>
                      {' · '}
                      <strong className="transcript-turn__you">{t('transcripts.preview.you')}</strong>
                    </>
                  )}
                  {turn.is_user === false && <> · {t('transcripts.preview.other')}</>}
                  {turn.speaker_label !== null && (
                    <span className="muted" lang="en">
                      {' '}
                      ({turn.speaker_label})
                    </span>
                  )}
                </p>
                <p lang="en" className="transcript-turn__text">
                  {turn.text}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}
