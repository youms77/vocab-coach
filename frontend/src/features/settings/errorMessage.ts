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
    return { text: t(`errors.${key}`), detail: withDetail ? error.message : null, reasons }
  }
  if (error.status === 502 || error.status === 504) {
    // Vite's proxy answers this way when the backend is down.
    return { text: t('errors.network'), detail: null, reasons: [] }
  }
  return { text: t('errors.unexpected', { status: error.status }), detail: null, reasons: [] }
}
