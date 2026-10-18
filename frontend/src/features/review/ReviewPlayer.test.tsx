import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CheckProductionResult, GradeResult, RecordResult } from '../../api/reviews'
import type { ReviewStep, SessionSummary, Step } from '../../api/session'
import i18n from '../../i18n'
import {
  gradeAnswer,
  plan,
  progress,
  recordAnswer,
  type ReviewCase,
  reviewCases,
  reviewStep,
  studySession,
} from '../../test/fixtures'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { unavailableCheck } from '../../test/writingFixtures'

const summary: SessionSummary = {
  format: 'session-1',
  reviews: 1,
  failed_reviews: 0,
  discoveries_started: 0,
  discoveries_completed: 0,
  productions: 0,
  words: 0,
  duration_ms: 60_000,
  planned_minutes: 5,
}

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /session/today': { plan: plan(), open_session: null },
  'GET /decks': [],
  'GET /settings': {},
  'POST /session/7/end': () => Response.json(studySession(7, { summary })),
}

const reviewOf = (review: ReviewStep): Step => ({
  type: 'review',
  session_id: 7,
  progress: progress({ reviews_remaining: 1, new_remaining: 0 }),
  review,
})
const done: Step = { type: 'done', session_id: 7, progress: progress({ new_remaining: 0 }) }

interface Routes {
  review: ReviewStep
  grade?: GradeResult | (() => Response)
  reveal?: object
  record?: RecordResult | (() => Response)
  /** The AI check of a typed sentence; unavailable unless a test says otherwise. */
  check?: CheckProductionResult | (() => Response | Promise<Response>)
  /** What `next` answers once a review is recorded. */
  after?: Step
}

/** A session whose `next` gives one review, then `after` (done by default) once it is recorded. */
function session({ review, grade, reveal, record, check, after = done }: Routes) {
  let recorded = false
  return mockApi({
    ...base,
    'POST /session/start': () => Response.json(studySession(7), { status: 200 }),
    'GET /session/7/next': () => Response.json(recorded ? after : reviewOf(review)),
    'POST /reviews/grade': () =>
      typeof grade === 'function' ? grade() : Response.json(grade ?? gradeAnswer()),
    'POST /reviews/reveal': () => Response.json(reveal),
    'POST /reviews/check-production': () =>
      typeof check === 'function' ? check() : Response.json(check ?? unavailableCheck()),
    'POST /reviews': () => {
      if (typeof record === 'function') return record()
      recorded = true
      return Response.json(record ?? recordAnswer())
    },
  })
}

const reviewCalls = (calls: RecordedCall[]) =>
  calls
    .filter((c) => c.path.startsWith('/reviews') || c.path.startsWith('/session/7/next'))
    .map((c) => `${c.method} ${c.path}`)
const recordBodies = (calls: RecordedCall[]) =>
  calls.filter((c) => c.method === 'POST' && c.path === '/reviews').map((c) => c.body)

const cardTitle = (c: ReviewCase) =>
  ({
    recognition_in_sentence: 'Recognise the term in a sentence',
    listening_comprehension: 'Listen and understand',
    typed_recall: 'Recall the English term',
    gap_fill: 'Fill the gap',
    sentence_production: 'Write a sentence',
    spoken_answer: 'Answer aloud',
    self_assessment: 'Do you remember?',
  })[c.step.exercise_type] as string

/** The answer each case gives: an option, a typed text, or "Show". */
async function answer(user: ReturnType<typeof userEvent.setup>, c: ReviewCase) {
  if (c.step.input === 'choice') {
    await user.click(screen.getByRole('button', { name: /^3 to examine something in more detail/ }))
  } else if (c.step.exercise_type === 'sentence_production') {
    await user.type(screen.getByLabelText('Your sentence'), 'I will look at the numbers.{Enter}')
  } else if (c.step.input === 'text') {
    await user.type(screen.getByRole('textbox'), 'drill down inot{Enter}')
  } else {
    await user.click(screen.getByRole('button', { name: /^Show (the answer|an example answer)$/ }))
  }
}

