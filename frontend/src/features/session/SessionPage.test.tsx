import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SessionSummary, Step } from '../../api/session'
import {
  plan,
  progress,
  recordAnswer,
  type ReviewCase,
  reviewCases,
  studySession,
} from '../../test/fixtures'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const summary: SessionSummary = {
  format: 'session-1',
  reviews: 4,
  failed_reviews: 1,
  discoveries_started: 1,
  discoveries_completed: 1,
  productions: 1,
  words: 9,
  duration_ms: 754_000,
  planned_minutes: 25,
}

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': {
    ai_off: false,
    degraded: false,
    demo: false,
    order: [],
    providers: [],
  },
  'GET /session/today': { plan: plan(), open_session: null },
  'GET /decks': [],
}

const step = (body: Partial<Step> & Pick<Step, 'type'>, sessionId = 7) =>
  ({ session_id: sessionId, progress: progress(), ...body }) as Step

const nextCalls = (calls: RecordedCall[], id = 7) =>
  calls.filter((c) => c.method === 'GET' && c.path.startsWith(`/session/${id}/next`))

afterEach(() => {
  vi.useRealTimers()
})

describe('Session page', () => {
  it('opens a new session (201) and walks wait → practice info → done → summary', async () => {
    const now = new Date('2026-10-17T10:00:00Z')
    vi.useFakeTimers({ shouldAdvanceTime: true, now })
    const until = new Date(now.getTime() + 4 * 60_000).toISOString()
    // The steps in order; the last one repeats.
    const queue = [
      step({ type: 'wait', wait: { until } }),
      step({
        type: 'practice_info',
        practice: {
          targeted_practice: {
            category_code: 'grammar.preposition',
            error_count: 5,
          },
          consolidation_task_id: null,
        },
      }),
    ]
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': (call) =>
        Response.json(
          call.path.includes('practice_seen=true')
            ? step({ type: 'done', progress: progress({ new_remaining: 0 }) })
            : queue.length > 1
              ? queue.shift()
              : queue[0],
        ),
      'POST /session/7/end': () =>
        Response.json(studySession(7, { ended_at: '2026-10-17T10:20:00Z', summary })),
    })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderApp('/session')

    const heading = await screen.findByRole('heading', { name: 'Short break' })
    expect(heading).toHaveFocus()
    expect(screen.getByText('Next card in 4 min.')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Session progress' })).toHaveTextContent(
      'New terms: 0 done, 1 left',
    )

    // At `until` (plus the one-second margin) the page asks again by itself.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4 * 60_000 + 1_000)
    })
    expect(await screen.findByRole('heading', { name: 'Also planned today' })).toBeInTheDocument()
    expect(
      screen.getByText(/grammar.preposition \(5 errors in the last 14 days\)/),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: 'Session complete' })).toBeInTheDocument()
    const summaryList = screen.getByRole('heading', {
      name: 'Session summary',
    }).nextElementSibling
    expect(summaryList).toHaveTextContent('Reviews4')
    expect(summaryList).toHaveTextContent('Discoveries completed1')
    expect(summaryList).toHaveTextContent('Time spent13 min')
    expect(summaryList).toHaveTextContent('Time planned25 min')
  })

  it('names the targeted category by its label, and by its code when the tree is unavailable', async () => {
    const practice = step({
      type: 'practice_info',
      practice: {
        targeted_practice: { category_code: 'grammar.preposition', error_count: 5 },
        consolidation_task_id: null,
      },
    })
    mockApi({
      ...base,
      'GET /error-categories': categoryTree(),
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': practice,
    })
    renderApp('/session')
    expect(
      await screen.findByText(/Prepositions \(5 errors in the last 14 days\)/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/grammar\.preposition/)).toBeNull()
  })

  it('falls back to the category code when the tree cannot be loaded', async () => {
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': step({
        type: 'practice_info',
        practice: {
          targeted_practice: { category_code: 'grammar.preposition', error_count: 5 },
          consolidation_task_id: null,
        },
      }),
    })
    renderApp('/session')
    expect(
      await screen.findByText(/grammar\.preposition \(5 errors in the last 14 days\)/),
    ).toBeInTheDocument()
  })

  it('sends practice_seen=true after the practice information, then ends the session once', async () => {
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': (call) =>
        Response.json(
          call.path.includes('practice_seen=true')
            ? step({ type: 'done' })
            : step({
                type: 'practice_info',
                practice: { targeted_practice: null, consolidation_task_id: 3 },
              }),
        ),
      'POST /session/7/end': () => Response.json(studySession(7, { summary })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    await screen.findByText(/A consolidation task/)
    expect(screen.getByText(/available in a later version/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByRole('heading', { name: 'Session summary' })

    expect(nextCalls(calls).map((c) => c.path)).toEqual([
      '/session/7/next',
      '/session/7/next?practice_seen=true',
    ])
    expect(calls.filter((c) => c.path === '/session/7/end')).toHaveLength(1)
  })

  it('resumes the open session (200) and walks several reviews → wait → done → summary', async () => {
    const now = new Date('2026-10-17T10:00:00Z')
    vi.useFakeTimers({ shouldAdvanceTime: true, now })
    const until = new Date(now.getTime() + 2 * 60_000).toISOString()
    const choice = reviewCases.find((c) => c.name === 'recognition_in_sentence') as ReviewCase
    const self = reviewCases.find((c) => c.name === 'self_assessment (receptive)') as ReviewCase
    const typed = reviewCases.find((c) => c.name === 'typed_recall') as ReviewCase
    // Each recorded review moves the session on; then a learning card makes it wait.
    const steps: Step[] = [
      step({ type: 'review', review: { ...typed.step, card_id: 1 } }, 9),
      step({ type: 'review', review: { ...choice.step, card_id: 2 } }, 9),
      step({ type: 'review', review: { ...self.step, card_id: 3 } }, 9),
      step({ type: 'wait', wait: { until } }, 9),
      step({ type: 'done' }, 9),
    ]
    let index = 0
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(9), { status: 200 }),
      'GET /session/9/next': () => {
        // The wait is over once its time has come.
        if (steps[index].type === 'wait' && Date.now() >= Date.parse(until)) index += 1
        return Response.json(steps[index])
      },
      'POST /reviews/grade': (call) =>
        Response.json((call.body as { card_id: number }).card_id === 1 ? typed.grade : choice.grade),
      'POST /reviews/reveal': () => Response.json(self.reveal),
      'POST /reviews': () => {
        index += 1
        return Response.json(recordAnswer())
      },
      'POST /session/9/end': () =>
        Response.json(studySession(9, { summary: { ...summary, reviews: 3 } })),
    })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderApp('/session')

    await screen.findByRole('heading', { name: 'Recall the English term' })
    await user.type(screen.getByRole('textbox'), 'drill down inot{Enter}')
    await screen.findByRole('group', { name: 'How well did you remember?' })
    await user.keyboard('3')
    await screen.findByRole('heading', { name: 'Recognise the term in a sentence' })
    expect(screen.getByText(/Saved: the previous card comes back/)).toBeInTheDocument()
    await user.keyboard('2')
    await screen.findByRole('region', { name: 'Correction' })
    await user.keyboard('3')
    await screen.findByRole('heading', { name: 'Do you remember?' })
    await user.keyboard(' ')
    await screen.findByRole('region', { name: 'Correction' })
    await user.keyboard('4')

    await screen.findByRole('heading', { name: 'Short break' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2 * 60_000 + 1_000)
    })
    const summaryList = (await screen.findByRole('heading', { name: 'Session summary' }))
      .nextElementSibling
    expect(summaryList).toHaveTextContent('Reviews3')
    expect(
      calls.filter((c) => c.method === 'POST' && c.path === '/reviews').map((c) => c.body),
    ).toMatchObject([
      { card_id: 1, final_rating: 3, answer: 'drill down inot' },
      { card_id: 2, final_rating: 3, choice_index: 1 },
      { card_id: 3, final_rating: 4 },
    ])
    expect(calls.filter((c) => c.path === '/session/9/end')).toHaveLength(1)
  })

  it('keeps "End the session" with its confirmation during a review', async () => {
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(9), { status: 200 }),
      'GET /session/9/next': () =>
        Response.json(step({ type: 'review', review: reviewCases[0].step }, 9)),
      'POST /session/9/end': () => Response.json(studySession(9, { summary })),
    })
    const user = userEvent.setup()
    renderApp('/session')
    await screen.findByRole('heading', { name: 'Recognise the term in a sentence' })
    await user.click(screen.getByRole('button', { name: 'End the session' }))
    expect(calls.some((c) => c.path === '/session/9/end')).toBe(false)
    expect(screen.getByRole('button', { name: 'Keep going' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Yes, end it' }))
    expect(await screen.findByRole('heading', { name: 'Session summary' })).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/session/9/end')).toHaveLength(1)
  })

  it('can always be ended from the header, and "Keep going" cancels', async () => {
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': () =>
        Response.json(step({ type: 'wait', wait: { until: '2099-01-01T00:00:00Z' } })),
      'POST /session/7/end': () => Response.json(studySession(7, { summary })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    await screen.findByRole('heading', { name: 'Short break' })
    await user.click(screen.getByRole('button', { name: 'End the session' }))
    await user.click(screen.getByRole('button', { name: 'Keep going' }))
    expect(screen.getByRole('heading', { name: 'Short break' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'End the session' }))
    await user.click(screen.getByRole('button', { name: 'Yes, end it' }))
    await screen.findByRole('heading', { name: 'Session summary' })
    expect(calls.filter((c) => c.path === '/session/7/end')).toHaveLength(1)
  })

  it('"Check now" asks for the next step again', async () => {
    const calls = mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': () =>
        Response.json(step({ type: 'wait', wait: { until: '2099-01-01T00:00:00Z' } })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    await screen.findByRole('heading', { name: 'Short break' })
    await user.click(screen.getByRole('button', { name: 'Check now' }))
    await waitFor(() => expect(nextCalls(calls)).toHaveLength(2))
  })

  it('offers a new session when this one is closed', async () => {
    let started = 0
    const calls = mockApi({
      ...base,
      'POST /session/start': () => {
        started += 1
        return Response.json(studySession(started === 1 ? 7 : 8), {
          status: 201,
        })
      },
      'GET /session/7/next': () => apiErrorResponse(409, 'session_closed'),
      'GET /session/8/next': () => Response.json(step({ type: 'done' }, 8)),
      'POST /session/8/end': () => Response.json(studySession(8, { summary })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    expect(
      await screen.findByRole('heading', {
        name: 'This session is already closed.',
      }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'End the session' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start a new session' }))

    await screen.findByRole('heading', { name: 'Session summary' })
    expect(calls.filter((c) => c.path === '/session/start')).toHaveLength(2)
  })

  it('goes back home when the session does not exist', async () => {
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': () => apiErrorResponse(404, 'session_not_found'),
    })
    renderApp('/session')

    expect(await screen.findByRole('heading', { level: 1, name: 'Welcome' })).toBeInTheDocument()
  })

  it('says when the local server cannot be reached, and retries', async () => {
    let attempts = 0
    mockApi({
      ...base,
      'POST /session/start': () => {
        attempts += 1
        if (attempts === 1) throw new TypeError('Failed to fetch')
        return Response.json(studySession(7), { status: 201 })
      },
      'GET /session/7/next': () =>
        Response.json(step({ type: 'wait', wait: { until: '2099-01-01T00:00:00Z' } })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    expect(await screen.findByText(/Cannot reach the local server/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { name: 'Short break' })).toBeInTheDocument()
  })

  it('stops speech when the user leaves the page', async () => {
    const fake = installFakeSpeech()
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': () =>
        Response.json(step({ type: 'wait', wait: { until: '2099-01-01T00:00:00Z' } })),
    })
    const user = userEvent.setup()
    renderApp('/session')

    await screen.findByRole('heading', { name: 'Short break' })
    const before = fake.cancelCount
    await user.click(screen.getByRole('link', { name: 'Home' }))
    await screen.findByRole('heading', { level: 1, name: 'Welcome' })
    expect(fake.cancelCount).toBeGreaterThan(before)
  })

  it('is translated into French', async () => {
    window.localStorage.setItem('vocab-coach.language', 'fr')
    mockApi({
      ...base,
      'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
      'GET /session/7/next': () =>
        Response.json(step({ type: 'wait', wait: { until: '2099-01-01T00:00:00Z' } })),
    })
    const { i18n } = await import('../../i18n').then((m) => ({
      i18n: m.default,
    }))
    await act(() => i18n.changeLanguage('fr'))
    renderApp('/session')

    expect(await screen.findByRole('heading', { name: 'Petite pause' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Terminer la séance' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vérifier maintenant' })).toBeInTheDocument()
  })
})
