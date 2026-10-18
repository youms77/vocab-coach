import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CheckProductionResult, GradeResult } from '../../api/reviews'
import type { ReviewStep, SessionSummary, Step } from '../../api/session'
import i18n from '../../i18n'
import {
  gradeAnswer,
  plan,
  progress,
  recordAnswer,
  reviewStep,
  studySession,
} from '../../test/fixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import {
  CHECKED_SENTENCE,
  checkAnswer,
  checkedFeedback,
  EXAMPLE_ANSWER,
  unavailableCheck,
} from '../../test/writingFixtures'

// The AI check of a typed `sentence_production` (M5.b1, D-129, D-142).

const production = reviewStep({
  srs_state: 'review',
  exercise_type: 'sentence_production',
  exercise_template_id: 33,
  self_graded: true,
  prompt: { situation: 'Your manager asks how you will analyse a drop in sales.' },
})
const otherCard = reviewStep({ card_id: 22, lexical_item_id: 6, exercise_template_id: 35 })

const summary: SessionSummary = {
  format: 'session-1',
  reviews: 1,
  failed_reviews: 0,
  discoveries_started: 0,
  discoveries_completed: 0,
  productions: 1,
  words: 6,
  duration_ms: 60_000,
  planned_minutes: 5,
}

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /session/today': { plan: plan(), open_session: null },
  'GET /decks': [],
  'GET /settings': {},
  'GET /error-categories': [],
  'POST /session/7/end': () => Response.json(studySession(7, { summary })),
}

const reviewOf = (review: ReviewStep): Step => ({
  type: 'review',
  session_id: 7,
  progress: progress({ reviews_remaining: 1, new_remaining: 0 }),
  review,
})
const done: Step = { type: 'done', session_id: 7, progress: progress({ new_remaining: 0 }) }

interface Script {
  check?: CheckProductionResult | (() => Response | Promise<Response>)
  grade?: GradeResult
  record?: () => Response
  /** What `next` gives once the review is recorded. */
  after?: Step
}

function session({ check, grade, record, after = done }: Script = {}) {
  let recorded = false
  return mockApi({
    ...base,
    'POST /session/start': () => Response.json(studySession(7)),
    'GET /session/7/next': () => Response.json(recorded ? after : reviewOf(production)),
    'POST /reviews/check-production': () =>
      typeof check === 'function' ? check() : Response.json(check ?? checkAnswer()),
    'POST /reviews/grade': () =>
      Response.json(
        grade ??
          gradeAnswer({
            outcome: null,
            proposed_rating: null,
            expected: null,
            warnings: [],
            solution: { example_answer: EXAMPLE_ANSWER },
          }),
      ),
    'POST /reviews': () => {
      if (record !== undefined) return record()
      recorded = true
      return Response.json(recordAnswer())
    },
  })
}

