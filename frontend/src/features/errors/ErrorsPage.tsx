import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useSearchParams } from 'react-router'

import {
  ERROR_SOURCES,
  ERRORS_PAGE_SIZE,
  type ErrorFilters,
  type ErrorSource,
  filtersToParams,
  labelOf,
  parseFilters,
  useErrorCategories,
  useErrors,
} from '../../api/errors'
import { useItem } from '../../api/library'
import { PageTitle } from '../../components/PageTitle'
import { formatShortDate } from '../session/format'
import { ErrorText } from '../settings/ErrorText'
import { CategorySelect } from './CategorySelect'
import { productionLink } from './logRules'

function FilterForm({
  filters,
  onApply,
}: {
  filters: ErrorFilters
  onApply: (next: ErrorFilters) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const categories = useErrorCategories()
  const [category, setCategory] = useState(filters.category)
  const [source, setSource] = useState<ErrorSource | ''>(filters.source)
  const [q, setQ] = useState(filters.q)
  const [from, setFrom] = useState(filters.from)
  const [to, setTo] = useState(filters.to)

  function submit(event: FormEvent) {
    event.preventDefault()
    onApply({ ...filters, category, source, q, from, to, page: 1 })
  }

  function reset() {
    onApply({ category: '', source: '', q: '', from: '', to: '', itemId: null, page: 1 })
  }

  return (
    <form className="library-filters" role="search" onSubmit={submit}>
      <div className="field">
        <label htmlFor={`${id}-category`}>{t('errorLog.filters.category')}</label>
        <CategorySelect
          id={`${id}-category`}
          tree={categories.data ?? []}
          value={category}
          onChange={setCategory}
          mode="filter"
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-source`}>{t('errorLog.filters.source')}</label>
        <select
          id={`${id}-source`}
          value={source}
          onChange={(e) => setSource(e.target.value as ErrorSource | '')}
        >
          <option value="">{t('errorLog.filters.anySource')}</option>
          {ERROR_SOURCES.map((value) => (
            <option key={value} value={value}>
              {t(`errorLog.source.${value}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${id}-q`}>{t('errorLog.filters.search')}</label>
        <input
          id={`${id}-q`}
          type="search"
          maxLength={300}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-from`}>{t('errorLog.filters.from')}</label>
        <input id={`${id}-from`} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-to`}>{t('errorLog.filters.to')}</label>
        <input id={`${id}-to`} type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <div className="filter-actions">
        <button type="submit" className="button button--primary">
          {t('errorLog.filters.apply')}
        </button>
        <button type="button" className="button" onClick={reset}>
          {t('errorLog.filters.reset')}
        </button>
      </div>
    </form>
  )
}

/** The chip of the `item_id` filter: the term's name, and a button that removes the filter. */
function TermChip({ itemId, onRemove }: { itemId: number; onRemove: () => void }) {
  const { t } = useTranslation()
  const item = useItem(itemId)
  const name = item.data?.term ?? t('errorLog.filters.termUnknown', { id: itemId })
  return (
    <p className="filter-chip">
      <span lang={item.data !== undefined ? 'en' : undefined}>{t('errorLog.filters.term', { term: name })}</span>
      <button
        type="button"
        className="button button--small"
        onClick={onRemove}
        aria-label={t('errorLog.filters.removeTerm')}
      >
        ×
      </button>
    </p>
  )
}

/** The error log: filters and the facets of the filtered set, 25 per page. Everything is in the URL. */
export function ErrorsPage() {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const filters = parseFilters(params)
  const errors = useErrors(filters)
  const apply = (next: ErrorFilters) => setParams(filtersToParams(next))
  const data = errors.data
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / ERRORS_PAGE_SIZE))
  const filtered =
    filters.category !== '' ||
    filters.source !== '' ||
    filters.q.trim() !== '' ||
    filters.from !== '' ||
    filters.to !== '' ||
    filters.itemId !== null

  return (
    <div className="errors-page">
      <section className="hero">
        <PageTitle>{t('errorLog.title')}</PageTitle>
        <p className="muted">{t('errorLog.intro')}</p>
        <p className="link-row">
          <Link to="/errors/new">{t('errorLog.addLink')}</Link>
          <Link to="/errors/categories">{t('errorLog.categoriesLink')}</Link>
        </p>
      </section>

      <section className="card" aria-labelledby="errors-filters-title">
        <h2 id="errors-filters-title">{t('errorLog.filters.title')}</h2>
        {/* Remounted when the URL changes, so the fields always show the applied filters. */}
        <FilterForm key={params.toString()} filters={filters} onApply={apply} />
        {filters.itemId !== null && (
          <TermChip itemId={filters.itemId} onRemove={() => apply({ ...filters, itemId: null, page: 1 })} />
        )}
      </section>

      <section className="card" aria-labelledby="errors-list-title">
        <h2 id="errors-list-title" className="visually-hidden">
          {t('errorLog.title')}
        </h2>
        {errors.isPending && <p className="muted">{t('errorLog.loading')}</p>}
        {errors.isError && <ErrorText error={errors.error} />}
        {data !== undefined && (
          <>
            {data.facets.length > 0 && (
              <div className="facets">
                <h3>{t('errorLog.facets.title')}</h3>
                <ul className="facets__list">
                  {data.facets.map((facet) => (
                    <li key={facet.code}>
                      <button
                        type="button"
                        className="button button--small"
                        aria-pressed={filters.category === facet.code}
                        onClick={() =>
                          apply({
                            ...filters,
                            category: filters.category === facet.code ? '' : facet.code,
                            page: 1,
                          })
                        }
                      >
                        {t('errorLog.facets.item', {
                          label: labelOf(facet, i18n.language),
                          count: facet.count,
                        })}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="muted" role="status">
              {data.total === 0
                ? filtered
                  ? t('errorLog.list.emptyFiltered')
                  : t('errorLog.list.empty')
                : t('errorLog.list.count', { count: data.total })}
            </p>
            {data.errors.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t('errorLog.list.date')}</th>
                      <th scope="col">
                        {t('errorLog.list.wrong')} → {t('errorLog.list.correction')}
                      </th>
                      <th scope="col">{t('errorLog.list.category')}</th>
                      <th scope="col">{t('errorLog.list.source')}</th>
                      <th scope="col">{t('errorLog.list.term')}</th>
                      <th scope="col">{t('errorLog.list.text')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.errors.map((error) => {
                      const text = productionLink(error)
                      return (
                        <tr key={error.id}>
                          <td>{formatShortDate(error.occurred_at, i18n.language)}</td>
                          <th scope="row" className="cell-wrap" lang="en">
                            <Link to={`/errors/${error.id}`} state={{ search: location.search }}>
                              {error.erroneous_text}
                            </Link>{' '}
                            → <span>{error.correction}</span>
                          </th>
                          <td>
                            {labelOf(error.category, i18n.language)}{' '}
                            <code className="category-code">{error.category.code}</code>
                            {error.category.status === 'proposed' && (
                              <span className="muted"> ({t('errorLog.categories.status.proposed')})</span>
                            )}
                          </td>
                          <td>{t(`errorLog.source.${error.source}`)}</td>
                          <td lang="en">
                            {error.term !== null ? (
                              <Link to={`/library/items/${error.term.id}`}>{error.term.term}</Link>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>
                            {text !== null ? <Link to={text}>{t('errorLog.list.openText')}</Link> : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {data.total > ERRORS_PAGE_SIZE && (
              <nav className="pager" aria-label={t('library.pager.label')}>
                <button
                  type="button"
                  className="button"
                  disabled={filters.page <= 1}
                  onClick={() => apply({ ...filters, page: filters.page - 1 })}
                >
                  {t('library.pager.previous')}
                </button>
                <span>{t('library.pager.page', { page: filters.page, pages })}</span>
                <button
                  type="button"
                  className="button"
                  disabled={filters.page >= pages}
                  onClick={() => apply({ ...filters, page: filters.page + 1 })}
                >
                  {t('library.pager.next')}
                </button>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  )
}
