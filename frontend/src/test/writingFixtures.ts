import type { CategoryNode, ErrorOut } from '../api/errors'
import type {
  CorrectionError,
  CorrectionResult,
  CorrectionSentence,
  Feedback,
  Production,
  Span,
  WritingTopic,
} from '../api/productions'
import type { CheckProductionResult } from '../api/reviews'
import { sheetSummary } from './fixtures'

// Fictional data for the writing, correction and review-check tests (M5.b1).

export const SENTENCE_1 = "Last year I moved to Yaoundé to start my master's degree."
export const SENTENCE_2 = 'Since then, I lived in campus with two friends from my class.'
export const PARAGRAPH = `${SENTENCE_1} ${SENTENCE_2}`

/** The span of `fragment` in `text` as the backend counts it: Unicode code points. */
export function spanOf(text: string, fragment: string, error: number, sentence = 1): Span {
  const at = text.indexOf(fragment)
  if (at < 0) throw new Error(`"${fragment}" is not in the text`)
  const start = Array.from(text.slice(0, at)).length
  return { error, sentence_index: sentence, start, end: start + Array.from(fragment).length }
}

export function correctionError(overrides: Partial<CorrectionError> = {}): CorrectionError {
  return {
    sentence_index: 2,
    wrong: 'in campus',
    correction: 'on campus',
    alternatives: ['at university'],
    category_code: 'grammar.preposition.fixed_expression',
    proposed_subcategory: null,
    explanation_en: 'We say "on campus" (a fixed expression).',
    explanation_fr: 'On dit « on campus » (expression figée).',
    target_ref: null,
    ...overrides,
  }
}

export const TWO_ERRORS: CorrectionError[] = [
  correctionError({
    wrong: 'I lived',
    correction: 'I have lived',
    alternatives: [],
    category_code: 'grammar.tense.past_simple_vs_present_perfect',
    explanation_en: '"Since then" needs the present perfect.',
    explanation_fr: '« Since then » demande le present perfect.',
  }),
  correctionError(),
]

export function feedback(
  text: string,
  overrides: { errors?: CorrectionError[]; spans?: Span[]; output?: object; extra?: object } = {},
): Feedback {
  const errors = overrides.errors ?? TWO_ERRORS
  const sentences: CorrectionSentence[] = [
    { index: 1, corrected: SENTENCE_1, status: 'correct' },
    {
      index: 2,
      corrected: 'Since then, I have lived on campus with two friends from my class.',
      status: errors.length > 0 ? 'corrected' : 'correct',
    },
  ]
  return {
    format: 'correction-1',
    prompt_version: 'production_correction@1',
    provider: 'gemini',
    model: 'gemini-test',
    output: {
      sentences,
      corrected_text: `${SENTENCE_1} Since then, I have lived on campus with two friends from my class.`,
      natural_text: `${SENTENCE_1} Since then, I have been living on campus with two classmates.`,
      errors,
      naturalness_notes: [],
      targets: [],
      overall_comment: 'Clear and well organised.',
      ...overrides.output,
    },
    spans:
      overrides.spans ??
      errors.map((error, index) => spanOf(text, error.wrong, index, error.sentence_index)),
    error_event_ids: errors.map((_, index) => 11 + index),
    targets: [],
    ...overrides.extra,
  }
}

export function production(overrides: Partial<Production> = {}): Production {
  return {
    id: 5,
    kind: 'writing',
    modality: 'written',
    prompt_text: 'Describe where you live.',
    text: PARAGRAPH,
    word_count: 23,
    corrected: false,
    feedback: null,
    ai_call_id: null,
    study_session_id: null,
    targets: [],
    created_at: '2026-10-18T09:00:00Z',
    updated_at: '2026-10-18T09:00:00Z',
    ...overrides,
  }
}

export function correctedProduction(overrides: Partial<Production> = {}): Production {
  const text = overrides.text ?? PARAGRAPH
  return production({
    corrected: true,
    feedback: overrides.feedback ?? feedback(text),
    ...overrides,
    text,
  })
}

export function loggedErrors(errors: CorrectionError[] = TWO_ERRORS): ErrorOut[] {
  return errors.map((error, index) => ({
    id: 11 + index,
    source: 'writing',
    original_text: PARAGRAPH,
    erroneous_text: error.wrong,
    correction: error.correction,
    alternatives: error.alternatives,
    explanation: error.explanation_en,
    explanation_fr: error.explanation_fr,
    category: {
      code: error.category_code,
      label_en: error.category_code.includes('tense') ? 'Past simple or present perfect' : 'Fixed expression',
      label_fr: error.category_code.includes('tense')
        ? 'Prétérit ou present perfect'
        : 'Expression figée',
      status: 'active',
    },
    term: null,
    production_attempt_id: 5,
    review_log_id: null,
    occurred_at: '2026-10-18T09:00:00Z',
    updated_at: '2026-10-18T09:00:00Z',
  }))
}

