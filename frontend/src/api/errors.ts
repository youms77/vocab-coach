import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

// backend/app/api/error_log.py (ErrorOut, the category tree). M5.b2 adds the list, edit and
// category-management hooks to this file.

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
