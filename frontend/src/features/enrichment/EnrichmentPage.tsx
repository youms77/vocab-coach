import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import {
  usePendingEnrichment,
  useRunEnrichment,
  type RunBody,
  type UnavailableReason,
} from '../../api/enrichment'
import { useDecks } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'
import { Notice } from '../../components/Notice'

const LIST_LIMIT = 50

interface Totals {
  batches: number
  generated: number
  needsCompletion: number
  remaining: number | null
}

type Outcome =
  | { kind: 'done' }
  | { kind: 'stopped' }
  | { kind: 'stalled' }
  | { kind: 'unavailable'; reason: UnavailableReason | null }
  | { kind: 'error'; error: unknown }

const noTotals: Totals = { batches: 0, generated: 0, needsCompletion: 0, remaining: null }

/**
 * Batch enrichment: `POST /enrichment/run` does one batch (at most 5 terms); this page calls it
 * again while terms remain, the AI answers and the user has not asked to stop. An AI failure is a
 * report, not an error: the terms stay waiting and can get a sheet by hand (degraded mode).
 */
export function EnrichmentPage() {
  const { t } = useTranslation()
  const id = useId()
  const decks = useDecks()
  const [deckId, setDeckId] = useState<number | null>(null)
  const [includeIncomplete, setIncludeIncomplete] = useState(false)
  const pending = usePendingEnrichment(deckId, includeIncomplete)
  const run = useRunEnrichment()
  const [running, setRunning] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [totals, setTotals] = useState<Totals>(noTotals)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const stopRef = useRef(false)

  // Leaving the page ends the loop after the current batch (the server always finishes it).
  useEffect(
    () => () => {
      stopRef.current = true
    },
    [],
  )

  async function start() {
    const body: RunBody = { include_incomplete: includeIncomplete }
    if (deckId !== null) body.deck_id = deckId
    stopRef.current = false
    setStopping(false)
    setRunning(true)
    setOutcome(null)
    let sum = noTotals
    setTotals(sum)
    try {
      for (;;) {
        const report = await run.mutateAsync(body)
        const written = report.generated + report.needs_completion
        sum = {
          batches: sum.batches + 1,
          generated: sum.generated + report.generated,
          needsCompletion: sum.needsCompletion + report.needs_completion,
          remaining: report.remaining,
        }
        setTotals(sum)
        if (report.status === 'unavailable' || report.reason !== null) {
          setOutcome({ kind: 'unavailable', reason: report.reason })
          break
        }
        if (report.item_ids.length === 0 || report.remaining === 0) {
          setOutcome({ kind: 'done' })
          break
        }
        if (written === 0) {
          // Nothing could be written (every term changed meanwhile): do not spin.
          setOutcome({ kind: 'stalled' })
          break
        }
        if (stopRef.current) {
          setOutcome({ kind: 'stopped' })
          break
        }
      }
    } catch (error) {
      setOutcome({ kind: 'error', error })
    } finally {
      setRunning(false)
      setStopping(false)
    }
  }

  const count = pending.data?.count ?? 0

  return (
    <div className="library-page">
      <p>
        <Link to="/library">{t('library.back')}</Link>
      </p>
      <section className="hero">
        <h1>{t('enrichment.title')}</h1>
        <p className="muted">{t('enrichment.intro')}</p>
      </section>
      <section className="card" aria-labelledby="enrichment-run-title">
        <h2 id="enrichment-run-title">{t('enrichment.runTitle')}</h2>
        <div className="library-form">
          <div className="field">
            <label htmlFor={`${id}-deck`}>{t('library.filters.deck')}</label>
            <select
              id={`${id}-deck`}
              value={deckId ?? ''}
              disabled={running}
              onChange={(e) => setDeckId(e.target.value === '' ? null : Number(e.target.value))}
            >
              <option value="">{t('enrichment.allDecks')}</option>
              {decks.data?.map((deck) => (
                <option key={deck.id} value={deck.id}>
                  {deck.name}
                </option>
              ))}
            </select>
          </div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={includeIncomplete}
              disabled={running}
              onChange={(e) => setIncludeIncomplete(e.target.checked)}
            />
            {t('enrichment.includeIncomplete')}
          </label>
        </div>
        {pending.isSuccess && (
          <p role="status">
            {count === 0 ? t('enrichment.nothing') : t('enrichment.waiting', { count })}
          </p>
        )}
        {pending.isError && <ErrorText error={pending.error} />}
        <div className="confirm">
          <button
            type="button"
            className="button button--primary"
            disabled={running || count === 0}
            onClick={() => void start()}
          >
            {t('enrichment.start')}
          </button>
          {running && (
            <button
              type="button"
              className="button"
              disabled={stopping}
              onClick={() => {
                stopRef.current = true
                setStopping(true)
              }}
            >
              {stopping ? t('enrichment.stopping') : t('enrichment.stop')}
            </button>
          )}
        </div>
        {running && (
          <p className="muted" aria-live="polite">
            <span className="spinner" aria-hidden="true" />{' '}
            {t('enrichment.working', { batch: totals.batches + 1 })}
          </p>
        )}
        {totals.batches > 0 && (
          <p role="status">
            {t('enrichment.progress', {
              generated: totals.generated,
              needsCompletion: totals.needsCompletion,
              remaining: totals.remaining ?? 0,
            })}
          </p>
        )}
        {outcome?.kind === 'done' && (
          <Notice tone="success" role="status">
            {t('enrichment.done')}
          </Notice>
        )}
        {outcome?.kind === 'stopped' && (
          <Notice tone="warning" role="status">
            {t('enrichment.stopped')}
          </Notice>
        )}
        {outcome?.kind === 'stalled' && (
          <Notice tone="warning" role="status">
            {t('enrichment.stalled')}
          </Notice>
        )}
        {outcome?.kind === 'error' && <ErrorText error={outcome.error} />}
        {totals.needsCompletion > 0 && !running && (
          <Notice tone="warning">{t('enrichment.skeletons')}</Notice>
        )}
        {outcome?.kind === 'unavailable' && (
          <div className="form-message form-message--warn degraded" role="alert">
            <p>
              <strong>{t('enrichment.degradedTitle')}</strong>{' '}
              {t('enrichment.degradedReason', {
                reason: t(`aiReasons.${outcome.reason ?? 'all_failed'}`),
              })}
            </p>
            <p>{t('enrichment.degraded')}</p>
            <p>
              <Link to="/settings">{t('aiBanner.link')}</Link>
            </p>
          </div>
        )}
      </section>
      {pending.isSuccess && count > 0 && (
        <section className="card" aria-labelledby="enrichment-list-title">
          <h2 id="enrichment-list-title">{t('enrichment.listTitle')}</h2>
          <p className="muted">{t('enrichment.listHint')}</p>
          <ul className="pending-list">
            {pending.data.items.slice(0, LIST_LIMIT).map((item) => (
              <li key={item.item_id}>
                <Link to={`/library/items/${item.item_id}`}>{item.term}</Link>{' '}
                <span className="muted">({t(`library.status.${item.status}`)})</span>
              </li>
            ))}
          </ul>
          {count > LIST_LIMIT && (
            <p className="muted">{t('enrichment.more', { count: count - LIST_LIMIT })}</p>
          )}
        </section>
      )}
    </div>
  )
}
