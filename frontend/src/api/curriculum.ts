import { useCallback } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiGet, apiSend } from './client'
import { decksKey, type ItemStatus, itemsKey, triageKey } from './library'
import { todayKey } from './session'

// backend/app/api/curriculum.py, services/curriculum.py and services/curriculum_units.py (module H,
// M8.a1 and M8.a2): "API reference for M8.b" in docs/PROGRESS.md.

export type TrackKind = 'wordlist' | 'scenarios'
export type UnitState = 'not_opened' | 'opened' | 'triaged'
export type UnitProgress = 'not_started' | 'in_progress' | 'done'
export type UnitContentStatus = 'pending' | 'generated' | 'edited'
export type UnitStep = 'formulas' | 'dialogue' | 'shadowing' | 'final_task'

export const UNIT_STEPS: readonly UnitStep[] = ['formulas', 'dialogue', 'shadowing', 'final_task']
/** Units per page of a track (the backend's default). */
export const TRACK_PAGE_SIZE = 25

export interface Labels {
  en: string
  fr: string
}

export interface TrackSummary {
  code: string
  kind: TrackKind
  source: 'ngsl' | 'nawl' | null
  title: Labels
  description: Labels
  unit_size: number | null
  unit_count: number
  available: boolean
  /** `wordlist_missing` when the word list file is not there. */
  reason: string | null
  started: boolean
  deck_id: number | null
  opened_units: number
  triaged_units: number
  syllabus_version: number
}

export interface UnitRow {
  number: number
  code: string
  title: string
  title_fr: string | null
  state: UnitState
  unit_id: number | null
  first_rank: number | null
  last_rank: number | null
  word_count: number | null
  content_status: UnitContentStatus | null
  progress: UnitProgress
}

export interface TrackDetail {
  track: TrackSummary
  total_units: number
  limit: number
  offset: number
  units: UnitRow[]
}

export interface StartResult {
  track: TrackSummary
  created: boolean
}

export interface UnitTerm {
  item_id: number
  term: string
  status: ItemStatus
}

export interface Formula {
  index: number
  text: string
  item_type: 'spoken_formula' | 'collocation' | 'phrase'
  function_en: string
  function_fr: string
  /** The backend's `FormulaOut.style`, serialised as `register`. */
  register: string
  /** The library term, once the formula was added. */
  item_id: number | null
}

export interface DialogueLine {
  speaker: string
  text: string
}

export interface Dialogue {
  setting_en: string
  setting_fr: string
  speakers: string[]
  lines: DialogueLine[]
}

export interface ShadowingLine {
  line_index: number
  text: string
  take_count: number
  done: boolean
}

export interface FinalTask {
  prompt_en: string
  prompt_fr: string
  minutes: number
  formula_refs: number[]
  target_item_ids: number[]
  attempt_ids: number[]
  corrected: boolean
}

export interface Scenario {
  revision: number
  edited: boolean
  format: string
  provider: string | null
  model: string | null
  prompt_version: string | null
  level: string | null
  formulas: Formula[]
  dialogue: Dialogue
  shadowing: ShadowingLine[]
  final_task: FinalTask
  steps: Record<UnitStep, boolean>
  /** Null when the unit is done. */
  next_step: UnitStep | null
}

export interface Unit {
  id: number
  track_code: string
  number: number
  code: string
  title: string
  state: UnitState
  progress: UnitProgress
  content_status: UnitContentStatus
  deck_id: number | null
  first_rank: number | null
  last_rank: number | null
  terms: UnitTerm[]
  /** Null for a word unit. */
  scenario: Scenario | null
}

export interface OpenResult {
  created: boolean
  imported: number
  attached: number
  skipped: number
  unit: Unit
}

export interface GenerationResult {
  status: 'ok' | 'incomplete' | 'unavailable'
  reason: string | null
  detail: string | null
  unit: Unit | null
}

export interface StepResult {
  changed: boolean
  unit: Unit
}

export interface TermsResult {
  imported: number
  attached: number
  skipped: number
  unit: Unit
}

export const curriculumKey = ['curriculum'] as const
export const tracksKey = [...curriculumKey, 'tracks'] as const
export const unitKey = (id: number) => [...curriculumKey, 'unit', id] as const

export function useTracks() {
  return useQuery({
    queryKey: tracksKey,
    queryFn: ({ signal }) => apiGet<TrackSummary[]>('/curriculum/tracks', { signal }),
  })
}

/** A slice of a track's units. `enabled` lets a page wait for what it needs. */
export function useTrackSlice(code: string, limit: number, offset: number, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...curriculumKey, 'track', code, limit, offset],
    queryFn: ({ signal }) =>
      apiGet<TrackDetail>(
        `/curriculum/tracks/${encodeURIComponent(code)}?limit=${limit}&offset=${offset}`,
        { signal },
      ),
    placeholderData: keepPreviousData,
  })
}

