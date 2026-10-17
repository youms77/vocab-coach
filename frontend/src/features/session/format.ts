/** Whole minutes for a duration in seconds; anything above zero shows as at least 1 minute. */
export function minutesOf(seconds: number): number {
  if (seconds <= 0) return 0
  return Math.max(1, Math.round(seconds / 60))
}

/** A calendar date ("2026-11-20") in the interface language, without a time-zone shift. */
export function formatDay(day: string, language: string): string {
  return new Intl.DateTimeFormat(language, { dateStyle: 'long', timeZone: 'UTC' }).format(
    new Date(`${day}T00:00:00Z`),
  )
}

/** An instant (UTC ISO string) as a local date and time. */
export function formatDateTime(iso: string, language: string): string {
  return new Intl.DateTimeFormat(language, { dateStyle: 'full', timeStyle: 'short' }).format(
    new Date(iso),
  )
}