const callsTo = (calls: RecordedCall[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path)
const recordBodies = (calls: RecordedCall[]) => callsTo(calls, 'POST', '/reviews').map((c) => c.body)

/** A request that stays open until the test answers it. */
function deferred() {
  let answer: (response: Response) => void = () => {}
  const promise = new Promise<Response>((resolve) => {
    answer = resolve
  })
  return { promise, answer }
}

async function sendSentence(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('heading', { name: 'Write a sentence' })
  await user.type(screen.getByLabelText('Your sentence'), `${CHECKED_SENTENCE}{Enter}`)
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Review player: sentence production checked by the AI', () => {
  it('sends the exact check body, then rates with the checked sentence and no auto_rating', async () => {
    const calls = session()
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    const result = await screen.findByRole('region', { name: 'Correction' })
    await waitFor(() => expect(result).toHaveFocus())

    expect(callsTo(calls, 'POST', '/reviews/check-production')).toHaveLength(1)
    expect(callsTo(calls, 'POST', '/reviews/check-production')[0].body).toEqual({
      card_id: 21,
      session_id: 7,
      exercise_template_id: 33,
      answer: CHECKED_SENTENCE,
      response_time_ms: expect.any(Number),
    })
    // The AI check replaces `grade`: nothing else is asked before the rating.
    expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(0)

    await user.click(within(screen.getByRole('group', { name: 'How well did you remember?' })).getByRole('button', { name: /^3 Good/ }))
    await screen.findByRole('heading', { name: 'Session summary' })
    const [body] = recordBodies(calls) as Record<string, unknown>[]
    expect(body).toMatchObject({ card_id: 21, final_rating: 3, answer: CHECKED_SENTENCE, production_attempt_id: 77 })
    expect(body).not.toHaveProperty('auto_rating')
    // The same response time is sent to the check and to the rating (D-121).
    expect(body.response_time_ms).toBe(
      (callsTo(calls, 'POST', '/reviews/check-production')[0].body as { response_time_ms: number })
        .response_time_ms,
    )
  })

  it('shows nothing of the example answer before the AI has answered (active recall)', async () => {
    const wait = deferred()
    session({ check: () => wait.promise })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Write a sentence' })
    expect(document.body.innerHTML).not.toContain('region by region')

    await user.type(screen.getByLabelText('Your sentence'), `${CHECKED_SENTENCE}{Enter}`)
    expect(await screen.findByText(/^Checking your sentence… \d+ s$/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
    expect(document.body.innerHTML).not.toContain('region by region')
    expect(document.body.innerHTML).not.toContain(EXAMPLE_ANSWER)

    await act(async () => wait.answer(Response.json(checkAnswer())))
    const result = await screen.findByRole('region', { name: 'Correction' })
    expect(result).toHaveTextContent('Example answer (one possibility among others):')
    expect(result).toHaveTextContent(EXAMPLE_ANSWER)
  })

  it('shows the errors and the feedback in a compact correction, with the sheet summary', async () => {
    session()
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    const result = await screen.findByRole('region', { name: 'Correction' })
    const marked = Array.from(result.querySelectorAll('mark'))
    expect(marked).toHaveLength(1)
    expect(marked[0].firstChild?.textContent).toBe('drill down in')
    expect(within(result).getByText('Error 1')).toBeInTheDocument()
    expect(within(result).getAllByText('drill down into').length).toBeGreaterThan(0)
    expect(within(result).getByText('"Drill down" takes "into".')).toBeInTheDocument()
    expect(within(result).getByRole('heading', { name: 'Corrected version' })).toBeInTheDocument()
    // Compact: no natural version, no copy button.
    expect(within(result).queryByRole('button', { name: 'Copy' })).toBeNull()
    // The sheet summary comes with the answer, as for the other types.
    expect(within(result).getByRole('link', { name: /full usage sheet/i })).toBeInTheDocument()
  })

  it('marks the proposed Again (1) as Suggested, and Enter accepts it', async () => {
    const calls = session({ check: checkAnswer({ proposed_rating: 1 }) })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    await screen.findByRole('region', { name: 'Correction' })
    const again = screen.getByRole('button', { name: /^1 Again/ })
    expect(again).toHaveTextContent('Suggested')
    expect(screen.getByRole('button', { name: /^3 Good/ })).not.toHaveTextContent('Suggested')
    await user.keyboard('{Enter}')
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ final_rating: 1, production_attempt_id: 77 }])
  })

  it('marks the proposed Good (3) as Suggested and Enter accepts it', async () => {
    const calls = session({ check: checkAnswer({ proposed_rating: 3, errors: [], feedback: checkedFeedback() }) })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    await screen.findByRole('region', { name: 'Correction' })
    expect(screen.getByRole('button', { name: /^3 Good/ })).toHaveTextContent('Suggested')
    expect(screen.getAllByText('Suggested')).toHaveLength(1)
    await user.keyboard('{Enter}')
    await screen.findByRole('heading', { name: 'Session summary' })
    const [body] = recordBodies(calls) as Record<string, unknown>[]
    expect(body).toMatchObject({ final_rating: 3, production_attempt_id: 77 })
    expect(body).not.toHaveProperty('auto_rating')
  })

  it('gives four buttons without a suggestion when the AI proposes no rating', async () => {
    const calls = session({ check: checkAnswer({ proposed_rating: null }) })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    await screen.findByRole('region', { name: 'Correction' })
    expect(screen.queryByText('Suggested')).toBeNull()
    expect(screen.getAllByRole('button', { name: /^[1-4] / })).toHaveLength(4)
    // Enter accepts nothing: there is no proposal.
    await user.keyboard('{Enter}')
    expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: /^2 Hard/ }))
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(recordBodies(calls)).toMatchObject([{ final_rating: 2, production_attempt_id: 77 }])
  })

  it('says that the target term is missing, from the stored correction', async () => {
    session({
      check: checkAnswer({
        feedback: checkedFeedback(CHECKED_SENTENCE, false),
        proposed_rating: 1,
      }),
    })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    const result = await screen.findByRole('region', { name: 'Correction' })
    expect(result).toHaveTextContent('Your sentence does not contain the term.')
  })

  describe('when the AI cannot check the sentence', () => {
    it.each([
      ['unavailable', unavailableCheck('unavailable', 'quota'), /not available: the free quota is used up/],
      ['incomplete', unavailableCheck('incomplete'), /could not be used/],
    ])('%s: the M4.c self-graded path, and the rating goes without the sentence', async (_name, check, notice) => {
      const calls = session({ check })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent(notice)
      expect(result).toHaveTextContent('Example answer (one possibility among others):')
      expect(screen.queryByText('Suggested')).toBeNull()
      expect(screen.getAllByRole('button', { name: /^[1-4] / })).toHaveLength(4)
      expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(1)

      await user.click(screen.getByRole('button', { name: /^3 Good/ }))
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls) as Record<string, unknown>[]
      expect(body).not.toHaveProperty('production_attempt_id')
      expect(body).not.toHaveProperty('auto_rating')
      expect(body).toMatchObject({ final_rating: 3, answer: CHECKED_SENTENCE })
    })

    it('a network error falls back the same way', async () => {
      const calls = session({ check: () => Promise.reject(new TypeError('Failed to fetch')) })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent('The AI check failed: Cannot reach the local server')
      await user.click(screen.getByRole('button', { name: /^3 Good/ }))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)[0]).not.toHaveProperty('production_attempt_id')
    })

    it('the French interface words the notice in French', async () => {
      await i18n.changeLanguage('fr')
      session({ check: unavailableCheck('unavailable', 'no_provider_configured') })
      const user = userEvent.setup()
      renderApp('/session')
      await screen.findByRole('heading', { name: 'Écrire une phrase' })
      await user.type(screen.getByLabelText('Votre phrase'), `${CHECKED_SENTENCE}{Enter}`)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent("La vérification par l'IA n'est pas disponible")
    })

    it('an empty sentence is never sent to the AI (the self-graded path of M4.c)', async () => {
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await screen.findByRole('heading', { name: 'Write a sentence' })
      await user.type(screen.getByLabelText('Your sentence'), '{Enter}')
      await screen.findByRole('region', { name: 'Correction' })
      expect(callsTo(calls, 'POST', '/reviews/check-production')).toHaveLength(0)
      expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(1)
    })

    it('a refusal such as exercise_mismatch offers to retry the card', async () => {
      session({ check: () => apiErrorResponse(422, 'exercise_mismatch') })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
      expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
    })
  })

  describe('while the AI is reading the sentence', () => {
    it('offers "Skip the check" after 5 seconds, then goes on self-graded and ignores the late answer', async () => {
      vi.useFakeTimers({
        shouldAdvanceTime: true,
        toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'],
      })
      const wait = deferred()
      const calls = session({ check: () => wait.promise })
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      renderApp('/session')
      await sendSentence(user)
      expect(await screen.findByText('Checking your sentence… 0 s')).toBeInTheDocument()
      expect(screen.getByLabelText('Your sentence')).toHaveAttribute('readonly')
      expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4_000)
      })
      expect(screen.queryByRole('button', { name: 'Skip the check and rate myself' })).toBeNull()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_500)
      })
      const skip = await screen.findByRole('button', { name: 'Skip the check and rate myself' })
      expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(0)

      await user.click(skip)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent('Check skipped. Rate your sentence yourself.')
      expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(1)
      expect(screen.queryByRole('button', { name: 'Skip the check and rate myself' })).toBeNull()

      // The AI answers after all: nothing changes, the sentence is rated without it.
      await act(async () => wait.answer(Response.json(checkAnswer())))
      expect(screen.queryByText('Suggested')).toBeNull()
      expect(result.querySelectorAll('mark')).toHaveLength(0)
      await user.click(screen.getByRole('button', { name: /^3 Good/ }))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)[0]).not.toHaveProperty('production_attempt_id')
    })

    it('ignores the keyboard shortcuts and a second submission', async () => {
      const wait = deferred()
      const calls = session({ check: () => wait.promise })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      await screen.findByText(/^Checking your sentence… \d+ s$/)

      // Keys pressed outside a field: the rating and accept shortcuts must not be armed.
      for (const key of ['1', '3', 'Enter', ' ', 'r']) fireEvent.keyDown(document.body, { key })
      await user.click(screen.getByRole('button', { name: 'Checking…' }))
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
      expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(0)
      expect(callsTo(calls, 'POST', '/reviews/check-production')).toHaveLength(1)

      await act(async () => wait.answer(Response.json(checkAnswer({ proposed_rating: 3 }))))
      await screen.findByRole('region', { name: 'Correction' })
      // The same key now rates: the shortcuts were off only while waiting.
      fireEvent.keyDown(document.body, { key: '3' })
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(1)
    })
  })

  describe('when the server does not recognise the checked sentence', () => {
    it('sends the rating once more, without production_attempt_id, and says so discreetly', async () => {
      let attempts = 0
      const calls = session({
        record: () => {
          attempts += 1
          return attempts === 1
            ? apiErrorResponse(409, 'production_mismatch')
            : Response.json(recordAnswer())
        },
      })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      await screen.findByRole('region', { name: 'Correction' })
      await user.click(screen.getByRole('button', { name: /^3 Good/ }))

      await waitFor(() => expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(2))
      const [first, second] = recordBodies(calls) as Record<string, unknown>[]
      expect(first).toHaveProperty('production_attempt_id', 77)
      expect(second).not.toHaveProperty('production_attempt_id')
      expect(second).toMatchObject({ final_rating: 3, answer: CHECKED_SENTENCE })
    })

    it('never sends a third time', async () => {
      const calls = session({ record: () => apiErrorResponse(409, 'production_mismatch') })
      const user = userEvent.setup()
      renderApp('/session')
      await sendSentence(user)
      await screen.findByRole('region', { name: 'Correction' })
      await user.click(screen.getByRole('button', { name: /^3 Good/ }))
      await waitFor(() => expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(2))
      // The second refusal is shown like any other rating error, and the user may rate again.
      expect(await screen.findByRole('alert')).toHaveTextContent('could not be linked to this card')
      expect(screen.getByRole('button', { name: /^3 Good/ })).toBeEnabled()
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(2)
    })
  })
})

