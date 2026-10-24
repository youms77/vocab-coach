import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ReviewAnswerOut } from '../../api/speech'
import type { ReviewStep, SessionSummary, Step } from '../../api/session'
import i18n from '../../i18n'
import {
  plan,
  progress,
  recordAnswer,
  type ReviewCase,
  reviewCases,
  studySession,
} from '../../test/fixtures'
import { installFakeRecorder, OPUS, recordTake, type RecorderKit } from '../../test/fakeRecorder'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import {
  HEARD_ANSWER,
  reviewAnswerOut,
  SPOKEN_EXAMPLE,
  untranscribedAnswer,
} from '../../test/speechFixtures'

// The oral answer in the review player (M6.b2.2, D-206, D-207): the recorder driven by Space and
// Enter, `POST /speech/review-answer`, the way out after 5 s and the self-graded fallback.

const spokenCase = reviewCases.find((r) => r.name === 'spoken_answer') as ReviewCase
const spokenCard: ReviewStep = spokenCase.step
const EXAMPLE = SPOKEN_EXAMPLE

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

type Answer = ReviewAnswerOut | (() => Response | Promise<Response>)

interface Script {
  answer?: Answer
  record?: () => Response
}

function session({ answer, record }: Script = {}) {
  let recorded = false
  return mockApi({
    ...base,
    'POST /session/start': () => Response.json(studySession(7)),
    'GET /session/7/next': () => Response.json(recorded ? done : reviewOf(spokenCard)),
    'POST /speech/review-answer': () =>
      typeof answer === 'function' ? answer() : Response.json(answer ?? reviewAnswerOut()),
    'POST /reviews/reveal': () => Response.json(spokenCase.reveal),
    'POST /reviews': () => {
      if (record !== undefined) return record()
      recorded = true
      return Response.json(recordAnswer())
    },
  })
}

