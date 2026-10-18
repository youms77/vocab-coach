import type { ErrorOut } from '../../api/errors'
import type { Feedback } from '../../api/productions'
import type {
  CheckProductionResult,
  GradeResult,
  Rating,
  RevealResult,
} from '../../api/reviews'

/*
 * The life of one review card (D-120, D-140). Pure: the player keeps the state in a ref as well, so
 * an action that the current phase does not allow (a second key press before React re-renders, or
 * an AI answer that arrives after "Skip the check") is refused synchronously and changes nothing.
 *
 *   answering --submit--> checking --checked--> answered --rate--> recording --recorded--> recorded
 *       ^                       |                      ^                   |
 *       +------checkFailed------+                      +---recordFailed----+
 *
 *   answering --submitProduction--> checking_production --productionChecked--> answered
 *                                          |        +--productionUnchecked--> checking
 *                                          +--checkFailed--> answering
 *
 * `checking_production` is a typed sentence being checked by the AI (D-129). It ends with the
 * AI's answer (`productionChecked`), or falls back to the self-graded path of M4.c
 * (`productionUnchecked`: unavailable, incomplete, network error, or "Skip the check").
 */

export type Phase =
  | 'answering'
  | 'checking_production'
  | 'checking'
  | 'answered'
  | 'recording'
  | 'recorded'

/** Why the AI check was not used; the player says so above the self-graded result. */
export type CheckNotice =
  | { kind: 'unavailable'; reason: string | null }
  | { kind: 'incomplete' }
  | { kind: 'skipped' }
  | { kind: 'failed'; error: unknown }

/** What the AI said about the sentence, kept for the correction shown with the result. */
export interface ProductionCheck {
  feedback: Feedback | null
  errors: ErrorOut[]
}

export interface ReviewState {
  phase: Phase
  /** The typed answer, kept when grading fails. */
  answer: string
  /** The option chosen (choice types), null for "I don't know" or a typed answer. */
  choiceIndex: number | null
  /** From the prompt being shown to the answer (or "Show"), never including the rating. */
  responseTimeMs: number | null
  result: GradeResult | null
  rating: Rating | null
  error: unknown
  /** The checked sentence, when the AI check was used (status ok). */
  check: ProductionCheck | null
  /** Sent with `POST /reviews` so the server rates from the stored correction (D-129). */
  productionAttemptId: number | null
  notice: CheckNotice | null
}

export type ReviewAction =
  | { type: 'type'; answer: string }
  | { type: 'submit'; choiceIndex: number | null; responseTimeMs: number }
  | { type: 'submitProduction'; responseTimeMs: number }
  | { type: 'productionChecked'; check: CheckProductionResult }
  | { type: 'productionUnchecked'; notice: CheckNotice }
  | { type: 'productionDropped' }
  | { type: 'checked'; result: GradeResult }
  | { type: 'checkFailed'; error: unknown }
  | { type: 'rate'; rating: Rating }
  | { type: 'recorded' }
  | { type: 'recordFailed'; error: unknown }

export const initialReviewState: ReviewState = {
  phase: 'answering',
  answer: '',
  choiceIndex: null,
  responseTimeMs: null,
  result: null,
  rating: null,
  error: null,
  check: null,
  productionAttemptId: null,
  notice: null,
}

/** True when the stored correction says the target term is not in the sentence. */
function termMissing(feedback: Feedback | null): boolean {
  return (feedback?.targets ?? []).some((target) => !target.used)
}

/** The AI check in the shape of a grade answer, so the result and the rating buttons are the same. */
export function checkedResult(check: CheckProductionResult): GradeResult {
  return {
    outcome: null,
    proposed_rating: check.proposed_rating,
    expected: null,
    accepted: [],
    diff: null,
    warnings: termMissing(check.feedback) ? ['term_missing'] : [],
    solution: check.solution,
    sheet_summary: check.sheet_summary,
  }
}

/** A reveal answer in the shape of a grade answer: no outcome, no proposed rating. */
export function revealedResult(revealed: RevealResult): GradeResult {
  return {
    outcome: null,
    proposed_rating: null,
    expected: null,
    accepted: [],
    diff: null,
    warnings: [],
    solution: revealed.solution,
    sheet_summary: revealed.sheet_summary,
  }
}

/** The next state, or the same object when the phase does not allow the action. */
export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case 'type':
      return state.phase === 'answering' ? { ...state, answer: action.answer } : state
    case 'submit':
      if (state.phase !== 'answering') return state
      return {
        ...state,
        phase: 'checking',
        choiceIndex: action.choiceIndex,
        responseTimeMs: action.responseTimeMs,
        error: null,
      }
    case 'submitProduction':
      if (state.phase !== 'answering') return state
      return {
        ...state,
        phase: 'checking_production',
        choiceIndex: null,
        responseTimeMs: action.responseTimeMs,
        error: null,
        notice: null,
      }
    case 'productionChecked':
      if (state.phase !== 'checking_production') return state
      return {
        ...state,
        phase: 'answered',
        result: checkedResult(action.check),
        check: { feedback: action.check.feedback, errors: action.check.errors },
        productionAttemptId: action.check.production_attempt_id,
      }
    case 'productionUnchecked':
      if (state.phase !== 'checking_production') return state
      return { ...state, phase: 'checking', notice: action.notice }
    case 'productionDropped':
      return state.phase === 'recording' && state.productionAttemptId !== null
        ? { ...state, productionAttemptId: null }
        : state
    case 'checked':
      if (state.phase !== 'checking') return state
      return { ...state, phase: 'answered', result: action.result }
    case 'checkFailed':
      if (state.phase !== 'checking' && state.phase !== 'checking_production') return state
      return { ...state, phase: 'answering', choiceIndex: null, responseTimeMs: null, error: action.error }
    case 'rate':
      if (state.phase !== 'answered') return state
      return { ...state, phase: 'recording', rating: action.rating, error: null }
    case 'recorded':
      return state.phase === 'recording' ? { ...state, phase: 'recorded' } : state
    case 'recordFailed':
      if (state.phase !== 'recording') return state
      return { ...state, phase: 'answered', rating: null, error: action.error }
  }
}
