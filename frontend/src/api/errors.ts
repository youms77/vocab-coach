import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'
import { todayKey } from './session'

// backend/app/api/error_log.py: the error log (list, edit, manual entry) and the category tree.

export const ERROR_SOURCES = [
  'writing',
  'speaking',
  'review',
  'transcript',
  'manual',
  'drill',
  'consolidation',
] as const
export type ErrorSource = (typeof ERROR_SOURCES)[number]

export interface CategoryRef {
  code: string
  label_en: string
  label_fr: string
  status: string
}

export interface TermRef {
  id: number
  term: string
}

export interface ErrorOut {
  id: number
  source: ErrorSource
  original_text: string
  erroneous_text: string
  correction: string
  alternatives: string[]
  explanation: string
  /** The AI's translation, while the explanation is still the AI's; null otherwise. */
  explanation_fr: string | null
  category: CategoryRef
  term: TermRef | null
  production_attempt_id: number | null
  review_log_id: number | null
  occurred_at: string
  updated_at: string
}

export type CategoryStatus = 'active' | 'proposed' | 'rejected'
export type CategoryOrigin = 'builtin' | 'user' | 'ai'

export interface CategoryNode {
  id: number
  code: string
  parent_code: string | null
  label_en: string
  label_fr: string
  description_en: string
  description_fr: string
  status: CategoryStatus
  origin: CategoryOrigin
  count: number
  count_recent: number
  children: CategoryNode[]
}

export const categoriesKey = ['error-categories'] as const
export const errorsKey = ['errors'] as const

export function useErrorCategories(enabled = true) {
  return useQuery({
    queryKey: categoriesKey,
    enabled,
    queryFn: ({ signal }) => apiGet<CategoryNode[]>('/error-categories', { signal }),
    staleTime: 60_000,
  })
}

/** Every node of the tree, parents before children, as a map by code. */
export function categoryLabels(tree: CategoryNode[]): Map<string, CategoryNode> {
  const byCode = new Map<string, CategoryNode>()
  const visit = (nodes: CategoryNode[]) => {
    // A label lookup must never take a page down: an unexpected answer gives an empty map.
    if (!Array.isArray(nodes)) return
    for (const node of nodes) {
      byCode.set(node.code, node)
      visit(node.children)
    }
  }
  visit(tree)
  return byCode
}

/** The label of a category in the interface language (the code is kept next to it by the page). */
export function labelOf(
  category: { label_en: string; label_fr: string },
  language: string,
): string {
  return language.startsWith('fr') ? category.label_fr : category.label_en
}

// --- The list ---------------------------------------------------------------------------------------

export const ERRORS_PAGE_SIZE = 25

export interface Facet {
  code: string
  label_en: string
  label_fr: string
  count: number
}

export interface ErrorPage {
  errors: ErrorOut[]
  total: number
  page: number
  page_size: number
  /** Per level-2 category, over the whole filtered set (not only this page). */
  facets: Facet[]
}

/** The list filters. Dates are calendar days ("2026-10-18") in the browser's time zone. */
export interface ErrorFilters {
  category: string
  source: ErrorSource | ''
  q: string
  from: string
  to: string
  itemId: number | null
  /** From 1. */
  page: number
}

export const emptyErrorFilters: ErrorFilters = {
  category: '',
  source: '',
  q: '',
  from: '',
  to: '',
  itemId: null,
  page: 1,
}

const DAY = /^\d{4}-\d{2}-\d{2}$/

/** Local midnight of a "YYYY-MM-DD" day, `offset` days later, as the UTC instant the backend wants. */
export function localMidnight(day: string, offset = 0): string | null {
  if (!DAY.test(day)) return null
  const [year, month, date] = day.split('-').map(Number)
  const at = new Date(year, month - 1, date + offset)
  return Number.isNaN(at.getTime()) ? null : at.toISOString()
}

/**
 * The backend query string. `occurred_to` is exclusive, so "to" sends the start of the day after
 * the last day wanted.
 */
export function errorsQuery(filters: ErrorFilters): string {
  const params = new URLSearchParams()
  if (filters.category !== '') params.set('category', filters.category)
  if (filters.source !== '') params.set('source', filters.source)
  if (filters.itemId !== null) params.set('item_id', String(filters.itemId))
  const from = localMidnight(filters.from)
  if (from !== null) params.set('occurred_from', from)
  const to = localMidnight(filters.to, 1)
  if (to !== null) params.set('occurred_to', to)
  if (filters.q.trim() !== '') params.set('q', filters.q.trim().slice(0, 300))
  params.set('page', String(filters.page))
  params.set('page_size', String(ERRORS_PAGE_SIZE))
  return params.toString()
}

