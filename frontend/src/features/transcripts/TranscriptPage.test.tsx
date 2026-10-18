import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import type { Production } from '../../api/productions'
import type { UserDesignation } from '../../api/transcripts'
import i18n from '../../i18n'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp, renderAppInBrowser } from '../../test/renderApp'
import {
  analysedTranscript,
  analysisResult,
  labelledPreview,
  OTHER_1,
  OTHER_2,
  PASTE,
  PASTE_UNLABELLED,
  problem,
  transcriptProduction,
  unlabelledPreview,
  USER_1,
  USER_2,
} from '../../test/transcriptFixtures'
import { categoryTree } from '../../test/writingFixtures'
import { forgetAll, recall } from './transcriptMemory'

const STUDY_DAY = '2026-10-18'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
  'GET /session/today': { plan: { study_day: STUDY_DAY }, open_session: null },
}

/** The preview as the backend gives it: the labelled paste suggests "You", the other has no label. */
function previewRoute(call: RecordedCall) {
  const body = call.body as { text: string; user?: UserDesignation }
  if (body.text === PASTE) {
    const user = body.user
    return Response.json(labelledPreview(user !== undefined && 'label' in user ? user.label : 'You'))
  }
  const user = body.user
  return Response.json(unlabelledPreview(user !== undefined && 'mode' in user ? user.mode : null))
}

interface Options {
  created?: () => Response
  correct?: () => Response | Promise<Response>
}

function backend({ created, correct }: Options = {}) {
  let current: Production = transcriptProduction()
  return mockApi({
    ...base,
    'POST /transcripts/preview': previewRoute,
    'POST /transcripts': () => created?.() ?? Response.json(current, { status: 201 }),
    'GET /productions/5': () => Response.json(current),
    'POST /productions/5/correct': () => {
      if (correct !== undefined) return correct()
      current = analysedTranscript()
      return Response.json(analysisResult())
    },
  })
}

const post = (calls: RecordedCall[], path: string) =>
  calls.filter((c) => c.method === 'POST' && c.path === path)

async function paste(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.click(screen.getByLabelText('The conversation'))
  await user.paste(text)
}

async function preview(user: ReturnType<typeof userEvent.setup>, text = PASTE) {
  await paste(user, text)
  await user.click(screen.getByRole('button', { name: 'Preview' }))
}

const turnItems = () => Array.from(document.querySelectorAll('.transcript-turn'))

beforeEach(() => {
  forgetAll()
  window.sessionStorage.clear()
})

