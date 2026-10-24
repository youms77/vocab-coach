import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { HISTORY_PAGE_SIZE, type Production, useProductions } from '../../api/productions'
import { PageTitle } from '../../components/PageTitle'
import { formatDateTime } from '../session/format'
import { ErrorText } from '../settings/ErrorText'

function Status({ item }: { item: Production }) {
  const { t } = useTranslation()
  if (item.transcription_status === 'silence') return <>{t('speaking.history.silent')}</>
  if (item.transcription_status !== 'ok') return <>{t('speaking.history.notTranscribed')}</>
  return <>{item.corrected ? t('speaking.history.corrected') : t('speaking.history.notCorrected')}</>
}

/**
 * The spoken productions, newest first, 20 per page (the page number is in the URL). The list also
 * holds the spoken answers of reviews: their topic is the question of the card, and the page says so.
 */
export function SpeakingHistoryPage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('page'))
  const page = Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
  const productions = useProductions('speaking', page)
  const total = productions.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE))

  const goTo = (target: number) => setParams(target === 0 ? {} : { page: String(target + 1) })

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('speaking.history.title')}</PageTitle>
        <p className="muted">{t('speaking.history.intro')}</p>
        <p className="link-row">
          <Link to="/speaking">{t('speaking.detail.another')}</Link>
          <Link to="/speaking/shadowing/history">{t('shadowing.history.title')}</Link>
        </p>
      </section>
      <section className="card" aria-label={t('speaking.history.title')}>
        {productions.isPending && <p className="muted">{t('speaking.detail.loading')}</p>}
        {productions.isError && <ErrorText error={productions.error} />}
        {productions.isSuccess && productions.data.items.length === 0 && (
          <p className="muted">{t('speaking.history.empty')}</p>
        )}
        {productions.isSuccess && productions.data.items.length > 0 && (
          <>
            <p className="muted" role="status">
              {t('speaking.history.count', { count: total })}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('speaking.history.date')}</th>
                    <th scope="col">{t('speaking.history.topic')}</th>
                    <th scope="col">{t('speaking.history.words')}</th>
                    <th scope="col">{t('speaking.history.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {productions.data.items.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">
                        <Link to={`/speaking/${item.id}`}>
                          {formatDateTime(item.created_at, i18n.language)}
                        </Link>
                      </th>
                      <td lang="en">{item.prompt_text ?? '—'}</td>
                      <td>{item.transcription_status === 'ok' ? item.word_count : '—'}</td>
                      <td>
                        <Status item={item} />
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
            <p className="muted field-hint">{t('speaking.history.mixed')}</p>
          </>
        )}
      </section>
    </div>
  )
}
