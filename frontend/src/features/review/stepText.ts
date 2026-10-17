import type { GradeResult } from '../../api/reviews'
import type { ReviewStep } from '../../api/session'

/** A non-empty string from a prompt or solution field, else null. */
export function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

/** The options of a choice prompt, in the server's order (D-103). */
export function promptOptions(review: ReviewStep): string[] {
  const value = review.prompt.options
  return Array.isArray(value) ? value.filter((o): o is string => typeof o === 'string') : []
}

/**
 * What R replays (D-123): before the answer, the sentence of a receptive card (or the term of a
 * receptive self-assessment without sentence), never anything for a productive card, whose term
 * is the answer; after the answer, the solution's sentence, else the term.
 */
export function replayText(review: ReviewStep, result: GradeResult | null): string | null {
  if (result !== null) {
    return (
      text(result.solution.sentence) ??
      text(result.solution.term) ??
      text(result.expected) ??
      text(result.sheet_summary?.term)
    )
  }
  if (review.direction === 'productive') return null
  if (review.exercise_type === 'self_assessment') return text(review.prompt.sentence) ?? review.term
  return text(review.prompt.sentence)
}

/** The term, once the answer is shown (for the "now consolidated" announcement). */
export function termOf(review: ReviewStep, result: GradeResult | null): string | null {
  return (
    text(result?.sheet_summary?.term) ??
    text(result?.solution.term) ??
    review.term ??
    (['typed_recall', 'gap_fill'].includes(review.exercise_type) ? text(result?.expected) : null)
  )
}