const typedAnswer: Record<string, string> = {
  typed_recall: 'drill down inot',
  gap_fill: 'drill down inot',
  sentence_production: 'I will look at the numbers.',
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Review player: every exercise type', () => {
  for (const c of reviewCases) {
    it(`${c.name}: answering → answered → rating, with the right calls and bodies`, async () => {
      installFakeSpeech()
      const calls = session({ review: c.step, grade: c.grade, reveal: c.reveal })
      const user = userEvent.setup()
      renderApp('/session')

      const title = await screen.findByRole('heading', { name: cardTitle(c) })
      expect(title).toHaveFocus()
      // Active recall: nothing of the solution in the page (text or attributes) before the attempt.
      for (const secret of c.secrets) expect(document.body.innerHTML).not.toContain(secret)
      expect(screen.queryByRole('group', { name: 'How well did you remember?' })).toBeNull()

      await answer(user, c)
      const result = await screen.findByRole('region', { name: 'Correction' })
      await waitFor(() => expect(result).toHaveFocus())

      const ratings = screen.getByRole('group', { name: 'How well did you remember?' })
      await user.click(within(ratings).getByRole('button', { name: /^3 Good/ }))
      await screen.findByRole('heading', { name: 'Session summary' })

      const graded = c.step.input !== 'none'
      // A typed sentence is first sent to the AI check; here it is unavailable, so the card goes
      // on exactly as in M4.c (`grade`, self-graded).
      const aiCheck = c.step.exercise_type === 'sentence_production' ? ['POST /reviews/check-production'] : []
      expect(reviewCalls(calls)).toEqual([
        'GET /session/7/next',
        ...aiCheck,
        graded ? 'POST /reviews/grade' : 'POST /reviews/reveal',
        'POST /reviews',
        'GET /session/7/next',
      ])
      const checkCall = calls.find((call) => /^\/reviews\/(grade|reveal)$/.test(call.path))
      expect(checkCall?.body).toMatchObject({
        card_id: 21,
        exercise_type: c.step.exercise_type,
        exercise_template_id: c.step.exercise_template_id,
      })
      const [body] = recordBodies(calls)
      expect(body).toEqual({
        card_id: 21,
        session_id: 7,
        exercise_type: c.step.exercise_type,
        exercise_template_id: c.step.exercise_template_id,
        answer: typedAnswer[c.step.exercise_type] ?? null,
        choice_index: c.step.input === 'choice' ? 2 : null,
        response_time_ms: expect.any(Number),
        final_rating: 3,
        expected_reps: 4,
      })
      expect(body).not.toHaveProperty('auto_rating')
    })
  }

  it('shows the solution of each type only after the attempt', async () => {
    const c = reviewCases.find((r) => r.name === 'listening_comprehension') as ReviewCase
    session({ review: c.step, grade: c.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Listen and understand' })
    await user.click(screen.getByRole('button', { name: /^1 to summarise quickly/ }))
    const result = await screen.findByRole('region', { name: 'Correction' })
    // The sentence appears after the answer; the right option and the wrong choice are marked.
    expect(result).toHaveTextContent('We need to drill down into these unexpected numbers.')
    expect(screen.getByRole('button', { name: /^3 to examine.*Right answer/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^1 to summarise quickly.*Your choice/ })).toBeDisabled()
  })

  it('speaks the listening sentence on display and keeps it out of the page', async () => {
    const fake = installFakeSpeech()
    const c = reviewCases.find((r) => r.name === 'listening_comprehension') as ReviewCase
    session({ review: c.step, grade: c.grade })
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Listen and understand' })
    await waitFor(() => expect(fake.spoken.map((u) => u.text)).toEqual([c.step.prompt.sentence]))
    expect(fake.spoken[0].lang).toBe('en-US')
    expect(screen.getByRole('button', { name: 'Listen to “the sentence”' })).toBeEnabled()
    expect(document.body.innerHTML).not.toContain('unexpected numbers')
  })

  it('presents the production example as an example, and translates term_missing', async () => {
    const c = reviewCases.find((r) => r.name === 'sentence_production') as ReviewCase
    session({ review: c.step, grade: c.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Write a sentence' })
    // Shift+Enter is a new line, not a submission.
    const field = screen.getByLabelText('Your sentence')
    await user.type(field, 'First line{Shift>}{Enter}{/Shift}second line')
    expect(field).toHaveValue('First line\nsecond line')
    expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
    await user.type(field, '{Enter}')
    const result = await screen.findByRole('region', { name: 'Correction' })
    expect(result).toHaveTextContent('Example answer (one possibility among others):')
    expect(result).toHaveTextContent('Your sentence does not contain the term.')
    expect(result).not.toHaveTextContent(/Expected answer/)
  })

  it('says that nothing is recorded yet for a spoken answer', async () => {
    const c = reviewCases.find((r) => r.name === 'spoken_answer') as ReviewCase
    session({ review: c.step, reveal: c.reveal })
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Answer aloud' })
    expect(screen.getByText(/Nothing is recorded yet/)).toBeInTheDocument()
  })
})

describe('Review player: rating', () => {
  it('marks the proposed rating with a text and lets the user choose another one', async () => {
    const typo = reviewCases.find((r) => r.name === 'typed_recall') as ReviewCase
    const calls = session({ review: typo.step, grade: typo.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down inot{Enter}')

    const ratings = await screen.findByRole('group', { name: 'How well did you remember?' })
    expect(within(ratings).getByRole('button', { name: '2 Hard Suggested' })).toBeInTheDocument()
    expect(within(ratings).getAllByText('Suggested')).toHaveLength(1)
    expect(screen.getByText('Suggested rating: Hard. You can choose another one.')).toBeInTheDocument()
    // The typo and its character diff are shown.
    expect(screen.getByText('Almost: a small typo')).toBeInTheDocument()
    expect(screen.getByText(/compared with the expected one/)).toBeInTheDocument()

    await user.click(within(ratings).getByRole('button', { name: /^3 Good/ }))
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ final_rating: 3 }])
  })

  it('never marks Easy: a proposed Good leaves Easy plain', async () => {
    session({ review: reviewStep(), grade: gradeAnswer({ proposed_rating: 3 }) })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    const ratings = await screen.findByRole('group', { name: 'How well did you remember?' })
    expect(within(ratings).getByRole('button', { name: '3 Good Suggested' })).toBeInTheDocument()
    expect(within(ratings).getByRole('button', { name: '4 Easy' })).toBeInTheDocument()
  })

  it('offers four neutral buttons for self-graded types', async () => {
    const c = reviewCases.find((r) => r.name === 'self_assessment (productive)') as ReviewCase
    session({ review: c.step, reveal: c.reveal })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Do you remember?' })
    await user.click(screen.getByRole('button', { name: 'Show the answer' }))
    const ratings = await screen.findByRole('group', { name: 'How well did you remember?' })
    expect(within(ratings).getAllByRole('button').map((b) => b.textContent)).toEqual([
      '1 Again',
      '2 Hard',
      '3 Good',
      '4 Easy',
    ])
    expect(screen.queryByText('Suggested')).toBeNull()
    expect(screen.getByText(/Rate yourself: no rating is suggested/)).toBeInTheDocument()
  })

  it('announces the next due date and a status change without delaying the next card', async () => {
    const next = reviewStep({ card_id: 22, expected_reps: 1 })
    session({
      review: reviewStep(),
      record: recordAnswer({
        due_after: '2026-11-03T08:00:00Z',
        item_status: 'consolidated',
        item_status_changed: true,
      }),
      after: reviewOf(next),
    })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await screen.findByRole('group', { name: 'How well did you remember?' })
    await user.keyboard('3')
    const status = await screen.findByText(/Saved: the previous card comes back on November 3, 2026\./)
    expect(status).toHaveAttribute('role', 'status')
    expect(status).toHaveTextContent('“drill down into” is now consolidated.')
    // The next card is a fresh one: empty field, no result.
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
    expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
  })
})

const pressed = (key: string, code: string) =>
  new KeyboardEvent('keydown', { key, code, bubbles: true, cancelable: true })

describe('Review player: keyboard', () => {
  const choice = reviewCases.find((r) => r.name === 'recognition_in_sentence') as ReviewCase

  it('choice: 2 picks and checks the option, 3 rates Good', async () => {
    const calls = session({ review: choice.step, grade: choice.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recognise the term in a sentence' })
    expect(document.querySelector('.key-hints')).toHaveTextContent('1–4 choose')
    await user.keyboard('2')
    await screen.findByRole('region', { name: 'Correction' })
    expect(calls.find((c) => c.path === '/reviews/grade')?.body).toMatchObject({ choice_index: 1 })
    await user.keyboard('3')
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ choice_index: 1, final_rating: 3 }])
  })

  it('typed: Enter in the field checks, Enter again accepts the proposed rating', async () => {
    const typo = reviewCases.find((r) => r.name === 'typed_recall') as ReviewCase
    const calls = session({ review: typo.step, grade: typo.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    // Digits typed in the field are text, not shortcuts.
    await user.type(screen.getByRole('textbox'), 'drill 3 down{Enter}')
    expect(screen.getByRole('textbox')).toHaveValue('drill 3 down')
    await screen.findByRole('region', { name: 'Correction' })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Correction' })).toHaveFocus())
    await user.keyboard('{Enter}')
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ answer: 'drill 3 down', final_rating: 2 }])
  })

  it('no input: Space shows the answer, 4 rates Easy', async () => {
    const c = reviewCases.find((r) => r.name === 'self_assessment (receptive)') as ReviewCase
    const calls = session({ review: c.step, reveal: c.reveal })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Do you remember?' })
    await user.keyboard(' ')
    await screen.findByRole('region', { name: 'Correction' })
    await user.keyboard('4')
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ final_rating: 4, answer: null, choice_index: null }])
  })

  it('no input: Enter shows the answer too', async () => {
    const c = reviewCases.find((r) => r.name === 'spoken_answer') as ReviewCase
    const calls = session({ review: c.step, reveal: c.reveal })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Answer aloud' })
    await user.keyboard('{Enter}')
    await screen.findByRole('region', { name: 'Correction' })
    expect(calls.filter((call) => call.path === '/reviews/reveal')).toHaveLength(1)
  })

  it('R replays the sentence, Shift+R slowly; nothing for a productive card before the answer', async () => {
    const fake = installFakeSpeech()
    session({ review: choice.step, grade: choice.grade })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recognise the term in a sentence' })
    await user.keyboard('r')
    await user.keyboard('{Shift>}R{/Shift}')
    expect(fake.spoken.map((u) => [u.text, u.rate])).toEqual([
      ['Let us drill down into the regional figures.', 1],
      ['Let us drill down into the regional figures.', 0.7],
    ])
  })

  it('R says nothing before a productive answer, then the term after it', async () => {
    const fake = installFakeSpeech()
    session({ review: reviewStep() })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    fireEvent.keyDown(document.body, { key: 'r', code: 'KeyR' })
    expect(fake.spoken).toHaveLength(0)
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await screen.findByRole('region', { name: 'Correction' })
    fireEvent.keyDown(document.body, { key: 'r', code: 'KeyR' })
    expect(fake.spoken.map((u) => u.text)).toEqual(['drill down into'])
  })

  it('ignores modifiers and auto-repeat, and sends one POST /reviews despite a double press', async () => {
    const calls = session({ review: choice.step, grade: choice.grade })
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recognise the term in a sentence' })
    fireEvent.keyDown(document.body, { key: '3', code: 'Digit3', ctrlKey: true })
    fireEvent.keyDown(document.body, { key: '3', code: 'Digit3', repeat: true })
    expect(calls.some((c) => c.path === '/reviews/grade')).toBe(false)

    act(() => {
      document.body.dispatchEvent(pressed('3', 'Digit3'))
      document.body.dispatchEvent(pressed('1', 'Digit1'))
    })
    await screen.findByRole('region', { name: 'Correction' })
    expect(calls.filter((c) => c.path === '/reviews/grade')).toHaveLength(1)

    fireEvent.keyDown(document.body, { key: '3', code: 'Digit3', altKey: true })
    fireEvent.keyDown(document.body, { key: '3', code: 'Digit3', repeat: true })
    expect(recordBodies(calls)).toHaveLength(0)
    // Two presses before React re-renders (one batch): one rating only.
    act(() => {
      document.body.dispatchEvent(pressed('3', 'Digit3'))
      document.body.dispatchEvent(pressed('4', 'Digit4'))
    })
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ final_rating: 3 }])
  })
})

