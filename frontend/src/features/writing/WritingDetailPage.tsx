import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import {
  type CorrectionResult,
  type Production,
  useCorrectProduction,
  useProduction,
} from '../../api/productions'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { CorrectionView } from './CorrectionView'

/** Why the text is not corrected: the AI's failure (a 200 answer) or a refused request. */
function NotCorrected({
  result,
  error,
  pending,
  seconds,
  onTryAgain,
}: {
  result: CorrectionResult | undefined
  error: unknown
  pending: boolean
  seconds: number
  onTryAgain: () => void
}) {
  const { t } = useTranslation()
  let message = t('writing.detail.notCorrected')
  if (result?.status === 'incomplete') message = t('writing.detail.notCorrectedIncomplete')
  else if (result?.status === 'unavailable') {
    message = t('writing.detail.notCorrectedReason', { reason: aiReasonText(t, result.reason) })
  }
  return (
    <section className="card" aria-labelledby="not-corrected-title">
      <h2 id="not-corrected-title" className="visually-hidden">
        {t('writing.detail.statusTitle')}
      </h2>
      <div role="status">
        {pending ? (
          <p>{t('writing.detail.checkingHint')}</p>
        ) : (
          <p className="form-message form-message--warn">{message}</p>
        )}
      </div>
      {error !== null && !pending && <ErrorText error={error} />}
      <p>
        <button type="button" className="button button--primary" onClick={onTryAgain} disabled={pending}>
          {pending ? t('writing.checking', { seconds }) : t('writing.detail.tryAgain')}
        </button>
      </p>
    </section>
  )
}

function Announcement({ production, result }: { production: Production; result: CorrectionResult | undefined }) {
  const { t } = useTranslation()
  // Said once, when this visit has just produced the correction (not when a stored one is opened).
  let message = ''
  if (result?.status === 'ok' && production.corrected) {
    message =
      result.errors.length === 0
        ? t('writing.detail.readyNoErrors')
        : t('writing.detail.ready', { count: result.errors.length })
  }
  return (
    <div className="visually-hidden" role="status" aria-live="polite">
      {message}
    </div>
  )
}

/**
 * One text and its correction. Arriving from `/writing` (router state `autoCorrect`) the page
 * starts the correction by itself, once; opened from the history or after a reload it only shows
 * what is stored and offers "Try again" when there is no correction yet.
 */
export function WritingDetailPage() {
  const { t, i18n } = useTranslation()
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const query = useProduction(valid ? id : 0, valid)
  const correct = useCorrectProduction()
  const elapsed = useElapsedSeconds(correct.isPending, correct.submittedAt)
  const started = useRef(false)
  const autoCorrect = (location.state as { autoCorrect?: boolean } | null)?.autoCorrect === true
  const production = query.data

  const run = () => {
    if (!correct.isPending) correct.mutate(id)
  }

  useEffect(() => {
    if (production === undefined || started.current || !autoCorrect) return
    started.current = true
    // Clear the flag at once: a reload must not start a correction again by itself.
    navigate(location.pathname, { replace: true, state: null })
    if (!production.corrected) correct.mutate(id)
  }, [production, autoCorrect, navigate, location.pathname, correct, id])

  if (!valid || (query.isError && query.error instanceof ApiError && query.error.status === 404)) {
    return (
      <div className="writing-page">
        <PageTitle>{t('writing.detail.title')}</PageTitle>
        <p className="form-message form-message--error" role="alert">
          {t('errors.production_not_found')}
        </p>
        <p>
          <Link to="/writing/history">{t('writing.detail.allTexts')}</Link>
        </p>
      </div>
    )
  }

  const result = correct.data?.status === 'ok' ? correct.data : undefined

  return (
    <div className="writing-page">
      <section className="hero">
        <PageTitle>{t('writing.detail.title')}</PageTitle>
        {production !== undefined && (
          <p className="muted">
            {formatDateTime(production.created_at, i18n.language)} ·{' '}
            {t('writing.text.words', { count: production.word_count })}
          </p>
        )}
        {production?.prompt_text != null && (
          <p>
            <strong>{t('writing.detail.topic')}</strong> <span lang="en">{production.prompt_text}</span>
          </p>
        )}
        <p className="link-row">
          <Link to="/writing">{t('writing.detail.writeAnother')}</Link>
          <Link to="/writing/history">{t('writing.detail.allTexts')}</Link>
        </p>
      </section>

      {query.isPending && valid && <p className="muted">{t('writing.detail.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {production !== undefined && (
        <>
          <Announcement production={production} result={result} />
          {!production.corrected && (
            <NotCorrected
              result={correct.data}
              error={correct.isError ? correct.error : null}
              pending={correct.isPending}
              seconds={elapsed}
              onTryAgain={run}
            />
          )}
          <section className="card" aria-label={t('writing.detail.correctionLabel')}>
            <CorrectionView
              text={production.text}
              feedback={production.feedback}
              errors={result?.errors}
              targets={production.targets}
              proposedCategories={result?.proposed_categories}
            />
          </section>
        </>
      )}
    </div>
  )
}
