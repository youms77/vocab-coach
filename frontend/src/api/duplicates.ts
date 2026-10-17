import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import { itemsKey, type DeckRef, type ItemStatus } from './library'

export interface GroupItem {
  id: number
  term: string
  normalized_form: string
  status: ItemStatus
  has_cards: boolean
  decks: DeckRef[]
}

export interface DuplicateGroup {
  match: 'exact' | 'possible'
  key: string // the shared normalised form (exact) or lemma (possible)
  items: GroupItem[]
}

// Under itemsKey, so a merge (useMergeItem invalidates itemsKey) refetches the groups.
export function useDuplicates() {
  return useQuery({
    queryKey: [...itemsKey, 'duplicates'],
    queryFn: ({ signal }) => apiGet<DuplicateGroup[]>('/duplicates', { signal }),
  })
}
