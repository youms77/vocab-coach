import { useMutation } from '@tanstack/react-query'

import { apiSend } from './client'

// backend/app/api/reviews.py. Only `grade` is used in M4.b (discovery's immediate exercises).

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

export interface GradeResult {
  outcome: Outcome | null
  proposed_rating: number | null
  expected: string | null
  accepted: string[]
  diff: DiffPart[] | null
  warnings: string[]
  solution: Record<string, unknown>
  sheet_summary: Record<string, unknown> | null
}

/** Grades an attempt and returns the solution. Writes nothing. */
export function useGrade() {
  return useMutation({
    mutationFn: (body: GradeBody) => apiSend<GradeResult>('POST', '/reviews/grade', body),
  })
}
