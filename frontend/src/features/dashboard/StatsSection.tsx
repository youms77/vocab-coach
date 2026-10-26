import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ErrorText } from '../settings/ErrorText'

/**
 * A section of the dashboard with its own request: a heading, a loading line, the failure with a
 * retry, and the content once the data is there. While another period loads, the previous data
 * stays (and the section says it is busy).
 */
export function StatsSection<T>({
  id,
  title,
  intro,
  query,
  children,
}: {
  id: string
  title: string
  intro?: string
  query: UseQueryResult<T>
  children: (data: T) => ReactNode
}) {
  const { t } = useTranslation()
  const headingId = `${id}-heading`
  return (
    <section id={id} className="card stats-section" aria-labelledby={headingId} aria-busy={query.isFetching}>
      <h2 id={headingId}>{title}</h2>
      {intro !== undefined && <p className="muted">{intro}</p>}
      {query.isPending && query.fetchStatus !== 'idle' && <p className="muted">{t('stats.loading')}</p>}
      {query.isError && (
        <>
          <ErrorText error={query.error} />
          <p>
            <button type="button" className="button" onClick={() => void query.refetch()}>
              {t('stats.retry')}
            </button>
          </p>
        </>
      )}
      {query.data !== undefined && children(query.data)}
    </section>
  )
}
