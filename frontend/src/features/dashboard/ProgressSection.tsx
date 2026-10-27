import { useTranslation } from 'react-i18next'

import { type ProgressStats, type Period, useStatsProgress } from '../../api/stats'
import { BarList } from '../../components/charts/BarList'
import { LineChart } from '../../components/charts/LineChart'
import { bucketAxisLabel, bucketLabel } from './bucketLabels'
import { formatDay, formatNumber } from './format'
import { StatsSection } from './StatsSection'

function Content({ data }: { data: ProgressStats }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const count = (value: number) => formatNumber(language, value, 0)
  const funnelMax = Math.max(1, ...data.funnel_order.map((status) => data.snapshot[status]))
  const forecastCards = data.forecast.reduce((sum, day) => sum + day.cards, 0)
  const forecastMinutes = Math.round(data.forecast.reduce((sum, day) => sum + day.seconds, 0) / 60)

  return (
    <>
      <h3>{t('stats.progress.funnelTitle')}</h3>
      <p className="muted field-hint">{t('stats.progress.funnelIntro')}</p>
      <BarList
        items={data.funnel_order.map((status) => ({
          id: status,
          label: t(`library.status.${status}`),
          fraction: data.snapshot[status] / funnelMax,
          text: count(data.snapshot[status]),
        }))}
      />
      <p className="muted">
        {t('stats.progress.outside')}{' '}
        {data.outside_funnel
          .map((status) => `${t(`library.status.${status}`)} ${count(data.snapshot[status])}`)
          .join(' · ')}
      </p>

      <h3>{t('stats.progress.evolutionTitle')}</h3>
      <p className="muted field-hint">{t('stats.progress.evolutionNote')}</p>
      <LineChart
        title={t('stats.progress.evolutionChart')}
        xLabels={data.rebuilt.map((b) => bucketLabel(t, language, data.granularity, b))}
        axisLabels={data.rebuilt.map((b) => bucketAxisLabel(language, b))}
        series={data.funnel_order.map((status) => ({
          id: status,
          label: t(`library.status.${status}`),
          values: data.rebuilt.map((b) => b.counts[status]),
        }))}
        format={count}
        min={0}
      />

      <h3>{t('stats.progress.activeTitle')}</h3>
      <LineChart
        title={t('stats.progress.activeChart')}
        xLabels={data.active.map((b) =>
          bucketLabel(t, language, data.granularity, { key: b.key, first_day: b.key, last_day: b.key }),
        )}
        axisLabels={data.active.map((b) => formatDay(language, b.key))}
        series={[{ id: 'active', label: t('stats.progress.activeSeries'), values: data.active.map((b) => b.active) }]}
        format={count}
        min={0}
      />

      <h3>{t('stats.progress.decksTitle')}</h3>
      {data.decks.length === 0 ? (
        <p className="muted">{t('stats.progress.decksEmpty')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('stats.progress.deck')}</th>
                <th scope="col">{t('stats.progress.deckStatus')}</th>
                <th scope="col">{t('stats.progress.deckTerms')}</th>
                <th scope="col">{t('stats.progress.deckDone')}</th>
              </tr>
            </thead>
            <tbody>
              {data.decks.map((deck) => {
                const learned =
                  (deck.items_by_status.consolidated ?? 0) +
                  (deck.items_by_status.active ?? 0) +
                  (deck.items_by_status.known ?? 0)
                return (
                  <tr key={deck.id}>
                    <th scope="row">{deck.name}</th>
                    <td>{t(`queue.status.${deck.status}`)}</td>
                    <td>{count(deck.item_count)}</td>
                    <td>
                      {deck.item_count === 0
                        ? '–'
                        : t('stats.ofCount', { successes: learned, n: deck.item_count })}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t('stats.progress.tracksTitle')}</h3>
      {data.tracks.length === 0 ? (
        <p className="muted">{t('stats.progress.tracksEmpty')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('stats.progress.track')}</th>
                <th scope="col">{t('stats.progress.trackUnits')}</th>
                <th scope="col">{t('stats.progress.trackOpened')}</th>
                <th scope="col">{t('stats.progress.trackDone')}</th>
              </tr>
            </thead>
            <tbody>
              {data.tracks.map((track) => (
                <tr key={track.code}>
                  <th scope="row">
                    {language.startsWith('fr') ? track.title_fr : track.title_en}
                    {!track.started && (
                      <span className="muted"> · {t('stats.progress.notStarted')}</span>
                    )}
                  </th>
                  <td>{count(track.unit_count)}</td>
                  <td>{track.started ? count(track.opened_units) : '–'}</td>
                  <td>{track.started ? count(track.done_units) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t('stats.progress.forecastTitle')}</h3>
      <p className="muted field-hint">{t('stats.progress.forecastIntro')}</p>
      <p>
        <strong>{t('stats.progress.forecastTotal', { count: forecastCards, minutes: forecastMinutes })}</strong>
      </p>
      <LineChart
        title={t('stats.progress.forecastChart')}
        xLabels={data.forecast.map((d) => formatDay(language, d.day))}
        series={[
          { id: 'cards', label: t('stats.progress.forecastCards'), values: data.forecast.map((d) => d.cards) },
        ]}
        format={count}
        min={0}
      />
    </>
  )
}

export function ProgressSection({ period }: { period: Period | null }) {
  const { t } = useTranslation()
  const progress = useStatsProgress(period)
  return (
    <StatsSection
      id="progress"
      title={t('stats.progress.title')}
      intro={t('stats.progress.intro')}
      query={progress}
    >
      {(data) => <Content data={data} />}
    </StatsSection>
  )
}
