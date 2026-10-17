import { fireEvent, render, renderHook } from '@testing-library/react'
import { describe, expect, it, type Mock, vi } from 'vitest'

import type { GradeResult } from '../../api/reviews'
import { initialReviewState, reviewReducer, revealedResult } from './reviewMachine'
import { type ReviewShortcutHandlers, useReviewShortcuts } from './useReviewShortcuts'

type Mocks = { [K in keyof ReviewShortcutHandlers]-?: Mock<NonNullable<ReviewShortcutHandlers[K]>> }

function handlers(): Mocks {
  return {
    choose: vi.fn(),
    reveal: vi.fn(),
    rate: vi.fn(),
    acceptProposed: vi.fn(),
    replay: vi.fn(),
  }
}

const key = (init: KeyboardEventInit, target: Element | Document = document) =>
  fireEvent.keyDown(target, init)

describe('useReviewShortcuts', () => {
  it('maps 1–4 to the option while answering a choice exercise', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ choose: h.choose, replay: h.replay }))
    key({ key: '1', code: 'Digit1' })
    key({ key: '4', code: 'Digit4' })
    key({ key: '5', code: 'Digit5' })
    expect(h.choose.mock.calls).toEqual([[0], [3]])
  })

  it('maps 1–4 to the rating once the answer is shown, and Enter to the proposed one', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ rate: h.rate, acceptProposed: h.acceptProposed }))
    key({ key: '2', code: 'Digit2' })
    key({ key: '3', code: 'Numpad3' })
    key({ key: 'Enter', code: 'Enter' })
    expect(h.rate.mock.calls).toEqual([[2], [3]])
    expect(h.acceptProposed).toHaveBeenCalledTimes(1)
  })

  it('reads the physical digit row (AZERTY without Shift gives "&", "é"...)', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ rate: h.rate }))
    key({ key: '&', code: 'Digit1' })
    key({ key: 'é', code: 'Digit2' })
    expect(h.rate.mock.calls).toEqual([[1], [2]])
  })

  it('reveals with Space or Enter for an exercise without input', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ reveal: h.reveal }))
    key({ key: ' ', code: 'Space' })
    key({ key: 'Enter', code: 'Enter' })
    expect(h.reveal).toHaveBeenCalledTimes(2)
  })

  it('replays with R and slowly with Shift+R, in every phase that has audio', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ rate: h.rate, replay: h.replay }))
    key({ key: 'r', code: 'KeyR' })
    key({ key: 'R', code: 'KeyR', shiftKey: true })
    expect(h.replay.mock.calls).toEqual([[false], [true]])
  })

  it('does nothing for a phase without the handler', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({}))
    key({ key: '1', code: 'Digit1' })
    key({ key: 'Enter', code: 'Enter' })
    key({ key: 'r', code: 'KeyR' })
    for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled()
  })

  it('ignores modifiers, auto-repeat and text fields', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ rate: h.rate, replay: h.replay, reveal: h.reveal }))
    const { container } = render(
      <div>
        <input aria-label="answer" />
        <textarea aria-label="sentence" />
        <select aria-label="pick">
          <option>a</option>
        </select>
        <div contentEditable suppressContentEditableWarning>
          editable
        </div>
      </div>,
    )
    key({ key: '1', code: 'Digit1', ctrlKey: true })
    key({ key: '2', code: 'Digit2', altKey: true })
    key({ key: '3', code: 'Digit3', metaKey: true })
    key({ key: '3', code: 'Digit3', repeat: true })
    for (const field of container.querySelectorAll('input, textarea, select, [contenteditable]')) {
      key({ key: '1', code: 'Digit1' }, field)
      key({ key: 'r', code: 'KeyR' }, field)
      key({ key: ' ', code: 'Space' }, field)
    }
    expect(h.rate).not.toHaveBeenCalled()
    expect(h.replay).not.toHaveBeenCalled()
    expect(h.reveal).not.toHaveBeenCalled()
  })

  it('leaves Enter and Space to a focused button (no double action)', () => {
    const h = handlers()
    renderHook(() => useReviewShortcuts({ reveal: h.reveal, acceptProposed: h.acceptProposed }))
    const { getByRole } = render(<button type="button">Show</button>)
    key({ key: 'Enter', code: 'Enter' }, getByRole('button'))
    key({ key: ' ', code: 'Space' }, getByRole('button'))
    expect(h.reveal).not.toHaveBeenCalled()
    expect(h.acceptProposed).not.toHaveBeenCalled()
    // Digits still work from a focused button.
    const rate = vi.fn()
    renderHook(() => useReviewShortcuts({ rate }))
    key({ key: '2', code: 'Digit2' }, getByRole('button'))
    expect(rate).toHaveBeenCalledWith(2)
  })

  it('uses the latest handlers without re-subscribing', () => {
    const first = vi.fn()
    const second = vi.fn()
    const { rerender } = renderHook(({ rate }) => useReviewShortcuts({ rate }), {
      initialProps: { rate: first },
    })
    rerender({ rate: second })
    key({ key: '1', code: 'Digit1' })
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledWith(1)
  })
})

