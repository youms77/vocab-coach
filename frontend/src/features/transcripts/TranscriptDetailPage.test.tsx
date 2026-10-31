import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import type { CorrectionResult, Production } from '../../api/productions'
import type { UserDesignation } from '../../api/transcripts'
import i18n from '../../i18n'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import {
  analysedTranscript,
  analysisResult,
  labelledPreview,
  PASTE,
  transcriptProduction,
  unavailableAnalysis,
} from '../../test/transcriptFixtures'
import { categoryTree } from '../../test/writingFixtures'
import { forgetAll, recall, remember } from './transcriptMemory'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
}

type Answer = CorrectionResult | (() => Response | Promise<Response>)

interface Options {
  /** What each POST /productions/5/correct answers, in order (the last one repeats). */
  answers?: Answer[]
  stored?: () => Production
}

function backend({ answers = [analysisResult()], stored }: Options = {}) {
  let attempts = 0
  let current: Production = transcriptProduction()
  return mockApi({
    ...base,
    'POST /transcripts/preview': (call: RecordedCall) => {
      const body = call.body as { user?: UserDesignation }
      return Response.json(
        labelledPreview(body.user !== undefined && 'label' in body.user ? body.user.label : 'You'),
      )
    },
    'GET /productions/5': () => Response.json(stored !== undefined ? stored() : current),
    'POST /productions/5/correct': () => {
      const next = answers[Math.min(attempts, answers.length - 1)]
      attempts += 1
      if (typeof next === 'function') return next()
      if (next.status === 'ok') current = next.attempt
      return Response.json(next)
    },
  })
}

const corrections = (calls: RecordedCall[]) =>
  calls.filter((c) => c.method === 'POST' && c.path === '/productions/5/correct')

const marks = () => Array.from(document.querySelectorAll('mark'))
const YOU = { label: 'You' }
const HEADING = 'Your conversation and its analysis'

/** Arrives as `/transcripts` does after "Save and analyse": the flag in the router state. */
async function arriveWithFlag(router: ReturnType<typeof renderApp>['router']) {
  await act(async () => {
    await router.navigate('/transcripts/5', { state: { autoAnalyse: true }, replace: true })
  })
}

beforeEach(() => forgetAll())

