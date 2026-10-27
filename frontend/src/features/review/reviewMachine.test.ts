import { describe, expect, it } from 'vitest'

import { reviewAnswerOut, untranscribedAnswer } from '../../test/speechFixtures'
import { checkAnswer, checkedFeedback, CHECKED_SENTENCE } from '../../test/writingFixtures'
import {
  initialReviewState,
  type ReviewAction,
  reviewReducer,
  revealedResult,
  type ReviewState,
} from './reviewMachine'

const run = (actions: ReviewAction[], from: ReviewState = initialReviewState) =>
  actions.reduce(reviewReducer, from)

const waiting = run([
  { type: 'type', answer: CHECKED_SENTENCE },
  { type: 'submitProduction', responseTimeMs: 4200 },
])

describe('reviewMachine: the AI check of a sentence', () => {
  it('goes answering → checking_production, keeping the answer and the response time', () => {
    expect(waiting.phase).toBe('checking_production')
    expect(waiting.answer).toBe(CHECKED_SENTENCE)
    expect(waiting.responseTimeMs).toBe(4200)
  })

  it('the AI answer gives the result, the correction and the production to send with the rating', () => {
    const state = reviewReducer(waiting, { type: 'productionChecked', check: checkAnswer() })
    expect(state.phase).toBe('answered')
    expect(state.productionAttemptId).toBe(77)
    expect(state.result?.proposed_rating).toBe(1)
    expect(state.result?.solution.example_answer).toBeDefined()
    expect(state.check?.feedback).toEqual(checkedFeedback())
    expect(state.notice).toBeNull()
  })

  it('derives term_missing from the stored correction', () => {
    const missing = checkAnswer({ feedback: checkedFeedback(CHECKED_SENTENCE, false) })
    expect(reviewReducer(waiting, { type: 'productionChecked', check: missing }).result?.warnings).toEqual([
      'term_missing',
    ])
    expect(
      reviewReducer(waiting, { type: 'productionChecked', check: checkAnswer() }).result?.warnings,
    ).toEqual([])
  })

  it('falls back to the self-graded path without any production to send', () => {
    const state = reviewReducer(waiting, { type: 'productionUnchecked', notice: { kind: 'skipped' } })
    expect(state.phase).toBe('checking')
    expect(state.productionAttemptId).toBeNull()
    expect(state.notice).toEqual({ kind: 'skipped' })
    const answered = reviewReducer(state, {
      type: 'checked',
      result: { ...checkAnswer(), outcome: null, expected: null, accepted: [], diff: null, warnings: [] },
    })
    expect(answered.phase).toBe('answered')
    expect(answered.productionAttemptId).toBeNull()
    expect(answered.check).toBeNull()
  })

  it('refuses a late AI answer once the user skipped the check (same state object)', () => {
    const skipped = reviewReducer(waiting, { type: 'productionUnchecked', notice: { kind: 'skipped' } })
    expect(reviewReducer(skipped, { type: 'productionChecked', check: checkAnswer() })).toBe(skipped)
    const answered = run([{ type: 'checked', result: checkAnswer() as never }], skipped)
    expect(reviewReducer(answered, { type: 'productionChecked', check: checkAnswer() })).toBe(answered)
    expect(reviewReducer(answered, { type: 'productionUnchecked', notice: { kind: 'incomplete' } })).toBe(
      answered,
    )
  })

  it('refuses a second submission while waiting, and the rating', () => {
    expect(reviewReducer(waiting, { type: 'submitProduction', responseTimeMs: 1 })).toBe(waiting)
    expect(reviewReducer(waiting, { type: 'submit', choiceIndex: null, responseTimeMs: 1 })).toBe(waiting)
    expect(reviewReducer(waiting, { type: 'rate', rating: 3 })).toBe(waiting)
    expect(reviewReducer(waiting, { type: 'type', answer: 'changed' })).toBe(waiting)
  })

  it('a blocking refusal goes back to answering', () => {
    const state = reviewReducer(waiting, { type: 'checkFailed', error: new Error('x') })
    expect(state.phase).toBe('answering')
    expect(state.responseTimeMs).toBeNull()
  })

  it('drops the production only while recording, for the single resend', () => {
    const answered = reviewReducer(waiting, { type: 'productionChecked', check: checkAnswer() })
    expect(reviewReducer(answered, { type: 'productionDropped' })).toBe(answered)
    const recording = reviewReducer(answered, { type: 'rate', rating: 3 })
    expect(recording.productionAttemptId).toBe(77)
    const dropped = reviewReducer(recording, { type: 'productionDropped' })
    expect(dropped.phase).toBe('recording')
    expect(dropped.productionAttemptId).toBeNull()
    // A second drop is a no-op: the resend happens once.
    expect(reviewReducer(dropped, { type: 'productionDropped' })).toBe(dropped)
  })
})

