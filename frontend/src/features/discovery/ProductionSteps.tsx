import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useShadowing } from '../../api/speech'
import { Recorder } from '../../speech/RecorderPanel'
import { SpeakButton } from '../../speech/SpeakButton'
import { StepHeading } from '../session/StepHeading'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { ComparisonView } from '../speaking/ComparisonView'

export const PERSONAL_MAX = 1000

/**
 * The optional recording of step 4b (D-199). The take is sent as a shadowing of the sentence on
 * screen (`origin=discovery`, with the term and the session); the comparison is compact. A refusal,
 * an unavailable transcription or silence is said and never blocks "Continue".
 */
function RepetitionRecording({
  text,
  itemId,
  sessionId,
}: {
  text: string
  itemId: number
  sessionId: number
}) {
  const { t } = useTranslation()
  const shadow = useShadowing()
  // A new, empty recorder after each take, so the same clip is not sent twice by mistake.
  const [round, setRound] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const sent = shadow.data
  useEffect(() => {
    if (shadow.isSuccess) heading.current?.focus()
  }, [shadow.isSuccess, shadow.data])

  let notice: string | null = null
  if (sent?.transcription.status === 'unavailable') {
    notice = t('discovery.repetition.unavailable', {
      reason: aiReasonText(t, sent.transcription.reason),
    })
  } else if (sent?.transcription.status === 'silence') {
    notice = t('discovery.repetition.silence')
  }

  return (
    <section className="discovery-check" aria-label={t('discovery.repetition.recordTitle')}>
      <p className="muted">{t('discovery.repetition.recordingHint')}</p>
      <Recorder
        key={round}
        use="shadowing"
        sending={shadow.isPending}
        sendingLabel={t('shadowing.sending')}
        onSend={(clip) =>
          shadow.mutate(
            {
              blob: clip.blob,
              durationS: clip.durationS,
              target: text,
              itemId,
              origin: 'discovery',
              studySessionId: sessionId,
            },
            { onSuccess: () => setRound((value) => value + 1) },
          )
        }
      />
      <div role="status">{notice !== null && <p className="form-message form-message--warn">{notice}</p>}</div>
      {shadow.isError && <ErrorText error={shadow.error} />}
      {sent !== undefined && sent.comparison !== null && (
        <>
          <h3 ref={heading} tabIndex={-1}>
            {t('discovery.repetition.yourTake')}
          </h3>
          <ComparisonView comparison={sent.comparison} compact />
        </>
      )}
      <p className="muted field-hint">{t('speaking.privacy')}</p>
    </section>
  )
}

/**
 * Step 4b: listen (normal, then slow) and repeat aloud, with an optional recording. "Done" goes on
 * whether or not a take was sent.
 */
export function RepetitionStep({
  text,
  itemId,
  sessionId,
  onDone,
}: {
  text: string
  itemId: number
  sessionId: number
  onDone: () => void
}) {
  const { t } = useTranslation()
  return (
    <>
      <StepHeading>{t('discovery.repetition.title')}</StepHeading>
      <p>{t('discovery.repetition.instructions')}</p>
      <blockquote className="discovery-sentence" lang="en">
        {text}
      </blockquote>
      <SpeakButton text={text} label={t('discovery.read.sentenceLabel')} />
      <RepetitionRecording text={text} itemId={itemId} sessionId={sessionId} />
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
