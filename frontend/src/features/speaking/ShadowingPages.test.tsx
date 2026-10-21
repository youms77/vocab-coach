import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Production } from '../../api/productions'
import type { SpeechOut } from '../../api/speech'
import i18n from '../../i18n'
import { installFakeRecorder, OPUS, recordTake, type RecorderKit } from '../../test/fakeRecorder'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp, renderAppInBrowser } from '../../test/renderApp'
import { comparison, HEARD, shadowing, speechOut, TARGET } from '../../test/speechFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const pending = (overrides: Partial<Production> = {}) =>
  shadowing({ transcription_status: 'pending', comparison: null, text: '', ...overrides })

const silent = () => shadowing({ transcription_status: 'silence', comparison: null, text: '' })

interface Options {
  stored?: Production
  send?: () => Response | Promise<Response>
  /** What each POST /productions/7/transcribe answers, in order (the last one repeats). */
  transcribe?: (() => Response)[]
  /** Called by a successful transcription: the stored production changes. */
  onTranscribed?: () => Production
}

/** A backend with one shadowing (id 7) that the page can send, read and transcribe. */
function backend({ stored = shadowing(), send, transcribe, onTranscribed }: Options = {}) {
  let current = stored
  let attempts = 0
  return mockApi({
    ...base,
    'POST /speech/shadowing': send ?? (() => Response.json(speechOut(), { status: 201 })),
    'GET /productions/7': () => Response.json(current),
    'POST /productions/7/transcribe': () => {
      const answer = transcribe?.[Math.min(attempts, transcribe.length - 1)]
      attempts += 1
      if (answer === undefined) {
        current = onTranscribed?.() ?? shadowing()
        return Response.json(speechOut())
      }
      const response = answer()
      if (response.ok && onTranscribed !== undefined) current = onTranscribed()
      return response
    },
  })
}

const post = (calls: RecordedCall[], path: string) =>
  calls.filter((call) => call.method === 'POST' && call.path.split('?')[0] === path)

const queryOf = (call: RecordedCall) =>
  Object.fromEntries(new URL(call.path, 'http://127.0.0.1').searchParams)

async function sendTake(user: ReturnType<typeof userEvent.setup>, kit: RecorderKit) {
  await recordTake(user, kit)
  await user.click(screen.getByRole('button', { name: 'Send' }))
}

