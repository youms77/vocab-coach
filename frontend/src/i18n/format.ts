/**
 * The one place that builds `Intl` formatters (M10.c, D-319). A formatter is memoised per language
 * and options, and every helper takes the active language, so a language change shows at once
 * (the components re-render with `i18n.language`) and no formatter is rebuilt on each render.
 *
 * Study days ("2026-10-27") are calendar days, not instants: they are read as UTC and formatted in
 * UTC, so the day never moves with the browser time zone (`new Date('2026-10-27')` is already UTC
 * and would give the day before west of Greenwich if it were formatted in local time).
 */

const numberFormats = new Map<string, Intl.NumberFormat>()
const dateFormats = new Map<string, Intl.DateTimeFormat>()

function numberFormat(language: string, options: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const key = `${language}|${JSON.stringify(options)}`
  let format = numberFormats.get(key)
  if (format === undefined) {
    format = new Intl.NumberFormat(language, options)
    numberFormats.set(key, format)
  }
  return format
}

function dateFormat(language: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${language}|${JSON.stringify(options)}`
  let format = dateFormats.get(key)
  if (format === undefined) {
    // 24-hour clock in French, 12-hour in English (what `Intl` gives for each language).
    format = new Intl.DateTimeFormat(language, options)
    dateFormats.set(key, format)
  }
  return format
}

/** "2,983" in English, "2 983" in French (a narrow no-break space, from `Intl`). */
export function formatNumber(language: string, value: number, digits?: number): string {
  return numberFormat(language, digits === undefined ? {} : { maximumFractionDigits: digits }).format(
    value,
  )
}

/** A proportion in 0..1: "12.5%" in English, "12,5 %" in French. */
export function formatPercent(language: string, value: number, digits = 1): string {
  return numberFormat(language, { style: 'percent', maximumFractionDigits: digits }).format(value)
}

const dayOf = (day: string) => new Date(`${day}T00:00:00Z`)

/** A study day (YYYY-MM-DD) without a time-zone shift. */
export function formatStudyDay(
  language: string,
  day: string,
  options: Intl.DateTimeFormatOptions = { dateStyle: 'medium' },
): string {
  return dateFormat(language, { ...options, timeZone: 'UTC' }).format(dayOf(day))
}

/** An instant (ISO string, UTC) in the browser's time zone. */
export function formatInstant(
  language: string,
  iso: string | Date,
  options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' },
): string {
  return dateFormat(language, options).format(typeof iso === 'string' ? new Date(iso) : iso)
}

/** The memoised formatter itself, for a component that formats many values (a table). */
export function numberFormatter(
  language: string,
  options: Intl.NumberFormatOptions = {},
): Intl.NumberFormat {
  return numberFormat(language, options)
}

export function dateFormatter(
  language: string,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  return dateFormat(language, options)
}
