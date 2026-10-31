import { formatInstant, formatStudyDay } from '../../i18n/format'

/** Whole minutes for a duration in seconds; anything above zero shows as at least 1 minute. */
export function minutesOf(seconds: number): number {
  if (seconds <= 0) return 0
  return Math.max(1, Math.round(seconds / 60))
}

/** A calendar date ("2026-11-20") in the interface language, without a time-zone shift. */
export function formatDay(day: string, language: string): string {
  return formatStudyDay(language, day, { dateStyle: 'long' })
}

/** An instant (UTC ISO string) as a short local date (for tables). */
export function formatShortDate(iso: string, language: string): string {
  return formatInstant(language, iso, { dateStyle: 'medium' })
}

/** An instant (UTC ISO string) as a local date and time. */
export function formatDateTime(iso: string, language: string): string {
  return formatInstant(language, iso, { dateStyle: 'full', timeStyle: 'short' })
}
