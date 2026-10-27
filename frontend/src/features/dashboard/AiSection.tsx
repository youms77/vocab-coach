import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { type AiStats, type Period, useStatsAi } from '../../api/stats'
import { LineChart } from '../../components/charts/LineChart'
import { formatDay, formatNumber } from './format'
import { StatsSection } from './StatsSection'

const PROVIDERS = ['gemini', 'groq', 'ollama', 'azure'] as const

function providerLabel(t: TFunction, name: string): string {
  return (PROVIDERS as readonly string[]).includes(name)
    ? t(`settings.provider.names.${name as (typeof PROVIDERS)[number]}`)
    : name
}

function Content({ data }: { data: AiStats }) {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  const count = (value: number) => formatNumber(language, value, 0)
  const requests = data.totals.reduce((sum, p) => sum + p.requests, 0)
  const providers = [...new Set(data.days.flatMap((d) => d.providers.map((p) => p.provider)))]
  const perProvider = (day: AiStats['days'][number], provider: string) =>
    day.providers.find((p) => p.provider === provider)?.requests ?? 0

  return (
    <>
      <h3>{t('stats.ai.callsTitle')}</h3>
      {requests === 0 ? (
        <p className="muted">{t('stats.ai.empty')}</p>
      ) : (
        <>
          <p className="stats-total">
            <strong>{t('stats.ai.requests', { count: requests })}</strong>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('stats.ai.provider')}</th>
                  <th scope="col">{t('stats.ai.successes')}</th>
                  <th scope="col">{t('stats.ai.errors')}</th>
                  <th scope="col">{t('stats.ai.rateLimited')}</th>
                  <th scope="col">{t('stats.ai.quotaExhausted')}</th>
                  <th scope="col">{t('stats.ai.tokens')}</th>
                  <th scope="col">{t('stats.ai.duration')}</th>
                </tr>
              </thead>
              <tbody>
                {data.totals.map((p) => {
                  const failures = Object.values(p.errors).reduce((sum, n) => sum + n, 0)
                  return (
                    <tr key={p.provider}>
                      <th scope="row">
                        {providerLabel(t, p.provider)}
                        {p.models.length > 0 && (
                          <span className="muted" lang="en">
                            {' '}
                            · {p.models.join(', ')}
                          </span>
                        )}
                      </th>
                      <td>{t('stats.ofCount', { successes: count(p.successes), n: count(p.requests) })}</td>
                      <td>{count(failures)}</td>
                      <td>{count(p.rate_limited)}</td>
                      <td>{count(p.quota_exhausted)}</td>
                      <td>{`${count(p.input_tokens)} / ${count(p.output_tokens)}`}</td>
                      <td>
                        {p.avg_duration_ms === null
                          ? '–'
                          : t('stats.ai.milliseconds', { value: count(p.avg_duration_ms) })}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="muted field-hint">{t('stats.ai.tokensNote')}</p>
        </>
      )}

      {data.totals.some((p) => Object.keys(p.errors).length > 0) && (
        <>
          <h3>{t('stats.ai.errorsTitle')}</h3>
          <ul className="stats-list">
            {data.totals.flatMap((p) =>
              Object.entries(p.errors).map(([code, n]) => (
                <li key={`${p.provider}-${code}`}>
                  {providerLabel(t, p.provider)} · <code>{code}</code>{' '}
                  <span className="muted">{t('stats.ai.times', { count: n })}</span>
                </li>
              )),
            )}
          </ul>
        </>
      )}

      <h3>{t('stats.ai.perDayTitle')}</h3>
      <p className="muted field-hint">{t('stats.ai.perDayNote')}</p>
      <LineChart
        title={t('stats.ai.chart')}
        xLabels={data.days.map((d) => formatDay(language, d.day))}
        series={
          providers.length === 0
            ? [{ id: 'all', label: t('stats.ai.allProviders'), values: data.days.map((d) => d.requests) }]
            : providers.map((provider) => ({
                id: provider,
                label: providerLabel(t, provider),
                values: data.days.map((d) => perProvider(d, provider)),
              }))
        }
        format={count}
        min={0}
      />

      <h3>{t('stats.ai.azureTitle')}</h3>
      <p>
        {t('stats.ai.azureUse', {
          month: data.azure_month.month,
          minutes: formatNumber(language, data.azure_month.audio_seconds / 60, 1),
          count: data.azure_month.assessments,
        })}
      </p>
      <p className="muted field-hint">{t('stats.ai.azureNote')}</p>
    </>
  )
}

export function AiSection({ period }: { period: Period | null }) {
  const { t } = useTranslation()
  const ai = useStatsAi(period)
  return (
    <StatsSection id="ai" title={t('stats.ai.title')} intro={t('stats.ai.intro')} query={ai}>
      {(data) => <Content data={data} />}
    </StatsSection>
  )
}
