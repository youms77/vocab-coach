import type {
  ErrorBucket,
  ErrorStats,
  MemoryStats,
  Overview,
  Rate,
  Share,
} from '../api/stats'

// Fictional answers of /api/stats/* in the shapes of "API reference for M9.b" (docs/PROGRESS.md).

export const STUDY_DAY = '2026-09-01'

export const rate = (value: number | null, errors = 0, words = 0): Rate => ({
  value,
  errors,
  words,
  insufficient: value === null,
})

export const share = (value: number | null, successes = 0, n = 0): Share => ({
  value,
  successes,
  n,
  insufficient: value === null,
})

export const overview = (overrides: Partial<Overview> = {}): Overview => ({
  computed_at: '2026-09-01T10:00:00Z',
  study_day: STUDY_DAY,
  demo: false,
  error_rate_last_28: rate(5.75, 92, 1600),
  error_rate_previous_28: rate(6.67, 114, 1710),
  retention_last_28: share(0.9, 188, 209),
  target_retention: 0.9,
  current_target: 0.9,
  active_terms: { value: 15, n: 117 },
  current_streak: { value: 12, n: 25 },
  study_minutes_last_7: 74,
  study_days_last_7: 5,
  reviews_due_tomorrow: { value: 10, n: 86 },
  ...overrides,
})

const bucket = (key: string) => ({ key, first_day: key, last_day: key })

const FIXED = 'grammar.preposition.fixed_expression'
const TENSE = 'grammar.tense.past_simple_vs_present_perfect'

export function errorBuckets(): ErrorBucket[] {
  return [
    {
      ...bucket('2026-08-24'),
      rate: rate(6.5, 13, 200),
      level1: [{ code: 'grammar', level: 1, rate: rate(6.5, 13, 200) }],
      level2: [],
      unnormalized: 0,
    },
    {
      // Under 100 words: no value, only the counts.
      ...bucket('2026-08-31'),
      rate: rate(null, 2, 40),
      level1: [{ code: 'grammar', level: 1, rate: rate(null, 2, 40) }],
      level2: [],
      unnormalized: 1,
    },
  ]
}

export function errorStats(overrides: Partial<ErrorStats> = {}): ErrorStats {
  return {
    computed_at: '2026-09-01T10:00:00Z',
    study_day: STUDY_DAY,
    from: '2026-08-03',
    to: STUDY_DAY,
    granularity: 'day',
    demo: false,
    rates: {
      rate: rate(6.1, 15, 240),
      level1: [{ code: 'grammar', level: 1, rate: rate(6.1, 15, 240) }],
      level2: [],
      unnormalized: { total: 3, by_reason: { drill: 2, review: 1, manual: 0, other: 0 } },
      unnormalized_by_category: {},
      buckets: errorBuckets(),
    },
    top_recurring: [
      {
        key: 'in campus|on campus',
        erroneous_text: 'in campus',
        correction: 'on campus',
        category: FIXED,
        count: 7,
        first_at: '2026-08-05T09:00:00Z',
        last_at: '2026-08-30T09:00:00Z',
        examples: ['I live in campus.', `${'A very long spoken answer about campus life. '.repeat(8)}end`],
        has_card: true,
      },
    ],
    trends: {
      window_a: { start: '2026-06-06', end: '2026-07-03' },
      window_b: { start: '2026-07-04', end: '2026-08-31' },
      words_a: 1710,
      words_b: 1601,
      by_status: {
        declining: [
          {
            code: FIXED,
            level: 3,
            status: 'declining',
            window_a: rate(2.5, 42, 1710),
            window_b: rate(1.5, 24, 1601),
            ratio: 0.45,
          },
        ],
        rising: [
          {
            code: 'discourse',
            level: 1,
            status: 'rising',
            window_a: rate(0.2, 4, 1710),
            window_b: rate(0.4, 6, 1601),
            ratio: 1.6,
          },
        ],
        stable: [
          {
            code: TENSE,
            level: 3,
            status: 'stable',
            window_a: rate(1.6, 27, 1710),
            window_b: rate(1.9, 30, 1601),
            ratio: 1.19,
          },
        ],
        insufficient: [],
      },
      fixed_share: share(0.105, 12, 114),
    },
    ...overrides,
  }
}

export function memoryStats(overrides: Partial<MemoryStats> = {}): MemoryStats {
  return {
    computed_at: '2026-09-01T10:00:00Z',
    study_day: STUDY_DAY,
    from: '2026-08-03',
    to: STUDY_DAY,
    granularity: 'day',
    demo: false,
    default_target: 0.9,
    retention: {
      all: share(0.887, 339, 382),
      receptive: share(0.92, 150, 163),
      productive: share(null, 3, 6),
      target: 0.9,
      buckets: [
        {
          ...bucket('2026-08-24'),
          all: share(0.9, 18, 20),
          receptive: share(0.9, 18, 20),
          productive: share(null, 0, 0),
          target: 0.9,
        },
      ],
    },
    calibration: [
      { low: 0.8, high: 0.9, predicted: 0.85, observed: share(0.8, 8, 10) },
      { low: 0.9, high: 1, predicted: 0.95, observed: share(null, 2, 4) },
    ],
    success_by_exercise: [
      { exercise_type: 'gap_fill', success: share(0.9, 90, 100) },
      { exercise_type: 'spoken_answer', success: share(null, 1, 3) },
    ],
    rating_agreement: { changed: share(0.2, 10, 50), raised: 6, lowered: 4 },
    lapses: {
      total: 4,
      buckets: [{ ...bucket('2026-08-24'), lapses: 4, review_state_reviews: 40 }],
      top_items: [{ item_id: 7, lapses: 3 }],
    },
    top_lapsed_terms: [
      { item_id: 7, term: 'mitigate', lapses: 3 },
      { item_id: 9, term: null, lapses: 1 },
    ],
    stability: [
      {
        direction: 'receptive',
        cards: 20,
        unreviewed: 5,
        ranges: [
          { low: 0, high: 1, count: 3 },
          { low: 90, high: null, count: 12 },
        ],
        median_days: 12.5,
      },
    ],
    time_to_consolidation: {
      n: 0,
      days: { n: 0, q1: null, median: null, q3: null, minimum: null, maximum: null },
      reviews: { n: 0, q1: null, median: null, q3: null, minimum: null, maximum: null },
      distribution: [],
      items: [],
    },
    ...overrides,
  }
}