/** One page (25 units) of a track, counted from 0. */
export function useTrack(code: string, page: number) {
  return useTrackSlice(code, TRACK_PAGE_SIZE, page * TRACK_PAGE_SIZE)
}

export function useUnit(id: number) {
  return useQuery({
    enabled: id > 0,
    queryKey: unitKey(id),
    queryFn: ({ signal }) => apiGet<Unit>(`/curriculum/units/${id}`, { signal }),
  })
}

/** Everything a write can change: tracks and units, the library, the triage queue and Today. */
function useRefreshAll() {
  const queryClient = useQueryClient()
  return () => {
    for (const key of [curriculumKey, itemsKey, decksKey, triageKey, todayKey]) {
      void queryClient.invalidateQueries({ queryKey: key })
    }
  }
}

export function useStartTrack() {
  const refresh = useRefreshAll()
  return useMutation({
    mutationFn: (code: string) =>
      apiSend<StartResult>('POST', `/curriculum/tracks/${encodeURIComponent(code)}/start`),
    onSuccess: refresh,
  })
}

export function useOpenUnit() {
  const refresh = useRefreshAll()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, number }: { code: string; number: number }) =>
      apiSend<OpenResult>(
        'POST',
        `/curriculum/tracks/${encodeURIComponent(code)}/units/${number}/open`,
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(unitKey(result.unit.id), result.unit)
      refresh()
    },
  })
}

/**
 * Writes a scenario unit with the AI (a few seconds). `incomplete` and `unavailable` are HTTP 200
 * answers with nothing written; a `409 unit_generated` (written meanwhile, e.g. in another tab)
 * only refreshes what is shown.
 */
export function useGenerateUnit() {
  const refresh = useRefreshAll()
  return useMutation({
    mutationFn: ({ code, number }: { code: string; number: number }) =>
      apiSend<GenerationResult>(
        'POST',
        `/curriculum/tracks/${encodeURIComponent(code)}/units/${number}/generate`,
      ),
    onSuccess: (result) => {
      if (result.status === 'ok') refresh()
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'unit_generated') refresh()
    },
  })
}

export function useMarkStep() {
  const refresh = useRefreshAll()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ unitId, step }: { unitId: number; step: 'formulas' | 'dialogue' }) =>
      apiSend<StepResult>('POST', `/curriculum/units/${unitId}/steps/${step}`),
    onSuccess: (result) => {
      queryClient.setQueryData(unitKey(result.unit.id), result.unit)
      refresh()
    },
  })
}

export function useAddUnitTerms() {
  const refresh = useRefreshAll()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ unitId, indices }: { unitId: number; indices: number[] }) =>
      apiSend<TermsResult>('POST', `/curriculum/units/${unitId}/terms`, { indices }),
    onSuccess: (result) => {
      queryClient.setQueryData(unitKey(result.unit.id), result.unit)
      refresh()
    },
  })
}

/** A formula as `PUT /curriculum/units/{id}/content` takes it (`register` is the JSON key). */
export interface FormulaEdit {
  text: string
  item_type: Formula['item_type']
  function_en: string
  function_fr: string
  register: string
}

/** What an edit replaces: absent parts stay as they are. Positions are 0-based (D-250). */
export interface UnitContentEdit {
  expected_revision: number
  formulas?: FormulaEdit[]
  dialogue?: Dialogue
  shadowing?: number[]
  final_task?: Pick<FinalTask, 'prompt_en' | 'prompt_fr' | 'minutes' | 'formula_refs'>
}

/**
 * Replaces whole parts of a scenario unit under its revision (never calls the AI). 409
 * `unit_changed` and 422 `invalid_content` are left to the editor, which keeps its edits on screen;
 * a 409 only reads the unit again so that "Load the latest version" has something to load.
 */
export function useEditUnitContent() {
  const refresh = useRefreshAll()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ unitId, edit }: { unitId: number; edit: UnitContentEdit }) =>
      apiSend<Unit>('PUT', `/curriculum/units/${unitId}/content`, edit),
    onSuccess: (unit) => {
      queryClient.setQueryData(unitKey(unit.id), unit)
      refresh()
    },
    onError: (error, { unitId }) => {
      if (error instanceof ApiError && error.code === 'unit_changed') {
        void queryClient.invalidateQueries({ queryKey: unitKey(unitId) })
      }
    },
  })
}

/** Takes linked to a unit change its counters and steps: its page reads it again. */
export function useInvalidateUnits() {
  const queryClient = useQueryClient()
  return useCallback(
    () => void queryClient.invalidateQueries({ queryKey: [...curriculumKey, 'unit'] }),
    [queryClient],
  )
}
