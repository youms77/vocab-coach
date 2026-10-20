import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiGet, apiSend } from './client'
import type { ErrorOut } from './errors'
import type { Comparison } from './speech'

// backend/app/api/productions.py, api/writing.py and the stored `correction-1` feedback
// (app/services/corrections.py, D-128).

export type ProductionKind = 'writing' | 'transcript_analysis' | 'drill' | 'shadowing' | 'speaking' | string

export interface ProductionTarget {
  lexical_item_id: number
  term: string
  used: boolean | null
  used_correctly: boolean | null
}

export type SentenceStatus = 'correct' | 'corrected' | 'unnatural'

export interface CorrectionSentence {
  index: number
  corrected: string
  status: SentenceStatus
}

export interface CorrectionError {
  sentence_index: number
  wrong: string
  correction: string
  alternatives: string[]
  category_code: string
  proposed_subcategory: unknown
  explanation_en: string
  explanation_fr: string | null
  target_ref: number | null
}

export interface NaturalnessNote {
  sentence_index: number
  text: string
  suggestion: string
  note: string
}

export interface CorrectionOutput {
  sentences: CorrectionSentence[]
  corrected_text: string
  natural_text: string | null
  errors: CorrectionError[]
  naturalness_notes: NaturalnessNote[]
  targets: unknown[]
  overall_comment: string
}

/** Position of `output.errors[error]` in `text`, in Unicode code points (D-128). */
export interface Span {
  error: number
  sentence_index: number
  start: number
  end: number
}

export interface TargetCheck {
  ref: number
  lexical_item_id: number
  used: boolean
  used_correctly: boolean | null
  ai_used: boolean | null
  comment: string | null
  disagreement: boolean
}

/** A unit of a transcript: a user turn, or a piece of a long one (`turn` is 0-based, D-133). */
export interface TranscriptUnit {
  index: number
  turn: number
  start: number
  end: number
  opens_turn: boolean
}

/**
 * `format: "correction-1"` is the written correction; `"transcript-1"` has the same keys plus
 * `units`, `context_sent` and `calls` (units play the part of sentences, D-134). Any other format
 * is shown as plain text by the correction view.
 */
export interface Feedback {
  format: string
  prompt_version?: string
  provider?: string
  model?: string
  output?: CorrectionOutput
  spans?: Span[]
  error_event_ids?: number[]
  targets?: TargetCheck[]
  units?: TranscriptUnit[]
  context_sent?: boolean
  calls?: { ai_call_id: number | null; provider: string | null; model: string | null; units: number[] }[]
}

export interface Production {
  id: number
  kind: ProductionKind
  modality: string
  prompt_text: string | null
  text: string
  word_count: number
  corrected: boolean
  feedback: Feedback | null
  ai_call_id: number | null
  study_session_id: number | null
  targets: ProductionTarget[]
  created_at: string
  updated_at: string
  /** Spoken productions (M6): the recording, whether it was transcribed, the comparison. */
  audio_url: string | null
  audio_seconds: number | null
  transcription_status: 'pending' | 'ok' | 'silence' | null
  comparison: Comparison | null
}

export interface ProposedCategory {
  id: number
  code: string
  parent_code: string
  label_en: string
  label_fr: string
  description_en: string
  status: string
}

export type AiStatus = 'ok' | 'incomplete' | 'unavailable'

/** An AI failure is a 200 answer with `status` and `reason`, not an HTTP error (D-081). */
export interface CorrectionResult {
  status: AiStatus
  reason: string | null
  attempt: Production
  errors: ErrorOut[]
  proposed_categories: ProposedCategory[]
}

export interface ProductionPage {
  items: Production[]
  total: number
  limit: number
  offset: number
}

export const TOPIC_TAGS = ['academic', 'interview', 'data_science', 'everyday', 'campus'] as const
export type TopicTag = (typeof TOPIC_TAGS)[number]

export interface WritingTopic {
  id: string
  en: string
  fr: string
  tags: TopicTag[]
}

export const MAX_TEXT_CHARS = 4000
export const MAX_PROMPT_CHARS = 500
export const HISTORY_PAGE_SIZE = 20

export const productionsKey = ['productions'] as const

export interface CreateWritingBody {
  kind: 'writing'
  text: string
  prompt: string | null
  target_item_ids: number[]
  study_session_id: number | null
}

export function useCreateProduction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateWritingBody) => apiSend<Production>('POST', '/productions', body),
    onSuccess: (created) => {
      queryClient.setQueryData([...productionsKey, 'detail', created.id], created)
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
    },
  })
}

export function useProduction(id: number, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...productionsKey, 'detail', id],
    queryFn: ({ signal }) => apiGet<Production>(`/productions/${id}`, { signal }),
  })
}

export function useProductions(kind: string, page: number) {
  return useQuery({
    queryKey: [...productionsKey, 'list', kind, page],
    queryFn: ({ signal }) =>
      apiGet<ProductionPage>(
        `/productions?kind=${kind}&limit=${HISTORY_PAGE_SIZE}&offset=${page * HISTORY_PAGE_SIZE}`,
        { signal },
      ),
  })
}

/** What a successful correction changes: the production, the lists, the error log and the counts. */
export function applyCorrection(queryClient: QueryClient, result: CorrectionResult) {
  if (result.status !== 'ok') return
  queryClient.setQueryData([...productionsKey, 'detail', result.attempt.id], result.attempt)
  void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
  void queryClient.invalidateQueries({ queryKey: ['error-categories'] })
  void queryClient.invalidateQueries({ queryKey: ['errors'] })
}

/** Corrected meanwhile (another tab, or a retry that did succeed): show what is stored. */
export function applyCorrectionError(queryClient: QueryClient, error: unknown, id: number) {
  if (error instanceof ApiError && error.code === 'already_corrected') {
    void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'detail', id] })
  }
}

/**
 * Corrects a production with the AI. It takes 2 to 60 s: the caller disables its button while
 * this runs. A corrected production changes the error log and the category counts too.
 */
export function useCorrectProduction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => apiSend<CorrectionResult>('POST', `/productions/${id}/correct`),
    onError: (error, id) => applyCorrectionError(queryClient, error, id),
    onSuccess: (result) => applyCorrection(queryClient, result),
  })
}

export function useWritingTopics(tag: TopicTag | '') {
  return useQuery({
    queryKey: ['writing-topics', tag],
    queryFn: ({ signal }) =>
      apiGet<WritingTopic[]>(`/writing/topics?count=3${tag !== '' ? `&tag=${tag}` : ''}`, { signal }),
    staleTime: 5 * 60_000,
  })
}
