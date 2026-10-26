import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiGet, apiSend, apiUpload } from './client'
import { curriculumKey } from './curriculum'
import type { ErrorOut } from './errors'
import { type Feedback, productionsKey } from './productions'
import type { SheetSummary, Solution } from './reviews'

// backend/app/api/speech.py and app/services/speech.py (module F, D-170 to D-175, D-183).

export type StepOp = 'match' | 'close' | 'substituted' | 'missing' | 'extra'

/** Words `[target_start, target_end)` of the target were heard as `[heard_start, heard_end)`. */
export interface ComparisonStep {
  op: StepOp
  target_start: number
  target_end: number
  heard_start: number
  heard_end: number
  target: string | null
  heard: string | null
}

export interface UnrecognizedWord {
  position: number
  word: string
  /** What was heard instead; null when nothing was. */
  heard: string | null
}

export interface Comparison {
  version: string
  word_accuracy: number
  target_word_count: number
  heard_word_count: number
  recognized_count: number
  unrecognized: UnrecognizedWord[]
  steps: ComparisonStep[]
}

export type TranscriptionStatus = 'ok' | 'silence' | 'unavailable'

export interface Transcription {
  status: TranscriptionStatus
  text: string | null
  /** `unavailable`: `no_provider_configured`, `quota`, `network`, `auth`, `timeout`, `all_failed`, `incomplete`. */
  reason: string | null
}

export type ErrorType = 'None' | 'Mispronunciation' | 'Omission' | 'Insertion' | string

export interface PhonemeScore {
  phoneme: string
  accuracy: number | null
}

export interface WordScore {
  word: string
  accuracy: number | null
  error_type: ErrorType
  offset_ms: number | null
  duration_ms: number | null
  phonemes: PhonemeScore[]
}

/** The stored `azure-pa-1` document (D-215). Scores are 0-100, null on silence. */
export interface PronunciationScores {
  provider: string
  model: string
  assessed_at: string
  status: 'ok' | 'silence'
  overall: {
    accuracy: number | null
    fluency: number | null
    completeness: number | null
    pronunciation: number | null
  }
  words: WordScore[]
  duration_s: number | null
}

export type AssessableReason =
  | 'not_shadowing'
  | 'no_target'
  | 'no_audio'
  | 'disabled'
  | 'not_configured'
  | 'already_assessed'
  | 'unsupported_format'
  | 'too_long'

export interface SpeechOut {
  production_id: number
  audio_url: string
  audio_seconds: number | null
  transcription: Transcription
  comparison: Comparison | null
  pronunciation?: PronunciationScores | null
  assessable?: boolean
  assessable_reason?: AssessableReason | null
}

export interface ReviewAnswerOut {
  production_attempt_id: number
  transcription: Transcription
  status: 'ok' | 'incomplete' | 'unavailable'
  reason: string | null
  feedback: Feedback | null
  errors: ErrorOut[]
  proposed_rating: 1 | 3 | null
  warnings: string[]
  solution: Solution
  sheet_summary: SheetSummary | null
}

export interface ReviewAnswerBody {
  blob: Blob
  card_id: number
  session_id: number
  exercise_template_id: number
  durationS: number
  response_time_ms: number
}

/**
 * Stores, transcribes and corrects a spoken answer of a review (D-183): two AI calls, up to about
 * 90 s. A plain function, not a mutation, so that `signal` lets the page stop waiting (the
 * recording stays stored). Every refusal comes before any write.
 */
export function reviewAnswer(body: ReviewAnswerBody, signal?: AbortSignal) {
  return apiUpload<ReviewAnswerOut>(
    '/speech/review-answer',
    body.blob,
    {
      card_id: body.card_id,
      session_id: body.session_id,
      exercise_template_id: body.exercise_template_id,
      duration_s: body.durationS,
      response_time_ms: body.response_time_ms,
    },
    { signal },
  )
}

export const SPEAKING_TAGS = [
  'interview',
  'presenting',
  'academic',
  'data_science',
  'everyday',
  'campus',
] as const
export type SpeakingTag = (typeof SPEAKING_TAGS)[number]

export interface SpeakingTopic {
  id: string
  en: string
  fr: string
  tags: SpeakingTag[]
}

export interface ShadowingBody {
  blob: Blob
  durationS: number
  target: string
  itemId?: number
  origin?: 'shadowing' | 'discovery'
  studySessionId?: number
  /** A line of a scenario unit (module H): the take counts for its shadowing step. */
  unitId?: number
}

/** Stores and transcribes a shadowing: a few seconds. A failed transcription is a 201 answer. */
export function useShadowing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ShadowingBody) =>
      apiUpload<SpeechOut>('/speech/shadowing', body.blob, {
        target_text: body.target,
        duration_s: body.durationS,
        item_id: body.itemId,
        origin: body.origin ?? 'shadowing',
        study_session_id: body.studySessionId,
        unit_id: body.unitId,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
      void queryClient.invalidateQueries({ queryKey: curriculumKey })
    },
  })
}

export interface SpeakingBody {
  blob: Blob
  durationS: number
  promptText?: string
  /** The final task of a scenario unit: the server takes its prompt (no `promptText`). */
  unitId?: number
}

/** Stores and transcribes a free speech (M6.b2 screens); the correction is a separate call. */
export function useSpeaking() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SpeakingBody) =>
      apiUpload<SpeechOut>('/speech/speaking', body.blob, {
        duration_s: body.durationS,
        prompt_text: body.promptText,
        unit_id: body.unitId,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
      void queryClient.invalidateQueries({ queryKey: curriculumKey })
    },
  })
}

/** Runs the transcription again for a recording that has none (`pending`). */
export function useTranscribe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiSend<SpeechOut>('POST', `/productions/${id}/transcribe`),
    onSuccess: (result) => {
      if (result.transcription.status === 'unavailable') return
      void queryClient.invalidateQueries({
        queryKey: [...productionsKey, 'detail', result.production_id],
      })
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
      // A transcribed take counts for a scenario unit's shadowing step.
      void queryClient.invalidateQueries({ queryKey: curriculumKey })
    },
    onError: (error, id) => {
      // Transcribed meanwhile (another tab): show what is stored.
      if (error instanceof ApiError && error.code === 'already_transcribed') {
        void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'detail', id] })
      }
    },
  })
}

export function useSpeakingTopics(tag: SpeakingTag | '') {
  return useQuery({
    queryKey: ['speaking-topics', tag],
    queryFn: ({ signal }) =>
      apiGet<SpeakingTopic[]>(`/speaking/topics?count=3${tag !== '' ? `&tag=${tag}` : ''}`, {
        signal,
      }),
    staleTime: 5 * 60_000,
  })
}
