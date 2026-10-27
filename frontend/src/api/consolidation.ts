import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend, apiUpload } from './client'
import { type Production, productionsKey } from './productions'
import { todayKey } from './session'
import type { SpeechOut } from './speech'

// backend/app/api/consolidation.py and api/speech.py (M7.a1, M7.a2): "API reference for M7.b".

export type DeckReason =
  | 'excluded_kind'
  | 'deck_done'
  | 'task_open'
  | 'no_productive_cards'
  | 'below_ratio'
  | 'not_enough_candidates'

export interface ConsolidationDeck {
  deck_id: number
  name: string
  ready: boolean
  reason: DeckReason | null
  ratio: number
  stable_cards: number
  productive_cards: number
  threshold_ratio: number
  min_stability_days: number
  candidates: number
  open_task_id: number | null
}

export const TASK_TYPES = ['talk', 'speech', 'interview_answer'] as const
export type TaskType = (typeof TASK_TYPES)[number]

export type TaskStatus = 'proposed' | 'accepted' | 'completed' | 'dismissed'

export interface Bilingual {
  en: string
  fr: string
}

export interface TaskSection {
  heading: Bilingual
  guidance: Bilingual
  item_ids: number[]
}

export interface TaskTarget {
  item_id: number
  term: string
  item_status: string
  used_correctly_count: number
}

export interface TaskAttempt {
  production_id: number
  modality: 'written' | 'oral' | string
  corrected: boolean
  created_at: string
}

export interface ConsolidationTask {
  id: number
  deck: { id: number; name: string }
  status: TaskStatus
  task_type: TaskType
  source: 'ai' | 'template'
  title: Bilingual
  prompt: Bilingual
  audience: Bilingual
  target_minutes: number
  sections: TaskSection[]
  targets: TaskTarget[]
  attempts: TaskAttempt[]
  created_at: string
}

export interface TaskPage {
  items: ConsolidationTask[]
  total: number
  limit: number
  offset: number
}

export interface CreatedTask {
  status: 'ok'
  source: 'ai' | 'template'
  /** Why the AI did not make it (a template), or null. */
  reason: string | null
  task: ConsolidationTask
}

export const MIN_TERMS = 8
export const MAX_TERMS = 15
export const DEFAULT_TERMS = 10
export const TASKS_PAGE_SIZE = 20
export const MAX_WRITTEN_CHARS = 4000

export const consolidationKey = ['consolidation'] as const

export function useConsolidationDecks() {
  return useQuery({
    queryKey: [...consolidationKey, 'decks'],
    queryFn: ({ signal }) => apiGet<ConsolidationDeck[]>('/consolidation/decks', { signal }),
  })
}

export function useConsolidationTasks(page: number, status: TaskStatus | '') {
  return useQuery({
    queryKey: [...consolidationKey, 'tasks', status, page],
    queryFn: ({ signal }) =>
      apiGet<TaskPage>(
        `/consolidation/tasks?limit=${TASKS_PAGE_SIZE}&offset=${page * TASKS_PAGE_SIZE}${
          status !== '' ? `&status=${status}` : ''
        }`,
        { signal },
      ),
  })
}

export function useConsolidationTask(id: number) {
  return useQuery({
    enabled: id > 0,
    queryKey: [...consolidationKey, 'task', id],
    queryFn: ({ signal }) => apiGet<ConsolidationTask>(`/consolidation/tasks/${id}`, { signal }),
  })
}

export interface CreateTaskBody {
  deck_id: number
  task_type: TaskType
  term_count: number
}

/** Makes a task with the AI (a few seconds) or, when it cannot, from a template. */
export function useCreateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateTaskBody) =>
      apiSend<CreatedTask>('POST', '/consolidation/tasks', body),
    onSuccess: (created) => {
      queryClient.setQueryData([...consolidationKey, 'task', created.task.id], created.task)
      void queryClient.invalidateQueries({ queryKey: [...consolidationKey, 'decks'] })
      void queryClient.invalidateQueries({ queryKey: [...consolidationKey, 'tasks'] })
    },
  })
}

function useRefreshTask() {
  const queryClient = useQueryClient()
  return (task: ConsolidationTask) => {
    queryClient.setQueryData([...consolidationKey, 'task', task.id], task)
    void queryClient.invalidateQueries({ queryKey: [...consolidationKey, 'tasks'] })
    void queryClient.invalidateQueries({ queryKey: [...consolidationKey, 'decks'] })
    void queryClient.invalidateQueries({ queryKey: todayKey })
  }
}

export function useTaskStatus(id: number) {
  const refresh = useRefreshTask()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (to: Exclude<TaskStatus, 'proposed'>) =>
      apiSend<ConsolidationTask>('POST', `/consolidation/tasks/${id}/status`, { to }),
    onSuccess: refresh,
    // A change made meanwhile (another tab): show what is stored.
    onError: () =>
      void queryClient.invalidateQueries({ queryKey: [...consolidationKey, 'task', id] }),
  })
}

export function useWrittenAttempt(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      apiSend<Production>('POST', `/consolidation/tasks/${id}/attempts/written`, { text }),
    onSuccess: (created) => {
      queryClient.setQueryData([...productionsKey, 'detail', created.id], created)
      void queryClient.invalidateQueries({ queryKey: [...consolidationKey] })
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
    },
  })
}

export interface ConsolidationSpeechBody {
  blob: Blob
  durationS: number
}

/** Stores and transcribes the recorded talk; the correction is a separate call. */
export function useSpokenAttempt(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ConsolidationSpeechBody) =>
      apiUpload<SpeechOut>('/speech/consolidation', body.blob, {
        task_id: id,
        duration_s: body.durationS,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...consolidationKey] })
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
    },
  })
}