/** The filters of the page URL (`?category=&source=&q=&from=&to=&item_id=&page=`); junk is ignored. */
export function parseFilters(params: URLSearchParams): ErrorFilters {
  const source = params.get('source') ?? ''
  const itemId = Number(params.get('item_id'))
  const page = Number(params.get('page'))
  const day = (name: string) => {
    const value = params.get(name) ?? ''
    return localMidnight(value) !== null ? value : ''
  }
  return {
    category: params.get('category') ?? '',
    source: (ERROR_SOURCES as readonly string[]).includes(source) ? (source as ErrorSource) : '',
    q: params.get('q') ?? '',
    from: day('from'),
    to: day('to'),
    itemId: Number.isInteger(itemId) && itemId > 0 ? itemId : null,
    page: Number.isInteger(page) && page > 1 ? page : 1,
  }
}

/** The URL search parameters of some filters: empty values and page 1 are left out. */
export function filtersToParams(filters: ErrorFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.category !== '') params.set('category', filters.category)
  if (filters.source !== '') params.set('source', filters.source)
  if (filters.q.trim() !== '') params.set('q', filters.q.trim())
  if (filters.from !== '') params.set('from', filters.from)
  if (filters.to !== '') params.set('to', filters.to)
  if (filters.itemId !== null) params.set('item_id', String(filters.itemId))
  if (filters.page > 1) params.set('page', String(filters.page))
  return params
}

export function useErrors(filters: ErrorFilters) {
  const query = errorsQuery(filters)
  return useQuery({
    queryKey: [...errorsKey, 'list', query],
    queryFn: ({ signal }) => apiGet<ErrorPage>(`/errors?${query}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useError(id: number, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...errorsKey, 'detail', id],
    queryFn: ({ signal }) => apiGet<ErrorOut>(`/errors/${id}`, { signal }),
  })
}

/** Every write to the log changes the lists and the category counts. */
function useInvalidateLog() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: errorsKey }),
      queryClient.invalidateQueries({ queryKey: categoriesKey }),
    ])
}

export const MAX_ALTERNATIVES = 2

export interface CreateErrorBody {
  original_text: string | null
  erroneous_text: string
  correction: string
  alternatives: string[]
  category_code: string
  explanation: string
  lexical_item_id: number | null
}

export function useCreateError() {
  const invalidate = useInvalidateLog()
  return useMutation({
    mutationFn: (body: CreateErrorBody) => apiSend<ErrorOut>('POST', '/errors', body),
    onSuccess: invalidate,
  })
}

/** Only the changed fields are sent; `lexical_item_id: null` unlinks the term. */
export interface ErrorPatch {
  correction?: string
  alternatives?: string[]
  explanation?: string
  category_code?: string
  lexical_item_id?: number | null
}

export function usePatchError(id: number) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateLog()
  return useMutation({
    mutationFn: (body: ErrorPatch) => apiSend<ErrorOut>('PATCH', `/errors/${id}`, body),
    onSuccess: (updated) => {
      queryClient.setQueryData([...errorsKey, 'detail', id], updated)
      return invalidate()
    },
  })
}

export function useDeleteError(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<void>('DELETE', `/errors/${id}`),
    // The lists only: refetching this error's own detail (still mounted) would answer 404.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: [...errorsKey, 'list'] }),
        queryClient.invalidateQueries({ queryKey: categoriesKey }),
      ]),
  })
}

// --- Categories -------------------------------------------------------------------------------------

export interface CreateCategoryBody {
  parent_code: string | null
  slug: string
  label_en: string
  label_fr: string
  description_en: string
  description_fr: string
}

/** Same rule as the backend: a lowercase letter, then 1 to 40 lowercase letters, digits or `_`. */
export const SLUG_PATTERN = /^[a-z][a-z0-9_]{1,40}$/

export function useCreateCategory() {
  const invalidate = useInvalidateLog()
  return useMutation({
    mutationFn: (body: CreateCategoryBody) =>
      apiSend<CategoryNode>('POST', '/error-categories', body),
    onSuccess: invalidate,
  })
}

export interface ResolveBody {
  decision: 'accept' | 'reject'
  label_en?: string
  label_fr?: string
}

export interface ResolveResult {
  category: CategoryNode
  reassigned_error_ids: number[]
}

export function useResolveCategory(id: number) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateLog()
  return useMutation({
    mutationFn: (body: ResolveBody) =>
      apiSend<ResolveResult>('POST', `/error-categories/${id}/resolve`, body),
    onSuccess: (result) => {
      // A rejection moves errors to the parent, and targeted practice reads the counts.
      if (result.reassigned_error_ids.length > 0) {
        void queryClient.invalidateQueries({ queryKey: todayKey })
      }
      // Not awaited: the proposal's card unmounts when the tree refreshes, and a `mutate` callback
      // of an unmounted component never runs.
      void invalidate()
    },
    // A proposal resolved elsewhere answers `category_not_proposed`: show the tree as it is.
    onError: () => void queryClient.invalidateQueries({ queryKey: categoriesKey }),
  })
}
