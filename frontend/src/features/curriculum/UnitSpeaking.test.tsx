import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import {
  detail,
  LINE_1,
  scenarioRows,
  scenarioTrack,
  scenarioUnit,
} from '../../test/curriculumFixtures'
import { installFakeRecorder, recordTake, type RecorderKit } from '../../test/fakeRecorder'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp, renderAppInBrowser } from '../../test/renderApp'
import {
  shadowing,
  speakingCorrection,
  speakingOut,
  speech,
  speechOut,
  SPEECH,
} from '../../test/speechFixtures'
import { categoryTree, topics } from '../../test/writingFixtures'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const unitWithTakes = () =>
  scenarioUnit(
    { progress: 'in_progress' },
    {
      final_task: {
        prompt_en: 'Introduce yourself for one minute.',
        prompt_fr: 'Présentez-vous pendant une minute.',
        minutes: 1,
        formula_refs: [0, 2],
        target_item_ids: [],
        attempt_ids: [],
        corrected: false,
      },
    },
  )

function backend() {
  return mockApi({
    'GET /health': { status: 'ok', version: '0.1.0', demo: false },
    'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
    'GET /curriculum/units/21': () => Response.json(unitWithTakes()),
    'GET /curriculum/tracks/speaking_scenarios': () =>
      Response.json(detail(scenarioTrack(), scenarioRows(1), { total_units: 16 })),
    'GET /speaking/topics': topics(),
    'GET /error-categories': categoryTree(),
    'POST /speech/shadowing': () =>
      Response.json(speechOut({ comparison: null, transcription: { status: 'ok', text: LINE_1, reason: null } }), {
        status: 201,
      }),
    'GET /productions/7': () => Response.json(shadowing({ prompt_text: LINE_1 })),
    'POST /speech/speaking': () => Response.json(speakingOut(), { status: 201 }),
    'GET /productions/9': () => Response.json(speech()),
    'POST /productions/9/correct': () => Response.json(speakingCorrection()),
  })
}

const post = (calls: RecordedCall[], path: string) =>
  calls.filter((call) => call.method === 'POST' && call.path.split('?')[0] === path)

const queryOf = (call: RecordedCall) =>
  Object.fromEntries(new URL(call.path, 'http://127.0.0.1').searchParams)

async function send(user: ReturnType<typeof userEvent.setup>, kit: RecorderKit) {
  await recordTake(user, kit, { ms: 6000 })
  await user.click(screen.getByRole('button', { name: 'Send' }))
}

describe('Shadowing a line of a unit', () => {
  it('takes the line and the unit from the unit page, clears the state, sends unit_id and keeps ?unit=', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum/units/21')

    await user.click(await screen.findByRole('link', { name: 'Shadow this line, number 1' }))
    const field = await screen.findByLabelText('Sentence to repeat')
    expect(field).toHaveValue(LINE_1)
    // The sentence is the unit's: it cannot be edited.
    expect(field).toHaveAttribute('readonly')
    expect(screen.getByRole('link', { name: 'Back to the unit' })).toHaveAttribute(
      'href',
      '/curriculum/units/21',
    )
    // The state was read once and cleared.
    await waitFor(() => expect(router.state.location.state).toBeNull())

    await send(user, kit)
    expect(await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })).toBeInTheDocument()
    const sent = post(calls, '/speech/shadowing')
    expect(sent).toHaveLength(1)
    expect(queryOf(sent[0]!)).toEqual({
      target_text: LINE_1,
      duration_s: '6',
      origin: 'shadowing',
      unit_id: '21',
    })
    expect(router.state.location.pathname + router.state.location.search).toBe(
      '/speaking/shadowing/7?unit=21',
    )
    expect(router.state.historyAction).toBe('REPLACE')
    expect(screen.getByRole('link', { name: 'Back to the unit' })).toHaveAttribute(
      'href',
      '/curriculum/units/21',
    )
  })

  it('forgets the unit after a reload: the page is a free shadowing again and sends no unit_id', async () => {
    installFakeRecorder()
    backend()
    const { router } = renderAppInBrowser('/')
    await act(() =>
      router.navigate('/speaking/shadowing', { state: { target: LINE_1, unitId: 21 } }),
    )
    expect(await screen.findByLabelText('Sentence to repeat')).toHaveValue(LINE_1)
    // What a reload would read back from `history.state`: nothing.
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())
    expect(JSON.stringify(window.history.state)).not.toContain('unitId')
    expect(JSON.stringify(window.history.state)).not.toContain(LINE_1)
  })

  it('keeps ?unit= when the detail page clears its own state', async () => {
    backend()
    const { router } = renderApp({
      pathname: '/speaking/shadowing/7',
      search: '?unit=21',
      state: { unavailableReason: 'quota' },
    })
    await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })
    await waitFor(() => expect(router.state.location.state).toBeNull())
    expect(router.state.location.search).toBe('?unit=21')
    expect(screen.getByRole('link', { name: 'Back to the unit' })).toBeInTheDocument()
  })
})

