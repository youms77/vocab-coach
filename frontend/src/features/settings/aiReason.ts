import type { TFunction } from 'i18next'

// The gateway's `UnavailableReason` values (backend/app/ai/types.py); D-095 words them for any task.
// `incomplete` is the transcription's: the provider answered without a usable text (D-171).
const REASONS = [
  'no_provider_configured',
  'network',
  'quota',
  'auth',
  'timeout',
  'all_failed',
  'incomplete',
] as const
type Reason = (typeof REASONS)[number]

const isReason = (value: string | null): value is Reason =>
  (REASONS as readonly (string | null)[]).includes(value)

/** The translated reason an AI call failed; an unknown or missing one reads as "the providers failed". */
export function aiReasonText(t: TFunction, reason: string | null): string {
  return t(`aiReasons.${isReason(reason) ? reason : 'all_failed'}`)
}
