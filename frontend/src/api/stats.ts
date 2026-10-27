import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { Deck, ItemStatus } from './library'

// backend/app/api/stats.py and app/domain/stats/ (module I, M9.a): "API reference for M9.b" in
// docs/PROGRESS.md. Everything is read-only and computed from the logs.

export type Granularity = 'day' | 'week'

/** The period of the statistics: study days, both included. */
export interface Period {
  from: string
  to: string
  granularity: Granularity
}

/** Errors per 100 words; `value` is null (and `insufficient` true) under the minimum of words. */
export interface Rate {
  value: number | null
  errors: number
  words: number
  insufficient: boolean
}

/** A proportion; `value` is null (and `insufficient` true) under the minimum of reviews. */
export interface Share {
  value: number | null
  successes: number
  n: number
  insufficient: boolean
}

export interface Bucket {
  /** The day, or the Monday of the week. */
  key: string
  first_day: string
  last_day: string
}

export interface Quartiles {
  n: number
  q1: number | null
  median: number | null
  q3: number | null
  minimum: number | null
  maximum: number | null
}

export interface Range {
  low: number
  high: number | null
  count: number
}

export interface StatsHeader {
  computed_at: string
  study_day: string
  demo: boolean
}

export interface PeriodHeader extends StatsHeader {
  from: string
  to: string
  granularity: Granularity
}

// --- Overview ---------------------------------------------------------------------------------------

export interface Counted {
  value: number
  n: number
}

export interface Overview extends StatsHeader {
  error_rate_last_28: Rate
  error_rate_previous_28: Rate
  retention_last_28: Share
  target_retention: number | null
  current_target: number
  active_terms: Counted
  current_streak: Counted
  study_minutes_last_7: number
  study_days_last_7: number
  reviews_due_tomorrow: Counted
}

// --- Errors -----------------------------------------------------------------------------------------

export interface CategoryRate {
  code: string
  level: number
  rate: Rate
}

export interface ErrorBucket extends Bucket {
  rate: Rate
  level1: CategoryRate[]
  level2: CategoryRate[]
  unnormalized: number
}

export interface Unnormalized {
  total: number
  by_reason: Record<'drill' | 'review' | 'manual' | 'other', number>
}

export interface RecurringError {
  key: string
  erroneous_text: string
  correction: string
  category: string
  count: number
  first_at: string
  last_at: string
  examples: string[]
  has_card: boolean
}

export type TrendStatus = 'declining' | 'rising' | 'stable' | 'insufficient'
export const TREND_STATUSES: readonly TrendStatus[] = ['declining', 'rising', 'stable', 'insufficient']

export interface Trend {
  code: string
  level: number
  status: TrendStatus
  window_a: Rate
  window_b: Rate
  ratio: number | null
}

export interface TrendWindow {
  start: string
  end: string
}

export interface ErrorStats extends PeriodHeader {
  rates: {
    rate: Rate
    level1: CategoryRate[]
    level2: CategoryRate[]
    unnormalized: Unnormalized
    unnormalized_by_category: Record<string, number>
    buckets: ErrorBucket[]
  }
  top_recurring: RecurringError[]
  trends: {
    window_a: TrendWindow
    window_b: TrendWindow
    words_a: number
    words_b: number
    by_status: Record<TrendStatus, Trend[]>
    fixed_share: Share
  }
}

// --- Memory -----------------------------------------------------------------------------------------

export interface RetentionBucket extends Bucket {
  all: Share
  receptive: Share
  productive: Share
  target: number | null
}

export interface CalibrationBin {
  low: number
  high: number
  predicted: number | null
  observed: Share
}

export interface StabilityGroup {
  direction: string
  cards: number
  unreviewed: number
  ranges: Range[]
  median_days: number | null
}

export interface LapseBucket extends Bucket {
  lapses: number
  review_state_reviews: number
}

export interface MemoryStats extends PeriodHeader {
  default_target: number
  retention: {
    all: Share
    receptive: Share
    productive: Share
    target: number | null
    buckets: RetentionBucket[]
  }
  calibration: CalibrationBin[]
  success_by_exercise: { exercise_type: string; success: Share }[]
  rating_agreement: { changed: Share; raised: number; lowered: number }
  lapses: {
    total: number
    buckets: LapseBucket[]
    top_items: { item_id: number; lapses: number }[]
  }
  top_lapsed_terms: { item_id: number; term: string | null; lapses: number }[]
  stability: StabilityGroup[]
  time_to_consolidation: {
    n: number
    days: Quartiles
    reviews: Quartiles
    distribution: Range[]
    items: { item_id: number; days: number; reviews: number }[]
  }
}