describe('Transcript page: paste and preview', () => {
  it('previews a labelled conversation: numbered turns, yours marked in words, "You" pre-chosen', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    expect(await screen.findByRole('heading', { level: 1, name: 'Conversation transcript' })).toHaveFocus()

    await preview(user)

    expect(await screen.findByRole('radio', { name: /^You\b/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /^ChatGPT\b/ })).not.toBeChecked()
    expect(post(calls, '/transcripts/preview')).toHaveLength(1)
    expect(post(calls, '/transcripts/preview')[0].body).toEqual({ text: PASTE })

    const turns = turnItems()
    expect(turns).toHaveLength(4)
    expect(turns.map((turn) => turn.classList.contains('transcript-turn--user'))).toEqual([
      false,
      true,
      false,
      true,
    ])
    // Not by colour alone: the word "You" is written on your turns, "Other speaker" on the others.
    expect(within(turns[1] as HTMLElement).getByText('You')).toBeInTheDocument()
    expect(within(turns[0] as HTMLElement).getByText(/Other speaker/)).toBeInTheDocument()
    expect(within(turns[0] as HTMLElement).getByText('Turn 1')).toBeInTheDocument()
    expect(screen.getByText(/Your turns: 2 · 13 words · \d+ \/ 6000 characters/)).toBeInTheDocument()
  })

  it('reads the text again with the new choice when the designation changes', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await user.click(await screen.findByRole('radio', { name: /^ChatGPT\b/ }))

    await waitFor(() => expect(post(calls, '/transcripts/preview')).toHaveLength(2))
    expect(post(calls, '/transcripts/preview')[1].body).toEqual({ text: PASTE, user: { label: 'ChatGPT' } })
    await waitFor(() => expect(screen.getByRole('radio', { name: /^ChatGPT\b/ })).toBeChecked())
    const turns = turnItems()
    expect(turns.map((turn) => turn.classList.contains('transcript-turn--user'))).toEqual([
      true,
      false,
      true,
      false,
    ])
  })

  it('without labels: three modes, none chosen, saving blocked until one is', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user, PASTE_UNLABELLED)

    expect(await screen.findByRole('radio', { name: 'I speak first' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'I speak second' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'All of it is mine' })).not.toBeChecked()
    expect(screen.getByText('Choose one to continue.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeDisabled()

    await user.click(screen.getByRole('radio', { name: 'I speak second' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: 'I speak second' })).toBeChecked())
    expect(post(calls, '/transcripts/preview')[1].body).toEqual({
      text: PASTE_UNLABELLED,
      user: { mode: 'alternating_user_second' },
    })
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeEnabled()
  })

  it('writes the problems in the interface language, with the severity in words', async () => {
    mockApi({
      ...base,
      'POST /transcripts/preview': () =>
        Response.json(
          labelledPreview('You', [
            problem('single_speaker', 'warning'),
            problem('unlabelled_text', 'info', 3),
            problem('too_large', 'error'),
            problem('a_future_code', 'info'),
          ]),
        ),
    })
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)

    expect(await screen.findByText(/Only one speaker was found\./)).toBeInTheDocument()
    expect(screen.getByText('⚠ Warning')).toBeInTheDocument()
    expect(screen.getAllByText('Note')).toHaveLength(2) // the two "info" problems
    expect(screen.getByText('⚠ Error')).toBeInTheDocument()
    expect(screen.getByText(/Some text comes before the first speaker label/)).toBeInTheDocument()
    expect(screen.getByText('(line 3)')).toBeInTheDocument()
    // An error stops the save; an unknown code falls back to the backend's English message.
    expect(screen.getByText(/backend text for a_future_code/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeDisabled()
  })

  it('explains a lone "Note:" line that opened a turn (D-133)', async () => {
    const lonely = labelledPreview('You')
    lonely.labels = [...lonely.labels, { label: 'Note', turns: 1, words: 3, chars: 14, known: null }]
    mockApi({ ...base, 'POST /transcripts/preview': () => Response.json(lonely) })
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    expect(await screen.findByText(/“Note” has only one turn/)).toBeInTheDocument()
  })

  it('refuses more than 60 000 characters: a message, a disabled button, no request, no maxLength', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    const field = await screen.findByLabelText('The conversation')
    expect(field).not.toHaveAttribute('maxlength')

    await paste(user, 'a'.repeat(60_001))

    expect(
      await screen.findByText('This text has 60001 characters and the limit is 60000. Shorten it before the preview.'),
    ).toBeInTheDocument()
    expect(screen.getByText('60001 / 60000 characters')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Preview' })
    expect(button).toBeDisabled()
    await user.click(button)
    expect(post(calls, '/transcripts/preview')).toHaveLength(0)
    expect(field).toHaveValue('a'.repeat(60_001)) // the paste is not cut
  })

  it('counts in code points, like the server', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await paste(user, '😀😀😀')
    expect(screen.getByText('3 / 60000 characters')).toBeInTheDocument()
  })

  it('hides the preview and the choice when the text changes afterwards', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })

    await user.type(screen.getByLabelText('The conversation'), ' More.')

    expect(screen.queryByRole('radio', { name: /^You\b/ })).not.toBeInTheDocument()
    expect(screen.getByText('The text changed since the preview. Preview it again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeDisabled()
  })
})