export function correctionResult(overrides: Partial<CorrectionResult> = {}): CorrectionResult {
  return {
    status: 'ok',
    reason: null,
    attempt: correctedProduction(),
    errors: loggedErrors(),
    proposed_categories: [],
    ...overrides,
  }
}

export const unavailableResult = (reason: string | null = 'no_provider_configured'): CorrectionResult =>
  correctionResult({
    status: 'unavailable',
    reason,
    attempt: production(),
    errors: [],
  })

export function node(
  code: string,
  label_en: string,
  label_fr: string,
  children: CategoryNode[] = [],
  overrides: Partial<CategoryNode> = {},
): CategoryNode {
  return {
    id: code.length * 7,
    code,
    parent_code: code.includes('.') ? code.slice(0, code.lastIndexOf('.')) : null,
    label_en,
    label_fr,
    description_en: '',
    description_fr: '',
    status: 'active',
    origin: 'builtin',
    count: 0,
    count_recent: 0,
    children,
    ...overrides,
  }
}

export const categoryTree = (): CategoryNode[] => [
  node('grammar', 'Grammar', 'Grammaire', [
    node('grammar.preposition', 'Prepositions', 'Prépositions', [
      node('grammar.preposition.fixed_expression', 'Fixed expression', 'Expression figée'),
      node('grammar.preposition.by_for_since', 'By, for, since', 'By, for, since'),
    ]),
    node('grammar.tense', 'Tenses', 'Temps', [
      node(
        'grammar.tense.past_simple_vs_present_perfect',
        'Past simple or present perfect',
        'Prétérit ou present perfect',
      ),
    ]),
  ]),
]

export const topics = (): WritingTopic[] => [
  {
    id: 'campus_life',
    en: 'Describe a typical day on your campus.',
    fr: 'Décrivez une journée type sur votre campus.',
    tags: ['campus', 'everyday'],
  },
  {
    id: 'a_chart',
    en: 'Explain a chart you saw recently.',
    fr: 'Expliquez un graphique vu récemment.',
    tags: ['data_science'],
  },
  {
    id: 'a_trip',
    en: 'Tell us about a trip you remember.',
    fr: 'Racontez un voyage dont vous vous souvenez.',
    tags: ['everyday'],
  },
]

// --- AI check of a review sentence (POST /reviews/check-production) --------------------------------


export const CHECKED_SENTENCE = 'We will drill down in the sales data.'
export const EXAMPLE_ANSWER = 'I will drill down into the sales data region by region.'

const sentenceError = correctionError({
  sentence_index: 1,
  wrong: 'drill down in',
  correction: 'drill down into',
  alternatives: [],
  category_code: 'grammar.preposition.fixed_expression',
  explanation_en: '"Drill down" takes "into".',
  explanation_fr: '« Drill down » se construit avec « into ».',
  target_ref: 0,
})

export function checkedFeedback(text = CHECKED_SENTENCE, used = true): Feedback {
  return {
    format: 'correction-1',
    prompt_version: 'production_correction@1',
    provider: 'gemini',
    model: 'gemini-test',
    output: {
      sentences: [{ index: 1, corrected: 'We will drill down into the sales data.', status: 'corrected' }],
      corrected_text: 'We will drill down into the sales data.',
      natural_text: null,
      errors: [sentenceError],
      naturalness_notes: [],
      targets: [],
      overall_comment: '',
    },
    spans: [spanOf(text, 'drill down in', 0, 1)],
    error_event_ids: [41],
    targets: [
      {
        ref: 0,
        lexical_item_id: 5,
        used,
        used_correctly: false,
        ai_used: used,
        comment: null,
        disagreement: false,
      },
    ],
  }
}

export function checkAnswer(overrides: Partial<CheckProductionResult> = {}): CheckProductionResult {
  return {
    production_attempt_id: 77,
    status: 'ok',
    reason: null,
    feedback: checkedFeedback(),
    errors: loggedErrors([sentenceError]).map((row) => ({ ...row, id: 41, production_attempt_id: 77 })),
    proposed_rating: 1,
    solution: { example_answer: EXAMPLE_ANSWER },
    sheet_summary: sheetSummary(),
    ...overrides,
  }
}

export const unavailableCheck = (
  status: 'unavailable' | 'incomplete' = 'unavailable',
  reason: string | null = 'no_provider_configured',
): CheckProductionResult =>
  checkAnswer({
    status,
    reason: status === 'unavailable' ? reason : null,
    feedback: null,
    errors: [],
    proposed_rating: null,
  })
