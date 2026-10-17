import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpeakButton } from '../../speech/SpeakButton'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'

export const PERSONAL_MAX = 1000

/** Step 4b: listen (normal, then slow) and repeat aloud. Nothing is recorded yet (M6). */
export function RepetitionStep({ text, onDone }: { text: string; onDone: () => void }) {
  const { t } = useTranslation()
  return (
    <>
      <StepHeading>{t('discovery.repetition.title')}</StepHeading>
      <p>{t('discovery.repetition.instructions')}</p>
      <blockquote className="discovery-sentence" lang="en">
        {text}
      </blockquote>
      <SpeakButton text={text} label={t('discovery.read.sentenceLabel')} />
      <p className="muted">{t('discovery.repetition.recordingLater')}</p>
      <button type="button" className="button button--primary" onClick={onDone}>
        {t('discovery.repetition.done')}
      </button>
    </>
  )
}

/** Step 4c: an optional sentence of the user's own, sent with `complete`. */
export function PersonalSentenceStep({
  term,
  onFinish,
  sending,
  error,
}: {
  term: string
  onFinish: (sentence: string | null) => void
  sending: boolean
  error: unknown
}) {
  const { t } = useTranslation()
  const [sentence, setSentence] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (sending) return
    const text = sentence.trim()
    onFinish(text === '' ? null : text)
  }

  return (
    <form className="discovery-form" onSubmit={submit}>
      <StepHeading>{t('discovery.personal.title')}</StepHeading>
      <div className="field">
        <label htmlFor="discovery-personal">{t('discovery.personal.label', { term })}</label>
        <textarea
          id="discovery-personal"
          lang="en"
          rows={3}
          maxLength={PERSONAL_MAX}
          value={sentence}
          onChange={(event) => setSentence(event.target.value)}
          aria-describedby="discovery-personal-hint"
        />
        <p id="discovery-personal-hint" className="muted field-hint">
          {t('discovery.personal.hint')}
        </p>
      </div>
      <div className="button-row">
        <button type="submit" className="button button--primary" disabled={sending}>
          {sending ? t('discovery.personal.finishing') : t('discovery.personal.finish')}
        </button>
        <button
          type="button"
          className="button"
          disabled={sending}
          onClick={() => !sending && onFinish(null)}
        >
          {t('discovery.personal.skip')}
        </button>
      </div>
      {error !== null && <ErrorText error={error} />}
    </form>
  )
}
