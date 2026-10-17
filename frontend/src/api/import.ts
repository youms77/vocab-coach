import { useMutation, useQueryClient } from '@tanstack/react-query'

import { apiSend } from './client'
import { decksKey, itemsKey, triageKey, type Candidate, type ItemType } from './library'

/** The backend refuses a longer text (`MAX_TEXT_CHARS` in app/api/library.py). */
export const MAX_IMPORT_CHARS = 300_000

export const SEVERITIES = ['info', 'warning', 'ambiguous', 'error'] as const
export type Severity = (typeof SEVERITIES)[number]

// `ProblemCode` in backend/app/domain/markdown_import.py: one i18n message per code.
export const PROBLEM_CODES = [
  'too_large',
  'not_utf8',
  'invalid_header',
  'invalid_header_value',
  'unclosed_header',
  'unknown_header_key',
  'invalid_deadline',
  'past_deadline',
  'heading_ignored',
  'horizontal_rule',
  'multiple_separators',
  'looks_like_definition',
  'looks_like_sentence',
  'nested_item',
  'empty_term',
  'term_too_long',
  'term_not_in_sentence',
  'duplicate_in_file',
  'duplicate_exact',
  'duplicate_possible',
  'already_in_deck',
  'existing_status_kept',
] as const
export type ProblemCode = (typeof PROBLEM_CODES)[number]

export function isProblemCode(code: string): code is ProblemCode {
  return (PROBLEM_CODES as readonly string[]).includes(code)
}

export interface Problem {
  line: number | null
  severity: Severity
  code: string
  message: string
  suggestion: Record<string, unknown> | null
}

export interface ImportHeader {
  deck: string | null
  domain: string | null
  source: string | null
  context: string | null
  deadline: string | null
}

export type OnDuplicate = 'attach' | 'new' | 'skip'

export interface PreviewRow {
  line: number
  raw: string
  term: string
  sentence: string | null
  item_type: ItemType
  normalized_form: string
  include: boolean
  ambiguous: boolean
  problems: Problem[]
  duplicates: Candidate[]
  in_target_deck: boolean
  default_on_duplicate: 'attach' | 'new' | null
}

export interface Preview {
  header: ImportHeader
  rows: PreviewRow[]
  problems: Problem[]
  rejected: boolean
  lines_read: number
  importable: number
  ambiguous: number
  with_duplicates: number
}

export interface CommitRow {
  line: number
  term: string
  sentence: string | null
  item_type: ItemType
  include: boolean
  confirmed: boolean
  on_duplicate?: OnDuplicate
  attach_to?: number
}

export interface CommitBody {
  header: ImportHeader
  rows: CommitRow[]
  target: { deck_id: number } | { new_deck_name: string }
  intake: 'triage' | 'queued'
}

export interface ImportSummary {
  deck_id: number
  created_deck: boolean
  lines_read: number
  imported: number
  attached: number
  skipped: number
  ambiguous: number
  item_ids: number[]
}

/** Nothing is written: the preview only reads the library to find duplicates. */
export function usePreview() {
  return useMutation({
    mutationFn: (body: { text: string; deck_id?: number }) =>
      apiSend<Preview>('POST', '/import/preview', body),
  })
}

export function useCommit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CommitBody) => apiSend<ImportSummary>('POST', '/import/commit', body),
    onSuccess: () =>
      Promise.all(
        [itemsKey, decksKey, triageKey].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  })
}
