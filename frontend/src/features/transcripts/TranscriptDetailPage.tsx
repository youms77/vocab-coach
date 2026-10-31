import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '../../api/client'
import { type CorrectionResult, type Production, useProduction } from '../../api/productions'
import { type TranscriptBody, useAnalyseTranscript } from '../../api/transcripts'
import { PageTitle } from '../../components/PageTitle'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { formatDateTime } from '../session/format'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { CorrectionView } from '../writing/CorrectionView'
import { forget, recall } from './transcriptMemory'
import { TranscriptInputForm } from './TranscriptInputForm'
import { useTranscriptInput } from './useTranscriptInput'
import { Notice } from '../../components/Notice'

/** "Paste the conversation again": the same paste and choice as the first page, then the analysis. */
function PasteAgain({
  pending,
  error,
  onAnalyse,
}: {
  pending: boolean
  error: unknown
  onAnalyse: (body: TranscriptBody) => void
}) {
  const { t } = useTranslation()
  const input = useTranscriptInput()
  return (
    <div className="transcript-again">
      <TranscriptInputForm input={input} readOnly={pending} />
      <p>
        <button
          type="button"
          className="button button--primary"
          disabled={!input.ready || pending}
          onClick={() => input.user !== null && onAnalyse({ text: input.text, user: input.user })}
        >
          {t('transcripts.detail.analyseWithPaste')}
        </button>
      </p>
      {error !== null && !pending && <ErrorText error={error} />}
    </div>
  )
}

function NotAnalysed({
  result,
  error,
  pending,
  seconds,
  hasMemory,
  onAnalyse,
}: {
  result: CorrectionResult | undefined
  error: unknown
  pending: boolean
  seconds: number
  hasMemory: boolean
  onAnalyse: (transcript?: TranscriptBody) => void
}) {
  const { t } = useTranslation()
  const [pasting, setPasting] = useState(false)
  let message = t('transcripts.detail.notAnalysed')
  if (result?.status === 'incomplete') message = t('transcripts.detail.notAnalysedIncomplete')
  else if (result?.status === 'unavailable') {
    message = t('transcripts.detail.notAnalysedReason', { reason: aiReasonText(t, result.reason) })
  }
  return (
    <section className="card" aria-labelledby="not-analysed-title">
      <h2 id="not-analysed-title" className="visually-hidden">
        {t('transcripts.detail.statusTitle')}
      </h2>
      <div role="status">
        {pending ? (
          <>
            <p>{t('transcripts.detail.analysing', { seconds })}</p>
            <p className="muted">{t('transcripts.detail.analysingHint')}</p>
          </>
        ) : (
          <Notice tone="warning">{message}</Notice>
        )}
      </div>
      {error !== null && !pending && !pasting && <ErrorText error={error} />}
      {!hasMemory && !pending && (
        <p className="muted">{t('transcripts.detail.noMemory')}</p>
      )}
      <p className="transcript-actions">
        {hasMemory ? (
          <button type="button" className="button button--primary" disabled={pending} onClick={() => onAnalyse()}>
            {pending ? t('transcripts.detail.analysingShort', { seconds }) : t('transcripts.detail.tryAgain')}
          </button>
        ) : (
          <>
            <button type="button" className="button" disabled={pending} onClick={() => onAnalyse()}>
              {pending && !pasting
                ? t('transcripts.detail.analysingShort', { seconds })
                : t('transcripts.detail.withoutContext')}
            </button>
            <button
              type="button"
              className="button"
              aria-expanded={pasting}
              disabled={pending}
              onClick={() => setPasting(!pasting)}
            >
              {t('transcripts.detail.pasteAgain')}
            </button>
          </>
        )}
      </p>
      {!hasMemory && pasting && (
        <PasteAgain pending={pending} error={error} onAnalyse={(body) => onAnalyse(body)} />
      )}
    </section>
  )
}

