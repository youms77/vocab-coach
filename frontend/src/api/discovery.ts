import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'
import { useInvalidateLibrary, type ItemStatus, type ItemType } from './library'
import type { Outcome } from './reviews'
import { type CardDirection, sessionKey, todayKey } from './session'

// backend/app/api/discovery.py (module B, D-104).

export interface DiscoveryStart {
  item_id: number
  term: string
  item_type: ItemType
  status: ItemStatus
  resumed: boolean
  // Never the sheet: it is read after the guess.
  sentence: { text: string; source: 'origin' | 'example' } | null
}

export type DiscoveryExerciseType = 'typed_recall' | 'gap_fill'

/** Prompts only: `typed_recall` {cue_fr, cue_definition}, `gap_fill` {sentence} with `___`. */
export interface DiscoveryExercise {
  exercise_type: DiscoveryExerciseType
  exercise_template_id: number
  prompt: Record<string, unknown>
}

export interface CompleteBody {
  session_id: number
  duration_ms: number | null
  guess: string | null
  exercise_results: { exercise_type: string; outcome: Outcome }[]
  personal_sentence: string | null
}

export interface CompleteResult {
  item_id: number
  status: ItemStatus
  cards: { card_id: number; direction: CardDirection; due: string }[]
  production_attempt_id: number | null
  warnings: string[]
}

export function useStartDiscovery(itemId: number) {
  return useMutation({
    mutationFn: (body: { session_id: number; deck_id: number | null }) =>
      apiSend<DiscoveryStart>('POST', `/discovery/${itemId}/start`, body),
  })
}

export function useDiscoveryExercises(itemId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...sessionKey, 'discovery', itemId, 'exercises'],
    queryFn: ({ signal }) =>
      apiGet<DiscoveryExercise[]>(`/discovery/${itemId}/exercises`, { signal }),
    enabled,
    staleTime: Infinity,
  })
}

export function useCompleteDiscovery(itemId: number) {
  const invalidateLibrary = useInvalidateLibrary()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CompleteBody) =>
      apiSend<CompleteResult>('POST', `/discovery/${itemId}/complete`, body),
    onSuccess: async () => {
      await invalidateLibrary()
      await queryClient.invalidateQueries({ queryKey: todayKey })
    },
  })
}
