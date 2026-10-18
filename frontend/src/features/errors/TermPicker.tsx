import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { TermRef } from '../../api/errors'
import { emptyFilters, useItems } from '../../api/library'

const MAX_RESULTS = 8

/**
 * Links an error to a term of the library: the term now linked (with "Unlink"), and a search field
 * (`GET /api/items?q=`) whose results are buttons. Controlled: the parent keeps the term.
 */
export function TermPicker({
  id,
  value,
  onChange,
}: {
  id: string
  value: TermRef | null
  onChange: (term: TermRef | null) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const trimmed = search.trim()
  const items = useItems({ ...emptyFilters, q: trimmed }, trimmed !== '')
  const results = trimmed === '' ? [] : (items.data?.items ?? []).slice(0, MAX_RESULTS)

  return (
    <div className="term-picker">
      <p className="term-picker__current">
        {value === null ? (
          <span className="muted">{t('errorLog.detail.noTerm')}</span>
        ) : (
          <>
            <Link to={`/library/items/${value.id}`} lang="en">
              {value.term}
            </Link>{' '}
            <button type="button" className="button button--small" onClick={() => onChange(null)}>
              {t('errorLog.detail.termUnlink')}
            </button>
          </>
        )}
      </p>
      <div className="field">
        <label htmlFor={id}>{t('errorLog.detail.termSearch')}</label>
        <input id={id} type="search" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div role="status">
        {trimmed !== '' && items.isFetching && items.data === undefined && (
          <p className="muted">{t('errorLog.detail.termSearching')}</p>
        )}
        {trimmed !== '' && items.isSuccess && results.length === 0 && (
          <p className="muted">{t('errorLog.detail.termNoMatch')}</p>
        )}
      </div>
      {results.length > 0 && (
        <ul className="term-picker__results">
          {results.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="button button--small"
                onClick={() => {
                  onChange({ id: item.id, term: item.term })
                  setSearch('')
                }}
              >
                {t('errorLog.detail.termPick', { term: item.term })}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
