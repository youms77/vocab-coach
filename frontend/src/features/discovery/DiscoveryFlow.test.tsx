import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CompleteResult, DiscoveryExercise, DiscoveryStart } from '../../api/discovery'
import type { GradeResult } from '../../api/reviews'
import type { SessionSummary, Step } from '../../api/session'
import { plan, progress, sheetVersion, studySession } from '../../test/fixtures'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { highlightTerm } from './highlight'

const SENTENCE = 'We account for regional fixed effects in all specifications.'
const DEFINITION = 'to consider something when you study a situation'

const started = (overrides: Partial<DiscoveryStart> = {}): DiscoveryStart => ({
  item_id: 20,
  term: 'account for',
  item_type: 'collocation',
  status: 'discovering',
  resumed: false,
  sentence: { text: SENTENCE, source: 'origin' },
  ...overrides,
})

const typedRecall: DiscoveryExercise = {
  exercise_type: 'typed_recall',
  exercise_template_id: 31,
  prompt: { cue_fr: 'tenir compte de', cue_definition: DEFINITION },
}
const gapFill: DiscoveryExercise = {
  exercise_type: 'gap_fill',
  exercise_template_id: 32,
  prompt: { sentence: 'We ___ regional fixed effects.' },
}

const graded = (overrides: Partial<GradeResult>): GradeResult => ({
  outcome: 'exact',
  proposed_rating: 3,
  expected: 'account for',
  accepted: [],
  diff: null,
  warnings: [],
  solution: { answer: 'account for', accepted: [] },
  sheet_summary: null,
  ...overrides,
})

const completed: CompleteResult = {
  item_id: 20,
  status: 'learning',
  cards: [
    { card_id: 41, direction: 'receptive', due: '2026-10-18T03:00:00Z' },
    { card_id: 42, direction: 'productive', due: '2026-10-18T03:00:00Z' },
  ],
  production_attempt_id: 5,
  warnings: ['term_missing'],
}

const summary: SessionSummary = {
  format: 'session-1',
  reviews: 0,
  failed_reviews: 0,
  discoveries_started: 1,
  discoveries_completed: 1,
  productions: 1,
  words: 3,
  duration_ms: 300_000,
  planned_minutes: 4,
}

const newItemStep: Step = {
  type: 'new_item',
  session_id: 7,
  progress: progress(),
  new_item: { item_id: 20, term: 'account for', deck_id: 3, resumed: false },
}
const doneStep: Step = {
  type: 'done',
  session_id: 7,
  progress: progress({ new_done: 1, new_remaining: 0 }),
}

/** The session around one discovery: `next` gives the new term until `complete` succeeded. */
function routes(overrides: Record<string, unknown> = {}) {
  let discovered = false
  return {
    'GET /health': { status: 'ok', version: '0.1.0', demo: false },
    'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
    'GET /session/today': { plan: plan(), open_session: null },
    'GET /decks': [],
    'GET /settings': {},
    'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
    'GET /session/7/next': () => Response.json(discovered ? doneStep : newItemStep),
    'POST /session/7/end': () => Response.json(studySession(7, { summary })),
    'POST /discovery/20/start': () => Response.json(started()),
    'GET /items/20/sheet': sheetVersion(),
    'GET /discovery/20/exercises': [typedRecall, gapFill],
    'POST /reviews/grade': (call: RecordedCall) => {
      const body = call.body as { exercise_type: string; answer: string | null }
      if (body.answer === null) return Response.json(graded({ outcome: 'empty', proposed_rating: 1 }))
      if (body.exercise_type === 'typed_recall') {
        return Response.json(
          graded({
            outcome: 'typo',
            proposed_rating: 2,
            accepted: ['accounts for'],
            diff: [
              { op: 'equal', given: 'ac', expected: 'ac' },
              { op: 'insert', given: '', expected: 'c' },
              { op: 'equal', given: 'ount for', expected: 'ount for' },
            ],
          }),
        )
      }
      return Response.json(graded({}))
    },
    'POST /discovery/20/complete': () => {
      discovered = true
      return Response.json(completed)
    },
    ...overrides,
  }
}

const sheetCalls = (calls: RecordedCall[]) => calls.filter((c) => c.path.startsWith('/items/20/sheet'))

