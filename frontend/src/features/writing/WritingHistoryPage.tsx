import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { HISTORY_PAGE_SIZE, useProductions } from '../../api/productions'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'

const EXCERPT = 90

function excerpt(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  const points = Array.from(flat)
  return points.length > EXCERPT ? `${points.slice(0, EXCERPT).join('')}…` : flat
}

/** The written texts, newest first, 20 per page (the page number is in the URL). */
export function WritingHistoryPage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const productions = useProductions('writing', page)
  const total = productions.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE))

  const goTo = (target: number) => setParams(target === 0 ? {} : { page: String(target + 1) })

  return (
    <div className="writing-page">
      <section className="hero">
        <PageTitle>{t('writing.history.title')}</PageTitle>
        <p className="muted">{t('writing.history.intro')}</p>
        <p className="link-row">
          <Link to="/writing">{t('writing.detail.writeAnother')}</Link>
        </p>
      </section>
      <section className="card" aria-label={t('writing.history.title')}>
        {productions.isPending && <p className="muted">{t('writing.detail.loading')}</p>}
        {productions.isError && <ErrorText error={productions.error} />}
        {productions.isSuccess && productions.data.items.length === 0 && (
          <p className="muted">{t('writing.history.empty')}</p>
        )}
        {productions.isSuccess && productions.data.items.length > 0 && (
          <>
            <p className="muted" role="status">
              {t('writing.history.count', { count: total })}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('writing.history.date')}</th>
                    <th scope="col">{t('writing.history.topic')}</th>
                    <th scope="col">{t('writing.history.text')}</th>
                    <th scope="col">{t('writing.history.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {productions.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        <Link to={`/writing/${item.id}`}>{formatDateTime(item.created_at, i18n.language)}</Link>
                      </th>
                      <td lang="en">{item.prompt_text ?? '—'}</td>
                      <td lang="en">{excerpt(item.text)}</td>
                      <td>
                        {item.corrected ? t('writing.history.corrected') : t('writing.history.notCorrected')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <nav className="pager" aria-label={t('library.pager.label')}>
              <button type="button" className="button" disabled={page === 0} onClick={() => goTo(page - 1)}>
                {t('library.pager.previous')}
              </button>
              <span>{t('library.pager.page', { page: page + 1, pages })}</span>
              <button
                type="button"
                className="button"
                disabled={page + 1 >= pages}
                onClick={() => goTo(page + 1)}
              >
                {t('library.pager.next')}
              </button>
            </nav>
            <p className="muted field-hint">{t('writing.history.mixed')}</p>
          </>
        )}
      </section>
    </div>
  )
}
