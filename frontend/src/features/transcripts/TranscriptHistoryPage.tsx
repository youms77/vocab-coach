import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { HISTORY_PAGE_SIZE, useProductions } from '../../api/productions'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'

/** The recorded conversations, newest first, 20 per page (the page number is in the URL). */
export function TranscriptHistoryPage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const productions = useProductions('transcript_analysis', page)
  const total = productions.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE))

  const goTo = (target: number) => setParams(target === 0 ? {} : { page: String(target + 1) })

  return (
    <div className="transcript-page">
      <section className="hero">
        <PageTitle>{t('transcripts.history.title')}</PageTitle>
        <p className="muted">{t('transcripts.history.intro')}</p>
        <p className="link-row">
          <Link to="/transcripts">{t('transcripts.detail.analyseAnother')}</Link>
        </p>
      </section>
      <section className="card" aria-label={t('transcripts.history.title')}>
        {productions.isPending && <p className="muted">{t('transcripts.detail.loading')}</p>}
        {productions.isError && <ErrorText error={productions.error} />}
        {productions.isSuccess && productions.data.items.length === 0 && (
          <p className="muted">{t('transcripts.history.empty')}</p>
        )}
        {productions.isSuccess && productions.data.items.length > 0 && (
          <>
            <p className="muted" role="status">
              {t('transcripts.history.count', { count: total })}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('transcripts.history.date')}</th>
                    <th scope="col">{t('transcripts.history.titleColumn')}</th>
                    <th scope="col">{t('transcripts.history.words')}</th>
                    <th scope="col">{t('transcripts.history.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {productions.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        <Link to={`/transcripts/${item.id}`}>
                          {formatDateTime(item.created_at, i18n.language)}
                        </Link>
                      </th>
                      <td lang="en">{item.prompt_text ?? t('transcripts.history.untitled')}</td>
                      <td>{item.word_count}</td>
                      <td>
                        {item.corrected
                          ? t('transcripts.history.analysed')
                          : t('transcripts.history.notAnalysed')}
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
