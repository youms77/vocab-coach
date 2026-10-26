import { useTranslation } from 'react-i18next'

import { EXPORT_CSV_URL, useStatsOverview } from '../../api/stats'
import { formatNumber, formatPercent, formatRate, formatShare, formatShareCounts } from './format'
import { Metric } from './Metric'
import { StatsSection } from './StatsSection'

/** The headline figures (`GET /api/stats/overview`) and the CSV export. */
export function OverviewSection() {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const overview = useStatsOverview()

  return (
    <StatsSection id="overview" title={t('stats.overview.title')} query={overview}>
      {(o) => (
        <>
          <dl className="stat-grid">
            <Metric
              label={t('stats.overview.errorRate')}
              detail={t('stats.overview.errorRateBefore', {
                rate: formatRate(t, language, o.error_rate_previous_28),
              })}
            >
              {formatRate(t, language, o.error_rate_last_28)}
            </Metric>
            <Metric
              label={t('stats.overview.retention')}
              detail={[
                o.retention_last_28.insufficient ? null : formatShareCounts(t, o.retention_last_28),
                t('stats.overview.target', {
                  target: formatPercent(language, o.target_retention ?? o.current_target, 0),
                }),
              ]
                .filter((part) => part !== null)
                .join(' · ')}
            >
              {formatShare(t, language, o.retention_last_28)}
            </Metric>
            <Metric
              label={t('stats.overview.activeTerms')}
              detail={t('stats.overview.ofTerms', { n: o.active_terms.n })}
            >
              {formatNumber(language, o.active_terms.value, 0)}
            </Metric>
            <Metric
              label={t('stats.overview.streak')}
              detail={t('stats.overview.activeDays30', { count: o.current_streak.n })}
            >
              {t('stats.overview.days', { count: o.current_streak.value })}
            </Metric>
            <Metric
              label={t('stats.overview.studyTime')}
              detail={t('stats.overview.studyDays', { count: o.study_days_last_7 })}
            >
              {t('stats.overview.minutes', { count: Math.round(o.study_minutes_last_7) })}
            </Metric>
            <Metric
              label={t('stats.overview.dueTomorrow')}
              detail={t('stats.overview.ofCards', { n: o.reviews_due_tomorrow.n })}
            >
              {formatNumber(language, o.reviews_due_tomorrow.value, 0)}
            </Metric>
          </dl>
          <p className="link-row">
            <a className="button" href={EXPORT_CSV_URL} download>
              {t('stats.export.download')}
            </a>
            <span className="muted field-hint">{t('stats.export.hint')}</span>
          </p>
        </>
      )}
    </StatsSection>
  )
}
