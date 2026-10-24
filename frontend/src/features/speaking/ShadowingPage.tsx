import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'

import { useAssessmentReady } from '../../api/pronunciation'
import { useShadowing } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { Recorder } from '../../speech/RecorderPanel'
import { SpeakButton } from '../../speech/SpeakButton'
import { convertToWav } from '../../speech/wav'
import { ErrorText } from '../settings/ErrorText'
import { readShadowTarget, SHADOW_MAX_CHARS } from './shadowTarget'

/**
 * Shadowing: listen to a sentence, record yourself repeating it, send. The sentence comes from the
 * navigation state `{target, itemId}` (a usage sheet's "Shadow this sentence") or from the field.
 * The state is read once and cleared at once, so a reload starts with an empty field (the
 * browser keeps the router state across a reload). Sending goes to `/speaking/shadowing/{id}`
 * with the history replaced: the recording is never sent twice by a reload.
 */
export function ShadowingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const shadow = useShadowing()
  const assessmentReady = useAssessmentReady()
  const [converting, setConverting] = useState(false)
  const [arrival] = useState(() => readShadowTarget(location.state))
  const [target, setTarget] = useState(arrival?.target ?? '')
  const consumed = useRef(false)
  const fieldId = useId()
  const countId = useId()

  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])

  const sentence = target.trim()
  // Code points, as the server counts them (`len` of the stripped text).
  const chars = Array.from(sentence).length
  const tooLong = chars > SHADOW_MAX_CHARS
  const usable = chars > 0 && !tooLong
  const sending = converting || shadow.isPending || shadow.isSuccess

  // With the pronunciation assessment on, the take is stored as WAV 16 kHz mono: Azure refuses the
  // webm that Chrome and Edge record and assesses the stored file (D-219). If the browser cannot
  // convert, the original is sent and the detail page says why it cannot be assessed.
  async function send(clip: { blob: Blob; durationS: number }) {
    let blob = clip.blob
    if (assessmentReady) {
      setConverting(true)
      blob = (await convertToWav(clip.blob)) ?? clip.blob
      setConverting(false)
    }
    shadow.mutate(
      {
        blob,
        durationS: clip.durationS,
        target: sentence,
        itemId: arrival?.itemId,
        origin: 'shadowing',
      },
      {
        onSuccess: (result) => {
          // An unavailable transcription is told on the next page (the reason only).
          const state =
            result.transcription.status === 'unavailable'
              ? { unavailableReason: result.transcription.reason ?? 'all_failed' }
              : null
          navigate(`/speaking/shadowing/${result.production_id}`, { replace: true, state })
        },
      },
    )
  }

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('shadowing.title')}</PageTitle>
        <p className="muted">{t('shadowing.intro')}</p>
        <p className="link-row">
          <Link to="/speaking/shadowing/history">{t('shadowing.historyLink')}</Link>
        </p>
      </section>

      <section className="card" aria-labelledby={`${fieldId}-heading`}>
        <h2 id={`${fieldId}-heading`}>{t('shadowing.step1')}</h2>
        <div className="field">
          <label htmlFor={fieldId}>{t('shadowing.targetLabel')}</label>
          <textarea
            id={fieldId}
            lang="en"
            rows={3}
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            readOnly={sending}
            aria-describedby={countId}
            aria-invalid={tooLong}
          />
          <p id={countId} className={`field-hint${tooLong ? ' field-hint--error' : ''}`}>
            {t('shadowing.chars', { chars, max: SHADOW_MAX_CHARS })}
          </p>
          {tooLong && (
            <p className="form-message form-message--error" role="alert">
              {t('shadowing.tooLong', { chars, max: SHADOW_MAX_CHARS })}
            </p>
          )}
        </div>
        {usable && (
          <p>
            <SpeakButton text={sentence} label={t('shadowing.sentenceLabel')} />
          </p>
        )}
      </section>

      <section className="card" aria-labelledby={`${fieldId}-record`}>
        <h2 id={`${fieldId}-record`}>{t('shadowing.step2')}</h2>
        <Recorder
          use="shadowing"
          disabled={!usable}
          sending={sending}
          sendingLabel={t('shadowing.sending')}
          onSend={(clip) => void send(clip)}
        />
        {!usable && <p className="muted field-hint">{t('shadowing.needSentence')}</p>}
        {shadow.isError && <ErrorText error={shadow.error} />}
        <p className="muted field-hint">{t('speaking.privacy')}</p>
      </section>
    </div>
  )
}
