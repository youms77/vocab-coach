import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { CorrectionResult, Production } from '../../api/productions'
import type { SpeechOut } from '../../api/speech'
import i18n from '../../i18n'
import { routes } from '../../routes'
import { installFakeRecorder, OPUS, recordTake, type RecorderKit } from '../../test/fakeRecorder'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp, renderAppInBrowser } from '../../test/renderApp'
import {
  correctedSpeech,
  SPEECH,
  SPEECH_TOPIC,
  speakingCorrection,
  speakingOut,
  speech,
} from '../../test/speechFixtures'
import { shadowing } from '../../test/speechFixtures'
import {
  categoryTree,
  correctedProduction,
  production,
  topics,
} from '../../test/writingFixtures'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /speaking/topics': topics(),
  'GET /error-categories': categoryTree(),
}

interface Options {
  /** The stored production (id 9) before anything happens. */
  stored?: Production
  send?: () => Response | Promise<Response>
  /** What each POST /productions/9/correct answers, in order (the last one repeats). */
  corrections?: (CorrectionResult | (() => Response | Promise<Response>))[]
  /** What POST /productions/9/transcribe answers and stores. */
  transcribed?: Production
  transcribeAnswer?: SpeechOut
}

/** A backend with one free speech (id 9) that the pages can send, read, transcribe and correct. */
function backend({
  stored = speech(),
  send,
  corrections = [speakingCorrection()],
  transcribed = speech(),
  transcribeAnswer = speakingOut(),
}: Options = {}) {
  let current = stored
  let attempts = 0
  return mockApi({
    ...base,
    'POST /speech/speaking': send ?? (() => Response.json(speakingOut(), { status: 201 })),
    'GET /productions/9': () => Response.json(current),
    'POST /productions/9/transcribe': () => {
      current = transcribed
      return Response.json(transcribeAnswer)
    },
    'POST /productions/9/correct': () => {
      const next = corrections[Math.min(attempts, corrections.length - 1)]
      attempts += 1
      if (typeof next === 'function') return next()
      if (next.status === 'ok') current = next.attempt
      return Response.json(next)
    },
  })
}

const post = (calls: RecordedCall[], path: string) =>
  calls.filter((call) => call.method === 'POST' && call.path.split('?')[0] === path)

const queryOf = (call: RecordedCall) =>
  Object.fromEntries(new URL(call.path, 'http://127.0.0.1').searchParams)

const marks = () => Array.from(document.querySelectorAll('mark'))

async function sendTake(user: ReturnType<typeof userEvent.setup>, kit: RecorderKit, ms = 6000) {
  await recordTake(user, kit, { ms })
  await user.click(screen.getByRole('button', { name: 'Send' }))
}

