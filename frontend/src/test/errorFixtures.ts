import type { CategoryNode, ErrorOut, ErrorPage, Facet } from '../api/errors'
import { categoryTree } from './writingFixtures'

// Fictional data for the error log, detail, manual-entry and category tests (M5.b2).

export const ORIGINAL = 'Since then, I lived in campus with two friends.'

export function errorRow(id: number, overrides: Partial<ErrorOut> = {}): ErrorOut {
  return {
    id,
    source: 'writing',
    original_text: ORIGINAL,
    erroneous_text: 'in campus',
    correction: 'on campus',
    alternatives: [],
    explanation: 'We say "on campus".',
    explanation_fr: null,
    category: {
      code: 'grammar.preposition.fixed_expression',
      label_en: 'Fixed expression',
      label_fr: 'Expression figée',
      status: 'active',
    },
    term: null,
    production_attempt_id: 5,
    review_log_id: null,
    occurred_at: '2026-10-18T09:00:00Z',
    updated_at: '2026-10-18T09:00:00Z',
    ...overrides,
  }
}

export const facets = (): Facet[] => [
  {
    code: 'grammar.preposition.fixed_expression',
    label_en: 'Fixed expression',
    label_fr: 'Expression figée',
    count: 7,
  },
  {
    code: 'grammar.tense.past_simple_vs_present_perfect',
    label_en: 'Past simple or present perfect',
    label_fr: 'Prétérit ou present perfect',
    count: 3,
  },
]

export function errorPage(errors: ErrorOut[], overrides: Partial<ErrorPage> = {}): ErrorPage {
  return {
    errors,
    total: errors.length,
    page: 1,
    page_size: 25,
    facets: facets(),
    ...overrides,
  }
}

/** `count` distinct errors with ids from `first`. */
export const manyErrors = (count: number, first = 1): ErrorOut[] =>
  Array.from({ length: count }, (_, index) =>
    errorRow(first + index, { erroneous_text: `wrong form ${first + index}`, original_text: '' }),
  )

/** The writing fixtures' tree plus an AI proposal under Prepositions and a rejected category. */
export function treeWithProposal(): CategoryNode[] {
  const tree = categoryTree()
  const prepositions = tree[0].children[0]
  prepositions.children.push(
    {
      id: 901,
      code: 'grammar.preposition.phrasal_particles',
      parent_code: 'grammar.preposition',
      label_en: 'Particles of phrasal verbs',
      label_fr: 'Particules des verbes à particule',
      description_en: 'Up, down, into after a verb.',
      description_fr: 'Up, down, into après un verbe.',
      status: 'proposed',
      origin: 'ai',
      count: 4,
      count_recent: 4,
      children: [],
    },
    {
      id: 902,
      code: 'grammar.preposition.old_idea',
      parent_code: 'grammar.preposition',
      label_en: 'Old idea',
      label_fr: 'Ancienne idée',
      description_en: '',
      description_fr: '',
      status: 'rejected',
      origin: 'ai',
      count: 0,
      count_recent: 0,
      children: [],
    },
  )
  return tree
}
