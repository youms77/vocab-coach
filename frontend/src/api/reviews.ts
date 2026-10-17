import { useMutation, useQueryClient } from '@tanstack/react-query'

import { apiSend } from './client'
import type { Pronunciation } from './enrichment'
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
}

export interface RecordResult {
  review_log_id: number
  due_after: string
  state_after: SrsState
  item_status: string
  item_status_changed: boolean
}

/** Records the final rating. Today's plan changes, so the Today card is refetched. */
export function useRecordReview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RecordBody) => apiSend<RecordResult>('POST', '/reviews', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: todayKey }),
  })
}
