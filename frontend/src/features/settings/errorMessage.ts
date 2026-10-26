import type { TFunction } from 'i18next'

import { ApiError } from '../../api/client'

// Every `detail.code` the backend can answer (D-063); anything else gets the generic message.
const KNOWN_CODES = [
  'forbidden_host',
  'forbidden_origin',
  'cross_site_request',
  'unsupported_media_type',
  'invalid_request',
  'invalid_credential',
  'invalid_setting',
  'unknown_provider',
  'set_in_environment',
  'env_file_locked',
  'test_in_progress',
  'demo_read_only',
  'env_file_write_failed',
  'database_unavailable',
  'item_not_found',
  'deck_not_found',
  'source_not_found',
  'duplicate_term',
  'already_in_deck',
  'item_has_history',
  'deck_has_history',
  'merge_conflict',
  'not_in_triage',
  'invalid_transition',
  'invalid_term',
  'row_rejected',
  'deck_name_required',
  'invalid_attach_target',
  'merge_same_item',
  'duplicate_decision',
  'enrichment_running',
  'sheet_edited',
  'sheet_changed',
  'sheet_not_found',
  'exercise_not_found',
  'item_archived',
  'invalid_exercise',
  'not_enough_context',
  'session_not_found',
  'session_closed',
  'card_not_found',
  'card_changed',
  'review_not_allowed',
  'not_due',
  'sheet_required',
  'already_discovered',
  'discovery_not_allowed',
  'exercise_mismatch',
  'invalid_queue',
  'already_corrected',
  'production_mismatch',
  'production_not_found',
  'text_too_long',
  'invalid_production',
  'not_correctable',
  'error_not_found',
  'category_not_found',
  'category_not_proposed',
  'unknown_category',
  'invalid_error',
  'category_exists',
  'transcript_mismatch',
  'invalid_transcript',
  'drill_not_found',
  'already_answered',
  'not_drillable',
  'audio_too_large',
  'unsupported_audio',
  'audio_empty',
  'audio_too_short',
  'audio_too_long',
  'invalid_target',
  'no_audio',
  'already_transcribed',
  'not_transcribed',
  'nothing_to_correct',
  'region_required',
  'invalid_region',
  'not_assessable',
  'assessment_disabled',
  'already_assessed',
  'unsupported_for_assessment',
  'wordlist_missing',
  'track_not_started',
  'not_a_wordlist_track',
  'not_a_scenario_track',
  'not_a_scenario_unit',
  'track_not_found',
  'unit_not_found',
  'syllabus_unavailable',
  'unit_generated',
  'unit_changed',
  'invalid_content',
  'invalid_step',
] as const

// These say *why* a value was refused (never the value itself): the English detail is kept.
const DETAILED_CODES: readonly string[] = [
  'invalid_credential',
  'invalid_setting',
  'invalid_production',
  'invalid_error',
]

type KnownCode = (typeof KNOWN_CODES)[number]

function isKnownCode(code: string | null): code is KnownCode {
  return (KNOWN_CODES as readonly (string | null)[]).includes(code)
}

// The transcript refusals carry `codes` (the parser's problem codes, `future_date`...): they are
// said in the interface language, one per line, under the sentence (D-151).
const TRANSCRIPT_CODES = ['invalid_transcript', 'text_too_long'] as const

function codesOf(error: ApiError): string[] {
  const codes = error.detail.codes
  return Array.isArray(codes) ? codes.filter((code): code is string => typeof code === 'string') : []
}

// The recording refusals carry their bounds (`min_s`, `max_s`, `max_bytes`) for the sentence.
function audioParams(error: ApiError): Record<string, string> {
  const number = (value: unknown) => (typeof value === 'number' ? String(value) : '?')
  const bytes = error.detail.max_bytes
  return {
    min: number(error.detail.min_s),
    max: number(error.detail.max_s),
    mb: typeof bytes === 'number' ? String(Math.round(bytes / 1024 / 1024)) : '10',
  }
}

export interface DescribedError {
  text: string
  /** The backend's English text, when it says why a value was refused. */
  detail: string | null
  /** Translated reasons (transcripts only). */
  reasons: string[]
}

/** The translated sentence for a failed request, plus the backend's English text when useful. */
export function describeError(t: TFunction, error: unknown): DescribedError {
  if (!(error instanceof ApiError)) {
    // fetch() itself failed: the backend (or the Vite proxy's target) is not running.
    return { text: t('errors.network'), detail: null, reasons: [] }
  }
  if (isKnownCode(error.code)) {
    const withDetail = DETAILED_CODES.includes(error.code)
    const codes = (TRANSCRIPT_CODES as readonly string[]).includes(error.code) ? codesOf(error) : []
    // `text_too_long` of a transcript is about 60 000 / 6 000 characters, not 4 000 and 40 sentences.
    const key = error.code === 'text_too_long' && codes.length > 0 ? 'text_too_long_transcript' : error.code
    const reasons = codes.map((code) =>
      t(`transcripts.reasons.${code}`, { defaultValue: t(`transcripts.problems.${code}`, { defaultValue: code }) }),
    )
    // A category that cannot be drilled says why (`level`, `pronunciation`, `proposed`...); an
    // unknown reason keeps the backend's English sentence.
    if (error.code === 'not_drillable') {
      const reason = error.detail.reason
      reasons.push(
        typeof reason === 'string'
          ? t(`drills.reasons.${reason}`, { defaultValue: error.message })
          : error.message,
      )
    }
    // The content of a unit was refused: each problem names a location, never the text (D-246).
    if (error.code === 'invalid_content') {
      const problems = error.detail.problems
      if (Array.isArray(problems)) {
        reasons.push(...problems.filter((p): p is string => typeof p === 'string'))
      }
    }
    return {
      text: (t as unknown as (key: string, options: Record<string, string>) => string)(
        `errors.${key}`,
        audioParams(error),
      ),
      detail: withDetail ? error.message : null,
      reasons,
    }
  }
  if (error.status === 502 || error.status === 504) {
    // Vite's proxy answers this way when the backend is down.
    return { text: t('errors.network'), detail: null, reasons: [] }
  }
  return { text: t('errors.unexpected', { status: error.status }), detail: null, reasons: [] }
}
