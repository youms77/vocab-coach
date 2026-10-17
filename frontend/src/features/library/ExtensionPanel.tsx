import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import {
  EXTENSION_DEFAULT,
  EXTENSION_MAX,
  EXTENSION_MIN,
  useExtendDeck,
  type ExtensionResult,
} from '../../api/enrichment'
import type { Deck } from '../../api/library'
import { ErrorText } from '../settings/ErrorText'

function Result({ deck, result }: { deck: Deck; result: ExtensionResult }) {
  const { t } = useTranslation()
  if (result.status !== 'ok') {
    const reason =
      result.status === 'incomplete'
        ? t('extension.incomplete')
        : t(`aiReasons.${result.reason ?? 'all_failed'}`)
    return (
      <p className="form-message form-message--warn" role="status">
        {t('extension.failed', { reason })}
      </p>
    )
  }
  const terms = new Map(result.created.map((item) => [item.id, item.term]))
  return (
    <div className="form-message form-message--ok" role="status">
      <p>{t('extension.created', { count: result.created.length })}</p>
      {result.created.length > 0 && (
        <>
          <p>{result.created.map((item) => item.term).join(' · ')}</p>
          <p>
            <Link to={`/triage?deck=${deck.id}`}>{t('extension.sortNow')}</Link>
          </p>
        </>
      )}
      {(result.dropped_existing > 0 || result.dropped_in_batch > 0) && (
        <p className="muted">
          {t('extension.dropped', {
            existing: result.dropped_existing,
            repeated: result.dropped_in_batch,
          })}
        </p>
      )}
      {result.possible_duplicates.length > 0 && (
        <>
          <p>{t('extension.possibleDuplicates')}</p>
          <ul>
            {result.possible_duplicates.map((d) => (
              <li key={d.item_id}>
                {terms.get(d.item_id) ?? d.item_id} ≈{' '}
                {d.candidates.map((c, i) => (
                  <span key={c.id}>
                    {i > 0 && ', '}
                    <Link to={`/library/items/${c.id}`}>{c.term}</Link>
                  </span>
                ))}
              </li>
            ))}
          </ul>
          <p>
            <Link to="/duplicates">{t('library.duplicatesLink')}</Link>
          </p>
        </>
      )}
    </div>
  )
}

/** List extension (SPEC module A): the AI suggests related terms, which wait for triage. */
export function ExtensionPanel({ deck }: { deck: Deck }) {
  const { t } = useTranslation()
  const id = useId()
  const extend = useExtendDeck(deck.id)
  const [open, setOpen] = useState(false)
  const [count, setCount] = useState(String(EXTENSION_DEFAULT))
  const value = Number(count)
  const valid = Number.isInteger(value) && value >= EXTENSION_MIN && value <= EXTENSION_MAX

  function submit(event: FormEvent) {
    event.preventDefault()
    if (valid) extend.mutate(value)
  }

  if (!open) {
    return (
      <button type="button" className="button" onClick={() => setOpen(true)}>
        {t('extension.open')}
      </button>
    )
  }
  return (
    <div className="extension">
      <form className="inline-fields" onSubmit={submit}>
        <div className="field">
          <label htmlFor={`${id}-count`}>{t('extension.count')}</label>
          <input
            id={`${id}-count`}
            type="number"
            min={EXTENSION_MIN}
            max={EXTENSION_MAX}
            step={1}
            value={count}
            onChange={(e) => setCount(e.target.value)}
            aria-describedby={`${id}-hint`}
          />
        </div>
        <button
          type="submit"
          className="button button--primary"
          disabled={!valid || extend.isPending}
        >
          {extend.isPending ? t('extension.working') : t('extension.submit')}
        </button>
        <button type="button" className="button" onClick={() => setOpen(false)}>
          {t('library.cancel')}
        </button>
      </form>
      <p className="field-hint" id={`${id}-hint`}>
        {t('extension.hint', { min: EXTENSION_MIN, max: EXTENSION_MAX })}
      </p>
      {extend.isError && <ErrorText error={extend.error} />}
      {extend.isSuccess && <Result deck={deck} result={extend.data} />}
    </div>
  )
}