const graded: GradeResult = {
  outcome: 'typo',
  proposed_rating: 2,
  expected: 'drill down into',
  accepted: [],
  diff: null,
  warnings: [],
  solution: { answer: 'drill down into', accepted: [] },
  sheet_summary: null,
}

describe('reviewReducer', () => {
  it('walks answering → checking → answered → recording → recorded', () => {
    let state = reviewReducer(initialReviewState, { type: 'type', answer: 'drill down inot' })
    state = reviewReducer(state, { type: 'submit', choiceIndex: null, responseTimeMs: 4200 })
    expect(state.phase).toBe('checking')
    state = reviewReducer(state, { type: 'checked', result: graded })
    expect(state).toMatchObject({ phase: 'answered', responseTimeMs: 4200, answer: 'drill down inot' })
    state = reviewReducer(state, { type: 'rate', rating: 3 })
    expect(state).toMatchObject({ phase: 'recording', rating: 3 })
    expect(reviewReducer(state, { type: 'recorded' }).phase).toBe('recorded')
  })

  it('refuses actions the phase does not allow (same object back)', () => {
    const answering = reviewReducer(initialReviewState, { type: 'type', answer: 'x' })
    expect(reviewReducer(answering, { type: 'rate', rating: 3 })).toBe(answering)
    const checking = reviewReducer(answering, { type: 'submit', choiceIndex: 1, responseTimeMs: 1 })
    expect(reviewReducer(checking, { type: 'submit', choiceIndex: 2, responseTimeMs: 2 })).toBe(checking)
    expect(reviewReducer(checking, { type: 'type', answer: 'y' })).toBe(checking)
    const answered = reviewReducer(checking, { type: 'checked', result: graded })
    const recording = reviewReducer(answered, { type: 'rate', rating: 1 })
    // A second key press before the answer: no second POST /reviews.
    expect(reviewReducer(recording, { type: 'rate', rating: 4 })).toBe(recording)
  })

  it('keeps the typed answer when grading fails, and allows rating again when recording fails', () => {
    const checking = reviewReducer(
      reviewReducer(initialReviewState, { type: 'type', answer: 'drill down' }),
      { type: 'submit', choiceIndex: null, responseTimeMs: 10 },
    )
    const failed = reviewReducer(checking, { type: 'checkFailed', error: new Error('offline') })
    expect(failed).toMatchObject({ phase: 'answering', answer: 'drill down', responseTimeMs: null })
    expect(failed.error).toBeInstanceOf(Error)

    const answered = reviewReducer(checking, { type: 'checked', result: graded })
    const recording = reviewReducer(answered, { type: 'rate', rating: 3 })
    const back = reviewReducer(recording, { type: 'recordFailed', error: new Error('offline') })
    expect(back).toMatchObject({ phase: 'answered', rating: null, responseTimeMs: 10 })
  })

  it('turns a reveal into a result without outcome or proposed rating', () => {
    expect(
      revealedResult({ solution: { example_answer: 'I would…' }, sheet_summary: null }),
    ).toMatchObject({ outcome: null, proposed_rating: null, solution: { example_answer: 'I would…' } })
  })
})
