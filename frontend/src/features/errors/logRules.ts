import type { ErrorOut } from '../../api/errors'
import { findFragment } from './fragment'

/**
 * Where a logged error's text can be reopened. `ErrorOut` has no production kind, so the source
 * tells: a `writing` or `review` error comes from a written production (`/writing/{id}`; a
 * review error may come from a spoken answer, and that page redirects to `/speaking/{id}`), a
 * `speaking` error from a free speech (`/speaking/{id}`, M6.b2), a `transcript` error from an
 * analysed conversation (`/transcripts/{id}`, M5.c1), a `drill` error from its drill
 * (`/drills/{id}`, M5.c2: the service gives the error the drill's own id as
 * `production_attempt_id`); a `consolidation` error from the page of its attempt (`/consolidation/attempts/{id}`, M7.b).
 */
export function productionLink(error: ErrorOut): string | null {
  if (error.production_attempt_id === null) return null
  if (error.source === 'writing' || error.source === 'review') {
    return `/writing/${error.production_attempt_id}`
  }
  if (error.source === 'speaking') return `/speaking/${error.production_attempt_id}`
  if (error.source === 'transcript') return `/transcripts/${error.production_attempt_id}`
  if (error.source === 'consolidation') return `/consolidation/attempts/${error.production_attempt_id}`
  return error.source === 'drill' ? `/drills/${error.production_attempt_id}` : null
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
