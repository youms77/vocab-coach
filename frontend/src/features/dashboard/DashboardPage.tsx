import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { type Period, useStatsOverview } from '../../api/stats'
import { PageTitle } from '../../components/PageTitle'
import { ErrorsSection } from './ErrorsSection'
import { formatFullDay } from './format'
import { MemorySection } from './MemorySection'
import { OverviewSection } from './OverviewSection'
import { defaultPeriod, parseGranularity, periodFromSearch, periodProblem } from './period'
import { PeriodPicker } from './PeriodPicker'

/**
 * `/stats`: the statistics dashboard (module I). The period lives in the URL (`from`, `to`,
 * `granularity`); without it, the last 30 study days. The headline figures never depend on it.
 */
export function DashboardPage() {
  const { t, i18n } = useTranslation()
  const [search, setSearch] = useSearchParams()
  const overview = useStatsOverview()
  const studyDay = overview.data?.study_day ?? null
  const hasPeriodInUrl = search.has('from') && search.has('to')

  // The default needs today's study day, which the overview carries: until it is there (or when the
  // URL has its own period) the sections wait.
  const fallback: Period | null = studyDay === null ? null : defaultPeriod(studyDay)
  const period: Period | null =
    fallback !== null
      ? periodFromSearch(search, fallback)
      : hasPeriodInUrl
        ? periodFromSearch(search, { from: '', to: '', granularity: 'day' })
        : null
  const problem = period === null ? null : periodProblem(period)
  const valid = period !== null && problem === null ? period : null

  const change = (next: Partial<Period>) => {
    const merged = { ...period, ...next } as Period
    const params = new URLSearchParams(search)
    for (const key of ['from', 'to'] as const) {
      const value = merged[key]
      if (value === '') params.delete(key)
      else params.set(key, value)
    }
    params.set('granularity', parseGranularity(merged.granularity))
    setSearch(params, { replace: true })
  }

  return (
    <div className="stats-page">
      <section className="hero">
        <PageTitle>{t('stats.title')}</PageTitle>
        <p className="muted">{t('stats.intro')}</p>
        {overview.data?.demo === true && <p className="muted">{t('stats.demo')}</p>}
        {overview.data !== undefined && (
          <p className="muted field-hint">
            {t('stats.computedAt', {
              date: new Intl.DateTimeFormat(i18n.language, {
                dateStyle: 'medium',
                timeStyle: 'short',
              }).format(new Date(overview.data.computed_at)),
            })}
          </p>
        )}
      </section>
      <nav className="stats-nav" aria-label={t('stats.sections')}>
        <a href="#overview">{t('stats.overview.title')}</a>
        <a href="#errors">{t('stats.errors.title')}</a>
        <a href="#memory">{t('stats.memory.title')}</a>
      </nav>
      <OverviewSection />
      <section className="card" aria-label={t('stats.period.label')}>
        {period !== null ? (
          <>
            <PeriodPicker period={period} problem={problem} onChange={change} />
            {valid !== null && (
              <p className="muted field-hint">
                {t('stats.period.summary', {
                  from: formatFullDay(i18n.language, valid.from),
                  to: formatFullDay(i18n.language, valid.to),
                })}
              </p>
            )}
          </>
        ) : (
          <p className="muted">{t('stats.loading')}</p>
        )}
      </section>
      <ErrorsSection period={valid} />
      <MemorySection period={valid} />
    </div>
  )
}
