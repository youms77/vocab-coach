import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'

export const ITEM_STATUSES = [
  'draft',
  'triage',
  'queued',
  'discovering',
  'learning',
  'consolidated',
  'active',
  'known',
  'archived',
] as const
export type ItemStatus = (typeof ITEM_STATUSES)[number]

export const ITEM_TYPES = ['word', 'collocation', 'phrase', 'spoken_formula'] as const
export type ItemType = (typeof ITEM_TYPES)[number]

export const SHEET_STATES = ['none', 'complete', 'needs_completion', 'edited'] as const
export type SheetState = (typeof SHEET_STATES)[number]

export const ITEM_SORTS = ['created_at', 'term', 'updated_at', 'status', 'status_changed_at'] as const
export type ItemSort = (typeof ITEM_SORTS)[number]

export interface DeckRef {
  id: number
  name: string
}

export interface Candidate {
  id: number
  term: string
  normalized_form: string
  status: ItemStatus
  match: 'exact' | 'possible'
  decks: DeckRef[]
}

export interface Item {
  id: number
  term: string
  normalized_form: string
  lemma: string | null
  item_type: ItemType
  part_of_speech: string | null
  origin_sentence: string | null
  notes: string | null
  status: ItemStatus
  status_changed_at: string
  discovered_at: string | null
  created_at: string
  updated_at: string
  decks: DeckRef[]
  sheet_status: SheetState
}

export interface DeckLink {
  deck_id: number
  deck_name: string
  position: number
  context_sentence: string | null
  added_at: string
}

export interface ItemDetail extends Item {
  deck_links: DeckLink[]
  has_history: boolean
  duplicates: Candidate[]
}

export interface ItemPage {
  total: number
  items: Item[]
}

export interface Deck {
  id: number
  name: string
  description: string | null
  domain: string | null
  kind: string
  status: string
  deadline: string | null
  priority: number | null
  queue_position: number | null
  source: { id: number; title: string } | null
  created_at: string
  updated_at: string
  item_count: number
  items_by_status: Partial<Record<ItemStatus, number>>
}

export interface ItemFilters {
  q: string
  deckId: number | null
  domain: string
  itemType: ItemType | ''
  status: ItemStatus | ''
  sheet: SheetState | ''
  includeArchived: boolean
  sort: ItemSort
  order: 'asc' | 'desc'
  page: number
}

export const PAGE_SIZE = 50

export const emptyFilters: ItemFilters = {
  q: '',
  deckId: null,
  domain: '',
  itemType: '',
  status: '',
  sheet: '',
  includeArchived: false,
  sort: 'created_at',
  order: 'desc',
  page: 0,
}

export function itemsQuery(filters: ItemFilters): string {
  const params = new URLSearchParams()
  if (filters.q.trim() !== '') params.set('q', filters.q.trim())
  if (filters.deckId !== null) params.set('deck_id', String(filters.deckId))
  if (filters.domain.trim() !== '') params.set('domain', filters.domain.trim())
  if (filters.itemType !== '') params.set('item_type', filters.itemType)
  if (filters.status !== '') params.set('status', filters.status)
  if (filters.sheet !== '') params.set('sheet', filters.sheet)
  if (filters.includeArchived) params.set('include_archived', 'true')
  params.set('sort', filters.sort)
  params.set('order', filters.order)
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(filters.page * PAGE_SIZE))
  return params.toString()
}

export const itemsKey = ['items'] as const
export const decksKey = ['decks'] as const
// Terms waiting for triage (api/triage.ts): status changes and deletions change that list too.
export const triageKey = ['triage'] as const

export function useItems(filters: ItemFilters) {
  const query = itemsQuery(filters)
  return useQuery({
    queryKey: [...itemsKey, 'list', query],
    queryFn: ({ signal }) => apiGet<ItemPage>(`/items?${query}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useItem(id: number) {
  return useQuery({
    queryKey: [...itemsKey, 'detail', id],
    queryFn: ({ signal }) => apiGet<ItemDetail>(`/items/${id}`, { signal }),
  })
}

export function useDecks() {
  return useQuery({
    queryKey: decksKey,
    queryFn: ({ signal }) => apiGet<Deck[]>('/decks', { signal }),
  })
}

/** Any write may change counts, statuses and deck contents: refetch the lists. */
function useInvalidateLibrary() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: itemsKey }),
      queryClient.invalidateQueries({ queryKey: decksKey }),
      queryClient.invalidateQueries({ queryKey: triageKey }),
    ])
}

export interface QuickAddBody {
  term: string
  sentence?: string
  deck_id?: number
  on_duplicate?: 'attach' | 'new'
  attach_to?: number
}

export interface QuickAddResult {
  item: Item
  deck_id: number
  attached: boolean
  duplicates: Candidate[]
}

export function useQuickAdd() {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: QuickAddBody) => apiSend<QuickAddResult>('POST', '/items', body),
    onSuccess: invalidate,
  })
}

export interface ItemPatch {
  term?: string
  origin_sentence?: string | null
  item_type?: ItemType
  part_of_speech?: string | null
  notes?: string | null
}

export function usePatchItem(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: ItemPatch) => apiSend<ItemDetail>('PATCH', `/items/${id}`, body),
    onSuccess: invalidate,
  })
}

export function useChangeStatus(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (to: ItemStatus) => apiSend<Item>('POST', `/items/${id}/status`, { to }),
    onSuccess: invalidate,
  })
}

export function useDeleteItem(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: () => apiSend<void>('DELETE', `/items/${id}`),
    onSuccess: invalidate,
  })
}

export function useMergeItem(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (into: number) =>
      apiSend<{ kept_id: number; removed_id: number; inverted: boolean }>(
        'POST',
        `/items/${id}/merge`,
        { into },
      ),
    onSuccess: invalidate,
  })
}

export interface DeckBody {
  name?: string
  description?: string | null
  domain?: string | null
  deadline?: string | null
}

export function useCreateDeck() {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: DeckBody & { name: string }) => apiSend<Deck>('POST', '/decks', body),
    onSuccess: invalidate,
  })
}

export function usePatchDeck(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: DeckBody) => apiSend<Deck>('PATCH', `/decks/${id}`, body),
    onSuccess: invalidate,
  })
}

export function useDeleteDeck(id: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: () =>
      apiSend<{ deck_id: number; deleted_item_ids: number[] }>('DELETE', `/decks/${id}`),
    onSuccess: invalidate,
  })
}