describe('Transcript page: details and privacy notice', () => {
  it('limits the date to the study day and shows the privacy notice before saving', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    const date = await screen.findByLabelText('Date of the conversation')
    await waitFor(() => expect(date).toHaveAttribute('max', STUDY_DAY))
    expect(date).toHaveAttribute('type', 'date')

    const notice = screen.getByText('Before you save').closest('section') as HTMLElement
    expect(notice).toHaveTextContent('Only your turns are saved.')
    expect(notice).toHaveTextContent('300 characters at most')
    expect(notice).toHaveTextContent('may be used to improve its models')

    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeEnabled()
    fireEvent.change(date, { target: { value: '2026-10-19' } })
    expect(screen.getByText('This date is in the future.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeDisabled()
    fireEvent.change(date, { target: { value: STUDY_DAY } })
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeEnabled()
  })

  it('blocks a title of more than 200 characters', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByLabelText('Title'))
    await user.paste('t'.repeat(201))
    expect(screen.getByText('201 / 200 characters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeDisabled()
  })

  it('shows the reasons of a refused recording, translated', async () => {
    backend({
      created: () =>
        apiErrorResponse(422, 'text_too_long', 'too big', { codes: ['too_large'] }),
    })
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByRole('button', { name: 'Save and analyse' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('at most 60,000 pasted characters and 6,000 characters in your own turns')
    expect(alert).toHaveTextContent('The text is too long')
    expect(screen.getByRole('button', { name: 'Save and analyse' })).toBeEnabled() // can retry
  })

  it('has a link from the writing page', async () => {
    mockApi({ ...base, 'GET /writing/topics': [] })
    renderApp('/writing')
    expect(await screen.findByRole('link', { name: 'Analyse a conversation transcript' })).toHaveAttribute(
      'href',
      '/transcripts',
    )
  })
})

describe('Transcript page: save and analyse', () => {
  it('sends the exact bodies, replaces the history entry and analyses once with the paste', async () => {
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByLabelText('Title'))
    await user.paste('Chat about campus')
    fireEvent.change(screen.getByLabelText('Date of the conversation'), { target: { value: '2026-10-17' } })
    await user.click(screen.getByRole('button', { name: 'Save and analyse' }))

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your conversation and its analysis' }),
    ).toBeInTheDocument()
    await waitFor(() => expect(document.querySelectorAll('mark')).toHaveLength(2))

    expect(post(calls, '/transcripts')).toHaveLength(1)
    expect(post(calls, '/transcripts')[0].body).toEqual({
      text: PASTE,
      user: { label: 'You' },
      title: 'Chat about campus',
      occurred_on: '2026-10-17',
      study_session_id: null,
    })
    expect(router.state.location.pathname).toBe('/transcripts/5')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(post(calls, '/productions/5/correct')).toHaveLength(1)
    expect(post(calls, '/productions/5/correct')[0].body).toEqual({
      transcript: { text: PASTE, user: { label: 'You' } },
    })
    // Empty optional fields are sent as null; the paste is forgotten once the analysis succeeded.
    expect(recall(5)).toBeUndefined()
  })

  it('sends nulls for an empty title and date', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByRole('button', { name: 'Save and analyse' }))
    await screen.findByRole('heading', { level: 1, name: 'Your conversation and its analysis' })
    expect(post(calls, '/transcripts')[0].body).toMatchObject({ title: null, occurred_on: null })
  })

  it('never puts the pasted text in the history state, the URL or the browser storage', async () => {
    backend()
    const user = userEvent.setup()
    const { router } = renderAppInBrowser('/transcripts')
    // Every navigation, as the browser and the router see it, is recorded on the way.
    const snapshots: string[] = []
    router.subscribe(() =>
      snapshots.push(
        JSON.stringify({
          history: window.history.state,
          location: router.state.location.state,
          url: window.location.href,
        }),
      ),
    )

    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByRole('button', { name: 'Save and analyse' }))
    await screen.findByRole('heading', { level: 1, name: 'Your conversation and its analysis' })
    await waitFor(() => expect(document.querySelectorAll('mark')).toHaveLength(2))

    const dump = (storage: Storage) =>
      Array.from({ length: storage.length }, (_, i) => `${storage.key(i)}=${storage.getItem(storage.key(i) ?? '')}`)
        .join('\n')
    const where = [
      ...snapshots,
      JSON.stringify(window.history.state),
      window.location.href,
      dump(window.localStorage),
      dump(window.sessionStorage),
    ]
    // The navigation to the analysis page was seen, and carried only the flag.
    expect(snapshots.some((snapshot) => snapshot.includes('autoAnalyse'))).toBe(true)
    for (const sentence of [OTHER_1, OTHER_2, USER_1, USER_2, 'ChatGPT']) {
      for (const place of where) expect(place).not.toContain(sentence)
    }
    router.dispose()
  })

  it('does not save twice on a double click', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    await preview(user)
    await screen.findByRole('radio', { name: /^You\b/ })
    const save = screen.getByRole('button', { name: 'Save and analyse' })
    await user.dblClick(save)
    await screen.findByRole('heading', { level: 1, name: 'Your conversation and its analysis' })
    expect(post(calls, '/transcripts')).toHaveLength(1)
  })
})

describe('Transcript page in French', () => {
  it('is translated: title, privacy notice, the modes', async () => {
    await i18n.changeLanguage('fr')
    backend()
    const user = userEvent.setup()
    renderApp('/transcripts')
    expect(
      await screen.findByRole('heading', { level: 1, name: "Transcription d'une conversation" }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Seuls vos tours sont enregistrés/)).toBeInTheDocument()
    expect(screen.getByText(/peut servir à améliorer ses modèles/)).toBeInTheDocument()

    await user.click(screen.getByLabelText('La conversation'))
    await user.paste(PASTE_UNLABELLED)
    await user.click(screen.getByRole('button', { name: 'Aperçu' }))
    expect(await screen.findByRole('radio', { name: 'Je parle en premier' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Tout est de moi' })).toBeInTheDocument()
    expect(screen.getByText(/Aucune étiquette de locuteur trouvée/)).toBeInTheDocument()
    expect(screen.getByText('Avertissement', { exact: false })).toBeInTheDocument()
  })
})
