import { useMutation, useQueryClient } from '@tanstack/react-query'

import { apiSend } from './client'
import type { Pronunciation } from './enrichment'
import type { ErrorOut } from './errors'
import type { AiStatus, Feedback } from './productions'
import { type SrsState, todayKey } from './session'

// backend/app/api/reviews.py and app/domain/review_steps.py (solutions, sheet summary).

export const EXERCISE_TYPES = [
  'recognition_in_sentence',
  'listening_comprehension',
  'typed_recall',
  'gap_fill',
  'sentence_production',
  'spoken_answer',
  'self_assessment',
] as const
export type ExerciseType = (typeof EXERCISE_TYPES)[number]

export const OUTCOMES = ['exact', 'form', 'typo', 'wrong', 'empty'] as const
export type Outcome = (typeof OUTCOMES)[number]

export interface DiffPart {
  op: 'equal' | 'replace' | 'insert' | 'delete'
  given: string
  expected: string
}

/** Exactly one of `card_id` (a review) and `item_id` (a term being discovered). */
export type GradeBody = (
  | { card_id: number; item_id?: never }
  | { item_id: number; card_id?: never }
) & {
  exercise_type: string
  exercise_template_id: number | null
  answer: string | null
  choice_index: number | null
  response_time_ms: number
}

/**
 * What is revealed after the attempt, by exercise type: choice types `{correct_index, meaning,
 * meaning_fr, sentence}`, gap-fill `{answer, accepted, sentence}` (completed), typed recall
 * `{answer, accepted}`, production and spoken `{example_answer}`, self-assessment `{term,
 * definition_simple, translation_fr, sentence}`. Every field is optional here: the page reads
 * what its type has.
 */
export interface Solution {
  correct_index?: number
  meaning?: string
  meaning_fr?: string
  sentence?: string | null
  answer?: string
  accepted?: string[]
  example_answer?: string
  term?: string
  definition_simple?: string | null
  translation_fr?: string[]
}

export interface SheetSummary {
  term: string
  part_of_speech: string | null
  definition_simple: string | null
  translation_fr: string[]
  pronunciation: Pronunciation | null
  examples: string[]
}

export interface GradeResult {
  outcome: Outcome | null
  proposed_rating: number | null
  expected: string | null
  accepted: string[]
  diff: DiffPart[] | null
  warnings: string[]
  solution: Solution
  sheet_summary: SheetSummary | null
}

/** Grades an attempt and returns the solution. Writes nothing. */
export function useGrade() {
  return useMutation({
    mutationFn: (body: GradeBody) => apiSend<GradeResult>('POST', '/reviews/grade', body),
  })
}

export interface RevealBody {
  card_id: number
  exercise_type: string
  exercise_template_id: number | null
}

export interface RevealResult {
  solution: Solution
  sheet_summary: SheetSummary | null
}

/** The solution of a self-graded exercise, after the attempt. Writes nothing. */
export function useRevealReview() {
  return useMutation({
    mutationFn: (body: RevealBody) => apiSend<RevealResult>('POST', '/reviews/reveal', body),
  })
}

export const RATINGS = [1, 2, 3, 4] as const
export type Rating = (typeof RATINGS)[number]

/** The backend grades the answer again: the proposed rating is never sent (an unknown field is refused). */
export interface RecordBody {
  card_id: number
  session_id: number
  exercise_type: string
  exercise_template_id: number | null
  answer: string | null
  choice_index: number | null
  response_time_ms: number
  final_rating: Rating
  expected_reps: number
  /** The production returned by `check-production` (sentence production only), else omitted. */
  production_attempt_id?: number
}

export interface RecordResult {
  review_log_id: number
  due_after: string
  state_after: SrsState
  item_status: string
  item_status_changed: boolean
  /** An error logged for a lexical confusion in a typed answer (M5.a1), else null. */
  error_event_id: number | null
}

/** Records the final rating. Today's plan changes, so the Today card is refetched. */
export function useRecordReview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RecordBody) => apiSend<RecordResult>('POST', '/reviews', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: todayKey }),
  })
}

export interface CheckProductionBody {
  card_id: number
  session_id: number
  exercise_template_id: number
  answer: string
  response_time_ms: number
}

/**
 * The AI check of a sentence production. The sentence is recorded either way; the solution and the
 * sheet summary come with the answer, once the attempt was made (D-103). `proposed_rating` is 1, 3
 * or null (rate it yourself).
 */
export interface CheckProductionResult {
  production_attempt_id: number
  status: AiStatus
  reason: string | null
  feedback: Feedback | null
  errors: ErrorOut[]
  proposed_rating: number | null
  solution: Solution
  sheet_summary: SheetSummary | null
}

/** Takes 2 to 60 s: `signal` lets the page stop waiting (the production stays recorded). */
export function checkProduction(body: CheckProductionBody, signal?: AbortSignal) {
  return apiSend<CheckProductionResult>('POST', '/reviews/check-production', body, signal)
}
