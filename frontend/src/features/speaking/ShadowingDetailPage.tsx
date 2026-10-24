import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import { type Production, useProduction } from '../../api/productions'
import { useTranscribe } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { SpeakButton } from '../../speech/SpeakButton'
import { INTELLIGIBILITY_CODE, type ManualErrorPrefill } from '../errors/prefill'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { AssessmentSection } from './AssessmentSection'
import { ComparisonView, type LoggedWord } from './ComparisonView'
import { PlayBoth } from './PlayBoth'
import { readUnavailableReason } from './shadowTarget'

function NotFound() {
  const { t } = useTranslation()
  return (
    <div className="speaking-page">
      <PageTitle>{t('shadowing.detail.title')}</PageTitle>
      <p className="form-message form-message--error" role="alert">
        {t('errors.production_not_found')}
      </p>
      <p>
        <Link to="/speaking/shadowing/history">{t('shadowing.detail.allShadowings')}</Link>
      </p>
    </div>
  )
}

/** A production that is not a shadowing (a written text, a free speech): a message and a way out. */
function NotAShadowing() {
  const { t } = useTranslation()
  return (
    <div className="speaking-page">
      <PageTitle>{t('shadowing.detail.title')}</PageTitle>
      <p className="form-message form-message--warn" role="alert">
        {t('shadowing.detail.notShadowing')}
      </p>
      <p className="link-row">
        <Link to="/errors">{t('shadowing.detail.errorLog')}</Link>
        <Link to="/speaking/shadowing/history">{t('shadowing.detail.allShadowings')}</Link>
      </p>
    </div>
  )
}

/**
 * One shadowing: the sentence, the recording ("Play both" plays the synthetic voice then the
 * recording), the transcription and the word-by-word comparison. A recording that was not
 * transcribed yet offers "Transcribe"; an unavailable provider is said with its reason and "Try
 * again". Nothing starts by itself: opening the page (or reloading it) only reads what is stored.
 */
export function ShadowingDetailPage() {
  const { t, i18n } = useTranslation()
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const query = useProduction(valid ? id : 0, valid)
  const transcribe = useTranscribe()
  const elapsed = useElapsedSeconds(transcribe.isPending, transcribe.submittedAt)
  const audio = useRef<HTMLAudioElement>(null)
  const result = useRef<HTMLHeadingElement>(null)
  // The reason the transcription failed when the recording was sent, handed over once.
  const [sentReason] = useState(() => readUnavailableReason(location.state))
  const consumed = useRef(false)

  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(location.pathname, { replace: true, state: null })
  }, [location.state, location.pathname, navigate])

  const production: Production | undefined = query.data
  const status = production?.transcription_status ?? null

  // After a transcription, the focus goes to its result.
  useEffect(() => {
    if (transcribe.isSuccess && status !== 'pending') result.current?.focus()
  }, [transcribe.isSuccess, status])

  if (!valid || (query.isError && query.error instanceof ApiError && query.error.status === 404)) {
    return <NotFound />
  }
  if (production !== undefined && production.kind !== 'shadowing') return <NotAShadowing />

  const target = production?.prompt_text ?? ''
  const failed = transcribe.data?.transcription.status === 'unavailable'
  const reason = failed ? (transcribe.data?.transcription.reason ?? null) : sentReason
  const unavailable = status === 'pending' && (failed || sentReason !== null)

  function logWord(word: LoggedWord) {
    if (production === undefined) return
    const prefill: ManualErrorPrefill = {
      original_text: production.text,
      erroneous_text: word.heard,
      correction: word.target,
      category_code: INTELLIGIBILITY_CODE,
      explanation: t('shadowing.detail.logExplanation', { heard: word.heard, target: word.target }),
    }
    void navigate('/errors/new', { state: prefill })
  }

  const announcement =
    transcribe.isSuccess && production?.comparison != null
      ? t('shadowing.detail.ready', {
          count: production.comparison.target_word_count,
          recognized: production.comparison.recognized_count,
        })
      : ''

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('shadowing.detail.title')}</PageTitle>
        {production !== undefined && (
          <p className="muted">{formatDateTime(production.created_at, i18n.language)}</p>
        )}
        <p className="link-row">
          <Link to="/speaking/shadowing">{t('shadowing.detail.another')}</Link>
          <Link to="/speaking/shadowing/history">{t('shadowing.detail.allShadowings')}</Link>
        </p>
      </section>

      {query.isPending && valid && <p className="muted">{t('shadowing.detail.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {production !== undefined && (
        <>
          <section className="card" aria-labelledby="shadow-target">
            <h2 id="shadow-target">{t('shadowing.detail.target')}</h2>
            <blockquote className="discovery-sentence" lang="en">
              {target}
            </blockquote>
            {target !== '' && <SpeakButton text={target} label={t('shadowing.sentenceLabel')} />}
          </section>

          <section className="card" aria-labelledby="shadow-recording">
            <h2 id="shadow-recording">{t('shadowing.detail.recording')}</h2>
            {production.audio_url !== null ? (
              <>
                {/* The server answers `Range`: the controls can seek. */}
                <audio
                  ref={audio}
                  controls
                  preload="metadata"
                  src={production.audio_url}
                  aria-label={t('shadowing.detail.recording')}
                  className="recorder__player"
                />
                {target !== '' && (
                  <p>
                    <PlayBoth target={target} audio={audio} />
                  </p>
                )}
              </>
            ) : (
              <p className="form-message form-message--warn">{t('shadowing.detail.noAudio')}</p>
            )}
          </section>

          <section className="card" aria-labelledby="shadow-result">
            <h2 id="shadow-result" ref={result} tabIndex={-1}>
              {t('shadowing.detail.result')}
            </h2>
            <div className="visually-hidden" role="status" aria-live="polite">
              {announcement}
            </div>

            {status === 'ok' &&
              (production.comparison !== null ? (
                <ComparisonView comparison={production.comparison} onLog={logWord} />
              ) : (
                <p lang="en">{production.text}</p>
              ))}

            {status === 'silence' && (
              <>
                <p className="form-message form-message--warn">{t('shadowing.detail.silence')}</p>
                <p>
                  <Link
                    to="/speaking/shadowing"
                    state={{ target, itemId: production.targets[0]?.lexical_item_id }}
                  >
                    {t('shadowing.detail.recordAgain')}
                  </Link>
                </p>
              </>
            )}

            {status === 'pending' && production.audio_url !== null && (
              <>
                <p className={unavailable ? 'form-message form-message--warn' : undefined}>
                  {unavailable
                    ? t('shadowing.detail.unavailable', { reason: aiReasonText(t, reason) })
                    : t('shadowing.detail.notTranscribed')}
                </p>
                <p>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={transcribe.isPending || query.isFetching}
                    onClick={() => transcribe.mutate(id)}
                  >
                    {transcribe.isPending
                      ? t('shadowing.detail.transcribing', { seconds: elapsed })
                      : unavailable
                        ? t('shadowing.detail.tryAgain')
                        : t('shadowing.detail.transcribe')}
                  </button>
                </p>
              </>
            )}

            {/* Transcribed meanwhile (409): the production is read again, nothing to say. */}
            {transcribe.isError &&
              !(transcribe.error instanceof ApiError && transcribe.error.code === 'already_transcribed') && (
                <ErrorText error={transcribe.error} />
              )}
            <p className="muted field-hint">{t('speaking.privacy')}</p>
          </section>

          <AssessmentSection production={production} />
        </>
      )}
    </div>
  )
}