describe('Review player: an error logged for a lexical confusion', () => {
  it('announces "Added to your error log" with a link to /errors/{id}', async () => {
    let recorded = false
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7)),
      'GET /session/7/next': () => Response.json(recorded ? reviewOf(otherCard) : reviewOf(production)),
      'POST /reviews/check-production': () => Response.json(unavailableCheck()),
      'POST /reviews/grade': () => Response.json(gradeAnswer({ warnings: [] })),
      'POST /reviews': () => {
        recorded = true
        return Response.json(recordAnswer({ error_event_id: 42 }))
      },
    })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    await screen.findByRole('region', { name: 'Correction' })
    await user.click(screen.getByRole('button', { name: /^3 Good/ }))

    const status = await screen.findByText(/Added to your error log/)
    expect(status.closest('[role="status"]')).not.toBeNull()
    expect(within(status.closest('p') as HTMLElement).getByRole('link', { name: 'See the error' })).toHaveAttribute(
      'href',
      '/errors/42',
    )
  })

  it('says nothing about the error log when there is none', async () => {
    let recorded = false
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7)),
      'GET /session/7/next': () => Response.json(recorded ? reviewOf(otherCard) : reviewOf(production)),
      'POST /reviews/check-production': () => Response.json(unavailableCheck()),
      'POST /reviews/grade': () => Response.json(gradeAnswer({ warnings: [] })),
      'POST /reviews': () => {
        recorded = true
        return Response.json(recordAnswer())
      },
    })
    const user = userEvent.setup()
    renderApp('/session')
    await sendSentence(user)
    await screen.findByRole('region', { name: 'Correction' })
    await user.click(screen.getByRole('button', { name: /^3 Good/ }))
    await screen.findByText(/Saved: the previous card comes back/)
    expect(screen.queryByText(/Added to your error log/)).toBeNull()
  })
})