const callsTo = (calls: RecordedCall[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path.split('?')[0] === path)
const uploads = (calls: RecordedCall[]) => callsTo(calls, 'POST', '/speech/review-answer')
const reveals = (calls: RecordedCall[]) => callsTo(calls, 'POST', '/reviews/reveal')
const recordBodies = (calls: RecordedCall[]) =>
  callsTo(calls, 'POST', '/reviews').map((c) => c.body as Record<string, unknown>)

/** A request that stays open until the test answers it. */
function deferred() {
  let answer: (response: Response) => void = () => {}
  const promise = new Promise<Response>((resolve) => {
    answer = resolve
  })
  return { promise, answer }
}

const space = () => fireEvent.keyDown(document.body, { key: ' ', code: 'Space' })
const enter = () => fireEvent.keyDown(document.body, { key: 'Enter', code: 'Enter' })

async function openCard() {
  await screen.findByRole('heading', { name: 'Answer aloud' })
}

/** Records with the page's own buttons and clicks "Send". */
async function recordAndSend(user: ReturnType<typeof userEvent.setup>, kit: RecorderKit, ms = 2000) {
  await recordTake(user, kit, { ms })
  await user.click(screen.getByRole('button', { name: 'Send' }))
}

const allTracksStopped = (kit: RecorderKit) =>
  kit.streams.length > 0 && kit.streams.every((s) => s.tracks.every((track) => track.stopped))

const ratingButton = (name: RegExp) => screen.getByRole('button', { name })

afterEach(() => {
  vi.useRealTimers()
})

describe('Review player: a spoken answer', () => {
  it('records, sends the exact request, then rates with the checked answer and no auto_rating', async () => {
    const kit = installFakeRecorder()
    const calls = session()
    const user = userEvent.setup()
    renderApp('/session')
    await openCard()

    await recordAndSend(user, kit)
    const result = await screen.findByRole('region', { name: 'Correction' })
    await waitFor(() => expect(result).toHaveFocus())

    expect(uploads(calls)).toHaveLength(1)
    const [upload] = uploads(calls)
    const query = new URLSearchParams(upload.path.split('?')[1])
    expect(Object.fromEntries(query)).toEqual({
      card_id: '21',
      session_id: '7',
      exercise_template_id: '34',
      duration_s: '2',
      response_time_ms: '2000',
    })
    expect(upload.headers['content-type']).toBe(OPUS)
    expect(upload.body).toBeInstanceOf(Blob)
    expect((upload.body as Blob).type).toBe(OPUS)
    // The solution comes with the answer: neither `grade` nor `reveal` is asked.
    expect(reveals(calls)).toHaveLength(0)
    expect(callsTo(calls, 'POST', '/reviews/grade')).toHaveLength(0)

    await user.click(
      within(screen.getByRole('group', { name: 'How well did you remember?' })).getByRole('button', {
        name: /^3 Good/,
      }),
    )
    await screen.findByRole('heading', { name: 'Session summary' })
    const [body] = recordBodies(calls)
    expect(body).toEqual({
      card_id: 21,
      session_id: 7,
      exercise_type: 'spoken_answer',
      exercise_template_id: 34,
      answer: null,
      choice_index: null,
      response_time_ms: 2000,
      final_rating: 3,
      expected_reps: 4,
      production_attempt_id: 88,
    })
    expect(body).not.toHaveProperty('auto_rating')
    // The same response time went to `review-answer` and to the rating (D-121).
    expect(body.response_time_ms).toBe(Number(query.get('response_time_ms')))
  })

  it('shows nothing of the solution before the answer, in every phase (active recall)', async () => {
    const kit = installFakeRecorder()
    const wait = deferred()
    session({ answer: () => wait.promise })
    const user = userEvent.setup()
    renderApp('/session')
    await openCard()
    const noLeak = () => {
      for (const secret of [...spokenCase.secrets, EXAMPLE, 'find the cause']) {
        expect(document.body.innerHTML).not.toContain(secret)
      }
      expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
    }

    // answering
    noLeak()
    expect(screen.getByText('How would you explore an unexpected result?')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /example/i })).toBeNull()
    // capturing
    await user.click(screen.getByRole('button', { name: 'Start recording' }))
    await screen.findByRole('button', { name: 'Stop recording' })
    noLeak()
    // captured
    kit.advance(2000)
    await user.click(screen.getByRole('button', { name: 'Stop recording' }))
    act(() => kit.recorder()?.finish())
    await screen.findByRole('button', { name: 'Send' })
    noLeak()
    // checking_spoken
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/^Checking your answer… \d+ s$/)).toBeInTheDocument()
    noLeak()

    await act(async () => wait.answer(Response.json(reviewAnswerOut())))
    const result = await screen.findByRole('region', { name: 'Correction' })
    expect(result).toHaveTextContent(EXAMPLE)
  })

  it('says what was heard, corrects it compactly and presents the example as one possibility', async () => {
    const kit = installFakeRecorder()
    session()
    const user = userEvent.setup()
    renderApp('/session')
    await openCard()
    await recordAndSend(user, kit)

    const result = await screen.findByRole('region', { name: 'Correction' })
    expect(within(result).getByRole('heading', { name: 'What the speech recognition heard' })).toBeInTheDocument()
    const marked = Array.from(result.querySelectorAll('mark'))
    expect(marked).toHaveLength(1)
    expect(marked[0].firstChild?.textContent).toBe('drill down in')
    // The mark's number sits inside the text: the heard words are there, around the mark.
    expect(result).toHaveTextContent(/I would drill down in.*the data to find the cause./)
    expect(within(result).getByText('"Drill down" takes "into".')).toBeInTheDocument()
    // Compact: no natural version, no structure, no copy button.
    expect(within(result).queryByRole('button', { name: 'Copy' })).toBeNull()
    expect(within(result).queryByRole('heading', { name: 'Structure' })).toBeNull()
    expect(result).toHaveTextContent('Example answer (one possibility among others):')
    expect(result).toHaveTextContent(EXAMPLE)
    expect(within(result).getByRole('link', { name: /full usage sheet/i })).toBeInTheDocument()
  })

  it('shows the 90-second sentence under Send and while waiting, and says the wait once', async () => {
    const kit = installFakeRecorder()
    const wait = deferred()
    session({ answer: () => wait.promise })
    const user = userEvent.setup()
    renderApp('/session')
    await openCard()
    await recordTake(user, kit)
    expect(screen.getByText(/Two AI steps check your answer.*up to about 90 seconds/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText(/^Checking your answer… \d+ s$/)
    expect(screen.getByText(/Two AI steps check your answer.*up to about 90 seconds/)).toBeInTheDocument()
    // The counter is hidden from screen readers; the polite status is said once, without the seconds.
    const statuses = screen.getAllByRole('status').filter((el) => el.textContent === 'Checking your answer…')
    expect(statuses).toHaveLength(1)
    // The recorder is gone while waiting: nothing can be sent twice.
    expect(screen.queryByRole('button', { name: 'Send' })).toBeNull()
    await act(async () => wait.answer(Response.json(reviewAnswerOut())))
  })

  describe('the suggested rating', () => {
    it('Again (1) is marked Suggested and Enter accepts it', async () => {
      const kit = installFakeRecorder()
      const calls = session({ answer: reviewAnswerOut({ proposed_rating: 1 }) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByRole('region', { name: 'Correction' })
      expect(ratingButton(/^1 Again/)).toHaveTextContent('Suggested')
      expect(ratingButton(/^3 Good/)).not.toHaveTextContent('Suggested')
      enter()
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)).toMatchObject([{ final_rating: 1, production_attempt_id: 88 }])
    })

    it('Good (3) is marked Suggested', async () => {
      const kit = installFakeRecorder()
      const calls = session({ answer: reviewAnswerOut({ proposed_rating: 3, errors: [] }) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByRole('region', { name: 'Correction' })
      expect(ratingButton(/^3 Good/)).toHaveTextContent('Suggested')
      expect(screen.getAllByText('Suggested')).toHaveLength(1)
      enter()
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls)
      expect(body).toMatchObject({ final_rating: 3, production_attempt_id: 88 })
      expect(body).not.toHaveProperty('auto_rating')
    })

    it('no proposed rating gives four buttons without a suggestion, and Enter accepts nothing', async () => {
      const kit = installFakeRecorder()
      const calls = session({ answer: reviewAnswerOut({ proposed_rating: null }) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(screen.queryByText('Suggested')).toBeNull()
      expect(screen.getAllByRole('button', { name: /^[1-4] / })).toHaveLength(4)
      expect(result).toHaveTextContent('Compare with your own answer, then rate yourself.')
      enter()
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
      await user.click(ratingButton(/^2 Hard/))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)).toMatchObject([{ final_rating: 2, production_attempt_id: 88 }])
    })

    it('term_not_heard is translated and leaves the rating to the user', async () => {
      const kit = installFakeRecorder()
      session({ answer: reviewAnswerOut({ warnings: ['term_not_heard'], proposed_rating: null }) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent('The term was not heard: you may have forgotten it, or the speech recognition missed it.')
      expect(result).not.toHaveTextContent('term_not_heard')
      expect(screen.queryByText('Suggested')).toBeNull()
    })
  })

  describe('when the recording could not be understood', () => {
    it.each([
      ['unavailable', untranscribedAnswer(), /could not be transcribed: the free quota is used up/],
      [
        'silent',
        untranscribedAnswer({ status: 'silence', text: null, reason: null }),
        /No speech was heard in your recording/,
      ],
    ])('%s: says so, shows the example, and keeps the production for the rating', async (_name, answer, message) => {
      const kit = installFakeRecorder()
      const calls = session({ answer })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent(message)
      expect(result).toHaveTextContent(EXAMPLE)
      expect(screen.queryByText('Suggested')).toBeNull()
      // No further request: the solution is in the answer already.
      expect(reveals(calls)).toHaveLength(0)

      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls)
      expect(body).toMatchObject({ final_rating: 3, production_attempt_id: 88 })
      expect(body).not.toHaveProperty('auto_rating')
    })

    it('a failed correction still shows what was heard, says why, and keeps the production', async () => {
      const kit = installFakeRecorder()
      const calls = session({
        answer: reviewAnswerOut({
          status: 'unavailable',
          reason: 'quota',
          feedback: null,
          errors: [],
          proposed_rating: null,
        }),
      })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent(HEARD_ANSWER)
      expect(result).toHaveTextContent('The correction is not available: the free quota is used up')
      expect(result).toHaveTextContent(EXAMPLE)
      expect(screen.queryByText('Suggested')).toBeNull()
      await user.click(ratingButton(/^2 Hard/))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)[0]).toHaveProperty('production_attempt_id', 88)
    })
  })

  describe('when the server refuses the recording', () => {
    it.each([
      ['audio_too_short', 422],
      ['audio_too_long', 422],
      ['audio_empty', 422],
      ['unsupported_audio', 415],
      ['audio_too_large', 413],
    ])('%s: back to the take, which can be sent again', async (code, status) => {
      const kit = installFakeRecorder()
      let attempts = 0
      const calls = session({
        answer: () => {
          attempts += 1
          return attempts === 1
            ? apiErrorResponse(status, code, code, { min_s: 1, max_s: 90, max_bytes: 10 * 1024 * 1024 })
            : Response.json(reviewAnswerOut())
        },
      })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)

      expect(await screen.findByRole('alert')).toBeInTheDocument()
      const send = await screen.findByRole('button', { name: 'Send' })
      expect(screen.getByRole('button', { name: 'Record again' })).toBeInTheDocument()
      // The same take is still there, nothing was revealed or recorded.
      expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
      expect(reveals(calls)).toHaveLength(0)
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
      expect(kit.createdUrls).toHaveLength(1)

      await user.click(send)
      await screen.findByRole('region', { name: 'Correction' })
      expect(uploads(calls)).toHaveLength(2)
    })

    it('a take that is too short cannot be sent, by button or by Enter', async () => {
      const kit = installFakeRecorder()
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordTake(user, kit, { ms: 300 })
      expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
      expect(screen.getByRole('alert')).toHaveTextContent('too short')
      enter()
      expect(uploads(calls)).toHaveLength(0)
    })

    it.each([
      ['not_due', 409, 'Continue the session'],
      ['review_not_allowed', 409, 'Continue the session'],
      ['exercise_mismatch', 422, 'Retry'],
    ])('%s is handled as for grade, without a fallback', async (code, status, button) => {
      const kit = installFakeRecorder()
      const calls = session({ answer: () => apiErrorResponse(status, code) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      expect(await screen.findByRole('button', { name: button })).toBeInTheDocument()
      expect(reveals(calls)).toHaveLength(0)
      expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
      expect(allTracksStopped(kit)).toBe(true)
    })

    it.each(['session_closed', 'session_not_found'])('%s goes to the session page', async (code) => {
      const kit = installFakeRecorder()
      const calls = session({ answer: () => apiErrorResponse(code === 'session_closed' ? 409 : 404, code) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await waitFor(() => expect(screen.queryByRole('heading', { name: 'Answer aloud' })).toBeNull())
      expect(reveals(calls)).toHaveLength(0)
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
    })
  })

  describe('the self-graded fallback', () => {
    it('a network error falls back to reveal, says so, and rates without the production', async () => {
      const kit = installFakeRecorder()
      const calls = session({ answer: () => Promise.reject(new TypeError('Failed to fetch')) })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent('The check failed: Cannot reach the local server')
      expect(result).toHaveTextContent(EXAMPLE)
      expect(reveals(calls)).toHaveLength(1)
      expect(reveals(calls)[0].body).toEqual({
        card_id: 21,
        exercise_type: 'spoken_answer',
        exercise_template_id: 34,
      })
      expect(screen.getAllByRole('button', { name: /^[1-4] / })).toHaveLength(4)
      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls)
      expect(body).not.toHaveProperty('production_attempt_id')
      expect(body).not.toHaveProperty('auto_rating')
      expect(body).toMatchObject({ final_rating: 3, answer: null })
    })

    it('an unexpected server error falls back the same way', async () => {
      const kit = installFakeRecorder()
      const calls = session({ answer: () => apiErrorResponse(500, 'internal_error') })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByRole('region', { name: 'Correction' })
      expect(reveals(calls)).toHaveLength(1)
      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)[0]).not.toHaveProperty('production_attempt_id')
    })

    it('"Answer without recording" is always there, whatever the phase, and reveals without a production', async () => {
      const kit = installFakeRecorder()
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      const decline = () => screen.getByRole('button', { name: 'Answer without recording' })
      expect(decline()).not.toHaveClass('button--primary')
      await user.click(screen.getByRole('button', { name: 'Start recording' }))
      await screen.findByRole('button', { name: 'Stop recording' })
      expect(decline()).toBeEnabled()
      kit.advance(2000)
      await user.click(screen.getByRole('button', { name: 'Stop recording' }))
      act(() => kit.recorder()?.finish())
      await screen.findByRole('button', { name: 'Send' })
      expect(decline()).toBeEnabled()

      await user.click(decline())
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent(EXAMPLE)
      expect(uploads(calls)).toHaveLength(0)
      expect(reveals(calls)).toHaveLength(1)
      // The microphone is off, the clip is thrown away.
      expect(allTracksStopped(kit)).toBe(true)
      expect(kit.revokedUrls).toEqual(kit.createdUrls)
      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls)
      expect(body).not.toHaveProperty('production_attempt_id')
      // The answer time is the end of the recording.
      expect(body.response_time_ms).toBe(2000)
    })

    it('a refused microphone says so and makes "Answer without recording" the main button', async () => {
      const kit = installFakeRecorder()
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      kit.refuseNext('NotAllowedError')
      await user.click(screen.getByRole('button', { name: 'Start recording' }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Access to the microphone was refused.')
      const decline = screen.getByRole('button', { name: 'Answer without recording' })
      expect(decline).toHaveClass('button--primary')
      // Not stuck in "capturing": the keys and the button start a new try.
      expect(screen.getByRole('button', { name: 'Start recording' })).toBeEnabled()

      await user.click(decline)
      await screen.findByRole('region', { name: 'Correction' })
      expect(reveals(calls)).toHaveLength(1)
      expect(uploads(calls)).toHaveLength(0)
      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      expect(recordBodies(calls)[0]).not.toHaveProperty('production_attempt_id')
    })

    it('a browser that cannot record offers only the self-graded way', async () => {
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      expect(screen.getByRole('alert')).toHaveTextContent('This browser cannot record sound')
      expect(screen.getByRole('button', { name: 'Start recording' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Answer without recording' })).toHaveClass('button--primary')
      // No key starts anything, and the hint does not promise one.
      space()
      expect(screen.queryByRole('button', { name: 'Stop recording' })).toBeNull()
      expect(screen.queryByText('start recording')).toBeNull()
      await user.click(screen.getByRole('button', { name: 'Answer without recording' }))
      await screen.findByRole('region', { name: 'Correction' })
      expect(reveals(calls)).toHaveLength(1)
    })

    it('a card without a template has no recorder, only "Answer without recording"', async () => {
      installFakeRecorder()
      mockApi({
        ...base,
        'POST /session/start': () => Response.json(studySession(7)),
        'GET /session/7/next': () => Response.json(reviewOf({ ...spokenCard, exercise_template_id: null })),
        'POST /reviews/reveal': () => Response.json(spokenCase.reveal),
      })
      renderApp('/session')
      await openCard()
      expect(screen.queryByRole('button', { name: 'Start recording' })).toBeNull()
      expect(screen.getByRole('button', { name: 'Answer without recording' })).toBeInTheDocument()
    })
  })

  describe('while the AI is working', () => {
    function fakeTimers() {
      vi.useFakeTimers({
        shouldAdvanceTime: true,
        toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'],
      })
    }

    it('offers "Skip the check" after 5 s, falls back to reveal and refuses the late answer', async () => {
      fakeTimers()
      const kit = installFakeRecorder()
      const wait = deferred()
      const calls = session({ answer: () => wait.promise })
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      expect(await screen.findByText('Checking your answer… 0 s')).toBeInTheDocument()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4_000)
      })
      expect(screen.queryByRole('button', { name: 'Skip the check and rate myself' })).toBeNull()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_500)
      })
      const skip = await screen.findByRole('button', { name: 'Skip the check and rate myself' })
      expect(reveals(calls)).toHaveLength(0)

      await user.click(skip)
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent('Check skipped. Rate your answer yourself.')
      expect(reveals(calls)).toHaveLength(1)
      expect(screen.queryByRole('button', { name: 'Skip the check and rate myself' })).toBeNull()

      // The AI answers after all: nothing changes, the answer is rated without it.
      await act(async () => wait.answer(Response.json(reviewAnswerOut())))
      expect(screen.queryByText('Suggested')).toBeNull()
      expect(result).not.toHaveTextContent(HEARD_ANSWER)
      expect(result.querySelectorAll('mark')).toHaveLength(0)
      await user.click(ratingButton(/^3 Good/))
      await screen.findByRole('heading', { name: 'Session summary' })
      const [body] = recordBodies(calls)
      expect(body).not.toHaveProperty('production_attempt_id')
      expect(body).toMatchObject({ final_rating: 3, answer: null })
    })

    it('ignores the keys, and a second Skip, while waiting', async () => {
      const kit = installFakeRecorder()
      const wait = deferred()
      const calls = session({ answer: () => wait.promise })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByText(/^Checking your answer… \d+ s$/)

      for (const key of ['1', '3', 'Enter', ' ', 'r']) fireEvent.keyDown(document.body, { key })
      expect(uploads(calls)).toHaveLength(1)
      expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(0)
      expect(reveals(calls)).toHaveLength(0)
      expect(kit.getUserMedia).toHaveBeenCalledTimes(1)
      await act(async () => wait.answer(Response.json(reviewAnswerOut({ proposed_rating: 3 }))))
      await screen.findByRole('region', { name: 'Correction' })
      // The same key now rates: the shortcuts were off only while waiting.
      fireEvent.keyDown(document.body, { key: '3' })
      await screen.findByRole('heading', { name: 'Session summary' })
    })
  })

  describe('when the server does not recognise the answer', () => {
    it('sends the rating once more, without production_attempt_id', async () => {
      const kit = installFakeRecorder()
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
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByRole('region', { name: 'Correction' })
      await user.click(ratingButton(/^3 Good/))

      await waitFor(() => expect(callsTo(calls, 'POST', '/reviews')).toHaveLength(2))
      const [first, second] = recordBodies(calls)
      expect(first).toHaveProperty('production_attempt_id', 88)
      expect(second).not.toHaveProperty('production_attempt_id')
      expect(second).toMatchObject({ final_rating: 3 })
    })
  })

  describe('the keyboard', () => {
    it('Space starts and stops the take, Enter sends it; the hints follow the phase', async () => {
      const kit = installFakeRecorder()
      const calls = session()
      renderApp('/session')
      await openCard()
      const hints = () => document.querySelector('.key-hints')?.textContent ?? ''
      expect(hints()).toContain('Space start recording')
      expect(hints()).not.toContain('Enter')

      space()
      await screen.findByRole('button', { name: 'Stop recording' })
      expect(hints()).toContain('Space stop recording')
      // Enter does nothing while recording.
      enter()
      expect(uploads(calls)).toHaveLength(0)
      kit.advance(2000)
      space()
      act(() => kit.recorder()?.finish())
      await screen.findByRole('button', { name: 'Send' })
      expect(hints()).toContain('Enter send')
      expect(hints()).not.toContain('Space')
      // Space does nothing once the take is ready.
      space()
      expect(kit.getUserMedia).toHaveBeenCalledTimes(1)
      expect(uploads(calls)).toHaveLength(0)

      enter()
      await screen.findByRole('region', { name: 'Correction' })
      expect(uploads(calls)).toHaveLength(1)
      expect(hints()).toContain('1–4 rate')
    })

    it('a double Space opens the microphone once', async () => {
      const kit = installFakeRecorder()
      session()
      renderApp('/session')
      await openCard()
      act(() => {
        space()
        space()
      })
      await screen.findByRole('button', { name: 'Stop recording' })
      expect(kit.getUserMedia).toHaveBeenCalledTimes(1)
      expect(kit.streams).toHaveLength(1)
    })

    it('a double Enter sends one recording', async () => {
      const kit = installFakeRecorder()
      const wait = deferred()
      const calls = session({ answer: () => wait.promise })
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordTake(user, kit)
      act(() => {
        enter()
        enter()
      })
      await screen.findByText(/^Checking your answer… \d+ s$/)
      expect(uploads(calls)).toHaveLength(1)
      await act(async () => wait.answer(Response.json(reviewAnswerOut())))
      await screen.findByRole('region', { name: 'Correction' })
    })

    it('ignores modifiers, auto-repeat, a field and a focused button', async () => {
      const kit = installFakeRecorder()
      session()
      renderApp('/session')
      await openCard()
      fireEvent.keyDown(document.body, { key: ' ', code: 'Space', ctrlKey: true })
      fireEvent.keyDown(document.body, { key: ' ', code: 'Space', repeat: true })
      const input = document.createElement('input')
      document.body.append(input)
      fireEvent.keyDown(input, { key: ' ', code: 'Space' })
      input.remove()
      // A focused button is activated by the browser itself: the page must not act twice.
      fireEvent.keyDown(screen.getByRole('button', { name: 'Answer without recording' }), {
        key: ' ',
        code: 'Space',
      })
      expect(kit.getUserMedia).not.toHaveBeenCalled()
    })

    it('does not reveal the solution: Space and Enter never show an example', async () => {
      installFakeRecorder()
      const calls = session()
      renderApp('/session')
      await openCard()
      enter()
      expect(reveals(calls)).toHaveLength(0)
      expect(screen.queryByRole('region', { name: 'Correction' })).toBeNull()
      expect(document.body.innerHTML).not.toContain(EXAMPLE)
    })
  })

  describe('the microphone', () => {
    it('is released as soon as the take ends, whatever comes next', async () => {
      const kit = installFakeRecorder()
      session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordTake(user, kit)
      expect(allTracksStopped(kit)).toBe(true)
    })

    it('is released when the card goes away while recording', async () => {
      const kit = installFakeRecorder()
      session()
      const user = userEvent.setup()
      const { unmount } = renderApp('/session')
      await openCard()
      await user.click(screen.getByRole('button', { name: 'Start recording' }))
      await screen.findByRole('button', { name: 'Stop recording' })
      expect(allTracksStopped(kit)).toBe(false)
      unmount()
      expect(allTracksStopped(kit)).toBe(true)
      expect(kit.createdUrls).toEqual(kit.revokedUrls)
    })

    it('is released when the wait is given up', async () => {
      const kit = installFakeRecorder()
      const wait = deferred()
      session({ answer: () => wait.promise })
      const user = userEvent.setup()
      const { unmount } = renderApp('/session')
      await openCard()
      await recordAndSend(user, kit)
      await screen.findByText(/^Checking your answer… \d+ s$/)
      unmount()
      expect(allTracksStopped(kit)).toBe(true)
      wait.answer(Response.json(reviewAnswerOut()))
    })

    it('"Record again" throws the take away and goes back to the start', async () => {
      const kit = installFakeRecorder()
      const calls = session()
      const user = userEvent.setup()
      renderApp('/session')
      await openCard()
      await recordTake(user, kit)
      await user.click(screen.getByRole('button', { name: 'Record again' }))
      expect(screen.getByRole('button', { name: 'Start recording' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Send' })).toBeNull()
      expect(uploads(calls)).toHaveLength(0)
      // Space starts a new take: the machine went back to answering.
      space()
      await screen.findByRole('button', { name: 'Stop recording' })
      expect(kit.getUserMedia).toHaveBeenCalledTimes(2)
    })
  })

  describe('the French interface', () => {
    it('words the buttons, the wait and the notice in French', async () => {
      await i18n.changeLanguage('fr')
      const kit = installFakeRecorder()
      const wait = deferred()
      session({ answer: () => wait.promise })
      const user = userEvent.setup()
      renderApp('/session')
      await screen.findByRole('heading', { name: 'Répondre à voix haute' })
      expect(screen.getByRole('button', { name: 'Répondre sans enregistrer' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: "Démarrer l'enregistrement" }))
      await screen.findByRole('button', { name: "Arrêter l'enregistrement" })
      kit.advance(2000)
      await user.click(screen.getByRole('button', { name: "Arrêter l'enregistrement" }))
      act(() => kit.recorder()?.finish())
      await user.click(await screen.findByRole('button', { name: 'Envoyer' }))
      expect(await screen.findByText(/^Vérification de votre réponse… \d+ s$/)).toBeInTheDocument()
      expect(screen.getByText(/Deux étapes d'IA vérifient votre réponse/)).toBeInTheDocument()
      await act(async () =>
        wait.answer(Response.json(reviewAnswerOut({ warnings: ['term_not_heard'], proposed_rating: null }))),
      )
      const result = await screen.findByRole('region', { name: 'Correction' })
      expect(result).toHaveTextContent("Le terme n'a pas été entendu")
      expect(result).toHaveTextContent('Exemple de réponse (une possibilité parmi d\'autres)')
    })
  })
})
