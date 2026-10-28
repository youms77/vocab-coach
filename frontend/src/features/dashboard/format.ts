import type { TFunction } from 'i18next'

import type { Rate, Share } from '../../api/stats'
import {
  formatNumber as formatNumberIn,
  formatPercent as formatPercentIn,
  formatStudyDay,
} from '../../i18n/format'

/**
 * One place that turns the statistics' values into text. A value the backend flags `insufficient`
 * (or sends as null) is never shown as a number: the text says there is not enough data, with the
 * count reached so far (D-266).
 */

export function formatNumber(language: string, value: number, digits = 1): string {
  return formatNumberIn(language, value, digits)
}

/** A proportion in 0..1 as a percentage. */
export function formatPercent(language: string, value: number, digits = 1): string {
  return formatPercentIn(language, value, digits)
}

/** "2.4 per 100 words", or "Not enough data" with the words counted. */
export function formatRate(t: TFunction, language: string, rate: Rate): string {
  if (rate.insufficient || rate.value === null) {
    return t('stats.insufficient.words', { count: rate.words })
  }
  return t('stats.rate', { value: formatNumber(language, rate.value, 2) })
}

/** "89 %", or "Not enough data" with the reviews counted. */
export function formatShare(t: TFunction, language: string, share: Share): string {
  if (share.insufficient || share.value === null) {
    return t('stats.insufficient.reviews', { count: share.n })
  }
  return formatPercent(language, share.value)
}

/** "339 of 382", the counts behind a share. */
export function formatShareCounts(t: TFunction, share: Share): string {
  return t('stats.ofCount', { successes: share.successes, n: share.n })
}

/** An ISO day as a short date ("12 Oct"), read as UTC so the day never moves. */
export function formatDay(language: string, day: string): string {
  return formatStudyDay(language, day, { day: 'numeric', month: 'short' })
}

/** An ISO day with its year, for the period summary. */
export function formatFullDay(language: string, day: string): string {
  return formatStudyDay(language, day, { dateStyle: 'medium' })
}