describe('Shadowing: a new take', () => {
  it('sends the exact request, then shows the take at /speaking/shadowing/7 (history replaced)', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/speaking/shadowing')

    expect(await screen.findByRole('heading', { level: 1, name: 'Shadowing' })).toHaveFocus()
    // No sentence, no recording.
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeDisabled()
    await user.type(screen.getByLabelText('Sentence to repeat'), TARGET)
    expect(screen.getByRole('button', { name: 'Listen to “the sentence”' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Listen slowly to “the sentence”' })).toBeInTheDocument()
    expect(screen.getByText(/sent to Groq for transcription; it stays in your data folder/)).toBeInTheDocument()
    await sendTake(user, kit)

    expect(await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })).toBeInTheDocument()
    const sent = post(calls, '/speech/shadowing')
    expect(sent).toHaveLength(1)
    expect(queryOf(sent[0]!)).toEqual({ target_text: TARGET, duration_s: '2', origin: 'shadowing' })
    expect(sent[0]!.body).toBeInstanceOf(Blob)
    expect((sent[0]!.body as Blob).type).toBe(OPUS)
    expect(sent[0]!.headers['content-type']).toBe(OPUS)
    expect(router.state.location.pathname).toBe('/speaking/shadowing/7')
    expect(router.state.historyAction).toBe('REPLACE')
    // The microphone was given back.
    expect(kit.streams.every((stream) => stream.tracks.every((track) => track.stopped))).toBe(true)
  })

  it('takes the sentence and the term from the navigation state, and sends the term', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp({
      pathname: '/speaking/shadowing',
      state: { target: TARGET, itemId: 20 },
    })

    expect(await screen.findByLabelText('Sentence to repeat')).toHaveValue(TARGET)
    await sendTake(user, kit)
    await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })
    expect(queryOf(post(calls, '/speech/shadowing')[0]!)).toMatchObject({ item_id: '20' })
    expect(router.state.location.state).toBeNull()
  })

  it('clears the navigation state at once: after a reload the field is empty', async () => {
    installFakeRecorder()
    backend()
    const { router } = renderAppInBrowser('/')
    await act(() => router.navigate('/speaking/shadowing', { state: { target: TARGET, itemId: 20 } }))

    expect(await screen.findByLabelText('Sentence to repeat')).toHaveValue(TARGET)
    // What a reload would read back from `history.state`.
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())
    expect(JSON.stringify(window.history.state)).not.toContain(TARGET)
  })

  it('counts the sentence in code points and accepts 400 of them (no maxLength)', async () => {
    installFakeRecorder()
    backend()
    const user = userEvent.setup()
    renderApp('/speaking/shadowing')
    const field = await screen.findByLabelText('Sentence to repeat')
    expect(field).not.toHaveAttribute('maxlength')

    // 250 emoji: 250 code points, 500 UTF-16 units.
    await user.click(field)
    await user.paste('😀'.repeat(250))
    expect(screen.getByText('250 / 400 characters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeEnabled()

    await user.paste('😀'.repeat(151))
    expect(screen.getByText('401 / 400 characters')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('too long (401 of 400 characters)')
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeDisabled()
  })

  it('shows a refusal of the server and stays on the page', async () => {
    const kit = installFakeRecorder()
    backend({
      send: () => apiErrorResponse(422, 'audio_too_short', 'too short', { min_s: 0.5, max_s: 30 }),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/speaking/shadowing')
    await user.type(await screen.findByLabelText('Sentence to repeat'), TARGET)
    await sendTake(user, kit)

    expect(await screen.findByText('The recording is too short: it must last at least 0.5 s.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/speaking/shadowing')
    // The take is still there, the user can send it again.
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('says why on the next page when the transcription is unavailable, then retries', async () => {
    const kit = installFakeRecorder()
    const unavailable: SpeechOut = speechOut({
      comparison: null,
      transcription: { status: 'unavailable', text: null, reason: 'no_provider_configured' },
    })
    const calls = backend({
      stored: pending(),
      send: () => Response.json(unavailable, { status: 201 }),
      onTranscribed: () => shadowing(),
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing')
    await user.type(await screen.findByLabelText('Sentence to repeat'), TARGET)
    await sendTake(user, kit)

    expect(
      await screen.findByText(
        'The transcription is not available: no AI provider is set up. Your recording is kept.',
      ),
    ).toBeInTheDocument()
    // Nothing started by itself.
    expect(post(calls, '/productions/7/transcribe')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(post(calls, '/productions/7/transcribe')).toHaveLength(1)
  })
})

describe('Shadowing: the page of one take', () => {
  it('shows the sentence, the recording and the comparison, and starts nothing by itself', async () => {
    installFakeRecorder()
    installFakeSpeech()
    const calls = backend()
    renderApp('/speaking/shadowing/7')

    expect(await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })).toHaveFocus()
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(screen.getByText(TARGET)).toBeInTheDocument()
    const player = document.querySelector('audio') as HTMLAudioElement
    expect(player).toHaveAttribute('controls')
    expect(player).toHaveAttribute('src', '/api/productions/7/audio')
    expect(screen.getByText(/not a pronunciation judge/)).toBeInTheDocument()
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0)
  })

  it('offers "Transcribe" for a recording that is not transcribed, then shows the comparison', async () => {
    installFakeRecorder()
    const calls = backend({ stored: pending(), onTranscribed: () => shadowing() })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    expect(await screen.findByText('This recording is not transcribed yet.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Transcribe' }))
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(post(calls, '/productions/7/transcribe')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Transcribe' })).not.toBeInTheDocument()
    // The focus goes to the result.
    expect(screen.getByRole('heading', { name: 'Transcription and comparison' })).toHaveFocus()
  })

  it('says that no speech was heard, with a link to record again', async () => {
    installFakeRecorder()
    backend({ stored: silent() })
    renderApp('/speaking/shadowing/7')

    expect(await screen.findByText('No speech was heard in this recording.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Record again' })).toHaveAttribute('href', '/speaking/shadowing')
    expect(screen.queryByRole('button', { name: 'Transcribe' })).not.toBeInTheDocument()
  })

  it('says why a transcription is unavailable and offers "Try again" until it works', async () => {
    installFakeRecorder()
    const unavailable = () =>
      Response.json(
        speechOut({
          comparison: null,
          transcription: { status: 'unavailable', text: null, reason: 'quota' },
        }),
      )
    const calls = backend({
      stored: pending(),
      transcribe: [unavailable, () => Response.json(speechOut())],
      onTranscribed: () => shadowing(),
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Transcribe' }))
    expect(
      await screen.findByText(/The transcription is not available: the free quota is used up/),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(post(calls, '/productions/7/transcribe')).toHaveLength(2)
  })

  it('reads the production again on 409 already_transcribed, without an error message', async () => {
    installFakeRecorder()
    let stored = pending()
    const calls = mockApi({
      ...base,
      'GET /productions/7': () => Response.json(stored),
      'POST /productions/7/transcribe': () => {
        // Another tab transcribed it first.
        stored = shadowing()
        return apiErrorResponse(409, 'already_transcribed')
      },
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Transcribe' }))
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(screen.queryByText('This recording was already transcribed.')).not.toBeInTheDocument()
    expect(calls.filter((call) => call.path === '/productions/7').length).toBeGreaterThanOrEqual(2)
  })

  it('does not take a written text for a shadowing', async () => {
    installFakeRecorder()
    backend({ stored: shadowing({ kind: 'writing', modality: 'written' }) })
    renderApp('/speaking/shadowing/7')

    expect(await screen.findByText(/not a shadowing/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the error log' })).toHaveAttribute('href', '/errors')
  })

  it('says when the take does not exist', async () => {
    installFakeRecorder()
    mockApi({ ...base, 'GET /productions/7': () => apiErrorResponse(404, 'production_not_found') })
    renderApp('/speaking/shadowing/7')
    expect(await screen.findByRole('alert')).toHaveTextContent('This text does not exist')
  })

  it('is in French', async () => {
    installFakeRecorder()
    backend({ stored: pending() })
    await i18n.changeLanguage('fr')
    renderApp('/speaking/shadowing/7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Votre shadowing' })).toBeInTheDocument()
    expect(await screen.findByText("Cet enregistrement n'est pas encore transcrit.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Transcrire' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Écouter les deux' })).toBeInTheDocument()
  })
})

describe('Shadowing: "Play both"', () => {
  it('plays the synthetic voice, then the recording, one after the other', async () => {
    const kit = installFakeRecorder()
    const speech = installFakeSpeech()
    backend()
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Play both' }))
    // First the voice, and only the voice.
    expect(speech.spoken.map((utterance) => utterance.text)).toEqual([TARGET])
    expect(kit.play).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()

    act(() => speech.finish())
    // Then the recording.
    expect(kit.play).toHaveBeenCalledTimes(1)
    expect(speech.spoken).toHaveLength(1)

    act(() => {
      document.querySelector('audio')?.dispatchEvent(new Event('ended'))
    })
    expect(screen.getByRole('button', { name: 'Play both' })).toBeInTheDocument()
  })

  it('can be cancelled while the voice speaks: the recording never plays', async () => {
    const kit = installFakeRecorder()
    const speech = installFakeSpeech()
    backend()
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Play both' }))
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(speech.speaking).toBe(false)
    act(() => speech.finish())
    expect(kit.play).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Play both' })).toBeInTheDocument()
  })

  it('can be cancelled while the recording plays', async () => {
    const kit = installFakeRecorder()
    const speech = installFakeSpeech()
    backend()
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Play both' }))
    act(() => speech.finish())
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(kit.pause).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Play both' })).toBeInTheDocument()
  })

  it('plays the recording alone when the browser has no English voice', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech([])
    backend()
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    await user.click(await screen.findByRole('button', { name: 'Play both' }))
    expect(kit.play).toHaveBeenCalledTimes(1)
  })
})

describe('Shadowing: the history', () => {
  const page = (items: Production[], total: number) => () => Response.json({ items, total, limit: 20, offset: 0 })

  it('lists the takes, 20 per page, with the page in the URL', async () => {
    const calls = mockApi({
      ...base,
      'GET /productions': page(
        [shadowing(), silent(), pending({ id: 9 })].map((item, index) => ({ ...item, id: 7 + index })),
        45,
      ),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/speaking/shadowing/history')

    expect(await screen.findByRole('heading', { level: 1, name: 'Shadowing history' })).toBeInTheDocument()
    const table = await screen.findByRole('table')
    expect(within(table).getByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(within(table).getByText('No speech heard')).toBeInTheDocument()
    expect(within(table).getByText('Not transcribed')).toBeInTheDocument()
    expect(within(table).getAllByText(TARGET)).toHaveLength(3)
    const links = within(table).getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', '/speaking/shadowing/7')
    expect(screen.getByText('45 shadowings')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(calls.find((call) => call.path.startsWith('/productions'))!.path).toBe(
      '/productions?kind=shadowing&limit=20&offset=0',
    )

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(router.state.location.search).toBe('?page=2'))
    await waitFor(() =>
      expect(calls.map((call) => call.path)).toContain('/productions?kind=shadowing&limit=20&offset=20'),
    )
  })

  it('says when there is nothing yet', async () => {
    mockApi({ ...base, 'GET /productions': page([], 0) })
    renderApp('/speaking/shadowing/history')
    expect(await screen.findByText('No shadowing yet.')).toBeInTheDocument()
  })
})

describe('Shadowing: nothing of the recording is kept in the browser', () => {
  it('writes no transcription to the storages or to history.state', async () => {
    const kit = installFakeRecorder()
    installFakeSpeech()
    backend()
    const user = userEvent.setup()
    const { router } = renderAppInBrowser('/speaking/shadowing')
    // `history.state` at every navigation: a state cleared a moment later would escape a final check.
    const seen: string[] = []
    router.subscribe(() => seen.push(JSON.stringify(window.history.state)))

    await user.type(await screen.findByLabelText('Sentence to repeat'), TARGET)
    await sendTake(user, kit)
    expect(await screen.findByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/speaking/shadowing/7')

    const everything = [
      ...seen,
      JSON.stringify(window.history.state),
      JSON.stringify({ ...window.localStorage }),
      JSON.stringify({ ...window.sessionStorage }),
      window.location.href,
    ].join('\n')
    expect(seen.length).toBeGreaterThan(0)
    expect(everything).not.toContain(HEARD)
    expect(everything).not.toContain('really')
    expect(comparison().steps.length).toBeGreaterThan(0)
  })
})

describe('Shadowing: the top bar', () => {
  it('has a "Speaking" link to the shadowing page, "Oral" in French', async () => {
    installFakeRecorder()
    const user = userEvent.setup()
    mockApi({ ...base, 'GET /productions': () => Response.json({ items: [], total: 0, limit: 20, offset: 0 }) })
    renderApp('/speaking/shadowing/history')

    const nav = await screen.findByRole('navigation', { name: 'Main' })
    const link = within(nav).getByRole('link', { name: 'Speaking' })
    expect(link).toHaveAttribute('href', '/speaking/shadowing')
    // The current section is marked in the bar.
    expect(link).toHaveAttribute('aria-current', 'page')
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(within(nav).getByRole('link', { name: 'Oral' })).toBeInTheDocument()
  })
})
