import { useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { MAX_UPLOAD_BYTES, formatClock, unsupportedReason, type RecordingUse } from './recorder'
import { type Clip, useRecorder } from './useRecorder'
import { cancelSpeech } from './useSpeech'

/**
 * The voice recorder (D-193): "Start recording" / "Stop recording", then "Listen", "Record again"
 * and "Send". The parent decides what sending means. The state is said in words (a red dot and
 * the text, never the colour alone) and announced politely when it starts and stops; the timer
 * itself is not a live region (it would be read every second).
 */
export function Recorder({
  use,
  onSend,
  sending = false,
  sendLabel,
  sendingLabel,
  disabled = false,
}: {
  use: RecordingUse
  onSend: (clip: Clip) => void
  sending?: boolean
  sendLabel?: string
  sendingLabel?: string
  /** Nothing can start (the parent is busy or has nothing to record yet). */
  disabled?: boolean
}) {
  const { t, i18n } = useTranslation()
  const number = (value: number) => value.toLocaleString(i18n.language)
  const recorder = useRecorder(use)
  const audio = useRef<HTMLAudioElement>(null)
  const hintId = useId()
  const [tooLarge, setTooLarge] = useState(false)
  const { limits, status, clip } = recorder
  const unsupported = unsupportedReason()
  const error = recorder.reason ?? unsupported

  function send() {
    if (clip === null || recorder.tooShort || sending) return
    if (clip.blob.size > MAX_UPLOAD_BYTES) {
      setTooLarge(true)
      return
    }
    setTooLarge(false)
    onSend(clip)
  }

  function listen() {
    // The synthetic voice must not talk over the clip.
    cancelSpeech()
    const element = audio.current
    if (element === null) return
    element.currentTime = 0
    void Promise.resolve(element.play()).catch(() => {})
  }

  function again() {
    setTooLarge(false)
    recorder.reset()
  }

  let announcement = ''
  if (status === 'recording') announcement = t('recorder.started')
  else if (status === 'stopped' && clip !== null) {
    announcement = t('recorder.stopped', { time: formatClock(clip.durationS) })
  }

  return (
    <div className="recorder">
      <p id={hintId} className="muted field-hint">
        {t('recorder.range', { min: number(limits.min), max: number(limits.max) })}
        {use === 'speaking' && <> {t('recorder.rangeSpeaking')}</>}
      </p>

      {status === 'recording' && (
        <p className="recorder__status">
          <span className="recorder__dot" aria-hidden="true" />
          <strong>{t('recorder.recording', { time: formatClock(recorder.seconds) })}</strong>
        </p>
      )}
      {status === 'requesting' && <p className="muted">{t('recorder.requesting')}</p>}
      {recorder.warning && (
        <p className="form-message form-message--warn">
          {t('recorder.longWarning', { max: limits.max })}
        </p>
      )}

      <div className="button-row">
        {(status === 'idle' || status === 'error') && (
          <button
            type="button"
            className="button button--primary"
            onClick={recorder.start}
            disabled={disabled || unsupported !== null || sending}
            aria-describedby={hintId}
          >
            {t('recorder.start')}
          </button>
        )}
        {status === 'requesting' && (
          <button type="button" className="button" onClick={recorder.reset}>
            {t('recorder.cancel')}
          </button>
        )}
        {status === 'recording' && (
          <button type="button" className="button button--primary" onClick={recorder.stop}>
            {t('recorder.stop')}
          </button>
        )}
        {status === 'stopped' && clip !== null && (
          <>
            <button type="button" className="button" onClick={listen}>
              {t('recorder.listen')}
            </button>
            <button type="button" className="button" onClick={again} disabled={sending}>
              {t('recorder.again')}
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={send}
              disabled={recorder.tooShort || sending}
            >
              {sending ? (sendingLabel ?? t('recorder.sending')) : (sendLabel ?? t('recorder.send'))}
            </button>
          </>
        )}
      </div>

      {status === 'stopped' && clip !== null && (
        <>
          <p className="muted">{t('recorder.length', { time: formatClock(clip.durationS) })}</p>
          {/* The local clip, before sending: a `blob:` URL the hook revokes. */}
          <audio ref={audio} src={clip.url} preload="auto" className="recorder__audio" />
        </>
      )}
      {recorder.tooShort && (
        <p className="form-message form-message--warn" role="alert">
          {t('recorder.tooShort', { min: number(limits.min) })}
        </p>
      )}
      {tooLarge && (
        <p className="form-message form-message--error" role="alert">
          {t('recorder.tooLarge', { mb: MAX_UPLOAD_BYTES / 1024 / 1024 })}
        </p>
      )}
      {error !== null && (
        <div className="form-message form-message--error" role="alert">
          <p>{t(`recorder.errors.${error}`)}</p>
          {error === 'denied' && <p>{t('recorder.deniedHelp')}</p>}
        </div>
      )}

      <div className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </div>
    </div>
  )
}
