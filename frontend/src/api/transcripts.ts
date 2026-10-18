import { useMutation, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiSend } from './client'
import {
  applyCorrection,
  applyCorrectionError,
  type CorrectionResult,
  type Production,
  productionsKey,
} from './productions'

// backend/app/api/transcripts.py, api/productions.py and app/domain/transcript_import.py (D-133,
// D-134). Errors use the D-063 format (see features/settings/errorMessage.ts).

export const MAX_PASTED_CHARS = 60_000
export const MAX_USER_CHARS = 6_000
export const MAX_TITLE_CHARS = 200
export const CONTEXT_CHARS = 300

export type UserMode = 'alternating_user_first' | 'alternating_user_second' | 'all_mine'
export const USER_MODES: readonly UserMode[] = [
  'alternating_user_first',
  'alternating_user_second',
  'all_mine',
]

/** Who the user is: a speaker label, or a mode when the text has no labels. */
export type UserDesignation = { label: string } | { mode: UserMode }

export type Severity = 'info' | 'warning' | 'error'

/** The parser's stable problem codes (D-133); each has an i18n key. */
export const PROBLEM_CODES = [
  'empty_text',
  'too_large',
  'no_speaker_labels',
  'single_speaker',
  'unlabelled_text',
  'empty_turn',
  'unknown_label',
  'no_user_turns',
] as const
export type ProblemCode = (typeof PROBLEM_CODES)[number]

export interface TranscriptProblem {
  line: number | null
  severity: Severity
  code: ProblemCode | string
  message: string
}

export interface PreviewTurn {
  /** From 1, in the order of the transcript. */
  index: number
  speaker_label: string | null
  text: string
  line_start: number
  /** Null when no designation could be applied. */
  is_user: boolean | null
}

export interface LabelCount {
  label: string
  turns: number
  words: number
  chars: number
  known: 'user' | 'other' | null
}

export interface TranscriptPreview {
  turns: PreviewTurn[]
  labels: LabelCount[]
  labelled: boolean
  suggested_user_label: string | null
  designation: UserDesignation | null
  user: { turns: number; words: number; chars: number } | null
  problems: TranscriptProblem[]
}

/** The pasted text again, to give the AI the other speaker's turns as context (never stored). */
export interface TranscriptBody {
  text: string
  user: UserDesignation
}

export interface CreateTranscriptBody extends TranscriptBody {
  title: string | null
  occurred_on: string | null
  study_session_id: number | null
}

/** The length the backend counts: Unicode code points. */
export function codePoints(text: string): number {
  return Array.from(text).length
}

/** Writes nothing: parses the paste and shows the turns, the labels and the problems. */
export function usePreviewTranscript() {
  return useMutation({
    mutationFn: (body: { text: string; user?: UserDesignation }) =>
      apiSend<TranscriptPreview>('POST', '/transcripts/preview', body),
  })
}

/** Stores the user's turns only (no analysis yet). */
export function useCreateTranscript() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateTranscriptBody) => apiSend<Production>('POST', '/transcripts', body),
    onSuccess: (created) => {
      queryClient.setQueryData([...productionsKey, 'detail', created.id], created)
      void queryClient.invalidateQueries({ queryKey: [...productionsKey, 'list'] })
    },
  })
}

/**
 * Analyses a recorded transcript. A long one makes several AI calls (up to a few minutes). With
 * `transcript` the AI also reads the other speaker's turn before each of yours; without it, the
 * units are checked without context. `onDone` runs in the hook (not in `mutate`), so it also
 * runs when the page has been left: the caller forgets the pasted text there.
 */
export function useAnalyseTranscript(onDone?: (id: number) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, transcript }: { id: number; transcript?: TranscriptBody }) =>
      apiSend<CorrectionResult>(
        'POST',
        `/productions/${id}/correct`,
        transcript !== undefined ? { transcript } : undefined,
      ),
    onError: (error, { id }) => {
      applyCorrectionError(queryClient, error, id)
      if (error instanceof ApiError && error.code === 'already_corrected') onDone?.(id)
    },
    onSuccess: (result, { id }) => {
      applyCorrection(queryClient, result)
      if (result.status === 'ok') onDone?.(id)
    },
  })
}