describe('The final talk of a unit', () => {
  it('shows the unit prompt instead of the topics, sends unit_id without a prompt and goes to ?unit=', async () => {
    const kit = installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum/units/21')

    await user.click(await screen.findByRole('link', { name: 'Record my talk' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Free speaking' })).toBeInTheDocument()
    expect(await screen.findByText('Introduce yourself for one minute.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Use this subject' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the unit' })).toHaveAttribute(
      'href',
      '/curriculum/units/21',
    )
    await waitFor(() => expect(router.state.location.state).toBeNull())

    await send(user, kit)
    expect(await screen.findByRole('heading', { level: 1, name: 'Your speech and its correction' })).toBeInTheDocument()
    const sent = post(calls, '/speech/speaking')
    expect(sent).toHaveLength(1)
    expect(queryOf(sent[0]!)).toEqual({ duration_s: '6', unit_id: '21' })
    expect(router.state.location.pathname + router.state.location.search).toBe('/speaking/9?unit=21')
    // The correction ran once, by itself, and the unit page is read again on the way back.
    await waitFor(() => expect(post(calls, '/productions/9/correct')).toHaveLength(1))
    expect(screen.getByRole('link', { name: 'Back to the unit' })).toHaveAttribute(
      'href',
      '/curriculum/units/21',
    )
    await waitFor(() => expect(router.state.location.state).toBeNull())
    expect(router.state.location.search).toBe('?unit=21')
  })

  it('clears the unit from history.state at once, so a reload is free speaking again', async () => {
    backend()
    const { router } = renderAppInBrowser('/')
    await act(() => router.navigate('/speaking', { state: { unitId: 21 } }))
    expect(await screen.findByText('Introduce yourself for one minute.')).toBeInTheDocument()
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())

    // What a reload would read back from `history.state`: no unit, nothing to send.
    expect(JSON.stringify(window.history.state)).not.toContain('unitId')
  })
})

describe('A unit leaves nothing of the recordings in the browser', () => {
  it('writes no text to the storages, the URL or history.state, at any navigation', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech()
    backend()
    const user = userEvent.setup()
    window.localStorage.clear()
    window.sessionStorage.clear()
    const { router } = renderAppInBrowser('/curriculum/units/21')
    const seen: string[] = []
    router.subscribe(() => seen.push(JSON.stringify(window.history.state) + window.location.href))

    // Shadow a line, come back, record the talk.
    await user.click(await screen.findByRole('link', { name: 'Shadow this line, number 1' }))
    await screen.findByLabelText('Sentence to repeat')
    await send(user, kit)
    await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })
    await user.click(screen.getByRole('link', { name: 'Back to the unit' }))
    await user.click(await screen.findByRole('link', { name: 'Record my talk' }))
    await screen.findByText('Introduce yourself for one minute.')
    await send(user, kit)
    await screen.findByRole('heading', { level: 1, name: 'Your speech and its correction' })
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())

    const everything = [
      ...seen,
      JSON.stringify(window.history.state),
      JSON.stringify({ ...window.localStorage }),
      JSON.stringify({ ...window.sessionStorage }),
      window.location.href,
    ].join('\n')
    expect(seen.length).toBeGreaterThan(0)
    // The shadowed line travels in the router state, which is cleared on arrival: it is never in
    // the browser's history after it. Neither is a word of what was heard or transcribed.
    const states = seen.filter((entry) => entry.includes('"usr":{'))
    for (const entry of states) expect(entry).not.toContain(SPEECH.slice(0, 20))
    expect(everything).not.toContain(SPEECH.slice(0, 20))
    expect(JSON.stringify(window.history.state)).not.toContain(LINE_1)
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(LINE_1)
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(LINE_1)
  })
})
