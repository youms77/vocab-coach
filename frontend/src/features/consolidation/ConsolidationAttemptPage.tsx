import type { TFunction } from 'i18next'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'

import { ApiError } from '../../api/client'
import { useConsolidationTask, useTaskStatus } from '../../api/consolidation'
import {
  type ConsolidationSummary,
  type CorrectionResult,
  type Production,
  type ProductionTarget,
  useCorrectProduction,
  useProduction,
} from '../../api/productions'
import { useTranscribe } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { readAutoCorrect } from '../speaking/speakingState'
import { readUnavailableReason } from '../speaking/shadowTarget'
import { CorrectionView } from '../writing/CorrectionView'
import { Notice } from '../../components/Notice'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

type Group = 'correct' | 'wrong' | 'absent' | 'unknown'

function groupOf(target: ProductionTarget): Group {
  if (target.used === false) return 'absent'
  if (target.used === true && target.used_correctly === true) return 'correct'
  if (target.used === true && target.used_correctly === false) return 'wrong'
  return 'unknown'
}

/**
 * What the correction found about the terms of the task: used well (and, right after the
 * correction, which of them became active), used wrongly (the review card of each was reinforced)
 * and not used. A reload shows the groups from the stored checks; the "now active" and
 * "reinforced" marks come from the answer of the correction call only (D-235).
 */