describe('Free speaking: a new take', () => {
  it('sends the exact request, then corrects once at /speaking/9 (history replaced)', async () => {
    const kit = installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/speaking')

    expect(await screen.findByRole('heading', { level: 1, name: 'Free speaking' })).toHaveFocus()
    expect(screen.getByText(/sent to Groq for transcription; it stays in your data folder/)).toBeInTheDocument()
    expect(screen.getByText(/Aim for 1 to 2 minutes/)).toBeInTheDocument()
    const first = await screen.findByText('Describe a typical day on your campus.')
    await user.click(
      within(first.closest('li') as HTMLElement).getByRole('button', { name: 'Use this subject' }),
    )
    await sendTake(user, kit)

    expect(await screen.findByRole('heading', { level: 2, name: 'What the speech recognition heard' })).toBeInTheDocument()
    const sent = post(calls, '/speech/speaking')
    expect(sent).toHaveLength(1)
    expect(queryOf(sent[0]!)).toEqual({
      duration_s: '6',
      prompt_text: 'Describe a typical day on your campus.',
    })
    expect(sent[0]!.body).toBeInstanceOf(Blob)
    expect((sent[0]!.body as Blob).type).toBe(OPUS)
    expect(sent[0]!.headers['content-type']).toBe(OPUS)
    expect(router.state.location.pathname).toBe('/speaking/9')
    expect(router.state.historyAction).toBe('REPLACE')
    // The state was consumed: nothing is left that could start a correction again.
    expect(router.state.location.state).toBeNull()
    expect(post(calls, '/productions/9/correct')).toHaveLength(1)
    expect(post(calls, '/productions/9/transcribe')).toHaveLength(0)
    expect(kit.streams.every((stream) => stream.tracks.every((track) => track.stopped))).toBe(true)
  })

  it('filters the subjects by theme (including "Presenting") and sends your own subject', async () => {
    const kit = installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/speaking')

    await screen.findByText('Describe a typical day on your campus.')
    await user.selectOptions(screen.getByLabelText('Topic theme'), 'Presenting')
    await waitFor(() =>
      expect(calls.some((call) => call.path === '/speaking/topics?count=3&tag=presenting')).toBe(true),
    )

    await user.click(screen.getByRole('button', { name: 'Speak on my own subject' }))
    await user.type(screen.getByLabelText('Your subject (500 characters at most)'), 'My thesis.')
    await sendTake(user, kit)
    await screen.findByRole('heading', { level: 1, name: 'Your speech and its correction' })
    expect(queryOf(post(calls, '/speech/speaking')[0]!)).toEqual({
      duration_s: '6',
      prompt_text: 'My thesis.',
    })
  })

  it('can speak without a subject (no topic is sent)', async () => {
    const kit = installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/speaking')
    await screen.findByText('Describe a typical day on your campus.')
    await sendTake(user, kit)
    await screen.findByRole('heading', { level: 1, name: 'Your speech and its correction' })
    expect(queryOf(post(calls, '/speech/speaking')[0]!)).toEqual({ duration_s: '6' })
  })

  it('does not send a take shorter than 5 seconds', async () => {
    const kit = installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/speaking')
    await recordTake(user, kit, { ms: 2000 })
    expect(screen.getByRole('alert')).toHaveTextContent('too short (at least 5 s)')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(post(calls, '/speech/speaking')).toHaveLength(0)
  })

  it('shows a refusal of the server and stays on the page with the take', async () => {
    const kit = installFakeRecorder()
    backend({ send: () => apiErrorResponse(422, 'audio_too_long', 'long', { min_s: 5, max_s: 180 }) })
    const user = userEvent.setup()
    const { router } = renderApp('/speaking')
    await sendTake(user, kit)
    expect(await screen.findByText(/The recording is too long/)).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/speaking')
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('goes on with an unavailable transcription: the reason, then Transcribe and the correction', async () => {
    const kit = installFakeRecorder()
    const calls = backend({
      stored: speech({ transcription_status: 'pending', text: '' }),
      send: () =>
        Response.json(
          speakingOut({ transcription: { status: 'unavailable', text: null, reason: 'quota' } }),
          { status: 201 },
        ),
    })
    const user = userEvent.setup()
    renderApp('/speaking')
    await sendTake(user, kit)

    expect(await screen.findByText(/The transcription is not available/)).toBeInTheDocument()
    // Nothing started by itself.
    expect(post(calls, '/productions/9/correct')).toHaveLength(0)
    expect(post(calls, '/productions/9/transcribe')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('heading', { level: 2, name: 'What the speech recognition heard' })
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual([
      '/speech/speaking?duration_s=6',
      '/productions/9/transcribe',
      '/productions/9/correct',
    ])
  })

  it('keeps no recording text in the storages or in history.state', async () => {
    const kit = installFakeRecorder()
    backend()
    const user = userEvent.setup()
    window.localStorage.clear()
    window.sessionStorage.clear()
    const { router } = renderAppInBrowser('/')
    await act(() => router.navigate('/speaking'))
    await sendTake(user, kit)
    await screen.findByRole('heading', { level: 2, name: 'What the speech recognition heard' })
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())
    for (const store of [window.localStorage, window.sessionStorage]) {
      expect(JSON.stringify({ ...store })).not.toContain('campus')
    }
    expect(JSON.stringify(window.history.state)).not.toContain('autoCorrect')
  })
})

describe('Free speaking: the page of one speech', () => {
  it('shows the topic, the recording, the marks, the versions and the structure', async () => {
    backend({ stored: correctedSpeech() })
    renderApp('/speaking/9')

    expect(await screen.findByRole('heading', { level: 1, name: 'Your speech and its correction' })).toHaveFocus()
    expect(await screen.findByText(SPEECH_TOPIC)).toBeInTheDocument()
    const audio = screen.getByLabelText('Your recording', { selector: 'audio' })
    expect(audio).toHaveAttribute('src', '/api/productions/9/audio')
    expect(await screen.findByRole('heading', { name: 'What the speech recognition heard' })).toBeInTheDocument()
    expect(screen.getByText(/a mistake the recogniser smoothed over is not reported/)).toBeInTheDocument()
    expect(marks().map((m) => m.firstChild?.textContent)).toEqual(['in campus', 'since two years'])
    expect(screen.getByRole('heading', { name: 'Corrected version' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'More natural version' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(screen.getByText('Part 1')).toBeInTheDocument()
  })

  it('a reload (no state) never starts anything: it offers "Correct my speech"', async () => {
    const calls = backend()
    renderApp('/speaking/9')
    expect(await screen.findByText('This speech is transcribed but not corrected yet.')).toBeInTheDocument()
    expect(screen.getByText(SPEECH)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Correct my speech' })).toBeEnabled()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(post(calls, '/productions/9/correct')).toHaveLength(0)
  })

  it('consumes autoCorrect once, even in StrictMode, and clears the state at once', async () => {
    window.history.replaceState(null, '', '/')
    const calls = backend()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const router = createMemoryRouter(routes, {
      initialEntries: [{ pathname: '/speaking/9', state: { autoCorrect: true } }],
    })
    render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </StrictMode>,
    )
    await screen.findByRole('heading', { name: 'Structure' })
    expect(post(calls, '/productions/9/correct')).toHaveLength(1)
    expect(router.state.location.state).toBeNull()
  })

  it('says "Correcting… n s" while the AI works', async () => {
    let answer: (response: Response) => void = () => {}
    const calls = backend({
      corrections: [() => new Promise<Response>((resolve) => (answer = resolve))],
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })

    expect(await screen.findByRole('button', { name: 'Correcting… 0 s' })).toBeDisabled()
    expect(screen.getByText(/The AI is correcting what was heard/)).toBeInTheDocument()
    expect(post(calls, '/productions/9/correct')).toHaveLength(1)
    answer(Response.json(speakingCorrection()))
    expect(await screen.findByRole('heading', { name: 'Structure' })).toBeInTheDocument()
  })

  it('pending: "Transcribe", then the correction follows', async () => {
    const calls = backend({
      stored: speech({ transcription_status: 'pending', text: '' }),
    })
    const user = userEvent.setup()
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })

    expect(await screen.findByText('This recording is not transcribed yet.')).toBeInTheDocument()
    // The flag waits for the transcription: nothing runs yet.
    expect(post(calls, '/productions/9/correct')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Transcribe' }))
    expect(await screen.findByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual([
      '/productions/9/transcribe',
      '/productions/9/correct',
    ])
  })

  it('409 not_transcribed: the production is read again and "Transcribe" is offered', async () => {
    let reads = 0
    const calls = mockApi({
      ...base,
      // The first read is stale (it says the speech is transcribed).
      'GET /productions/9': () =>
        Response.json(reads++ === 0 ? speech() : speech({ transcription_status: 'pending', text: '' })),
      'POST /productions/9/correct': () => apiErrorResponse(409, 'not_transcribed', 'transcribe first'),
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByRole('button', { name: 'Transcribe' })).toBeInTheDocument()
    expect(post(calls, '/productions/9/correct')).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('silence: "No speech was heard", with a way to record again', async () => {
    const calls = backend({ stored: speech({ transcription_status: 'silence', text: '' }) })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByText('No speech was heard in this recording.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Record again' })).toHaveAttribute('href', '/speaking')
    expect(post(calls, '/productions/9/correct')).toHaveLength(0)
  })

  it('422 nothing_to_correct is told like a silence', async () => {
    backend({
      corrections: [() => apiErrorResponse(422, 'nothing_to_correct', 'nothing')],
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByText('No speech was heard in this recording.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('422 text_too_long: its own sentence, and no pointless retry', async () => {
    backend({
      corrections: [() => apiErrorResponse(422, 'text_too_long', 'too long', { max_chars: 4000 })],
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByText(/too long to be corrected in one go/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Try again|Correct my speech/ })).not.toBeInTheDocument()
  })

  it('an AI failure (HTTP 200) says why, then "Try again" works', async () => {
    const failed = speakingCorrection({
      status: 'unavailable',
      reason: 'no_provider_configured',
      attempt: speech(),
      errors: [],
    })
    const calls = backend({ corrections: [failed, speakingCorrection()] })
    const user = userEvent.setup()
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })

    expect(
      await screen.findByText('This speech is not corrected: no AI provider is set up.'),
    ).toBeInTheDocument()
    // The transcription is still shown.
    expect(screen.getByText(SPEECH)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(post(calls, '/productions/9/correct')).toHaveLength(2)
  })

  it('an incomplete answer has its own sentence', async () => {
    backend({
      corrections: [
        speakingCorrection({ status: 'incomplete', reason: null, attempt: speech(), errors: [] }),
      ],
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByText(/the AI's answer could not be used/)).toBeInTheDocument()
  })

  it('409 already_corrected reads the stored correction and says nothing', async () => {
    let corrected = false
    mockApi({
      ...base,
      'GET /productions/9': () => Response.json(corrected ? correctedSpeech() : speech()),
      'POST /productions/9/correct': () => {
        corrected = true
        return apiErrorResponse(409, 'already_corrected', 'done')
      },
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says a network failure and offers "Try again"', async () => {
    backend({
      corrections: [() => Response.json({ detail: 'boom' }, { status: 500 })],
    })
    renderApp({ pathname: '/speaking/9', state: { autoCorrect: true } })
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('speaks French with the same keys', async () => {
    await i18n.changeLanguage('fr')
    backend({ stored: correctedSpeech() })
    renderApp('/speaking/9')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Votre prise de parole et sa correction' }),
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('heading', { name: 'Ce que la reconnaissance vocale a entendu' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Passage 1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Structure' })).toBeInTheDocument()
  })

  it('a missing production gets a message and a way out', async () => {
    mockApi({ ...base, 'GET /productions/9': () => apiErrorResponse(404, 'production_not_found', 'none') })
    renderApp('/speaking/9')
    expect(await screen.findByRole('alert')).toHaveTextContent('does not exist')
    expect(screen.getByRole('link', { name: 'All my speeches' })).toHaveAttribute('href', '/speaking/history')
  })
})

describe('Free speaking: redirects between the written and the spoken pages', () => {
  it('/writing/:id of a spoken production goes to /speaking/:id (replace)', async () => {
    backend({ stored: correctedSpeech() })
    const { router } = renderApp('/writing/9')
    expect(await screen.findByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/speaking/9')
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('/speaking/:id of a written text goes to /writing/:id (replace)', async () => {
    mockApi({
      ...base,
      'GET /productions/5': () => Response.json(correctedProduction()),
    })
    const { router } = renderApp('/speaking/5')
    expect(await screen.findByRole('heading', { level: 1, name: 'Your text and its correction' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/writing/5')
    expect(router.state.historyAction).toBe('REPLACE')
  })

  it('/speaking/:id of another kind says so and links to the error log', async () => {
    mockApi({
      ...base,
      'GET /productions/7': () => Response.json(shadowing()),
    })
    const { router } = renderApp('/speaking/7')
    expect(await screen.findByRole('alert')).toHaveTextContent('has no page here')
    expect(router.state.location.pathname).toBe('/speaking/7')
    expect(screen.getByRole('link', { name: 'Open the error log' })).toHaveAttribute('href', '/errors')
  })

  it('a written text still opens at /writing/:id', async () => {
    mockApi({
      ...base,
      'GET /productions/5': () => Response.json(production()),
    })
    const { router } = renderApp('/writing/5')
    expect(await screen.findByRole('heading', { level: 1, name: 'Your text and its correction' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/writing/5')
  })
})

describe('Free speaking: the history', () => {
  const rows = (): Production[] => [
    correctedSpeech(),
    speech({ id: 10, prompt_text: 'What is a p-value?', transcription_status: 'silence', text: '' }),
    speech({ id: 11, transcription_status: 'pending', text: '' }),
    speech({ id: 12, prompt_text: null }),
  ]

  it('lists the spoken productions with their state, and says the answers of reviews are in it', async () => {
    const calls = mockApi({
      ...base,
      'GET /productions': () => Response.json({ items: rows(), total: 45, limit: 20, offset: 0 }),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/speaking/history')

    expect(await screen.findByRole('heading', { level: 1, name: 'My speeches' })).toHaveFocus()
    expect(await screen.findByText('45 speeches')).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/productions?kind=speaking&limit=20&offset=0')).toBe(true)
    expect(screen.getByText(/also holds your spoken answers in reviews/)).toBeInTheDocument()
    expect(screen.getByText('Corrected')).toBeInTheDocument()
    expect(screen.getByText('No speech heard')).toBeInTheDocument()
    expect(screen.getByText('Not transcribed')).toBeInTheDocument()
    expect(screen.getByText('What is a p-value?')).toBeInTheDocument()
    const links = screen.getAllByRole('link').filter((link) => /\/speaking\/\d+$/.test(link.getAttribute('href') ?? ''))
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/speaking/9',
      '/speaking/10',
      '/speaking/11',
      '/speaking/12',
    ])

    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(router.state.location.search).toBe('?page=2')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/productions?kind=speaking&limit=20&offset=20')).toBe(true),
    )
  })

  it('says when there is nothing yet', async () => {
    mockApi({
      ...base,
      'GET /productions': () => Response.json({ items: [], total: 0, limit: 20, offset: 0 }),
    })
    renderApp('/speaking/history')
    expect(await screen.findByText('No speech yet. Record the first one.')).toBeInTheDocument()
  })
})

describe('The Speaking link of the top bar', () => {
  it('points to /speaking', async () => {
    backend()
    renderApp('/')
    const link = await screen.findByRole('link', { name: 'Speaking' })
    expect(link).toHaveAttribute('href', '/speaking')
  })
})
