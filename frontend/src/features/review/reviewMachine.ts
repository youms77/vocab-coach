import type { GradeResult, Rating, RevealResult } from '../../api/reviews'

/*
 * The life of one review card (D-120). Pure: the player keeps the state in a ref as well, so an
 * action that the current phase does not allow (a second key press before React re-renders) is
 * refused synchronously and sends nothing.
 *
 *   answering --submit--> checking --checked--> answered --rate--> recording --recorded--> recorded
 *       ^                     |                    ^                   |
 *       +----checkFailed------+                    +----recordFailed---+
 */

export type Phase = 'answering' | 'checking' | 'answered' | 'recording' | 'recorded'

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
}

export type ReviewAction =
  | { type: 'type'; answer: string }
  | { type: 'submit'; choiceIndex: number | null; responseTimeMs: number }
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
    case 'checked':
      if (state.phase !== 'checking') return state
      return { ...state, phase: 'answered', result: action.result }
    case 'checkFailed':
      if (state.phase !== 'checking') return state
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