describe('Transcript page: the analysis starts by itself after saving', () => {
  it('analyses once with the pasted conversation, clears the flag and shows the turns', async () => {
    const calls = backend()
    remember(5, { text: PASTE, user: YOU })
    const { router } = renderApp('/')
    await arriveWithFlag(router)

    expect(await screen.findByRole('heading', { level: 1, name: HEADING })).toBeInTheDocument()
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(1)
    expect(corrections(calls)[0].body).toEqual({ transcript: { text: PASTE, user: YOU } })
    expect(router.state.location.state).toBeNull()
    expect(recall(5)).toBeUndefined()

    // Your turns, grouped by turn; the context is announced; no "natural version".
    expect(screen.getByText('Your turn 1')).toBeInTheDocument()
    expect(screen.getByText('Your turn 2')).toBeInTheDocument()
    expect(screen.getByText(/Analysed with the other speaker's context/)).toBeInTheDocument()
    expect(screen.queryByText('More natural version')).not.toBeInTheDocument()
    expect(await screen.findByText('Analysis ready: 2 errors found.')).toBeInTheDocument()
    expect(screen.getByText('Only your turns are saved.')).toBeInTheDocument()
  })

  it('shows the counter, the several-calls hint and a single request while it waits', async () => {
    let release: (response: Response) => void = () => undefined
    const calls = backend({
      answers: [() => new Promise<Response>((resolve) => (release = resolve))],
    })
    remember(5, { text: PASTE, user: YOU })
    const { router } = renderApp('/')
    await arriveWithFlag(router)

    expect(await screen.findByText(/Analysing your turns… \d+ s/)).toBeInTheDocument()
    expect(screen.getByText(/several AI calls and can take a few minutes/)).toBeInTheDocument()
    const busy = screen.getByRole('button', { name: /Analysing… \d+ s/ })
    expect(busy).toBeDisabled()
    expect(corrections(calls)).toHaveLength(1)
    release(Response.json(analysisResult()))
    await waitFor(() => expect(marks()).toHaveLength(2))
  })

  it('says why the AI could not analyse, keeps the paste, and "Try again" only calls /correct', async () => {
    const calls = backend({ answers: [unavailableAnalysis('quota'), analysisResult()] })
    remember(5, { text: PASTE, user: YOU })
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await arriveWithFlag(router)

    expect(
      await screen.findByText(/Your turns are saved but were not analysed: the free quota is used up/),
    ).toBeInTheDocument()
    expect(recall(5)).toBeDefined() // an AI failure keeps the paste for the retry

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(2)
    expect(corrections(calls)[1].body).toEqual({ transcript: { text: PASTE, user: YOU } })
    expect(calls.filter((c) => c.method === 'POST' && c.path !== '/productions/5/correct')).toHaveLength(0)
    expect(recall(5)).toBeUndefined()
  })

  it('says it when the answer could not be used', async () => {
    backend({ answers: [{ ...unavailableAnalysis(), status: 'incomplete', reason: null }] })
    remember(5, { text: PASTE, user: YOU })
    const { router } = renderApp('/')
    await arriveWithFlag(router)
    expect(await screen.findByText(/the AI's answer could not be used/)).toBeInTheDocument()
  })
})

describe('Transcript page: after a reload (the paste is gone)', () => {
  it('starts nothing by itself and offers the two ways forward', async () => {
    const calls = backend()
    renderApp('/transcripts/5')

    expect(await screen.findByRole('button', { name: "Analyse without the other speaker's context" })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Paste the conversation again' })).toBeEnabled()
    expect(screen.getByText(/is not kept after a reload/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(corrections(calls)).toHaveLength(0)
  })

  it('"without context" sends no body', async () => {
    const calls = backend({
      answers: [analysisResult({ attempt: analysedTranscript({ feedback: { ...analysedTranscript().feedback!, context_sent: false } }) })],
    })
    const user = userEvent.setup()
    renderApp('/transcripts/5')
    await user.click(await screen.findByRole('button', { name: "Analyse without the other speaker's context" }))

    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(1)
    expect(corrections(calls)[0].body).toBeUndefined()
    expect(screen.getByText('Analysed without the other speaker\'s context.')).toBeInTheDocument()
  })

  it('"paste again" previews the paste, then sends it with the chosen user', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/transcripts/5')
    await user.click(await screen.findByRole('button', { name: 'Paste the conversation again' }))
    await user.click(screen.getByLabelText('The conversation'))
    await user.paste(PASTE)
    expect(screen.getByRole('button', { name: 'Analyse with this conversation' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByRole('radio', { name: /^You\b/ })).toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Analyse with this conversation' }))

    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(1)
    expect(corrections(calls)[0].body).toEqual({ transcript: { text: PASTE, user: YOU } })
  })

  it('keeps the pasted text when the server says it does not match', async () => {
    const calls = backend({
      answers: [() => apiErrorResponse(409, 'transcript_mismatch'), analysisResult()],
    })
    const user = userEvent.setup()
    renderApp('/transcripts/5')
    await user.click(await screen.findByRole('button', { name: 'Paste the conversation again' }))
    await user.click(screen.getByLabelText('The conversation'))
    await user.paste(PASTE)
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByRole('radio', { name: /^You\b/ })
    await user.click(screen.getByRole('button', { name: 'Analyse with this conversation' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'does not match the turns saved for this transcript',
    )
    expect(screen.getByLabelText('The conversation')).toHaveValue(PASTE)
    // Fixing the choice is possible without pasting again.
    await user.click(screen.getByRole('button', { name: 'Analyse with this conversation' }))
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(2)
  })

  it('shows the stored analysis when it was analysed meanwhile (already_corrected)', async () => {
    let analysed = false
    const calls = backend({
      stored: () => (analysed ? analysedTranscript() : transcriptProduction()),
      answers: [
        () => {
          analysed = true
          return apiErrorResponse(409, 'already_corrected')
        },
      ],
    })
    const user = userEvent.setup()
    renderApp('/transcripts/5')
    await user.click(await screen.findByRole('button', { name: "Analyse without the other speaker's context" }))

    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(1)
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/productions/5')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('opens a stored analysis without calling the AI', async () => {
    const calls = backend({ stored: () => analysedTranscript() })
    renderApp('/transcripts/5')
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(corrections(calls)).toHaveLength(0)
    expect(screen.queryByText(/not analysed/)).not.toBeInTheDocument()
  })

  it('says so for an unknown transcript', async () => {
    mockApi({ ...base, 'GET /productions/5': () => apiErrorResponse(404, 'production_not_found') })
    renderApp('/transcripts/5')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})

describe('Transcript page in French', () => {
  it('is translated, with "vous"', async () => {
    await i18n.changeLanguage('fr')
    backend({ stored: () => analysedTranscript() })
    renderApp('/transcripts/5')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Votre conversation et son analyse' }),
    ).toBeInTheDocument()
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(screen.getByText('Votre tour 1')).toBeInTheDocument()
    expect(screen.getByText(/Analysé avec le contexte de l’interlocuteur/)).toBeInTheDocument()
    expect(screen.getByText('Seuls vos tours sont enregistrés.')).toBeInTheDocument()
  })
})