// --- Progress ---------------------------------------------------------------------------------------

export type ItemStatusCounts = Record<ItemStatus, number>

export interface FunnelBucket extends Bucket {
  /** Terms per status at the end of the bucket, rebuilt from the event log. */
  counts: ItemStatusCounts
}

export interface TrackProgress {
  code: string
  title_en: string
  title_fr: string
  kind: string
  started: boolean
  unit_count: number
  opened_units: number
  triaged_units: number
  done_units: number
}

export interface DayLoad {
  day: string
  cards: number
  seconds: number
}

export interface ProgressStats extends PeriodHeader {
  funnel_order: ItemStatus[]
  outside_funnel: ItemStatus[]
  snapshot: ItemStatusCounts
  rebuilt: FunnelBucket[]
  active: { key: string; active: number }[]
  decks: Deck[]
  tracks: TrackProgress[]
  forecast: DayLoad[]
}

// --- Practice ---------------------------------------------------------------------------------------

export interface StudyTimeBucket extends Bucket {
  seconds: number
  blocks: number
  actions: number
  /** The sessions' own duration, kept for comparison and never added to `seconds`. */
  session_seconds: number
}

export interface PracticeStats extends PeriodHeader {
  study_time: {
    seconds: number
    session_seconds: number
    active_days: number
    buckets: StudyTimeBucket[]
  }
  streaks: {
    current: number
    longest: number
    longest_end: string | null
    active_days_last_30: number
  }
  words: (Bucket & { written: number; oral: number })[]
  words_written: number
  words_oral: number
  speech: (Bucket & { seconds: number; by_kind: Record<string, number> })[]
  speech_seconds: number
  speech_by_kind: Record<string, number>
}

// --- AI ---------------------------------------------------------------------------------------------

export interface ProviderDay {
  provider: string
  models: string[]
  requests: number
  successes: number
  /** Error code to count. */
  errors: Record<string, number>
  rate_limited: number
  quota_exhausted: number
  input_tokens: number
  output_tokens: number
  avg_duration_ms: number | null
}

export interface AiDay {
  day: string
  requests: number
  successes: number
  providers: ProviderDay[]
}

export interface AiStats extends PeriodHeader {
  days: AiDay[]
  totals: ProviderDay[]
  azure_month: { month: string; audio_seconds: number; assessments: number }
}

// --- Hooks ------------------------------------------------------------------------------------------

export const statsKey = ['stats'] as const

function query(period: Period): string {
  return new URLSearchParams({
    from: period.from,
    to: period.to,
    granularity: period.granularity,
  }).toString()
}

export function useStatsOverview() {
  return useQuery({
    queryKey: [...statsKey, 'overview'],
    queryFn: ({ signal }) => apiGet<Overview>('/stats/overview', { signal }),
  })
}

export function useStatsErrors(period: Period | null) {
  return useQuery({
    enabled: period !== null,
    queryKey: [...statsKey, 'errors', period],
    queryFn: ({ signal }) =>
      apiGet<ErrorStats>(`/stats/errors?${query(period as Period)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useStatsMemory(period: Period | null) {
  return useQuery({
    enabled: period !== null,
    queryKey: [...statsKey, 'memory', period],
    queryFn: ({ signal }) =>
      apiGet<MemoryStats>(`/stats/memory?${query(period as Period)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useStatsProgress(period: Period | null) {
  return useQuery({
    enabled: period !== null,
    queryKey: [...statsKey, 'progress', period],
    queryFn: ({ signal }) =>
      apiGet<ProgressStats>(`/stats/progress?${query(period as Period)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useStatsPractice(period: Period | null) {
  return useQuery({
    enabled: period !== null,
    queryKey: [...statsKey, 'practice', period],
    queryFn: ({ signal }) =>
      apiGet<PracticeStats>(`/stats/practice?${query(period as Period)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useStatsAi(period: Period | null) {
  return useQuery({
    enabled: period !== null,
    queryKey: [...statsKey, 'ai', period],
    queryFn: ({ signal }) => apiGet<AiStats>(`/stats/ai?${query(period as Period)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

/** The CSV export of every table (a zip), served by the backend as an attachment. */
export const EXPORT_CSV_URL = '/api/export/csv'
