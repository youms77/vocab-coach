import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import type { Period } from '../../api/stats'
import { MAX_PERIOD_DAYS, type PeriodProblem } from './period'

/**
 * From, to and granularity. The URL holds them (the page owns the state), so an invalid entry is
 * said at once and nothing is asked of the backend until the period is valid.
 */
export function PeriodPicker({
  period,
  problem,
  onChange,
}: {
  period: Period
  problem: PeriodProblem | null
  onChange: (next: Partial<Period>) => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const messageId = `${id}-problem`
  return (
    <form className="period-picker" aria-label={t('stats.period.label')} onSubmit={(e) => e.preventDefault()}>
      <div className="field">
        <label htmlFor={`${id}-from`}>{t('stats.period.from')}</label>
        <input
          id={`${id}-from`}
          type="date"
          value={period.from}
          aria-invalid={problem !== null}
          aria-describedby={problem !== null ? messageId : undefined}
          onChange={(e) => onChange({ from: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-to`}>{t('stats.period.to')}</label>
        <input
          id={`${id}-to`}
          type="date"
          value={period.to}
          aria-invalid={problem !== null}
          aria-describedby={problem !== null ? messageId : undefined}
          onChange={(e) => onChange({ to: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-granularity`}>{t('stats.period.granularity')}</label>
        <select
          id={`${id}-granularity`}
          value={period.granularity}
          onChange={(e) => onChange({ granularity: e.target.value === 'week' ? 'week' : 'day' })}
        >
          <option value="day">{t('stats.period.day')}</option>
          <option value="week">{t('stats.period.week')}</option>
        </select>
      </div>
      {problem !== null && (
        <p id={messageId} className="form-message form-message--error" role="alert">
          {t(`stats.period.problem.${problem}`, { max: MAX_PERIOD_DAYS })}
        </p>
      )}
    </form>
  )
}
