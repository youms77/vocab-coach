import { describe, expect, it } from 'vitest'

import type { ItemResult } from '../../api/drills'
import { answerBody, drillItemReducer, initialItemState } from './drillMachine'

const result: ItemResult = {
  outcome: 'wrong',
  expected: 'on',
  accepted: [],
  correct_index: null,
  explanation_en: 'x',
  explanation_fr: 'y',
  given: 'in',
}

const submitted = drillItemReducer(initialItemState, {
  type: 'submit',
  attempt: { kind: 'text', answer: 'in' },
  responseTimeMs: 1200,
})

describe('drillItemReducer', () => {
  it('types only while answering', () => {
    const typed = drillItemReducer(initialItemState, { type: 'type', answer: 'o' })
    expect(typed.answer).toBe('o')
    expect(drillItemReducer(submitted, { type: 'type', answer: 'x' })).toBe(submitted)
  })

  it('submits once: a second submit changes nothing', () => {
    expect(submitted.phase).toBe('sending')
    expect(submitted.responseTimeMs).toBe(1200)
    const again = drillItemReducer(submitted, {
      type: 'submit',
      attempt: { kind: 'text', answer: 'on' },
      responseTimeMs: 5,
    })
    expect(again).toBe(submitted)
  })

  it('shows the result only after the server answered', () => {
    expect(submitted.result).toBeNull()
    expect(drillItemReducer(initialItemState, { type: 'answered', result, errorEventId: null })).toBe(
      initialItemState,
    )
    const answered = drillItemReducer(submitted, { type: 'answered', result, errorEventId: 7 })
    expect(answered).toMatchObject({ phase: 'answered', result, errorEventId: 7 })
    expect(drillItemReducer(answered, { type: 'failed', error: new Error('late') })).toBe(answered)
  })

  it('goes back to answering with the typed answer when sending fails', () => {
    const typed = drillItemReducer(initialItemState, { type: 'type', answer: 'in' })
    const sending = drillItemReducer(typed, {
      type: 'submit',
      attempt: { kind: 'text', answer: 'in' },
      responseTimeMs: 900,
    })
    const error = new Error('network')
    const failed = drillItemReducer(sending, { type: 'failed', error })
    expect(failed).toMatchObject({ phase: 'answering', answer: 'in', attempt: null, responseTimeMs: null, error })
  })
})

describe('answerBody', () => {
  it('sends `answer` for a gap-fill, even empty, and never `choice_index`', () => {
    expect(answerBody({ kind: 'text', answer: 'on' }, 800)).toEqual({ answer: 'on', response_time_ms: 800 })
    expect(answerBody({ kind: 'text', answer: '' }, 800)).toEqual({ answer: '', response_time_ms: 800 })
  })

  it('sends `choice_index` for a choice, null for "I don\'t know", and never `answer`', () => {
    expect(answerBody({ kind: 'choice', index: 2 }, 800)).toEqual({ choice_index: 2, response_time_ms: 800 })
    expect(answerBody({ kind: 'choice', index: null }, 800)).toEqual({
      choice_index: null,
      response_time_ms: 800,
    })
  })
})
