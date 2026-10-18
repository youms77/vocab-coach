import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'
import { categoriesKey, errorsKey } from './errors'

// backend/app/api/drills.py, services/drills.py and domain/drills.py (D-135, D-136). Errors use the
// D-063 format (see features/settings/errorMessage.ts). An unanswered item never carries its
// solution (D-103): `result` is only there once the item is answered.

export const DRILLS_PAGE_SIZE = 20
export const MIN_DRILL_ITEMS = 5
export const MAX_DRILL_ITEMS = 15
export const DEFAULT_DRILL_ITEMS = 10
/** `max_length` of a typed answer on the server. */
export const MAX_ANSWER_CHARS = 200

export type DrillOutcome = 'exact' | 'wrong' | 'empty'
export type DrillItemKind = 'gap_fill' | 'choice'

export interface DrillCategory {
  code: string
  label_en: string
  label_fr: string
}

export interface ItemResult {
  outcome: DrillOutcome
  expected: string
  accepted: string[]
  /** Into the options as shown; null for a gap-fill. */
  correct_index: number | null
  explanation_en: string
  explanation_fr: string
  /** What was typed, or the option chosen; empty for "I don't know". */
  given: string
}

export interface DrillItem {
  /** From 0. */
  index: number
  kind: DrillItemKind
  /** With one `___`. */
  sentence: string
  /** Shuffled by the server, in the same order on every read. */
  options: string[] | null
  answered: boolean
  result: ItemResult | null
}

export interface DrillScore {
  correct: number
  wrong: number
  empty: number
  answered: number
  total: number
}

export interface Drill {
  id: number
  category: DrillCategory
  rule_en: string
  rule_fr: string
  items: DrillItem[]
  completed: boolean
  score: DrillScore
  created_at: string
}

export interface DrillPage {
  items: Drill[]
  total: number
  limit: number
  offset: number
}

/** `status` is `ok` with a drill, else the AI failed (HTTP 200, nothing was written). */
export interface DrillCreated {
  status: 'ok' | 'incomplete' | 'unavailable'
  reason: string | null
  drill: Drill | null
}

export interface DrillRequest {
  category_code: string
  count: number
  study_session_id?: number
}

export interface AnswerBody {
  answer?: string | null
  choice_index?: number | null
  response_time_ms: number
}

export interface AnswerResult {
  result: ItemResult
  /** The error logged for a wrong answer. */
  error_event_id: number | null
  drill: Drill
}

export const drillsKey = ['drills'] as const

export function useDrills(category: string, page: number) {
  const params = new URLSearchParams({
    limit: String(DRILLS_PAGE_SIZE),
    offset: String(page * DRILLS_PAGE_SIZE),
  })
  if (category !== '') params.set('category', category)
  const query = params.toString()
  return useQuery({
    queryKey: [...drillsKey, 'list', query],
    queryFn: ({ signal }) => apiGet<DrillPage>(`/drills?${query}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useDrill(id: number, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...drillsKey, 'detail', id],
    queryFn: ({ signal }) => apiGet<Drill>(`/drills/${id}`, { signal }),
  })
}

/** Takes a few seconds: the AI writes the drill. A failure of the AI is an answer, not an error. */
export function useCreateDrill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: DrillRequest) => apiSend<DrillCreated>('POST', '/drills', body),
    onSuccess: (created) => {
      if (created.drill !== null) {
        queryClient.setQueryData([...drillsKey, 'detail', created.drill.id], created.drill)
      }
      void queryClient.invalidateQueries({ queryKey: [...drillsKey, 'list'] })
    },
  })
}

/**
 * Answers one item. The answer carries the whole drill, which replaces the cached one; a wrong
 * answer is logged as an error, so the error log and the category counts are stale too.
 */
export function useAnswerItem(drillId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ index, body }: { index: number; body: AnswerBody }) =>
      apiSend<AnswerResult>('POST', `/drills/${drillId}/items/${index}/answer`, body),
    onSuccess: (answered) => {
      queryClient.setQueryData([...drillsKey, 'detail', drillId], answered.drill)
      void queryClient.invalidateQueries({ queryKey: [...drillsKey, 'list'] })
      if (answered.error_event_id !== null) {
        void queryClient.invalidateQueries({ queryKey: errorsKey })
        void queryClient.invalidateQueries({ queryKey: categoriesKey })
      }
    },
  })
}
