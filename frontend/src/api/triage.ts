import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'
import { decksKey, itemsKey, triageKey, type DeckRef, type ItemType } from './library'

export const TRIAGE_DECISIONS = ['learn', 'unsure', 'known'] as const
export type TriageDecision = (typeof TRIAGE_DECISIONS)[number]

/** A term waiting for triage. No usage sheet on purpose (active recall). */
export interface TriageEntry {
  item_id: number
  term: string
  item_type: ItemType
  sentence: string | null
  decks: DeckRef[]
}

export type TriageCounts = Record<TriageDecision, number>

export function useTriage(deckId: number | null = null) {
  const query = deckId === null ? '' : `?deck_id=${deckId}`
  return useQuery({
    queryKey: [...triageKey, deckId],
    queryFn: ({ signal }) => apiGet<TriageEntry[]>(`/triage${query}`, { signal }),
  })
}

/** All or nothing: one term no longer in triage refuses the whole batch (409 not_in_triage). */
export function useDecide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (decisions: { item_id: number; decision: TriageDecision }[]) =>
      apiSend<TriageCounts>('POST', '/triage', { decisions }),
    // Refetch after a refusal too: the list was out of date.
    onSettled: () =>
      Promise.all(
        [triageKey, itemsKey, decksKey].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  })
}
