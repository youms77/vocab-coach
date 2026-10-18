import type { ErrorOut } from '../../api/errors'
import { findFragment } from './fragment'

/**
 * Where a logged error's text can be reopened. `ErrorOut` has no production kind: a `writing` or
 * `review` error comes from a written production (`/writing/{id}`); a transcript, a drill, a
 * speaking or a consolidation error has no page yet.
 */
export function productionLink(error: ErrorOut): string | null {
  if (error.production_attempt_id === null) return null
  return error.source === 'writing' || error.source === 'review'
    ? `/writing/${error.production_attempt_id}`
    : null
}

export type EntryProblem = 'wrongNotInOriginal' | 'sameAsCorrection'

/** The client-side checks of a manual entry; the server stays the judge (`invalid_error`). */
export function problemOf(original: string, wrong: string, correction: string): EntryProblem | null {
  const wrongForm = wrong.trim()
  if (wrongForm !== '' && wrongForm === correction.trim()) return 'sameAsCorrection'
  if (original.trim() !== '' && wrongForm !== '' && findFragment(original, wrongForm) === null) {
    return 'wrongNotInOriginal'
  }
  return null
}
