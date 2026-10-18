import { describe, expect, it } from 'vitest'

import { checkAnswer, checkedFeedback, CHECKED_SENTENCE } from '../../test/writingFixtures'
import { initialReviewState, type ReviewAction, reviewReducer, type ReviewState } from './reviewMachine'

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
