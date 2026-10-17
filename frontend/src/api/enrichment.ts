import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiGet, apiSend } from './client'
import { itemsKey, useInvalidateLibrary, type Candidate, type Item, type SheetState } from './library'

// --- Usage sheet (backend/app/domain/usage_sheet.py, schema version 1) ----------------------------

export const REGISTERS = ['academic', 'neutral', 'spoken', 'informal'] as const
export type Register = (typeof REGISTERS)[number]

export const EXAMPLE_KINDS = ['academic', 'spoken', 'general'] as const
export type ExampleKind = (typeof EXAMPLE_KINDS)[number]

export interface Pronunciation {
  ipa_us: string | null
  stressed_syllable: string | null
  note: string | null
}

export interface UsageSheet {
  schema_version: 1
  part_of_speech: string | null
  register_level: Register | null
  register_note: string | null
  meaning_in_context: string | null
  definition_simple: string | null
  translation_fr: string[]
  other_meanings: { definition: string; translation_fr: string }[]
  usage_notes: string | null
  collocations: { pattern: string; example: string | null }[]
  examples: { sentence: string; kind: ExampleKind }[]
  word_family: { form: string; part_of_speech: string }[]
  pronunciation: Pronunciation | null
  french_speaker_pitfalls: { wrong: string; right: string; explanation: string }[]
  confusables: { term: string; difference: string }[]
}

export interface SheetVersion {
  enrichment_id: number
  version: number // 1 = oldest
  is_current: boolean
  status: 'complete' | 'needs_completion'
  sheet_status: SheetState
  edited_by_user: boolean
  edited_at: string | null
  provider: string | null
  model: string | null
  prompt_version: string | null
  schema_version: number
  created_at: string
  content: UsageSheet
}

// The gateway's reasons (backend/app/ai/types.py UnavailableReason).
export const UNAVAILABLE_REASONS = [
  'no_provider_configured',
  'network',
  'quota',
  'auth',
  'timeout',
  'all_failed',
] as const
export type UnavailableReason = (typeof UNAVAILABLE_REASONS)[number]

/** One enrichment batch. An AI failure is a report (HTTP 200), not an error. */
export interface RunReport {
  status: 'ok' | 'partial' | 'unavailable'
  reason: UnavailableReason | null
  generated: number
  needs_completion: number
  superseded: number
  failed: number // regeneration failed: the existing sheet is kept
  remaining: number
  item_ids: number[]
}

export interface PendingItem {
  item_id: number
  term: string
  status: Item['status']
}

// --- Exercise templates (backend/app/domain/exercises.py) -----------------------------------------

export interface Exercise {
  id: number
  lexical_item_id: number
  exercise_type: string
  direction: string | null
  origin: string
  prompt_version: string | null
  edited_by_user: boolean
  content: Record<string, unknown>
  created_at: string
  updated_at: string
}

// --- List extension -------------------------------------------------------------------------------

// backend/app/ai/schemas/list_extension.py
export const EXTENSION_MIN = 10
export const EXTENSION_MAX = 30
export const EXTENSION_DEFAULT = 20

export interface ExtensionResult {
  status: 'ok' | 'incomplete' | 'unavailable'
  reason: UnavailableReason | null
  created: Item[]
  suggested: number
  dropped_existing: number
  dropped_in_batch: number
  possible_duplicates: { item_id: number; candidates: Candidate[] }[]
}

// --- Hooks ----------------------------------------------------------------------------------------

// Under `items`, so every library write (and the invalidation below) refreshes them too.
const sheetKey = (itemId: number) => [...itemsKey, 'sheet', itemId] as const
const exercisesKey = (itemId: number) => [...itemsKey, 'exercises', itemId] as const
export const pendingKey = [...itemsKey, 'pending'] as const

/** The current sheet, or `null` when the term has none yet (404 `sheet_not_found`). */
export function useSheet(itemId: number, enabled = true) {
  return useQuery({
    queryKey: [...sheetKey(itemId), 'current'],
    queryFn: async ({ signal }) => {
      try {
        return await apiGet<SheetVersion>(`/items/${itemId}/sheet`, { signal })
      } catch (error) {
        if (error instanceof ApiError && error.code === 'sheet_not_found') return null
        throw error
      }
    },
    enabled,
  })
}

export function useSheetVersions(itemId: number, enabled = true) {
  return useQuery({
    queryKey: [...sheetKey(itemId), 'versions'],
    queryFn: ({ signal }) => apiGet<SheetVersion[]>(`/items/${itemId}/sheet/versions`, { signal }),
    enabled,
  })
}

export function useSaveSheet(itemId: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: { content: UsageSheet; base_enrichment_id: number | null }) =>
      apiSend<SheetVersion>('PUT', `/items/${itemId}/sheet`, body),
    // The typed-recall exercise follows the saved sheet (D-082): refetch everything of the term.
    onSuccess: invalidate,
  })
}

/** 409 `sheet_edited` until it is sent with `confirm_overwrite: true` (the user's consent). */
export function useRegenerateSheet(itemId: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (confirmOverwrite: boolean) =>
      apiSend<RunReport>('POST', `/items/${itemId}/sheet/regenerate`, {
        confirm_overwrite: confirmOverwrite,
      }),
    onSuccess: invalidate,
  })
}

export function useExercises(itemId: number, enabled = true) {
  return useQuery({
    queryKey: exercisesKey(itemId),
    queryFn: ({ signal }) => apiGet<Exercise[]>(`/items/${itemId}/exercises`, { signal }),
    enabled,
  })
}

export function usePatchExercise(exercise: Exercise) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: Record<string, unknown>) =>
      apiSend<Exercise>('PATCH', `/exercises/${exercise.id}`, { content }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: exercisesKey(exercise.lexical_item_id) }),
  })
}

export function usePendingEnrichment(deckId: number | null, includeIncomplete: boolean) {
  const params = new URLSearchParams()
  if (deckId !== null) params.set('deck_id', String(deckId))
  if (includeIncomplete) params.set('include_incomplete', 'true')
  const query = params.toString()
  return useQuery({
    queryKey: [...pendingKey, query],
    queryFn: ({ signal }) =>
      apiGet<{ count: number; items: PendingItem[] }>(
        `/enrichment/pending${query === '' ? '' : `?${query}`}`,
        { signal },
      ),
  })
}

export interface RunBody {
  deck_id?: number
  item_ids?: number[]
  include_incomplete?: boolean
}

/** One batch of at most 5 terms. The caller loops (EnrichmentPage) and refreshes when done. */
export function useRunEnrichment() {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (body: RunBody) => apiSend<RunReport>('POST', '/enrichment/run', body),
    onSettled: invalidate,
  })
}

export function useExtendDeck(deckId: number) {
  const invalidate = useInvalidateLibrary()
  return useMutation({
    mutationFn: (count: number) =>
      apiSend<ExtensionResult>('POST', `/decks/${deckId}/extension`, { count }),
    onSuccess: invalidate,
  })
}