describe('Review player: response time', () => {
  it('measures from the prompt to the answer, not to the rating', async () => {
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'],
    })
    const calls = session({ review: reviewStep() })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000)
    })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await screen.findByRole('region', { name: 'Correction' })
    // Reading the correction for a minute does not count.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    await user.keyboard('3')
    await screen.findByRole('heading', { name: 'Session summary' })

    const graded = calls.find((c) => c.path === '/reviews/grade')?.body as { response_time_ms: number }
    const [recorded] = recordBodies(calls) as { response_time_ms: number }[]
    expect(graded.response_time_ms).toBeGreaterThanOrEqual(7_000)
    expect(graded.response_time_ms).toBeLessThan(10_000)
    expect(recorded.response_time_ms).toBe(graded.response_time_ms)
  })
})

describe('Review player: errors', () => {
  it('card_changed: asks for the next step with a discreet message', async () => {
    let tries = 0
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 200 }),
      'GET /session/7/next': () =>
        Response.json(reviewOf(tries === 0 ? reviewStep() : reviewStep({ card_id: 22 }))),
      'POST /reviews/grade': () => Response.json(gradeAnswer()),
      'POST /reviews': () => {
        tries += 1
        return apiErrorResponse(409, 'card_changed', 'changed', { reps: 5 })
      },
    })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await screen.findByRole('group', { name: 'How well did you remember?' })
    await user.keyboard('3')
    expect(await screen.findByText(/already rated elsewhere/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''))
    expect(reviewCalls(calls).filter((c) => c.startsWith('GET'))).toHaveLength(2)
  })

  for (const [code, message] of [
    ['not_due', 'This card is not due yet.'],
    ['review_not_allowed', 'This term cannot be reviewed or practised now.'],
  ] as const) {
    it(`${code}: says so and offers to continue the session`, async () => {
      const calls = session({
        review: reviewStep(),
        record: () => apiErrorResponse(409, code),
      })
      const user = userEvent.setup()
      renderApp('/session')
      await screen.findByRole('heading', { name: 'Recall the English term' })
      await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
      await screen.findByRole('group', { name: 'How well did you remember?' })
      await user.keyboard('3')
      expect(await screen.findByText(message)).toBeInTheDocument()
      // No rating buttons any more: rating again would be refused the same way.
      expect(screen.queryByRole('group', { name: 'How well did you remember?' })).toBeNull()
      const before = reviewCalls(calls).filter((c) => c.startsWith('GET')).length
      await user.click(screen.getByRole('button', { name: 'Continue the session' }))
      await waitFor(() =>
        expect(reviewCalls(calls).filter((c) => c.startsWith('GET'))).toHaveLength(before + 1),
      )
    })
  }

  it('exercise_mismatch: an unexpected error with "Retry"', async () => {
    const calls = session({
      review: reviewStep(),
      grade: () => apiErrorResponse(422, 'exercise_mismatch'),
    })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Retry' }))
    await waitFor(() =>
      expect(reviewCalls(calls).filter((c) => c.startsWith('GET'))).toHaveLength(2),
    )
    expect(await screen.findByRole('textbox')).toHaveValue('')
  })

  it('a failed grade keeps the answer typed and lets the user check again', async () => {
    let failing = true
    session({
      review: reviewStep(),
      grade: () => {
        if (failing) {
          failing = false
          return Response.json({ detail: 'boom' }, { status: 500 })
        }
        return Response.json(gradeAnswer())
      },
    })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    expect(await screen.findByText('Unexpected error (HTTP 500).')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('drill down into')
    expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly')
    expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByRole('region', { name: 'Correction' })).toBeInTheDocument()
  })

  it('a closed session during the rating offers a new session', async () => {
    session({ review: reviewStep(), record: () => apiErrorResponse(409, 'session_closed') })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down into{Enter}')
    await screen.findByRole('group', { name: 'How well did you remember?' })
    await user.keyboard('3')
    expect(await screen.findByRole('heading', { name: 'This session is already closed.' })).toBeInTheDocument()
  })
})

describe('Review player: French', () => {
  it('is translated', async () => {
    await i18n.changeLanguage('fr')
    session({ review: reviewStep() })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Retrouver le terme anglais' })
    expect(screen.getByText('Carte productive : du sens vers l\'anglais.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Le terme anglais'), 'drill down into{Enter}')
    const ratings = await screen.findByRole('group', { name: 'Vous en êtes-vous bien souvenu ?' })
    expect(within(ratings).getByRole('button', { name: '3 Bien Suggérée' })).toBeInTheDocument()
    expect(within(ratings).getByRole('button', { name: '1 À revoir' })).toBeInTheDocument()
    expect(screen.getByText('Raccourcis clavier', { exact: false })).toBeInTheDocument()
  })
})