describe('Discovery of a new term', () => {
  it('goes through the five steps, with active recall, and sends everything with complete', async () => {
    const fake = installFakeSpeech()
    const calls = mockApi(routes())
    const user = userEvent.setup()
    renderApp('/session')

    // 1. The sentence only: no sheet, no translation, no definition.
    const title = await screen.findByRole('heading', { name: '1. Read the sentence' })
    expect(title).toHaveFocus()
    expect(screen.getByText('account for', { selector: 'mark' })).toBeInTheDocument()
    expect(screen.getByText('Your original sentence')).toBeInTheDocument()
    expect(screen.queryByText(DEFINITION)).not.toBeInTheDocument()
    expect(screen.queryByText(/tenir compte/)).not.toBeInTheDocument()
    expect(calls.find((c) => c.path === '/discovery/20/start')?.body).toEqual({
      session_id: 7,
      deck_id: 3,
    })

    // "Listen" reads the sentence, not a definition.
    await user.click(screen.getByRole('button', { name: 'Listen to “the sentence”' }))
    expect(fake.spoken.at(-1)?.text).toBe(SENTENCE)

    // 2. The guess. The sheet is requested only after it.
    await user.type(screen.getByLabelText(/Your guess/), 'tenir compte')
    expect(sheetCalls(calls)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Show the sheet' }))

    // 3. The sheet, with the guess recalled, the pronunciation and audio.
    expect(await screen.findByRole('heading', { name: '3. The usage sheet' })).toBeInTheDocument()
    expect(screen.getByText('Your guess: “tenir compte”')).toBeInTheDocument()
    expect(await screen.findByText(DEFINITION)).toBeInTheDocument()
    expect(screen.getByText(/əˈkaʊnt fɔr/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Listen to “the term”' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Listen to “example 1”' })).toBeEnabled()
    expect(sheetCalls(calls)).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Go to the exercises' }))

    // 4a. Typed recall: folded sheet, no term in the heading, no solution before grade.
    expect(await screen.findByRole('heading', { name: 'Recall the English term' })).toBeInTheDocument()
    expect(screen.getByText('In French: tenir compte de')).toBeInTheDocument()
    expect(screen.queryByText(/Expected answer/)).not.toBeInTheDocument()
    expect(screen.queryByText(/account for/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show the sheet again' })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Your answer'), 'acount for{Enter}')
    expect(await screen.findByText('Almost: a small typo')).toBeInTheDocument()
    expect(screen.getByText('Expected answer: account for')).toBeInTheDocument()
    expect(screen.getByText('Also accepted: accounts for')).toBeInTheDocument()
    expect(screen.getByText(/compared with the expected one/)).toBeInTheDocument()
    const grade = calls.find((c) => c.path === '/reviews/grade')
    expect(grade?.body).toMatchObject({
      item_id: 20,
      exercise_type: 'typed_recall',
      exercise_template_id: 31,
      answer: 'acount for',
      choice_index: null,
    })
    expect(grade?.body).not.toHaveProperty('card_id')

    // The sheet can be reopened after the answer.
    await user.click(screen.getByRole('button', { name: 'Show the sheet again' }))
    expect(screen.getByText(DEFINITION)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next exercise' }))

    // 4a. Gap-fill, sheet folded again.
    expect(await screen.findByRole('heading', { name: 'Fill the gap' })).toBeInTheDocument()
    expect(screen.queryByText(DEFINITION)).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('The missing word or words'), 'account for')
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText('Correct')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    // 4b. Spoken repetition of the sentence.
    expect(await screen.findByRole('heading', { name: 'Say it aloud' })).toBeInTheDocument()
    expect(screen.getByText(/Recording your voice comes in a later version/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Listen slowly to “the sentence”' }))
    expect(fake.spoken.at(-1)?.text).toBe(SENTENCE)
    await user.click(screen.getByRole('button', { name: 'Done, I repeated it' }))

    // 4c. Personal sentence, then complete.
    await user.type(await screen.findByLabelText(/Write a sentence of your own/), 'I like statistics.')
    await user.click(screen.getByRole('button', { name: 'Finish the discovery' }))

    // 5. Into spaced repetition.
    expect(await screen.findByRole('heading', { name: '5. Into spaced repetition' })).toBeInTheDocument()
    expect(screen.getByText(/“account for” enters spaced repetition: first review on/)).toBeInTheDocument()
    expect(screen.getByText(/Your sentence does not contain the term; it is saved anyway/)).toBeInTheDocument()
    const complete = calls.find((c) => c.path === '/discovery/20/complete')
    expect(complete?.body).toEqual({
      session_id: 7,
      duration_ms: expect.any(Number),
      guess: 'tenir compte',
      exercise_results: [
        { exercise_type: 'typed_recall', outcome: 'typo' },
        { exercise_type: 'gap_fill', outcome: 'exact' },
      ],
      personal_sentence: 'I like statistics.',
    })

    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: 'Session summary' })).toBeInTheDocument()
    expect(screen.getByText('Discoveries completed').nextElementSibling).toHaveTextContent('1')
  }, 20_000) // a long walk: well above the default 5 s when the whole suite runs in parallel

  it('"I don\'t know" sends no guess; a missing exercise is skipped; an empty answer is graded', async () => {
    const calls = mockApi(routes({ 'GET /discovery/20/exercises': [gapFill] }))
    const user = userEvent.setup()
    renderApp('/session')

    await user.click(await screen.findByRole('button', { name: "I don't know" }))
    expect(await screen.findByText('You did not guess: read the sheet carefully.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Go to the exercises' }))

    // No typed recall: straight to the gap-fill, without a message.
    expect(await screen.findByRole('heading', { name: 'Fill the gap' })).toBeInTheDocument()
    expect(screen.getByText('Exercise 1 of 1')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Recall the English term' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText('No answer')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/reviews/grade')?.body).toMatchObject({ answer: null })
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    await user.click(await screen.findByRole('button', { name: 'Done, I repeated it' }))
    await user.click(await screen.findByRole('button', { name: 'Skip and finish' }))
    await screen.findByRole('heading', { name: '5. Into spaced repetition' })
    expect(calls.find((c) => c.path === '/discovery/20/complete')?.body).toMatchObject({
      guess: null,
      exercise_results: [{ exercise_type: 'gap_fill', outcome: 'empty' }],
      personal_sentence: null,
    })
  })

  it('goes straight to the repetition when the term has no exercise', async () => {
    const calls = mockApi(routes({ 'GET /discovery/20/exercises': [] }))
    const user = userEvent.setup()
    renderApp('/session')

    await user.click(await screen.findByRole('button', { name: "I don't know" }))
    await user.click(await screen.findByRole('button', { name: 'Go to the exercises' }))
    expect(await screen.findByRole('heading', { name: 'Say it aloud' })).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/reviews/grade')).toBe(false)
  })

  it('cannot send complete twice', async () => {
    let release: () => void = () => undefined
    const calls = mockApi(
      routes({
        'GET /discovery/20/exercises': [],
        'POST /discovery/20/complete': () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(Response.json(completed))
          }),
      }),
    )
    const user = userEvent.setup()
    renderApp('/session')

    await user.click(await screen.findByRole('button', { name: "I don't know" }))
    await user.click(await screen.findByRole('button', { name: 'Go to the exercises' }))
    await user.click(await screen.findByRole('button', { name: 'Done, I repeated it' }))
    const finish = await screen.findByRole('button', { name: 'Finish the discovery' })
    await user.click(finish)
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Skip and finish' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Saving…' }))
    release()
    await screen.findByRole('heading', { name: '5. Into spaced repetition' })
    expect(calls.filter((c) => c.path === '/discovery/20/complete')).toHaveLength(1)
  })

  it('mentions a resumed discovery, which starts again from the sentence', async () => {
    mockApi(routes({ 'POST /discovery/20/start': () => Response.json(started({ resumed: true })) }))
    renderApp('/session')

    expect(await screen.findByText(/it starts again from the sentence/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '1. Read the sentence' })).toBeInTheDocument()
  })

  it('shows the term alone when there is no sentence', async () => {
    mockApi(routes({ 'POST /discovery/20/start': () => Response.json(started({ sentence: null })) }))
    renderApp('/session')

    expect(await screen.findByText(/no sentence yet: here is the term alone/)).toBeInTheDocument()
    expect(screen.getByText('account for', { selector: 'mark' })).toBeInTheDocument()
  })

  it('links to the term page when the sheet is missing, then continues the session', async () => {
    const calls = mockApi(
      routes({ 'POST /discovery/20/start': () => apiErrorResponse(409, 'sheet_required') }),
    )
    const user = userEvent.setup()
    renderApp('/session')

    expect(await screen.findByText(/This term has no usable sheet yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Write the sheet of “account for”' })).toHaveAttribute(
      'href',
      '/library/items/20',
    )
    const before = calls.filter((c) => c.path.startsWith('/session/7/next')).length
    await user.click(screen.getByRole('button', { name: 'Continue the session' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.path.startsWith('/session/7/next')).length).toBe(before + 1),
    )
    expect(sheetCalls(calls)).toHaveLength(0)
  })

  it('moves on without a blocking message when the term was already discovered', async () => {
    let first = true
    mockApi(
      routes({
        'GET /session/7/next': () => {
          const body = first ? newItemStep : doneStep
          first = false
          return Response.json(body)
        },
        'POST /discovery/20/start': () => apiErrorResponse(409, 'already_discovered'),
      }),
    )
    renderApp('/session')

    expect(await screen.findByRole('heading', { name: 'Session summary' })).toBeInTheDocument()
    expect(screen.queryByText(/already discovered/)).not.toBeInTheDocument()
  })

  it('explains a discovery that is not allowed and lets the session go on', async () => {
    mockApi(
      routes({ 'POST /discovery/20/start': () => apiErrorResponse(409, 'discovery_not_allowed') }),
    )
    renderApp('/session')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/its deck is paused or done/)
    expect(screen.getByRole('button', { name: 'Continue the session' })).toBeInTheDocument()
  })

  it('is translated into French', async () => {
    mockApi(routes())
    const user = userEvent.setup()
    renderApp('/session')

    await screen.findByRole('heading', { name: '1. Read the sentence' })
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getByRole('heading', { name: '1. Lisez la phrase' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Je ne sais pas' })).toBeInTheDocument()
    expect(within(screen.getByRole('main')).getByText("Votre phrase d'origine")).toBeInTheDocument()
  })
})

describe('highlightTerm', () => {
  it('finds the term without case, and without a leading "to"', () => {
    expect(highlightTerm('Shed Light on it.', 'shed light on')).toEqual([
      { text: 'Shed Light on', match: true },
      { text: ' it.', match: false },
    ])
    expect(highlightTerm('We account for it.', 'to account for')[1]).toEqual({
      text: 'account for',
      match: true,
    })
    expect(highlightTerm('Nothing here.', 'outlier')).toEqual([{ text: 'Nothing here.', match: false }])
  })
})
