import type {
  AnswerBody,
  Drill,
  DrillItem,
  DrillOutcome,
  DrillScore,
  ItemResult,
} from '../api/drills'
import { apiErrorResponse, type RecordedCall } from './mockApi'

// Fictional drills for the M5.c2 tests. `drillServer` plays the backend's part: the specs hold the
// solutions, the answers it gives never carry them before an item is answered (D-103).

export interface ItemSpec {
  kind: 'gap_fill' | 'choice'
  sentence: string
  /** The options in the order the server shows them. */
  options?: string[]
  answer: string
  accepted?: string[]
  explanation_en: string
  explanation_fr: string
}

export const GAP_ON: ItemSpec = {
  kind: 'gap_fill',
  sentence: 'Most students live ___ campus.',
  answer: 'on',
  accepted: ['at'],
  explanation_en: 'We say "on campus".',
  explanation_fr: 'On dit « on campus ».',
}

export const CHOICE_SINCE: ItemSpec = {
  kind: 'choice',
  sentence: 'She has lived here ___ 2020.',
  options: ['for', 'since', 'during'],
  answer: 'since',
  explanation_en: '"Since" goes with a starting point.',
  explanation_fr: '« Since » va avec un point de départ.',
}

export const GAP_AT: ItemSpec = {
  kind: 'gap_fill',
  sentence: 'He is good ___ maths.',
  answer: 'at',
  explanation_en: 'We say "good at".',
  explanation_fr: 'On dit « good at ».',
}

export const MIXED_SPECS: ItemSpec[] = [GAP_ON, CHOICE_SINCE, GAP_AT]

/** Solutions nobody could guess: any of them in the page before the answer is a leak. */
export const TOKEN_SPEC: ItemSpec = {
  kind: 'gap_fill',
  sentence: 'The report was written ___ the deadline.',
  answer: 'ANSWER-TOKEN',
  accepted: ['ACCEPTED-TOKEN'],
  explanation_en: 'EXPLANATION-EN-TOKEN',
  explanation_fr: 'EXPLANATION-FR-TOKEN',
}

export const TOKEN_CHOICE_SPEC: ItemSpec = {
  kind: 'choice',
  sentence: 'They arrived ___ the meeting.',
  options: ['OPTION-A', 'OPTION-B-RIGHT', 'OPTION-C'],
  answer: 'OPTION-B-RIGHT',
  explanation_en: 'CHOICE-EXPLANATION-EN-TOKEN',
  explanation_fr: 'CHOICE-EXPLANATION-FR-TOKEN',
}

export const SOLUTION_TOKENS = [
  'ANSWER-TOKEN',
  'ACCEPTED-TOKEN',
  'EXPLANATION-EN-TOKEN',
  'EXPLANATION-FR-TOKEN',
  'CHOICE-EXPLANATION-EN-TOKEN',
  'CHOICE-EXPLANATION-FR-TOKEN',
  'expected',
  'correct_index',
]

export interface StoredAnswer {
  index: number
  given: string
  choice_index: number | null
  outcome: DrillOutcome
}

const normalize = (text: string) => text.trim().toLowerCase().replace(/[.,;:!?]+$/, '')

/** Grades like `domain/drills.py`: exact after normalisation, empty when nothing was given. */
export function grade(spec: ItemSpec, body: AnswerBody, index: number): StoredAnswer {
  if (spec.kind === 'choice') {
    const options = spec.options ?? []
    const chosen = body.choice_index ?? null
    if (chosen === null) return { index, given: '', choice_index: null, outcome: 'empty' }
    const right = options.indexOf(spec.answer)
    return {
      index,
      given: options[chosen],
      choice_index: chosen,
      outcome: chosen === right ? 'exact' : 'wrong',
    }
  }
  const given = (body.answer ?? '').trim()
  if (normalize(given) === '') return { index, given, choice_index: null, outcome: 'empty' }
  const expected = [spec.answer, ...(spec.accepted ?? [])].map(normalize)
  return { index, given, choice_index: null, outcome: expected.includes(normalize(given)) ? 'exact' : 'wrong' }
}

export function resultOf(spec: ItemSpec, answer: StoredAnswer): ItemResult {
  return {
    outcome: answer.outcome,
    expected: spec.answer,
    accepted: spec.accepted ?? [],
    correct_index: spec.kind === 'choice' ? (spec.options ?? []).indexOf(spec.answer) : null,
    explanation_en: spec.explanation_en,
    explanation_fr: spec.explanation_fr,
    given: answer.given,
  }
}

function scoreOf(total: number, answers: StoredAnswer[]): DrillScore {
  const count = (outcome: DrillOutcome) => answers.filter((a) => a.outcome === outcome).length
  return {
    correct: count('exact'),
    wrong: count('wrong'),
    empty: count('empty'),
    answered: answers.length,
    total,
  }
}

export interface DrillOptions {
  id?: number
  category?: { code: string; label_en: string; label_fr: string }
  created_at?: string
  rule_en?: string
  rule_fr?: string
}

export const PREPOSITION_CATEGORY = {
  code: 'grammar.preposition.fixed_expression',
  label_en: 'Fixed expression',
  label_fr: 'Expression figée',
}

/** The drill as the API shows it for these specs and answers: no solution before an answer. */
export function drillOf(specs: ItemSpec[], answers: StoredAnswer[] = [], options: DrillOptions = {}): Drill {
  const items: DrillItem[] = specs.map((spec, index) => {
    const answer = answers.find((a) => a.index === index)
    return {
      index,
      kind: spec.kind,
      sentence: spec.sentence,
      options: spec.kind === 'choice' ? (spec.options ?? null) : null,
      answered: answer !== undefined,
      result: answer !== undefined ? resultOf(spec, answer) : null,
    }
  })
  const score = scoreOf(specs.length, answers)
  return {
    id: options.id ?? 7,
    category: options.category ?? PREPOSITION_CATEGORY,
    rule_en: options.rule_en ?? 'Use "on" for a campus, "at" for a place of study.',
    rule_fr: options.rule_fr ?? 'On utilise « on » pour un campus, « at » pour un lieu d\'étude.',
    items,
    completed: score.answered === score.total,
    score,
    created_at: '2026-10-18T09:30:00Z',
  }
}

/** The error id the fake server gives to a wrong answer. */
export const errorIdOf = (index: number) => 500 + index

type Route = (call: RecordedCall) => Response | Promise<Response>

/**
 * The routes of one drill: `GET /drills/{id}` and one `POST .../answer` per item. Answering an
 * item twice answers 409 `already_answered`, like the backend.
 */
export function drillServer(specs: ItemSpec[], options: DrillOptions & { answered?: StoredAnswer[] } = {}) {
  const id = options.id ?? 7
  const answers: StoredAnswer[] = [...(options.answered ?? [])]
  const current = () => drillOf(specs, answers, options)
  const routes: Record<string, Route> = {
    [`GET /drills/${id}`]: () => Response.json(current()),
  }
  specs.forEach((spec, index) => {
    routes[`POST /drills/${id}/items/${index}/answer`] = (call) => {
      if (answers.some((a) => a.index === index)) {
        return apiErrorResponse(409, 'already_answered', 'This item was already answered.')
      }
      const stored = grade(spec, call.body as AnswerBody, index)
      answers.push(stored)
      return Response.json({
        result: resultOf(spec, stored),
        error_event_id: stored.outcome === 'wrong' ? errorIdOf(index) : null,
        drill: current(),
      })
    }
  })
  return { routes, answers }
}
