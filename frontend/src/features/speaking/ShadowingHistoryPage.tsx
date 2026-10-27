import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { HISTORY_PAGE_SIZE, type Production, useProductions } from '../../api/productions'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'

function Result({ item }: { item: Production }) {
  const { t } = useTranslation()
  if (item.transcription_status === 'ok' && item.comparison !== null) {
    return (
      <>
        {t('speaking.comparison.summary', {
          count: item.comparison.target_word_count,
          recognized: item.comparison.recognized_count,
        })}
      </>
    )
  }
  if (item.transcription_status === 'silence') return <>{t('shadowing.history.silent')}</>
  return <>{t('shadowing.history.notTranscribed')}</>
}

/** The shadowing takes, newest first, 20 per page (the page number is in the URL). */
export function ShadowingHistoryPage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const productions = useProductions('shadowing', page)
  const total = productions.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE))

  const goTo = (target: number) => setParams(target === 0 ? {} : { page: String(target + 1) })

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('shadowing.history.title')}</PageTitle>
        <p className="muted">{t('shadowing.history.intro')}</p>
        <p className="link-row">
          <Link to="/speaking/shadowing">{t('shadowing.detail.another')}</Link>
        </p>
      </section>
      <section className="card" aria-label={t('shadowing.history.title')}>
        {productions.isPending && <p className="muted">{t('shadowing.detail.loading')}</p>}
        {productions.isError && <ErrorText error={productions.error} />}
        {productions.isSuccess && productions.data.items.length === 0 && (
          <p className="muted">{t('shadowing.history.empty')}</p>
        )}
        {productions.isSuccess && productions.data.items.length > 0 && (
          <>
            <p className="muted" role="status">
              {t('shadowing.history.count', { count: total })}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('shadowing.history.date')}</th>
                    <th scope="col">{t('shadowing.history.sentence')}</th>
                    <th scope="col">{t('shadowing.history.result')}</th>
                  </tr>
                </thead>
                <tbody>
                  {productions.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        <Link to={`/speaking/shadowing/${item.id}`}>
                          {formatDateTime(item.created_at, i18n.language)}
                        </Link>
                      </th>
                      <td lang="en">{item.prompt_text ?? '—'}</td>
                      <td>
                        <Result item={item} />
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
          </>
        )}
      </section>
    </div>
  )
}
