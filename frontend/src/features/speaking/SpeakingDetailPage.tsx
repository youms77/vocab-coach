import type { TFunction } from 'i18next'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import {
  type CorrectionResult,
  type Production,
  useCorrectProduction,
  useProduction,
} from '../../api/productions'
import { useInvalidateUnits } from '../../api/curriculum'
import { useTranscribe } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { unitFromParam } from '../curriculum/unitRules'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { CorrectionView } from '../writing/CorrectionView'
import { readAutoCorrect } from './speakingState'
import { readUnavailableReason } from './shadowTarget'
import { Notice } from '../../components/Notice'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

function Message({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="speaking-page">
      <PageTitle>{title}</PageTitle>
      {children}
    </div>
  )
}

/** Why the speech is not corrected: the AI's failure (a 200 answer) or a refused request. */
function notCorrectedText(
  t: TFunction,
  result: CorrectionResult | undefined,
  error: unknown,
): string {
  if (result?.status === 'incomplete') return t('speaking.detail.notCorrectedIncomplete')
  if (result?.status === 'unavailable') {
    return t('speaking.detail.notCorrectedReason', { reason: aiReasonText(t, result.reason) })
  }
  if (codeOf(error) === 'text_too_long') return t('speaking.detail.textTooLong')
  return t('speaking.detail.notCorrected')
}

/**
 * One free speech: the topic, the recording, what the speech recognition heard and its correction.
 * Arriving from `/speaking` (router state `autoCorrect`) the page runs the correction by itself,
 * once; opened from the history or after a reload it only shows what is stored, and offers
 * "Transcribe" or "Correct my speech" when a step is missing. A click on "Transcribe" is the
 * user's own action, so a transcription that succeeds goes on to the correction.
 */
