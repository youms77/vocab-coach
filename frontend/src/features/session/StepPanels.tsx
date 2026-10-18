import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { PracticeStep, SessionSummary as Summary } from '../../api/session'
import { useCategoryName } from '../errors/useCategoryName'
import { minutesOf } from './format'
import { StepHeading } from './StepHeading'

// setTimeout takes at most a signed 32-bit number of milliseconds.
const MAX_TIMEOUT_MS = 2 ** 31 - 1
// Checked a little after `until`, so the backend sees the card as due.
const WAIT_MARGIN_MS = 1000

/**
 * `wait {until}`: a learning card comes back later today. A readable countdown, a check at
 * `until` (timer cleared when the panel goes away) and "Check now".
 */
export function WaitPanel({
  until,
  onCheck,
  checking,
}: {
  until: string
  onCheck: () => void
  checking: boolean
}) {
  const { t, i18n } = useTranslation()
  const [now, setNow] = useState(() => Date.now())
  const check = useRef(onCheck)
  useEffect(() => {
    check.current = onCheck
  }, [onCheck])

  const target = Date.parse(until)
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [])
  useEffect(() => {
    // Armed once per `until`: a check that answers the same `until` does not loop.
    const delay = Math.min(Math.max(0, target - Date.now()) + WAIT_MARGIN_MS, MAX_TIMEOUT_MS)
    const timer = setTimeout(() => check.current(), delay)
    return () => clearTimeout(timer)
  }, [target])

  const left = target - now
  const countdown =
    left <= 0
      ? t('session.wait.ready')
      : left >= 60_000
        ? t('session.wait.inMinutes', { count: Math.ceil(left / 60_000) })
        : t('session.wait.inSeconds', { count: Math.ceil(left / 1000) })
  const time = new Intl.DateTimeFormat(i18n.language, { timeStyle: 'short' }).format(target)

  return (
    <>
      <StepHeading>{t('steps.wait')}</StepHeading>
      <p>{t('session.wait.text', { time })}</p>
      <p className="wait-countdown">{countdown}</p>
      <p className="muted">{t('session.wait.auto')}</p>
      <button type="button" className="button" onClick={onCheck} disabled={checking}>
        {t('session.wait.check')}
      </button>
    </>
  )
}

/** Targeted practice and consolidation are information only in M4 (D-107). */
export function PracticeInfoPanel({
  practice,
  onContinue,
  busy,
}: {
  practice: PracticeStep
  onContinue: () => void
  busy: boolean
}) {
  const { t } = useTranslation()
  const categoryName = useCategoryName()
  const targeted = practice.targeted_practice
  return (
    <>
      <StepHeading>{t('steps.practice_info')}</StepHeading>
      <ul>
        {targeted !== null && (
          <li>
            {t('session.practice.targeted', {
              category: categoryName(targeted.category_code),
              count: targeted.error_count,
            })}
          </li>
        )}
        {practice.consolidation_task_id !== null && <li>{t('session.practice.consolidation')}</li>}
      </ul>
      <p className="muted">{t('session.practice.later')}</p>
      <button type="button" className="button button--primary" onClick={onContinue} disabled={busy}>
        {t('session.practice.continue')}
      </button>
    </>
  )
}

/** The session's summary, computed by the backend from the logs (D-107). */
export function SessionSummary({ summary }: { summary: Summary }) {
  const { t } = useTranslation()
  const rows: [string, string | number][] = [
    [t('session.summary.reviews'), summary.reviews],
    [t('session.summary.failed'), summary.failed_reviews],
    [t('session.summary.discoveriesStarted'), summary.discoveries_started],
    [t('session.summary.discoveriesCompleted'), summary.discoveries_completed],
    [t('session.summary.productions'), summary.productions],
    [t('session.summary.words'), summary.words],
    [
      t('session.summary.duration'),
      t('session.summary.minutes', { count: minutesOf(summary.duration_ms / 1000) }),
    ],
    [t('session.summary.planned'), t('session.summary.minutes', { count: summary.planned_minutes })],
  ]
  return (
    <>
      <StepHeading>{t('steps.done')}</StepHeading>
      <h3>{t('session.summary.title')}</h3>
      <dl className="session-summary">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Link to="/" className="button">
        {t('session.summary.home')}
      </Link>
    </>
  )
}
