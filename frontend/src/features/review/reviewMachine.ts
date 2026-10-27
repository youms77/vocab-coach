import type { ErrorOut } from '../../api/errors'
import type { Feedback } from '../../api/productions'
import type {
  CheckProductionResult,
  GradeResult,
  Rating,
  RevealResult,
} from '../../api/reviews'
import type { ReviewAnswerOut, Transcription } from '../../api/speech'

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
 *
 * A spoken answer (D-206) has its own three phases before `answered`:
 *
 *   answering --startCapture--> capturing --captured--> captured --submitSpoken--> checking_spoken
 *       ^                           |                      |  ^                          |
 *       +------discardCapture-------+----------------------+  +------spokenFailed--------+
 *   checking_spoken --spokenChecked--> answered
 *
 * and `spokenFallback` (any of the four phases of a spoken card) goes to `checking`, the reveal
 * of M4.c: the answer was not recorded, or the wait was given up ("Answer without recording",
 * a refused microphone, "Skip the check", a network failure).
 */

export type Phase =
  | 'answering'
  | 'capturing'
  | 'captured'
  | 'checking_spoken'
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
  /** A spoken answer: the user stopped waiting for the check. */
  | { kind: 'spoken_skipped' }
  /** A spoken answer: the check failed (network, unexpected error). */
  | { kind: 'spoken_failed'; error: unknown }

/** What the AI said about the sentence, kept for the correction shown with the result. */
export interface ProductionCheck {
  feedback: Feedback | null
  errors: ErrorOut[]
}

/** What the recogniser and the AI said about a spoken answer, kept for the result. */
export interface SpokenCheck {
  transcription: Transcription
  /** The correction's status; `ok` means `feedback` is the correction of what was heard. */
  status: ReviewAnswerOut['status']
  reason: string | null
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
  /** The spoken answer as heard and checked, once `review-answer` has answered. */
  spoken: SpokenCheck | null
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
  | { type: 'startCapture' }
  | { type: 'captured'; responseTimeMs: number }
  | { type: 'discardCapture' }
  | { type: 'submitSpoken' }
  | { type: 'spokenChecked'; answer: ReviewAnswerOut }
  | { type: 'spokenFailed'; error: unknown }
  | { type: 'spokenFallback'; notice: CheckNotice | null; responseTimeMs: number }
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
  spoken: null,
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

/**
 * A spoken answer in the shape of a grade answer. The rating is proposed only with a correction
 * (`ok`); `term_not_heard` stays a warning (the recogniser may have missed the word).
 */
export function spokenResult(answer: ReviewAnswerOut): GradeResult {
  return {
    outcome: null,
    proposed_rating: answer.status === 'ok' ? answer.proposed_rating : null,
    expected: null,
    accepted: [],
    diff: null,
    warnings: answer.warnings,
    solution: answer.solution,
    sheet_summary: answer.sheet_summary,
  }
}

/** True in the phases where a spoken answer has been started and not yet rated. */
export function spokenInProgress(phase: Phase): boolean {
  return phase === 'capturing' || phase === 'captured' || phase === 'checking_spoken'
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
    case 'startCapture':
      return state.phase === 'answering' ? { ...state, phase: 'capturing', error: null } : state
    case 'captured':
      if (state.phase !== 'capturing') return state
      return { ...state, phase: 'captured', responseTimeMs: action.responseTimeMs }
    case 'discardCapture':
      if (state.phase !== 'capturing' && state.phase !== 'captured') return state
      return { ...state, phase: 'answering', responseTimeMs: null, error: null }
    case 'submitSpoken':
      if (state.phase !== 'captured') return state
      return { ...state, phase: 'checking_spoken', error: null, notice: null }
    case 'spokenChecked':
      if (state.phase !== 'checking_spoken') return state
      return {
        ...state,
        phase: 'answered',
        result: spokenResult(action.answer),
        spoken: {
          transcription: action.answer.transcription,
          status: action.answer.status,
          reason: action.answer.reason,
          feedback: action.answer.feedback,
          errors: action.answer.errors,
        },
        productionAttemptId: action.answer.production_attempt_id,
      }
    case 'spokenFailed':
      if (state.phase !== 'checking_spoken') return state
      return { ...state, phase: 'captured', error: action.error }
    case 'spokenFallback':
      if (state.phase !== 'answering' && !spokenInProgress(state.phase)) return state
      return {
        ...state,
        phase: 'checking',
        choiceIndex: null,
        // The time of the answer is the end of the recording, when there was one.
        responseTimeMs: state.responseTimeMs ?? action.responseTimeMs,
        error: null,
        notice: action.notice,
      }
    case 'checked':
      if (state.phase !== 'checking') return state
      return { ...state, phase: 'answered', result: action.result }
    case 'checkFailed':
      if (
        state.phase !== 'checking' &&
        state.phase !== 'checking_production' &&
        state.phase !== 'checking_spoken'
      ) {
        return state
      }
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