export function TargetsSummary({
  targets,
  fresh,
}: {
  targets: ProductionTarget[]
  fresh: ConsolidationSummary | null | undefined
}) {
  const { t } = useTranslation()
  const activated = new Set(fresh?.activated_item_ids ?? [])
  const groups: Record<Group, ProductionTarget[]> = { correct: [], wrong: [], absent: [], unknown: [] }
  for (const target of targets) groups[groupOf(target)].push(target)
  const order: Group[] = ['correct', 'wrong', 'absent', 'unknown']

  return (
    <section className="card" aria-labelledby="attempt-summary">
      <h2 id="attempt-summary">{t('consolidation.summary.title')}</h2>
      <p>
        {t('consolidation.summary.counts', {
          total: targets.length,
          correct: groups.correct.length,
          wrong: groups.wrong.length,
          absent: groups.absent.length,
        })}
      </p>
      {order.map((group) =>
        groups[group].length === 0 ? null : (
          <div key={group}>
            <h3>
              {t(`consolidation.summary.groups.${group}`, { count: groups[group].length })}
            </h3>
            <p className="muted">{t(`consolidation.summary.hints.${group}`)}</p>
            <ul>
              {groups[group].map((target) => (
                <li key={target.lexical_item_id}>
                  <Link to={`/library/items/${target.lexical_item_id}`} lang="en">
                    {target.term}
                  </Link>
                  {group === 'correct' && activated.has(target.lexical_item_id) && (
                    <span className="badge">{t('consolidation.summary.nowActive')}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
      {fresh != null && (
        <p className="muted" role="status">
          {t('consolidation.summary.effect', {
            active: fresh.activated_item_ids.length,
            reinforced: fresh.reinforced_card_ids.length,
          })}
        </p>
      )}
    </section>
  )
}

function notCorrectedText(
  t: TFunction,
  result: CorrectionResult | undefined,
  error: unknown,
) {
  if (result?.status === 'incomplete') return t('consolidation.attempt.notCorrectedIncomplete')
  if (result?.status === 'unavailable') {
    return t('consolidation.attempt.notCorrectedReason', { reason: aiReasonText(t, result.reason) })
  }
  if (codeOf(error) === 'text_too_long') return t('speaking.detail.textTooLong')
  return t('consolidation.attempt.notCorrected')
}

function Attempt({ id }: { id: number }) {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const query = useProduction(id)
  const transcribe = useTranscribe()
  const correct = useCorrectProduction()
  const transcribing = useElapsedSeconds(transcribe.isPending, transcribe.submittedAt)
  const correcting = useElapsedSeconds(correct.isPending, correct.submittedAt)
  const heading = useRef<HTMLHeadingElement>(null)
  const [arrival] = useState(() => ({
    auto: readAutoCorrect(location.state),
    reason: readUnavailableReason(location.state),
  }))
  const wantsCorrection = useRef(arrival.auto)
  const consumed = useRef(false)
  const production: Production | undefined = query.data
  const status = production?.transcription_status ?? null
  const spoken = production?.modality === 'oral'

  const taskParam = Number(params.get('task'))
  const taskId = Number.isInteger(taskParam) && taskParam > 0 ? taskParam : 0
  const task = useConsolidationTask(taskId)
  const finish = useTaskStatus(taskId)

  // The browser keeps the router state across a reload: clear it at once, so a reload never starts
  // a correction by itself (D-142). The query string (the task) is kept.
  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])

  function startCorrection() {
    if (!correct.isPending) correct.mutate(id)
  }

  useEffect(() => {
    if (production === undefined || !wantsCorrection.current) return
    if (production.kind !== 'consolidation' || status === 'pending') return
    wantsCorrection.current = false
    if (status !== 'silence' && !production.corrected) correct.mutate(id)
  }, [production, status, correct, id])

  const done = correct.isSuccess || transcribe.isSuccess
  useEffect(() => {
    if (done) heading.current?.focus()
  }, [done])

  if (query.isError && query.error instanceof ApiError && query.error.status === 404) {
    return (
      <div className="consolidation-page">
        <PageTitle>{t('consolidation.attempt.title')}</PageTitle>
        <Notice tone="danger" role="alert">
          {t('errors.production_not_found')}
        </Notice>
        <p>
          <Link to="/consolidation">{t('consolidation.task.all')}</Link>
        </p>
      </div>
    )
  }
  // Another kind of production opened here: its own page shows it (writing redirects speaking).
  if (production !== undefined && production.kind !== 'consolidation') {
    return <Navigate to={`/writing/${production.id}`} replace />
  }

  const result = correct.data?.status === 'ok' ? correct.data : undefined
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
  const taskLink = taskId > 0 ? `/consolidation/tasks/${taskId}` : '/consolidation'

  let announcement = ''
  if (result !== undefined && production?.corrected) {
    announcement =
      result.errors.length === 0
        ? t('speaking.detail.readyNoErrors')
        : t('speaking.detail.ready', { count: result.errors.length })
  }
  const readyToCorrect = production !== undefined && !production.corrected && !silent && (!spoken || status === 'ok')

  return (
    <div className="consolidation-page">
      <section className="hero">
        <PageTitle>{t('consolidation.attempt.title')}</PageTitle>
        {production !== undefined && (
          <p className="muted">
            {formatDateTime(production.created_at, i18n.language)} ·{' '}
            {t(spoken ? 'consolidation.attempts.oral' : 'consolidation.attempts.written')}
          </p>
        )}
        <p className="link-row">
          <Link to={taskLink}>
            {taskId > 0 ? t('consolidation.attempt.backToTask') : t('consolidation.task.all')}
          </Link>
        </p>
      </section>

      {query.isPending && <p className="muted">{t('consolidation.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {production !== undefined && (
        <>
          {spoken && (
            <section className="card" aria-labelledby="attempt-recording">
              <h2 id="attempt-recording">{t('speaking.detail.recording')}</h2>
              {production.audio_url !== null ? (
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
          )}

          <section className="card" aria-labelledby="attempt-result">
            <h2 id="attempt-result" ref={heading} tabIndex={-1}>
              {t('consolidation.attempt.result')}
            </h2>
            <div className="visually-hidden" role="status" aria-live="polite">
              {announcement}
            </div>

            {silent && (
              <>
                <Notice tone="warning">{t('speaking.detail.silence')}</Notice>
                <p>
                  <Link to={taskLink}>{t('consolidation.attempt.recordAgain')}</Link>
                </p>
              </>
            )}

            {!silent && spoken && status === 'pending' && production.audio_url !== null && (
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
                        onSuccess: (finished) => {
                          if (finished.transcription.status === 'ok') startCorrection()
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
            {transcribe.isError && codeOf(transcribe.error) !== 'already_transcribed' && (
              <ErrorText error={transcribe.error} />
            )}

            {readyToCorrect && (
              <>
                <h3>{t(spoken ? 'speaking.detail.heard' : 'consolidation.attempt.yourText')}</h3>
                <p lang="en" className="correction-text">
                  {production.text}
                </p>
                {spoken && <p className="muted">{t('correction.heardNote')}</p>}
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
                          : t('consolidation.attempt.correct')}
                    </button>
                  </p>
                )}
              </>
            )}

            {production.corrected && (
              <div aria-label={t('speaking.detail.correctionLabel')}>
                <CorrectionView
                  text={production.text}
                  feedback={production.feedback}
                  errors={result?.errors}
                  targets={production.targets}
                  proposedCategories={result?.proposed_categories}
                />
              </div>
            )}
          </section>

          {production.corrected && production.targets.length > 0 && (
            <TargetsSummary targets={production.targets} fresh={result?.consolidation} />
          )}

          {production.corrected && task.data?.status === 'accepted' && (
            <section className="card" aria-labelledby="attempt-finish">
              <h2 id="attempt-finish">{t('consolidation.attempt.finishTitle')}</h2>
              <p className="muted">{t('consolidation.attempt.finishHint')}</p>
              <p className="today-actions">
                <button
                  type="button"
                  className="button button--primary"
                  disabled={finish.isPending}
                  onClick={() => finish.mutate('completed')}
                >
                  {t('consolidation.task.actions.completedYes')}
                </button>
                <Link to={taskLink} className="button">
                  {t('consolidation.attempt.another')}
                </Link>
              </p>
              {finish.isError && <ErrorText error={finish.error} />}
            </section>
          )}
          {production.corrected && task.data?.status === 'completed' && (
            <Notice tone="success" role="status">
              {t('consolidation.task.final.completed')}
            </Notice>
          )}
        </>
      )}
    </div>
  )
}

export function ConsolidationAttemptPage() {
  const params = useParams()
  const { t } = useTranslation()
  const id = Number(params.id)
  if (!Number.isInteger(id) || id <= 0) {
    return (
      <div className="consolidation-page">
        <PageTitle>{t('consolidation.attempt.title')}</PageTitle>
        <Notice tone="danger" role="alert">
          {t('errors.production_not_found')}
        </Notice>
        <p>
          <Link to="/consolidation">{t('consolidation.task.all')}</Link>
        </p>
      </div>
    )
  }
  // Keyed by the production: moving to another one starts the page afresh (state, refs, mutations).
  return <Attempt key={id} id={id} />
}
