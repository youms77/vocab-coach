import { useEffect, useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { ApiError } from '../../api/client'
import { useDecks } from '../../api/library'
import {
  TRIAGE_DECISIONS,
  useDecide,
  useTriage,
  type TriageCounts,
  type TriageDecision,
  type TriageEntry,
} from '../../api/triage'
import { isTyping } from '../../components/keyboard'
import { ErrorText } from '../settings/ErrorText'

function TermCard({
  entry,
  decision,
  current,
  onDecide,
}: {
  entry: TriageEntry
  decision: TriageDecision | undefined
  current: boolean
  onDecide: (decision: TriageDecision) => void
}) {
  const { t } = useTranslation()
  const name = useId()
  return (
    <li
      className={current ? 'triage-card triage-card--current' : 'triage-card'}
      data-item-id={entry.item_id}
    >
      <fieldset>
        <legend>
          <span className="triage-card__term">{entry.term}</span>{' '}
          <span className="muted">({t(`library.type.${entry.item_type}`)})</span>
        </legend>
        {entry.sentence !== null && <p className="triage-card__sentence">“{entry.sentence}”</p>}
        {entry.decks.length > 0 && (
          <p className="muted">{entry.decks.map((d) => d.name).join(', ')}</p>
        )}
        {current && <p className="muted triage-card__hint">{t('triage.shortcutHint')}</p>}
        <div className="triage-choices">
          {TRIAGE_DECISIONS.map((value, index) => (
            <label key={value} className={`triage-choice triage-choice--${value}`}>
              <input
                type="radio"
                name={name}
                value={value}
                checked={decision === value}
                onChange={() => onDecide(value)}
              />
              <span>
                {index + 1}. {t(`triage.decision.${value}`)}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
    </li>
  )
}

export function TriagePage() {
  const { t } = useTranslation()
  const deckField = useId()
  const [params, setParams] = useSearchParams()
  const fromUrl = Number(params.get('deck'))
  const deckId = Number.isInteger(fromUrl) && fromUrl > 0 ? fromUrl : null
  const decks = useDecks()
  const triage = useTriage(deckId)
  const decide = useDecide()
  const [decisions, setDecisions] = useState<Record<number, TriageDecision>>({})
  const [counts, setCounts] = useState<TriageCounts | null>(null)

  const entries = useMemo(() => triage.data ?? [], [triage.data])
  // Decisions for terms that left the list (refetch after a 409) are dropped.
  const chosen = entries.filter((e) => decisions[e.item_id] !== undefined)
  const firstOpen = entries.find((e) => decisions[e.item_id] === undefined)

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) return
      const index = ['1', '2', '3'].indexOf(event.key)
      if (index < 0 || isTyping(event.target)) return
      // The focused card if any, else the first term without a decision.
      const card = event.target instanceof HTMLElement ? event.target.closest('[data-item-id]') : null
      const focusedId = card instanceof HTMLElement ? Number(card.dataset.itemId) : null
      const entry = entries.find((e) => e.item_id === focusedId) ?? firstOpen
      if (entry === undefined) return
      event.preventDefault()
      setDecisions((previous) => ({ ...previous, [entry.item_id]: TRIAGE_DECISIONS[index]! }))
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [entries, firstOpen])

  function submit() {
    if (chosen.length === 0) return
    setCounts(null)
    decide.mutate(
      chosen.map((e) => ({ item_id: e.item_id, decision: decisions[e.item_id]! })),
      {
        onSuccess: (result) => {
          setCounts(result)
          setDecisions({})
        },
      },
    )
  }

  function changeDeck(value: string) {
    setDecisions({})
    setCounts(null)
    setParams(value === '' ? {} : { deck: value })
  }

  return (
    <div className="library-page">
      <section className="hero">
        <h1>{t('triage.title')}</h1>
        <p className="muted">{t('triage.intro')}</p>
        <p>
          <Link to="/library">{t('library.back')}</Link>
        </p>
      </section>
      <section className="card" aria-labelledby="triage-list-title">
        <h2 id="triage-list-title">{t('triage.listTitle')}</h2>
        <div className="field">
          <label htmlFor={deckField}>{t('library.filters.deck')}</label>
          <select id={deckField} value={deckId ?? ''} onChange={(e) => changeDeck(e.target.value)}>
            <option value="">{t('library.filters.any')}</option>
            {decks.data?.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name}
              </option>
            ))}
          </select>
        </div>
        {counts !== null && (
          <p className="form-message form-message--ok" role="status">
            {t('triage.done', { learn: counts.learn, unsure: counts.unsure, known: counts.known })}
          </p>
        )}
        {triage.isPending && <p className="muted">{t('library.loading')}</p>}
        {triage.isError && <ErrorText error={triage.error} />}
        {triage.isSuccess && entries.length === 0 && (
          <p className="muted">
            {t('triage.empty')} <Link to="/import">{t('triage.toImport')}</Link>
          </p>
        )}
        {entries.length > 0 && (
          <>
            <p className="muted">{t('triage.count', { count: entries.length })}</p>
            <ul className="triage-list">
              {entries.map((entry) => (
                <TermCard
                  key={entry.item_id}
                  entry={entry}
                  decision={decisions[entry.item_id]}
                  current={entry.item_id === firstOpen?.item_id}
                  onDecide={(value) => setDecisions({ ...decisions, [entry.item_id]: value })}
                />
              ))}
            </ul>
            <div className="triage-submit">
              <button
                type="button"
                className="button button--primary"
                disabled={decide.isPending || chosen.length === 0}
                onClick={submit}
              >
                {t('triage.submit', { count: chosen.length })}
              </button>
              {chosen.length > 0 && (
                <button type="button" className="button" onClick={() => setDecisions({})}>
                  {t('triage.clear')}
                </button>
              )}
            </div>
            {decide.isError && <ErrorText error={decide.error} />}
            {decide.error instanceof ApiError && decide.error.code === 'not_in_triage' && (
              <p className="muted">{t('triage.reloaded')}</p>
            )}
          </>
        )}
      </section>
    </div>
  )
}
