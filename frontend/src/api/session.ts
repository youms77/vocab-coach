import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './client'

// --- Today's plan (backend/app/domain/planner.py, SessionPlan) ------------------------------------

export type CardDirection = 'receptive' | 'productive'
export type SrsState = 'new' | 'learning' | 'review' | 'relearning'

export interface ReviewEntry {
  kind: 'review'
  card_id: number
  lexical_item_id: number
  direction: CardDirection
  state: SrsState
  due: string
  retrievability: number | null
  estimated_seconds: number
  overflow: boolean
}

export interface NewItemEntry {
  kind: 'new_item'
  lexical_item_id: number
  deck_id: number | null
  resumed: boolean
  estimated_seconds: number
}

export interface TargetedPracticeEntry {
  kind: 'targeted_practice'
  category_code: string
  error_count: number
  estimated_seconds: number
  overflow: boolean
}

export interface ConsolidationEntry {
  kind: 'consolidation'
  consolidation_task_id: number
  estimated_seconds: number
  overflow: boolean
}

export type PlanEntry = ReviewEntry | NewItemEntry | TargetedPracticeEntry | ConsolidationEntry

export type BlockKind = 'reviews' | 'new_items' | 'targeted_practice' | 'consolidation'

export interface PlanBlock {
  kind: BlockKind
  estimated_seconds: number
  entries: PlanEntry[]
}

export type PlanLimit = 'quota' | 'budget' | 'anticipation' | 'supply' | 'nothing_to_learn'

export interface DeadlinePace {
  deck_id: number
  deadline: string
  remaining: number
  days_left: number
  required_per_day: number
}

// A stable code and parameters, no text: the page translates them (D-029).
export type PlanWarning =
  | {
      code: 'reviews_over_budget'
      params: { review_seconds: number; budget_seconds: number; overflow_count: number }
    }
  | {
      code: 'deadline_unrealistic'
      params: {
        deck_id: number
        deadline: string
        remaining: number
        required_per_day: number
        achievable_per_day: number
        projected_finish: string | null
      }
    }
  | { code: 'deadline_passed'; params: { deck_id: number; deadline: string; remaining: number } }
  | { code: 'deadline_triage_pending'; params: { deck_id: number; count: number } }
  | { code: 'items_without_sheet'; params: { count: number; deck_ids: number[] } }

export type PlanWarningCode = PlanWarning['code']

export interface SessionPlan {
  study_day: string
  generated_at: string
  budget_seconds: number
  blocks: PlanBlock[]
  total_seconds: number
  new_items_allowed: number
  limit: PlanLimit
  caps: { quota: number; budget: number; anticipation: number; available: number }
  decks_to_activate: number[]
  deadline_paces: DeadlinePace[]
  warnings: PlanWarning[]
  observed_durations: string[]
}

/** The entries of one kind across the plan's blocks. */
export function entriesOf<K extends PlanEntry['kind']>(
  plan: SessionPlan,
  kind: K,
): Extract<PlanEntry, { kind: K }>[] {
  return plan.blocks
    .flatMap((block) => block.entries)
    .filter((entry): entry is Extract<PlanEntry, { kind: K }> => entry.kind === kind)
}

// --- Study session (backend/app/api/session.py, D-107) --------------------------------------------

export interface SessionSummary {
  format: string
  reviews: number
  failed_reviews: number
  discoveries_started: number
  discoveries_completed: number
  productions: number
  words: number
  duration_ms: number
  planned_minutes: number
}

export interface StudySession {
  id: number
  started_at: string
  ended_at: string | null
  study_day: string
  planned: { format: string; plan: SessionPlan }
  summary: SessionSummary | null
}

export interface Today {
  plan: SessionPlan
  open_session: StudySession | null
}

// --- Next step (backend/app/services/study_sessions.py, review_flow.py) ---------------------------

export interface Progress {
  reviews_done: number
  reviews_remaining: number
  new_done: number
  new_remaining: number
  estimated_seconds_remaining: number
}

/** A review as the API sends it: the prompt only, never the solution (D-103). Used by M4.c. */
export interface ReviewStep {
  card_id: number
  lexical_item_id: number
  direction: CardDirection
  srs_state: SrsState
  expected_reps: number
  exercise_type: string
  exercise_template_id: number | null
  input: 'choice' | 'text' | 'none'
  self_graded: boolean
  term: string | null
  prompt: Record<string, unknown>
  warnings: string[]
}

export interface NewItemStep {
  item_id: number
  term: string
  deck_id: number | null
  resumed: boolean
}

export interface PracticeStep {
  targeted_practice: { category_code: string; error_count: number } | null
  consolidation_task_id: number | null
}

interface StepBase {
  session_id: number
  progress: Progress
}

// Only the field of its type is set.
export type Step = StepBase &
  (
    | { type: 'review'; review: ReviewStep }
    | { type: 'new_item'; new_item: NewItemStep }
    | { type: 'wait'; wait: { until: string } }
    | { type: 'practice_info'; practice: PracticeStep }
    | { type: 'done' }
  )

export type StepType = Step['type']

// --- Hooks ----------------------------------------------------------------------------------------

export const sessionKey = ['session'] as const
export const todayKey = [...sessionKey, 'today'] as const
const nextKey = (sessionId: number, practiceSeen: boolean) =>
  [...sessionKey, sessionId, 'next', practiceSeen] as const

/** Today's plan, computed now (nothing written), and today's open session. */
export function useToday() {
  return useQuery({
    queryKey: todayKey,
    queryFn: ({ signal }) => apiGet<Today>('/session/today', { signal }),
  })
}

/** Idempotent within a study day: 201 (new session) and 200 (today's open one) are both a success. */
export function useStartSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<StudySession>('POST', '/session/start'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: todayKey }),
  })
}

/** The next step, computed live by the backend. Fetched again only when the page asks. */
export function useNextStep(sessionId: number | null, practiceSeen: boolean) {
  return useQuery({
    queryKey: nextKey(sessionId ?? 0, practiceSeen),
    queryFn: ({ signal }) =>
      apiGet<Step>(`/session/${sessionId}/next${practiceSeen ? '?practice_seen=true' : ''}`, {
        signal,
      }),
    enabled: sessionId !== null,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export function useEndSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: number) => apiSend<StudySession>('POST', `/session/${sessionId}/end`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: todayKey }),
  })
}
