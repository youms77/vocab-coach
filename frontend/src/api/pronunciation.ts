import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'
import { productionsKey } from './productions'
import type { PronunciationScores } from './speech'

// backend/app/api/speech.py and app/services/pronunciation.py (M6.c1, D-215, D-216).

export interface AssessResult {
  production_id: number
  status: 'ok' | 'silence' | 'unavailable' | 'incomplete'
  /** `unavailable`: `no_provider_configured`, `quota`, `auth`, `network`, `timeout`, `all_failed`. */
  reason: string | null
  scores: PronunciationScores | null
}

export interface PronunciationUsage {
  month: string
  audio_seconds: number
  assessments: number
  limit_seconds: number
  limit_checked_on: string
  note: string
}

export const pronunciationUsageKey = ['speech', 'pronunciation-usage'] as const

export function usePronunciationUsage(enabled = true) {
  return useQuery({
    queryKey: pronunciationUsageKey,
    queryFn: ({ signal }) => apiGet<PronunciationUsage>('/speech/pronunciation/usage', { signal }),
    enabled,
  })
}

/** Sends the stored recording to Microsoft (a few seconds). A failure is a 200 `unavailable`. */
export function useAssess() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiSend<AssessResult>('POST', `/productions/${id}/pronunciation`),
    onSettled: (_result, _error, id) => {
      // Also after `already_assessed` (409): show what is stored.
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
      void queryClient.invalidateQueries({ queryKey: pronunciationUsageKey })
    },
  })
}
