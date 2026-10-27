import type { TFunction } from 'i18next'

import type { Bucket, Granularity } from '../../api/stats'
import { formatDay } from './format'

/** The x label of a bucket: its day, or "Week of <Monday>". */
export function bucketLabel(
  t: TFunction,
  language: string,
  granularity: Granularity,
  bucket: Bucket,
): string {
  const day = formatDay(language, bucket.key)
  return granularity === 'week' ? t('stats.chart.weekOf', { date: day }) : day
}

/** The short x label for an axis: the day or the Monday, without "Week of". */
export function bucketAxisLabel(language: string, bucket: Bucket): string {
  return formatDay(language, bucket.key)
}