function SpeakingDetail({ id }: { id: number }) {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const query = useProduction(id)
  const transcribe = useTranscribe()
  const correct = useCorrectProduction()
  const transcribing = useElapsedSeconds(transcribe.isPending, transcribe.submittedAt)
  const correcting = useElapsedSeconds(correct.isPending, correct.submittedAt)
  const result = useRef<HTMLHeadingElement>(null)
  // Read once: the flag, and the reason the transcription failed when the recording was sent.
  const [arrival] = useState(() => ({
    auto: readAutoCorrect(location.state),
    reason: readUnavailableReason(location.state),
  }))
  const wantsCorrection = useRef(arrival.auto)
  const consumed = useRef(false)
  // `?unit=ID`: the talk is the final task of a scenario unit (module H); the way back goes there.
  const unitId = unitFromParam(new URLSearchParams(location.search).get('unit'))
  const production: Production | undefined = query.data
  const status = production?.transcription_status ?? null

  // The browser keeps the router state across a reload: clear it at once, so a reload never
  // starts a correction by itself (D-142). The ref guard covers StrictMode's second effect run.
  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])

  function startCorrection() {
    if (correct.isPending) return
    // A `not_transcribed` refusal (another tab, a stale page) reads the production again.
    correct.mutate(id)
  }

  // Arrived from the recording page: correct once the transcription is known to be there.
  useEffect(() => {
    if (production === undefined || !wantsCorrection.current) return
    if (production.kind !== 'speaking' || status === 'pending') return
    wantsCorrection.current = false
    if (status === 'ok' && !production.corrected) correct.mutate(id)
  }, [production, status, correct, id])

  const done = correct.isSuccess || transcribe.isSuccess
  // A correction completes the unit's final step: its page is read again on return.
  const refreshUnits = useInvalidateUnits()
  useEffect(() => {
    if (unitId !== null && done) refreshUnits()
  }, [unitId, done, refreshUnits])
  useEffect(() => {
    if (done) result.current?.focus()
  }, [done])

  if (query.isError && query.error instanceof ApiError && query.error.status === 404) {
    return (
      <Message title={t('speaking.detail.title')}>
        <Notice tone="danger" role="alert">
          {t('errors.production_not_found')}
        </Notice>
        <p>
          <Link to="/speaking/history">{t('speaking.detail.allSpeeches')}</Link>
        </p>
      </Message>
    )
  }
  if (production !== undefined && production.kind === 'consolidation') {
    return <Navigate to={`/consolidation/attempts/${production.id}`} replace />
  }
  // A written text opened here (a review error leads to `/writing/:id`, a spoken answer to this
  // page): the other page shows it.
  if (production !== undefined && production.kind === 'writing') {
    return <Navigate to={`/writing/${production.id}`} replace />
  }
  if (production !== undefined && production.kind !== 'speaking') {
    return (
      <Message title={t('speaking.detail.title')}>
        <Notice tone="warning" role="alert">
          {t('speaking.detail.notSpeaking')}
        </Notice>
        <p className="link-row">
          <Link to="/errors">{t('speaking.detail.errorLog')}</Link>
          <Link to="/speaking/history">{t('speaking.detail.allSpeeches')}</Link>
        </p>
      </Message>
    )
  }

  const corrected = correct.data?.status === 'ok' ? correct.data : undefined
  const failedTranscription = transcribe.data?.transcription.status === 'unavailable'
  const reason = failedTranscription
    ? (transcribe.data?.transcription.reason ?? null)
    : arrival.reason
  const unavailable = status === 'pending' && (failedTranscription || arrival.reason !== null)
  const silent = status === 'silence' || codeOf(correct.error) === 'nothing_to_correct'
  const correctionError =
    correct.isError &&
    !['already_corrected', 'not_transcribed', 'nothing_to_correct', 'text_too_long'].includes(
      codeOf(correct.error) ?? '',
    )
      ? correct.error
      : null

  let announcement = ''
  if (corrected !== undefined && production?.corrected) {
    announcement =
      corrected.errors.length === 0
        ? t('speaking.detail.readyNoErrors')
        : t('speaking.detail.ready', { count: corrected.errors.length })
  }

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('speaking.detail.title')}</PageTitle>
        {production !== undefined && (
          <p className="muted">{formatDateTime(production.created_at, i18n.language)}</p>
        )}
        {production?.prompt_text != null && (
          <p>
            <strong>{t('speaking.detail.topic')}</strong> <span lang="en">{production.prompt_text}</span>
          </p>
        )}
        <p className="link-row">
          {unitId !== null && <Link to={`/curriculum/units/${unitId}`}>{t('curriculum.backToUnit')}</Link>}
          <Link to="/speaking">{t('speaking.detail.another')}</Link>
          <Link to="/speaking/history">{t('speaking.detail.allSpeeches')}</Link>
        </p>
      </section>

      {query.isPending && <p className="muted">{t('speaking.detail.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {production !== undefined && (
        <>
          <section className="card" aria-labelledby="speech-recording">
            <h2 id="speech-recording">{t('speaking.detail.recording')}</h2>
            {production.audio_url !== null ? (
              // The server answers `Range`: the controls can seek.
              <audio
                controls
                preload="metadata"
                src={production.audio_url}
                aria-label={t('speaking.detail.recording')}
                className="recorder__player"
              />
            ) : (
              <Notice tone="warning">{t('speaking.detail.noAudio')}</Notice>
            )}
          </section>

          <section className="card" aria-labelledby="speech-result">
            <h2 id="speech-result" ref={result} tabIndex={-1}>
              {t('speaking.detail.result')}
            </h2>
            <div className="visually-hidden" role="status" aria-live="polite">
              {announcement}
            </div>

            {silent && (
              <>
                <Notice tone="warning">{t('speaking.detail.silence')}</Notice>
                <p>
                  <Link to="/speaking">{t('speaking.detail.recordAgain')}</Link>
                </p>
              </>
            )}

            {!silent && status === 'pending' && production.audio_url !== null && (
              <>
                <p className={unavailable ? 'form-message form-message--warn' : undefined}>
                  {unavailable
                    ? t('speaking.detail.unavailable', { reason: aiReasonText(t, reason) })
                    : t('speaking.detail.notTranscribed')}
                </p>
                <p>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={transcribe.isPending || query.isFetching}
                    onClick={() =>
                      transcribe.mutate(id, {
                        onSuccess: (done) => {
                          if (done.transcription.status === 'ok') startCorrection()
                        },
                      })
                    }
                  >
                    {transcribe.isPending
                      ? t('speaking.detail.transcribing', { seconds: transcribing })
                      : unavailable
                        ? t('speaking.detail.tryAgain')
                        : t('speaking.detail.transcribe')}
                  </button>
                </p>
              </>
            )}
            {/* Transcribed meanwhile (409): the production is read again, nothing to say. */}
            {transcribe.isError && codeOf(transcribe.error) !== 'already_transcribed' && (
              <ErrorText error={transcribe.error} />
            )}

            {!silent && status === 'ok' && !production.corrected && (
              <>
                <h3>{t('speaking.detail.heard')}</h3>
                <p lang="en" className="correction-text">
                  {production.text}
                </p>
                <p className="muted">{t('correction.heardNote')}</p>
                <div role="status">
                  {correct.isPending ? (
                    <p>{t('speaking.detail.checkingHint')}</p>
                  ) : (
                    <Notice tone="warning">
                      {notCorrectedText(t, correct.data, correct.error)}
                    </Notice>
                  )}
                </div>
                {correctionError !== null && !correct.isPending && <ErrorText error={correctionError} />}
                {codeOf(correct.error) !== 'text_too_long' && (
                  <p>
                    <button
                      type="button"
                      className="button button--primary"
                      onClick={startCorrection}
                      disabled={correct.isPending}
                    >
                      {correct.isPending
                        ? t('speaking.detail.checking', { seconds: correcting })
                        : correct.data !== undefined || correct.isError
                          ? t('speaking.detail.tryAgain')
                          : t('speaking.detail.correct')}
                    </button>
                  </p>
                )}
              </>
            )}

            {status === 'ok' && production.corrected && (
              <div aria-label={t('speaking.detail.correctionLabel')}>
                <CorrectionView
                  text={production.text}
                  feedback={production.feedback}
                  errors={corrected?.errors}
                  targets={production.targets}
                  proposedCategories={corrected?.proposed_categories}
                />
              </div>
            )}
            <p className="muted field-hint">{t('speaking.privacy')}</p>
          </section>
        </>
      )}
    </div>
  )
}

export function SpeakingDetailPage() {
  const params = useParams()
  const id = Number(params.id)
  const { t } = useTranslation()
  if (!Number.isInteger(id) || id <= 0) {
    return (
      <Message title={t('speaking.detail.title')}>
        <Notice tone="danger" role="alert">
          {t('errors.production_not_found')}
        </Notice>
        <p>
          <Link to="/speaking/history">{t('speaking.detail.allSpeeches')}</Link>
        </p>
      </Message>
    )
  }
  // Keyed by the production: moving to another one starts the page afresh (state, refs, mutations).
  return <SpeakingDetail key={id} id={id} />
}