/**
 * One transcript and its analysis. Arriving from `/transcripts` (router state `autoAnalyse`) the
 * page starts the analysis by itself, once, sending the pasted conversation kept in memory. After
 * a reload the memory is empty and nothing starts by itself: the user chooses to analyse without
 * the other speaker's context, or to paste the conversation again (D-151).
 */
export function TranscriptDetailPage() {
  const { t, i18n } = useTranslation()
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const id = Number(params.id)
  const valid = Number.isInteger(id) && id > 0
  const query = useProduction(valid ? id : 0, valid)
  const analyse = useAnalyseTranscript(forget)
  const elapsed = useElapsedSeconds(analyse.isPending, analyse.submittedAt)
  const started = useRef(false)
  const autoAnalyse = (location.state as { autoAnalyse?: boolean } | null)?.autoAnalyse === true
  const production = query.data

  const run = (transcript?: TranscriptBody) => {
    if (analyse.isPending) return
    // Without an explicit paste, the one kept in memory (if any) gives the context.
    analyse.mutate({ id, transcript: transcript ?? recall(id) })
  }

  useEffect(() => {
    if (production === undefined || started.current || !autoAnalyse) return
    started.current = true
    // Clear the flag at once: a reload must not start an analysis by itself.
    navigate(location.pathname, { replace: true, state: null })
    if (!production.corrected) analyse.mutate({ id, transcript: recall(id) })
  }, [production, autoAnalyse, navigate, location.pathname, analyse, id])

  if (!valid || (query.isError && query.error instanceof ApiError && query.error.status === 404)) {
    return (
      <div className="transcript-page">
        <PageTitle>{t('transcripts.detail.title')}</PageTitle>
        <Notice tone="danger" role="alert">
          {t('errors.production_not_found')}
        </Notice>
        <p>
          <Link to="/transcripts/history">{t('transcripts.detail.allTranscripts')}</Link>
        </p>
      </div>
    )
  }

  const result = analyse.data?.status === 'ok' ? analyse.data : undefined

  return (
    <div className="transcript-page">
      <section className="hero">
        <PageTitle>{t('transcripts.detail.title')}</PageTitle>
        {production !== undefined && (
          <>
            <p lang="en">
              <strong>{production.prompt_text ?? t('transcripts.history.untitled')}</strong>
            </p>
            <p className="muted">
              {formatDateTime(production.created_at, i18n.language)} ·{' '}
              {t('transcripts.detail.words', { count: production.word_count })}
            </p>
            <p className="muted">{t('transcripts.detail.onlyYours')}</p>
          </>
        )}
        <p className="link-row">
          <Link to="/transcripts">{t('transcripts.detail.analyseAnother')}</Link>
          <Link to="/transcripts/history">{t('transcripts.detail.allTranscripts')}</Link>
        </p>
      </section>

      {query.isPending && valid && <p className="muted">{t('transcripts.detail.loading')}</p>}
      {query.isError && <ErrorText error={query.error} />}

      {production !== undefined && (
        <>
          <Announcement production={production} result={result} />
          {!production.corrected && (
            <NotAnalysed
              result={analyse.data}
              error={analyse.isError ? analyse.error : null}
              pending={analyse.isPending}
              seconds={elapsed}
              hasMemory={recall(id) !== undefined}
              onAnalyse={run}
            />
          )}
          <section className="card" aria-label={t('transcripts.detail.analysisLabel')}>
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

function Announcement({ production, result }: { production: Production; result: CorrectionResult | undefined }) {
  const { t } = useTranslation()
  // Said once, when this visit has just produced the analysis (not when a stored one is opened).
  let message = ''
  if (result?.status === 'ok' && production.corrected) {
    message =
      result.errors.length === 0
        ? t('transcripts.detail.readyNoErrors')
        : t('transcripts.detail.ready', { count: result.errors.length })
  }
  return (
    <div className="visually-hidden" role="status" aria-live="polite">
      {message}
    </div>
  )
}
