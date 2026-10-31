import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { EXERCISE_TYPES, type ExerciseType } from '../../api/reviews'
import { type MemoryStats, type Period, type Range, useStatsMemory } from '../../api/stats'
import { BarList } from '../../components/charts/BarList'
import { LineChart } from '../../components/charts/LineChart'
import { bucketAxisLabel, bucketLabel } from './bucketLabels'
import {
  formatNumber,
  formatPercent,
  formatShare,
  formatShareCounts,
} from './format'
import { StatsSection } from './StatsSection'
import { English } from '../../components/English'

/** "0–1 days", "21–90 days", "90+ days". */
function rangeLabel(t: TFunction, range: Range): string {
  return range.high === null
    ? t('stats.memory.rangeOpen', { low: range.low })
    : t('stats.memory.range', { low: range.low, high: range.high })
}

function exerciseLabel(t: TFunction, code: string): string {
  return (EXERCISE_TYPES as readonly string[]).includes(code)
    ? t(`stats.exercise.${code as ExerciseType}`)
    : code
}

function directionLabel(t: TFunction, code: string): string {
  return code === 'receptive' || code === 'productive' ? t(`stats.memory.direction.${code}`) : code
}

function Content({ data }: { data: MemoryStats }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const { retention, calibration, time_to_consolidation: consolidation } = data
  const percent = (v: number) => formatPercent(language, v, 0)
  const labels = retention.buckets.map((b) => bucketLabel(t, language, data.granularity, b))
  const target = retention.target ?? data.default_target
  const share = (value: { value: number | null; insufficient: boolean }) =>
    value.insufficient ? null : value.value

  return (
    <>
      <h3>{t('stats.memory.retentionTitle')}</h3>
      <p className="stats-total">
        <strong>{formatShare(t, language, retention.all)}</strong>{' '}
        <span className="muted">
          {!retention.all.insufficient && `${formatShareCounts(t, retention.all)} · `}
          {t('stats.memory.targetMean', { target: percent(target) })}
        </span>
      </p>
      <LineChart
        title={t('stats.memory.retentionChart')}
        xLabels={labels}
        axisLabels={retention.buckets.map((b) => bucketAxisLabel(language, b))}
        series={[
          {
            id: 'all',
            label: t('stats.memory.direction.all'),
            values: retention.buckets.map((b) => share(b.all)),
          },
          {
            id: 'receptive',
            label: t('stats.memory.direction.receptive'),
            values: retention.buckets.map((b) => share(b.receptive)),
          },
          {
            id: 'productive',
            label: t('stats.memory.direction.productive'),
            values: retention.buckets.map((b) => share(b.productive)),
          },
          {
            id: 'target',
            label: t('stats.memory.targetLine'),
            values: retention.buckets.map((b) => b.target),
            dashed: true,
          },
        ]}
        format={percent}
        min={0}
        max={1}
      />
      <p className="muted field-hint">{t('stats.memory.retentionNote')}</p>

      <h3>{t('stats.memory.calibrationTitle')}</h3>
      <p className="muted field-hint">{t('stats.memory.calibrationIntro')}</p>
      <LineChart
        title={t('stats.memory.calibrationChart')}
        xLabels={calibration.map((c) => `${percent(c.low)}–${percent(c.high)}`)}
        series={[
          {
            id: 'predicted',
            label: t('stats.memory.predicted'),
            values: calibration.map((c) => c.predicted),
            dashed: true,
          },
          {
            id: 'observed',
            label: t('stats.memory.observed'),
            values: calibration.map((c) => share(c.observed)),
          },
        ]}
        format={percent}
        min={0}
        max={1}
      />

      <h3>{t('stats.memory.exerciseTitle')}</h3>
      {data.success_by_exercise.length === 0 ? (
        <p className="muted">{t('stats.memory.exerciseEmpty')}</p>
      ) : (
        <BarList
          items={data.success_by_exercise.map((e) => ({
            id: e.exercise_type,
            label: exerciseLabel(t, e.exercise_type),
            fraction: share(e.success),
            text: e.success.insufficient
              ? formatShare(t, language, e.success)
              : `${formatShare(t, language, e.success)} (${formatShareCounts(t, e.success)})`,
          }))}
        />
      )}
      <p>
        {t('stats.memory.agreement')}{' '}
        <strong>{formatShare(t, language, data.rating_agreement.changed)}</strong>
        {!data.rating_agreement.changed.insufficient && (
          <span className="muted">
            {' '}
            (
            {t('stats.memory.agreementDetail', {
              raised: data.rating_agreement.raised,
              lowered: data.rating_agreement.lowered,
            })}
            )
          </span>
        )}
      </p>

      <h3>{t('stats.memory.lapsesTitle')}</h3>
      <p>
        <strong>{t('stats.memory.lapses', { count: data.lapses.total })}</strong>
      </p>
      <LineChart
        title={t('stats.memory.lapsesChart')}
        xLabels={data.lapses.buckets.map((b) => bucketLabel(t, language, data.granularity, b))}
        axisLabels={data.lapses.buckets.map((b) => bucketAxisLabel(language, b))}
        series={[
          {
            id: 'lapses',
            label: t('stats.memory.lapsesSeries'),
            values: data.lapses.buckets.map((b) => b.lapses),
          },
        ]}
        format={(v) => formatNumber(language, v, 0)}
        min={0}
      />
      {data.top_lapsed_terms.length > 0 && (
        <>
          <h4>{t('stats.memory.topLapsed')}</h4>
          <ol className="stats-list">
            {data.top_lapsed_terms.map((term) => (
              <li key={term.item_id}>
                {term.term === null ? (
                  <span className="muted">{t('stats.memory.termGone')}</span>
                ) : (
                  <Link to={`/library/items/${term.item_id}`} lang="en">
                    <English>{term.term}</English>
                  </Link>
                )}{' '}
                <span className="muted">{t('stats.memory.lapses', { count: term.lapses })}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      <h3>{t('stats.memory.stabilityTitle')}</h3>
      <p className="muted field-hint">{t('stats.memory.stabilityIntro')}</p>
      {data.stability.map((group) => {
        const reviewed = group.cards - group.unreviewed
        return (
          <div key={group.direction}>
            <h4>{directionLabel(t, group.direction)}</h4>
            <p className="muted">
              {t('stats.memory.stabilityCounts', { cards: group.cards, unreviewed: group.unreviewed })}
              {group.median_days !== null &&
                ` · ${t('stats.memory.medianDays', { value: formatNumber(language, group.median_days, 1) })}`}
            </p>
            {reviewed > 0 && (
              <BarList
                items={group.ranges.map((range) => ({
                  id: `${group.direction}-${range.low}`,
                  label: rangeLabel(t, range),
                  fraction: reviewed === 0 ? null : range.count / reviewed,
                  text: String(range.count),
                }))}
              />
            )}
          </div>
        )
      })}

      <h3>{t('stats.memory.consolidationTitle')}</h3>
      {consolidation.n === 0 ? (
        <p className="muted">{t('stats.memory.consolidationEmpty')}</p>
      ) : (
        <>
          <p>
            <strong>{t('stats.memory.consolidationTerms', { count: consolidation.n })}</strong>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('stats.memory.measure')}</th>
                  <th scope="col">{t('stats.memory.q1')}</th>
                  <th scope="col">{t('stats.memory.median')}</th>
                  <th scope="col">{t('stats.memory.q3')}</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ['days', consolidation.days],
                    ['reviews', consolidation.reviews],
                  ] as const
                ).map(([measure, q]) => (
                  <tr key={measure}>
                    <th scope="row">{t(`stats.memory.measureName.${measure}`)}</th>
                    {[q.q1, q.median, q.q3].map((v, i) => (
                      <td key={i}>{v === null ? '–' : formatNumber(language, v, 1)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <BarList
            items={consolidation.distribution.map((range) => ({
              id: `c-${range.low}`,
              label: rangeLabel(t, range),
              fraction: range.count / consolidation.n,
              text: String(range.count),
            }))}
          />
        </>
      )}
    </>
  )
}

export function MemorySection({ period }: { period: Period | null }) {
  const { t } = useTranslation()
  const memory = useStatsMemory(period)
  return (
    <StatsSection
      id="memory"
      title={t('stats.memory.title')}
      intro={t('stats.memory.intro')}
      query={memory}
    >
      {(data) => <Content data={data} />}
    </StatsSection>
  )
}
