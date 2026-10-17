import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import {
  ITEM_SORTS,
  ITEM_STATUSES,
  ITEM_TYPES,
  PAGE_SIZE,
  SHEET_STATES,
  emptyFilters,
  useDecks,
  useItems,
  type ItemFilters,
  type ItemSort,
  type ItemStatus,
  type ItemType,
  type SheetState,
} from '../../api/library'
import { ErrorText } from '../settings/ErrorText'
import { QuickAdd } from './QuickAdd'

function Filters({
  filters,
  onChange,
}: {
  filters: ItemFilters
  onChange: (next: ItemFilters) => void
}) {
  const { t } = useTranslation()
  const decks = useDecks()
  const id = useId()
  // Any change of a filter goes back to the first page.
  const set = (patch: Partial<ItemFilters>) => onChange({ ...filters, ...patch, page: 0 })

  return (
    <form className="library-filters" role="search" onSubmit={(e) => e.preventDefault()}>
      <div className="field">
        <label htmlFor={`${id}-q`}>{t('library.filters.search')}</label>
        <input
          id={`${id}-q`}
          type="search"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-deck`}>{t('library.filters.deck')}</label>
        <select
          id={`${id}-deck`}
          value={filters.deckId ?? ''}
          onChange={(e) => set({ deckId: e.target.value === '' ? null : Number(e.target.value) })}
        >
          <option value="">{t('library.filters.any')}</option>
          {decks.data?.map((deck) => (
            <option key={deck.id} value={deck.id}>
              {deck.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-domain`}>{t('library.filters.domain')}</label>
        <input
          id={`${id}-domain`}
          value={filters.domain}
          onChange={(e) => set({ domain: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-type`}>{t('library.filters.type')}</label>
        <select
          id={`${id}-type`}
          value={filters.itemType}
          onChange={(e) => set({ itemType: e.target.value as ItemType | '' })}
        >
          <option value="">{t('library.filters.any')}</option>
          {ITEM_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`library.type.${type}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-status`}>{t('library.filters.status')}</label>
        <select
          id={`${id}-status`}
          value={filters.status}
          onChange={(e) => set({ status: e.target.value as ItemStatus | '' })}
        >
          <option value="">{t('library.filters.any')}</option>
          {ITEM_STATUSES.map((status) => (
            <option key={status} value={status}>
              {t(`library.status.${status}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-sheet`}>{t('library.filters.sheet')}</label>
        <select
          id={`${id}-sheet`}
          value={filters.sheet}
          onChange={(e) => set({ sheet: e.target.value as SheetState | '' })}
        >
          <option value="">{t('library.filters.any')}</option>
          {SHEET_STATES.map((state) => (
            <option key={state} value={state}>
              {t(`library.sheet.${state}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-sort`}>{t('library.filters.sort')}</label>
        <select
          id={`${id}-sort`}
          value={filters.sort}
          onChange={(e) => set({ sort: e.target.value as ItemSort })}
        >
          {ITEM_SORTS.map((sort) => (
            <option key={sort} value={sort}>
              {t(`library.sort.${sort}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-order`}>{t('library.filters.order')}</label>
        <select
          id={`${id}-order`}
          value={filters.order}
          onChange={(e) => set({ order: e.target.value as 'asc' | 'desc' })}
        >
          <option value="asc">{t('library.filters.asc')}</option>
          <option value="desc">{t('library.filters.desc')}</option>
        </select>
      </div>
      <label className="checkbox-line">
        <input
          type="checkbox"
          checked={filters.includeArchived}
          onChange={(e) => set({ includeArchived: e.target.checked })}
        />
        {t('library.filters.archived')}
      </label>
    </form>
  )
}

export function LibraryPage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const initialDeck = Number(params.get('deck'))
  const [filters, setFilters] = useState<ItemFilters>({
    ...emptyFilters,
    deckId: Number.isInteger(initialDeck) && initialDeck > 0 ? initialDeck : null,
  })
  const items = useItems(filters)
  const total = items.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="library-page">
      <section className="hero">
        <h1>{t('library.title')}</h1>
        <p className="muted">{t('library.intro')}</p>
        <p>
          <Link to="/library/decks">{t('library.decksLink')}</Link>
        </p>
      </section>
      <QuickAdd />
      <section className="card" aria-labelledby="terms-title">
        <h2 id="terms-title">{t('library.terms.title')}</h2>
        <Filters filters={filters} onChange={setFilters} />
        {items.isPending && <p className="muted">{t('library.loading')}</p>}
        {items.isError && <ErrorText error={items.error} />}
        {items.isSuccess && items.data.items.length === 0 && (
          <p className="muted">{t('library.terms.empty')}</p>
        )}
        {items.isSuccess && items.data.items.length > 0 && (
          <>
            <p className="muted" role="status">
              {t('library.terms.count', { count: total })}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('library.terms.term')}</th>
                    <th scope="col">{t('library.terms.type')}</th>
                    <th scope="col">{t('library.terms.status')}</th>
                    <th scope="col">{t('library.terms.sheet')}</th>
                    <th scope="col">{t('library.terms.decks')}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        <Link to={`/library/items/${item.id}`}>{item.term}</Link>
                      </th>
                      <td>{t(`library.type.${item.item_type}`)}</td>
                      <td>{t(`library.status.${item.status}`)}</td>
                      <td>{t(`library.sheet.${item.sheet_status}`)}</td>
                      <td>{item.decks.map((d) => d.name).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav className="pager" aria-label={t('library.pager.label')}>
              <button
                type="button"
                className="button"
                disabled={filters.page === 0}
                onClick={() => setFilters({ ...filters, page: filters.page - 1 })}
              >
                {t('library.pager.previous')}
              </button>
              <span>{t('library.pager.page', { page: filters.page + 1, pages })}</span>
              <button
                type="button"
                className="button"
                disabled={filters.page + 1 >= pages}
                onClick={() => setFilters({ ...filters, page: filters.page + 1 })}
              >
                {t('library.pager.next')}
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  )
}
