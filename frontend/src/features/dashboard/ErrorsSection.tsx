import { useTranslation } from 'react-i18next'

import {
  type CategoryRate,
  type ErrorStats,
  type Period,
  TREND_STATUSES,
  type Trend,
  useStatsErrors,
} from '../../api/stats'
import { LineChart, type LineSeries } from '../../components/charts/LineChart'
import { useCategoryName } from '../errors/useCategoryName'
import { bucketAxisLabel, bucketLabel } from './bucketLabels'
import {
  formatDay,
  formatNumber,
  formatPercent,
  formatRate,
  formatShare,
  formatShareCounts,
} from './format'
import { StatsSection } from './StatsSection'
import { CorrectionMark } from '../../components/CorrectionMark'

/** How many categories get their own line next to the total. */
const CHART_CATEGORIES = 4
/** The longest example shown in full; the whole text stays in the `title`. */
const EXAMPLE_LENGTH = 140

function shorten(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > EXAMPLE_LENGTH ? `${flat.slice(0, EXAMPLE_LENGTH - 1)}…` : flat
}

function TrendList({ trends, name }: { trends: Trend[]; name: (code: string) => string }) {
  const { t, i18n } = useTranslation()
  return (
    <ul className="stats-list">
      {trends.map((trend) => (
        <li key={trend.code}>
          <strong>{name(trend.code)}</strong>{' '}
          <span className="muted">
            {t('stats.errors.trendDetail', {
              from: trend.window_a.errors,
              to: trend.window_b.errors,
              ratio: trend.ratio === null ? '–' : formatNumber(i18n.language, trend.ratio, 2),
            })}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Content({ data }: { data: ErrorStats }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const name = useCategoryName()
  const { rates, top_recurring: top, trends } = data

  const byErrors = (a: CategoryRate, b: CategoryRate) => b.rate.errors - a.rate.errors
  const topCategories = rates.level1
    .filter((c) => c.rate.errors > 0)
    .sort(byErrors)
    .slice(0, CHART_CATEGORIES)
  const series: LineSeries[] = [
    {
      id: 'total',
      label: t('stats.errors.allErrors'),
      values: rates.buckets.map((b) => b.rate.value),
    },
    ...topCategories.map((c) => ({
      id: c.code,
      label: name(c.code),
      values: rates.buckets.map((b) => b.level1.find((x) => x.code === c.code)?.rate.value ?? null),
    })),
  ]
  const xLabels = rates.buckets.map((b) => bucketLabel(t, language, data.granularity, b))
  const unnormalized = rates.unnormalized

  return (
    <>
      <p className="stats-total">
        <strong>{formatRate(t, language, rates.rate)}</strong>{' '}
        <span className="muted">
          {t('stats.errors.periodCounts', {
            errors: rates.rate.errors,
            words: formatNumber(language, rates.rate.words, 0),
          })}
        </span>
      </p>
      <LineChart
        title={t('stats.errors.chartTitle')}
        xLabels={xLabels}
        axisLabels={rates.buckets.map((b) => bucketAxisLabel(language, b))}
        series={series}
        format={(v) => formatNumber(language, v, 1)}
        min={0}
      />
      <p className="muted field-hint">{t('stats.errors.chartNote')}</p>

      <h3>{t('stats.errors.byCategory')}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t('stats.errors.category')}</th>
              <th scope="col">{t('stats.errors.errors')}</th>
              <th scope="col">{t('stats.errors.rateColumn')}</th>
            </tr>
          </thead>
          <tbody>
            {[...rates.level1].sort(byErrors).map((c) => (
              <tr key={c.code}>
                <th scope="row">{name(c.code)}</th>
                <td>{c.rate.errors}</td>
                <td>{formatRate(t, language, c.rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unnormalized.total > 0 && (
        <p className="muted field-hint">
          {t('stats.errors.unnormalized', {
            total: unnormalized.total,
            drill: unnormalized.by_reason.drill,
            review: unnormalized.by_reason.review,
            manual: unnormalized.by_reason.manual,
            other: unnormalized.by_reason.other,
          })}
        </p>
      )}

      <h3>{t('stats.errors.topTitle')}</h3>
      {top.length === 0 ? (
        <p className="muted">{t('stats.errors.topEmpty')}</p>
      ) : (
        <ol className="stats-top">
          {top.map((e) => (
            <li key={e.key}>
              <p>
                <span lang="en">
                  <CorrectionMark wrong={e.erroneous_text} correction={e.correction} />
                </span>
                <span className="muted">
                  {' · '}
                  {name(e.category)}
                  {' · '}
                  {t('stats.errors.times', { count: e.count })}
                  {' · '}
                  {t('stats.errors.lastSeen', { date: formatDay(language, e.last_at.slice(0, 10)) })}
                  {e.has_card && ` · ${t('stats.errors.hasCard')}`}
                </span>
              </p>
              {e.examples.map((example) => (
                <blockquote key={example} className="stats-example" lang="en" title={example}>
                  {shorten(example)}
                </blockquote>
              ))}
            </li>
          ))}
        </ol>
      )}

      <h3>{t('stats.errors.trendsTitle')}</h3>
      <p className="muted field-hint">
        {t('stats.errors.trendsWindows', {
          aStart: formatDay(language, trends.window_a.start),
          aEnd: formatDay(language, trends.window_a.end),
          bStart: formatDay(language, trends.window_b.start),
          bEnd: formatDay(language, trends.window_b.end),
        })}
      </p>
      <p>
        {t('stats.errors.fixedShare')}{' '}
        <strong>{formatShare(t, language, trends.fixed_share)}</strong>
        {!trends.fixed_share.insufficient && (
          <span className="muted"> ({formatShareCounts(t, trends.fixed_share)})</span>
        )}
      </p>
      {TREND_STATUSES.map((status) => {
        const list = trends.by_status[status]
        if (list.length === 0) return null
        const heading = `${t(`stats.errors.status.${status}`)} (${list.length})`
        // Declining and rising are the news; the rest is there on demand.
        return status === 'declining' || status === 'rising' ? (
          <div key={status}>
            <h4>{heading}</h4>
            <TrendList trends={list} name={name} />
          </div>
        ) : (
          <details key={status} className="stats-more">
            <summary>{heading}</summary>
            <TrendList trends={list} name={name} />
          </details>
        )
      })}
      <p className="muted field-hint">
        {t('stats.errors.thresholds', {
          declining: formatPercent(language, 0.5, 0),
          rising: formatPercent(language, 1.5, 0),
        })}
      </p>
    </>
  )
}

export function ErrorsSection({ period }: { period: Period | null }) {
  const { t } = useTranslation()
  const errors = useStatsErrors(period)
  return (
    <StatsSection
      id="errors"
      title={t('stats.errors.title')}
      intro={t('stats.errors.intro')}
      query={errors}
    >
      {(data) => <Content data={data} />}
    </StatsSection>
  )
}
