import type { AnswerBody, ItemResult } from '../../api/drills'

/*
 * The life of one drill item (D-120 applied to drills). Pure: the player keeps the state in a ref as
 * well, so an action that the current phase does not allow (a second Enter before React
 * re-renders) is refused synchronously and changes nothing.
 *
 *   answering --submit--> sending --answered--> answered
 *       ^                    |
 *       +------failed--------+
 *
 * The solution only exists in `answered`, and only comes from the server's answer (D-103, D-136).
 */

export type Phase = 'answering' | 'sending' | 'answered'

/** What the user did: typed an answer (maybe empty), or chose an option (null: "I don't know"). */
export type Attempt = { kind: 'text'; answer: string } | { kind: 'choice'; index: number | null }

export interface DrillItemState {
  phase: Phase
  /** The typed answer, kept when sending fails. */
  answer: string
  attempt: Attempt | null
  /** From the item being shown to the answer, never including the time spent reading the result. */
  responseTimeMs: number | null
  result: ItemResult | null
  errorEventId: number | null
  error: unknown
}

export type DrillItemAction =
  | { type: 'type'; answer: string }
  | { type: 'submit'; attempt: Attempt; responseTimeMs: number }
  | { type: 'answered'; result: ItemResult; errorEventId: number | null }
  | { type: 'failed'; error: unknown }

export const initialItemState: DrillItemState = {
  phase: 'answering',
  answer: '',
  attempt: null,
  responseTimeMs: null,
  result: null,
  errorEventId: null,
  error: null,
}

/** The next state, or the same object when the phase does not allow the action. */
export function drillItemReducer(state: DrillItemState, action: DrillItemAction): DrillItemState {
  switch (action.type) {
    case 'type':
      return state.phase === 'answering' ? { ...state, answer: action.answer } : state
    case 'submit':
      if (state.phase !== 'answering') return state
      return {
        ...state,
        phase: 'sending',
        attempt: action.attempt,
        responseTimeMs: action.responseTimeMs,
        error: null,
      }
    case 'answered':
      if (state.phase !== 'sending') return state
      return { ...state, phase: 'answered', result: action.result, errorEventId: action.errorEventId }
    case 'failed':
      if (state.phase !== 'sending') return state
      return { ...state, phase: 'answering', attempt: null, responseTimeMs: null, error: action.error }
  }
}

/**
 * The request body of an attempt. A gap-fill sends `answer` (empty for "I don't know"), a choice
 * sends `choice_index` (null for "I don't know"); the server refuses the other field.
 */
export function answerBody(attempt: Attempt, responseTimeMs: number): AnswerBody {
  return attempt.kind === 'text'
    ? { answer: attempt.answer, response_time_ms: responseTimeMs }
    : { choice_index: attempt.index, response_time_ms: responseTimeMs }
}