describe('reviewMachine: a spoken answer', () => {
  const capturing = run([{ type: 'startCapture' }])
  const captured = run([{ type: 'captured', responseTimeMs: 6100 }], capturing)
  const sending = run([{ type: 'submitSpoken' }], captured)

  it('goes answering → capturing → captured → checking_spoken, fixing the response time at the end of the take', () => {
    expect(capturing.phase).toBe('capturing')
    expect(captured.phase).toBe('captured')
    expect(captured.responseTimeMs).toBe(6100)
    expect(sending.phase).toBe('checking_spoken')
    expect(sending.responseTimeMs).toBe(6100)
  })

  it('refuses an action that the phase does not allow with the same state object', () => {
    expect(reviewReducer(capturing, { type: 'startCapture' })).toBe(capturing)
    expect(reviewReducer(initialReviewState, { type: 'captured', responseTimeMs: 1 })).toBe(initialReviewState)
    expect(reviewReducer(capturing, { type: 'submitSpoken' })).toBe(capturing)
    expect(reviewReducer(sending, { type: 'submitSpoken' })).toBe(sending)
    expect(reviewReducer(sending, { type: 'startCapture' })).toBe(sending)
    expect(reviewReducer(sending, { type: 'discardCapture' })).toBe(sending)
    expect(reviewReducer(sending, { type: 'rate', rating: 3 })).toBe(sending)
    expect(reviewReducer(initialReviewState, { type: 'discardCapture' })).toBe(initialReviewState)
  })

  it('"Record again" goes back to answering and forgets the time', () => {
    for (const from of [capturing, captured]) {
      const state = reviewReducer(from, { type: 'discardCapture' })
      expect(state.phase).toBe('answering')
      expect(state.responseTimeMs).toBeNull()
    }
  })

  it('the answer gives the result, the correction and the production to rate with', () => {
    const state = reviewReducer(sending, { type: 'spokenChecked', answer: reviewAnswerOut() })
    expect(state.phase).toBe('answered')
    expect(state.productionAttemptId).toBe(88)
    expect(state.result?.outcome).toBeNull()
    expect(state.result?.proposed_rating).toBe(1)
    expect(state.result?.solution.example_answer).toBeDefined()
    expect(state.spoken?.transcription.status).toBe('ok')
    expect(state.spoken?.status).toBe('ok')
    expect(state.notice).toBeNull()
  })

  it('proposes a rating only with a correction, and keeps term_not_heard as a warning', () => {
    const warned = reviewReducer(sending, {
      type: 'spokenChecked',
      answer: reviewAnswerOut({ warnings: ['term_not_heard'], proposed_rating: null }),
    })
    expect(warned.result?.warnings).toEqual(['term_not_heard'])
    expect(warned.result?.proposed_rating).toBeNull()
    const silent = reviewReducer(sending, {
      type: 'spokenChecked',
      answer: untranscribedAnswer({ status: 'silence', text: null, reason: null }),
    })
    expect(silent.phase).toBe('answered')
    expect(silent.result?.proposed_rating).toBeNull()
    expect(silent.productionAttemptId).toBe(88)
    // A proposal without a correction is not trusted.
    const odd = reviewReducer(sending, {
      type: 'spokenChecked',
      answer: reviewAnswerOut({ status: 'unavailable', proposed_rating: 3 }),
    })
    expect(odd.result?.proposed_rating).toBeNull()
  })

  it('a late answer, after the way out or in any other phase, changes nothing', () => {
    const late = { type: 'spokenChecked', answer: reviewAnswerOut() } as const
    expect(reviewReducer(initialReviewState, late)).toBe(initialReviewState)
    expect(reviewReducer(capturing, late)).toBe(capturing)
    expect(reviewReducer(captured, late)).toBe(captured)
    const skipped = reviewReducer(sending, {
      type: 'spokenFallback',
      notice: { kind: 'spoken_skipped' },
      responseTimeMs: 9000,
    })
    expect(skipped.phase).toBe('checking')
    expect(reviewReducer(skipped, late)).toBe(skipped)
    const answered = reviewReducer(skipped, {
      type: 'checked',
      result: revealedResult({ solution: {}, sheet_summary: null }),
    })
    expect(answered.phase).toBe('answered')
    expect(reviewReducer(answered, late)).toBe(answered)
    expect(answered.productionAttemptId).toBeNull()
  })

  it('a refusal of the recording goes back to the take, which can be sent again', () => {
    const refused = reviewReducer(sending, { type: 'spokenFailed', error: new Error('audio') })
    expect(refused.phase).toBe('captured')
    expect(refused.error).toBeInstanceOf(Error)
    expect(refused.responseTimeMs).toBe(6100)
    const again = reviewReducer(refused, { type: 'submitSpoken' })
    expect(again.phase).toBe('checking_spoken')
    expect(again.error).toBeNull()
    expect(reviewReducer(captured, { type: 'spokenFailed', error: 1 })).toBe(captured)
  })

  it('the fallback is allowed from every spoken phase and keeps the end of the recording as the time', () => {
    const notice = { kind: 'spoken_failed', error: new Error('x') } as const
    for (const from of [initialReviewState, capturing, captured, sending]) {
      const state = reviewReducer(from, { type: 'spokenFallback', notice, responseTimeMs: 7000 })
      expect(state.phase).toBe('checking')
      expect(state.notice).toBe(notice)
      expect(state.productionAttemptId).toBeNull()
      expect(state.responseTimeMs).toBe(from.responseTimeMs ?? 7000)
    }
    const declined = reviewReducer(captured, { type: 'spokenFallback', notice: null, responseTimeMs: 7000 })
    expect(declined.notice).toBeNull()
    expect(declined.responseTimeMs).toBe(6100)
  })

  it('the fallback is refused once the card is answered or being rated', () => {
    const answered = reviewReducer(sending, { type: 'spokenChecked', answer: reviewAnswerOut() })
    const fallback = { type: 'spokenFallback', notice: null, responseTimeMs: 1 } as const
    expect(reviewReducer(answered, fallback)).toBe(answered)
    const rating = reviewReducer(answered, { type: 'rate', rating: 3 })
    expect(reviewReducer(rating, fallback)).toBe(rating)
    const checking = reviewReducer(captured, fallback)
    expect(reviewReducer(checking, fallback)).toBe(checking)
  })

  it('a blocking refusal goes back to answering', () => {
    const state = reviewReducer(sending, { type: 'checkFailed', error: new Error('not_due') })
    expect(state.phase).toBe('answering')
    expect(state.responseTimeMs).toBeNull()
  })
})
