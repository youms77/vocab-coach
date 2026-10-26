import type { Granularity, Period } from '../../api/stats'

/** The backend refuses a period of more than 366 study days (D-266). */
export const MAX_PERIOD_DAYS = 366
/** The default period: the last 30 study days, today included (D-266). */
export const DEFAULT_PERIOD_DAYS = 30

const DAY = /^\d{4}-\d{2}-\d{2}$/
const DAY_MS = 86_400_000

/** A study day as a UTC timestamp, or null when the text is not a real calendar date. */
function toMs(day: string): number | null {
  if (!DAY.test(day)) return null
  const ms = Date.parse(`${day}T00:00:00Z`)
  if (Number.isNaN(ms)) return null
  return new Date(ms).toISOString().slice(0, 10) === day ? ms : null
}

export function isStudyDay(day: string): boolean {
  return toMs(day) !== null
}

export function addDays(day: string, days: number): string {
  const ms = toMs(day)
  if (ms === null) throw new Error(`Not a study day: ${day}`)
  return new Date(ms + days * DAY_MS).toISOString().slice(0, 10)
}

export function defaultPeriod(studyDay: string): Period {
  return {
    from: addDays(studyDay, 1 - DEFAULT_PERIOD_DAYS),
    to: studyDay,
    granularity: 'day',
  }
}

export type PeriodProblem = 'invalid' | 'order' | 'tooLong'

/** Why a period would be refused (422 `invalid_request`), checked before asking. */
export function periodProblem(period: Period): PeriodProblem | null {
  const from = toMs(period.from)
  const to = toMs(period.to)
  if (from === null || to === null) return 'invalid'
  if (from > to) return 'order'
  return (to - from) / DAY_MS + 1 > MAX_PERIOD_DAYS ? 'tooLong' : null
}

export function parseGranularity(value: string | null): Granularity {
  return value === 'week' ? 'week' : 'day'
}

/** The period of the URL (`from`, `to`, `granularity`); what is missing comes from `fallback`. */
export function periodFromSearch(search: URLSearchParams, fallback: Period): Period {
  return {
    from: search.get('from') ?? fallback.from,
    to: search.get('to') ?? fallback.to,
    granularity: search.has('granularity')
      ? parseGranularity(search.get('granularity'))
      : fallback.granularity,
  }
}
