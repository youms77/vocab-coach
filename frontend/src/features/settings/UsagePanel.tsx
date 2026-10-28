import { useTranslation } from 'react-i18next'

import { type UsageRow, useAiUsage } from '../../api/ai'
import { dateFormatter, numberFormatter } from '../../i18n/format'
import { Notice } from '../../components/Notice'

function errorTotal(row: UsageRow) {
  return Object.values(row.errors).reduce((sum, n) => sum + n, 0)
}

function TodayTable({ rows }: { rows: UsageRow[] }) {
  const { t, i18n } = useTranslation()
  const number = numberFormatter(i18n.language)
  const oneDecimal = numberFormatter(i18n.language, { maximumFractionDigits: 1 })

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">{t('settings.usage.provider')}</th>
            <th scope="col">{t('settings.usage.model')}</th>
            <th scope="col">{t('settings.usage.requests')}</th>
            <th scope="col">{t('settings.usage.successes')}</th>
            <th scope="col">{t('settings.usage.errors')}</th>
            <th scope="col">{t('settings.usage.tokens')}</th>
            <th scope="col">{t('settings.usage.avgTime')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.provider}/${row.model}`}>
              <td>{row.provider}</td>
              <td>
                <code>{row.model}</code>
              </td>
              <td>{number.format(row.requests)}</td>
              <td>{number.format(row.successes)}</td>
              <td title={Object.entries(row.errors).map(([code, n]) => `${code}: ${n}`).join(', ')}>
                {number.format(errorTotal(row))}
              </td>
              <td>
                {number.format(row.input_tokens)} / {number.format(row.output_tokens)}
              </td>
              <td>
                {row.avg_duration_ms === null
                  ? '–'
                  : t('settings.usage.seconds', {
                      value: oneDecimal.format(row.avg_duration_ms / 1000),
                    })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The daily AI counter the spec asks for on the settings page (§7), from `ai_call_log`. */
export function UsagePanel() {
  const { t, i18n } = useTranslation()
  const usage = useAiUsage(7)
  const number = numberFormatter(i18n.language)
  const dayFormat = dateFormatter(i18n.language, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })

  return (
    <section className="card" aria-labelledby="usage-title">
      <h2 id="usage-title">{t('settings.usage.title')}</h2>
      <p className="muted">{t('settings.usage.intro')}</p>
      {usage.isPending && <p className="muted">{t('settings.loading')}</p>}
      {usage.isError && <Notice tone="danger">{t('settings.usage.loadError')}</Notice>}
      {usage.isSuccess && (
        <>
          <h3>{t('settings.usage.today')}</h3>
          {(usage.data.days[0]?.rows.length ?? 0) === 0 ? (
            <p className="muted">{t('settings.usage.none')}</p>
          ) : (
            <TodayTable rows={usage.data.days[0].rows} />
          )}
          <h3>{t('settings.usage.week')}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t('settings.usage.day')}</th>
                  <th scope="col">{t('settings.usage.requests')}</th>
                  <th scope="col">{t('settings.usage.successes')}</th>
                  <th scope="col">{t('settings.usage.tokens')}</th>
                </tr>
              </thead>
              <tbody>
                {usage.data.days.map((day) => (
                  <tr key={day.day}>
                    {/* A study day is a calendar date: format it as such, not as an instant. */}
                    <td>{dayFormat.format(new Date(`${day.day}T00:00:00Z`))}</td>
                    <td>{number.format(day.requests)}</td>
                    <td>{number.format(day.successes)}</td>
                    <td>
                      {number.format(day.input_tokens)} / {number.format(day.output_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
