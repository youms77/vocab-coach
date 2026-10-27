import type {
  AiStats,
  ErrorBucket,
  ErrorStats,
  ItemStatusCounts,
  MemoryStats,
  Overview,
  PracticeStats,
  ProgressStats,
  ProviderDay,
  Rate,
  Share,
} from '../api/stats'
import { deck } from './fixtures'

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

const counts = (overrides: Partial<ItemStatusCounts> = {}): ItemStatusCounts => ({
  draft: 0,
  triage: 0,
  queued: 0,
  discovering: 0,
  learning: 0,
  consolidated: 0,
  active: 0,
  known: 0,
  archived: 0,
  ...overrides,
})

export function progressStats(overrides: Partial<ProgressStats> = {}): ProgressStats {
  return {
    computed_at: '2026-09-01T10:00:00Z',
    study_day: STUDY_DAY,
    from: '2026-08-03',
    to: STUDY_DAY,
    granularity: 'day',
    demo: false,
    funnel_order: ['queued', 'discovering', 'learning', 'consolidated', 'active'],
    outside_funnel: ['draft', 'triage', 'known', 'archived'],
    snapshot: counts({
      draft: 1,
      triage: 6,
      queued: 40,
      discovering: 8,
      learning: 20,
      consolidated: 15,
      active: 10,
      known: 3,
      archived: 2,
    }),
    rebuilt: [
      {
        key: '2026-08-24',
        first_day: '2026-08-24',
        last_day: '2026-08-30',
        counts: counts({ queued: 44, learning: 18, active: 8 }),
      },
      {
        key: '2026-08-31',
        first_day: '2026-08-31',
        last_day: STUDY_DAY,
        counts: counts({ queued: 40, learning: 20, active: 10 }),
      },
    ],
    active: [
      { key: '2026-08-24', active: 8 },
      { key: '2026-08-31', active: 10 },
    ],
    decks: [
      deck(1, 'Econometrics core', {
        status: 'active',
        item_count: 30,
        items_by_status: { learning: 10, consolidated: 12, active: 5, known: 3 },
      }),
      deck(2, 'Meeting phrases', { status: 'paused', item_count: 0, items_by_status: {} }),
    ],
    tracks: [
      {
        code: 'ngsl',
        title_en: 'General everyday English',
        title_fr: 'Anglais courant',
        kind: 'wordlist',
        started: true,
        unit_count: 50,
        opened_units: 4,
        triaged_units: 2,
        done_units: 2,
      },
      {
        code: 'speaking',
        title_en: 'Speaking scenarios',
        title_fr: "Scénarios d'expression orale",
        kind: 'scenarios',
        started: false,
        unit_count: 12,
        opened_units: 0,
        triaged_units: 0,
        done_units: 0,
      },
    ],
    forecast: [
      { day: STUDY_DAY, cards: 30, seconds: 600 },
      { day: '2026-09-02', cards: 12, seconds: 240 },
      { day: '2026-09-03', cards: 0, seconds: 0 },
    ],
    ...overrides,
  }
}

export function practiceStats(overrides: Partial<PracticeStats> = {}): PracticeStats {
  return {
    computed_at: '2026-09-01T10:00:00Z',
    study_day: STUDY_DAY,
    from: '2026-08-03',
    to: STUDY_DAY,
    granularity: 'day',
    demo: false,
    study_time: {
      seconds: 5400,
      session_seconds: 6000,
      active_days: 18,
      buckets: [
        { ...bucket('2026-08-24'), seconds: 3000, blocks: 10, actions: 120, session_seconds: 3300 },
        { ...bucket('2026-08-31'), seconds: 2400, blocks: 8, actions: 90, session_seconds: 2700 },
      ],
    },
    streaks: { current: 4, longest: 12, longest_end: '2026-08-15', active_days_last_30: 21 },
    words: [
      { ...bucket('2026-08-24'), written: 400, oral: 150 },
      { ...bucket('2026-08-31'), written: 250, oral: 0 },
    ],
    words_written: 650,
    words_oral: 150,
    speech: [
      { ...bucket('2026-08-24'), seconds: 600, by_kind: { shadowing: 400, speaking: 200 } },
      { ...bucket('2026-08-31'), seconds: 0, by_kind: {} },
    ],
    speech_seconds: 600,
    speech_by_kind: { shadowing: 400, speaking: 200 },
    ...overrides,
  }
}

export const providerDay = (overrides: Partial<ProviderDay> = {}): ProviderDay => ({
  provider: 'gemini',
  models: ['gemini-3.5-flash-lite'],
  requests: 40,
  successes: 35,
  errors: { rate_limit: 3, timeout: 2 },
  rate_limited: 3,
  quota_exhausted: 1,
  input_tokens: 12000,
  output_tokens: 4000,
  avg_duration_ms: 850.4,
  ...overrides,
})

export function aiStats(overrides: Partial<AiStats> = {}): AiStats {
  return {
    computed_at: '2026-09-01T10:00:00Z',
    study_day: STUDY_DAY,
    from: '2026-08-03',
    to: STUDY_DAY,
    granularity: 'day',
    demo: false,
    days: [
      { day: '2026-08-31', requests: 25, successes: 22, providers: [providerDay({ requests: 25 })] },
      {
        day: STUDY_DAY,
        requests: 18,
        successes: 15,
        providers: [
          providerDay({ requests: 15 }),
          providerDay({
            provider: 'groq',
            models: ['llama'],
            requests: 3,
            successes: 3,
            errors: {},
            rate_limited: 0,
            quota_exhausted: 0,
            avg_duration_ms: null,
          }),
        ],
      },
    ],
    totals: [
      providerDay(),
      providerDay({
        provider: 'groq',
        models: ['llama'],
        requests: 3,
        successes: 3,
        errors: {},
        rate_limited: 0,
        quota_exhausted: 0,
        avg_duration_ms: null,
      }),
    ],
    azure_month: { month: '2026-09', audio_seconds: 300, assessments: 12 },
    ...overrides,
  }
}
