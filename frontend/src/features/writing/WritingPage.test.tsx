import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CorrectionResult, Production } from '../../api/productions'
import i18n from '../../i18n'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import {
  categoryTree,
  correctedProduction,
  correctionResult,
  PARAGRAPH,
  production,
  topics,
  unavailableResult,
} from '../../test/writingFixtures'
import { DRAFT_KEY } from './draft'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /writing/topics': topics(),
  'GET /error-categories': categoryTree(),
}

interface Options {
  /** What each POST /productions/5/correct answers, in order (the last one repeats). */
  corrections?: (CorrectionResult | (() => Response | Promise<Response>))[]
  create?: () => Response
  stored?: () => Production
}

/** A backend where one text is created (id 5) and then corrected as the script says. */
function backend({ corrections = [correctionResult()], create, stored }: Options = {}) {
  let attempts = 0
  let current: Production = production()
  return mockApi({
    ...base,
    'POST /productions': () =>
      create !== undefined ? create() : Response.json(current, { status: 201 }),
    'GET /productions/5': () => Response.json(stored !== undefined ? stored() : current),
    'POST /productions/5/correct': () => {
      const next = corrections[Math.min(attempts, corrections.length - 1)]
      attempts += 1
      if (typeof next === 'function') return next()
      if (next.status === 'ok') current = next.attempt
      return Response.json(next)
    },
  })
}

const post = (calls: RecordedCall[], path: string) =>
  calls.filter((c) => c.method === 'POST' && c.path === path)

async function writeAndSend(user: ReturnType<typeof userEvent.setup>, text = PARAGRAPH) {
  await user.click(screen.getByLabelText('Your text'))
  await user.paste(text)
  await user.click(screen.getByRole('button', { name: 'Correct my text' }))
}

const marks = () => Array.from(document.querySelectorAll('mark'))
const FIRST_TOPIC = 'Describe a typical day on your campus.'

describe('Writing page', () => {
  it('sends the exact bodies, then shows the correction at /writing/5 (history replaced)', async () => {
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/writing')
    expect(await screen.findByRole('heading', { level: 1, name: 'Writing' })).toHaveFocus()

    const first = await screen.findByText(FIRST_TOPIC)
    await user.click(
      within(first.closest('li') as HTMLElement).getByRole('button', { name: 'Use this topic' }),
    )
    await writeAndSend(user)

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your text and its correction' }),
    ).toBeInTheDocument()
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(post(calls, '/productions')).toHaveLength(1)
    expect(post(calls, '/productions')[0].body).toEqual({
      kind: 'writing',
      text: PARAGRAPH,
      prompt: FIRST_TOPIC,
      target_item_ids: [],
      study_session_id: null,
    })
    expect(post(calls, '/productions/5/correct')).toHaveLength(1)
    expect(post(calls, '/productions/5/correct')[0].body).toBeUndefined()
    // The order of the two writes.
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual([
      '/productions',
      '/productions/5/correct',
    ])
    // The URL is the production's, and the history entry was replaced (a reload creates nothing).
    expect(router.state.location.pathname).toBe('/writing/5')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(router.state.location.state).toBeNull()
    // The result is announced politely and shown in full.
    expect(screen.getByText('Correction ready: 2 errors found.')).toBeInTheDocument()
    expect(screen.getByText('Topic:')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Corrected version' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'More natural version' })).toBeInTheDocument()
  })

  it("sends the user's own topic when one is typed", async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await user.click(screen.getByRole('button', { name: 'Write on my own topic' }))
    await user.type(screen.getByLabelText('Your topic (500 characters at most)'), 'My first week')
    expect(screen.getByRole('status')).toHaveTextContent('Topic: My first week')
    await writeAndSend(user)
    await screen.findByRole('heading', { name: 'Your text and its correction' })
    expect((post(calls, '/productions')[0].body as { prompt: string }).prompt).toBe('My first week')
  })

  it('sends a null prompt when no topic is chosen', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)
    await screen.findByRole('heading', { name: 'Your text and its correction' })
    expect((post(calls, '/productions')[0].body as { prompt: unknown }).prompt).toBeNull()
  })

  it('filters the topics by theme, and shows the French only on demand', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    expect(calls.some((c) => c.path === '/writing/topics?count=3')).toBe(true)
    expect(screen.queryByText('Décrivez une journée type sur votre campus.')).toBeNull()
    const item = screen.getByText(FIRST_TOPIC).closest('li') as HTMLElement
    await user.click(within(item).getByRole('button', { name: 'Show in French' }))
    expect(screen.getByText('Décrivez une journée type sur votre campus.')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Topic theme'), 'campus')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/writing/topics?count=3&tag=campus')).toBe(true),
    )
  })

  it('shows the AI failure, keeps the text saved, and "Try again" only calls /correct', async () => {
    const calls = backend({ corrections: [unavailableResult('quota'), correctionResult()] })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)

    expect(
      await screen.findByText(/Your text is saved but was not corrected: the free quota is used up/),
    ).toBeInTheDocument()
    expect(screen.getByText('Not corrected yet')).toBeInTheDocument()
    expect(marks()).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(post(calls, '/productions')).toHaveLength(1)
    expect(post(calls, '/productions/5/correct')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('says that an incomplete answer could not be used', async () => {
    backend({ corrections: [{ ...unavailableResult(), status: 'incomplete', reason: null }] })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)
    expect(await screen.findByText(/the AI's answer could not be used/)).toBeInTheDocument()
  })

  it('disables the button while the correction runs and sends it once', async () => {
    let release: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const calls = backend({ corrections: [() => pending] })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)

    const button = await screen.findByRole('button', { name: /^Checking… \d+ s$/ })
    expect(button).toBeDisabled()
    await user.click(button)
    expect(post(calls, '/productions/5/correct')).toHaveLength(1)
    expect(screen.getByText(/The AI is checking your text/)).toBeInTheDocument()

    release(Response.json(correctionResult()))
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(post(calls, '/productions/5/correct')).toHaveLength(1)
  })

  it('reloads the stored correction on 409 already_corrected', async () => {
    let corrected = false
    const calls = backend({
      corrections: [
        () => {
          corrected = true
          return apiErrorResponse(409, 'already_corrected')
        },
      ],
      stored: () => (corrected ? correctedProduction() : production()),
    })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(post(calls, '/productions/5/correct')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('refuses a text over 4,000 characters before sending anything', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await user.click(screen.getByLabelText('Your text'))
    await user.paste('a'.repeat(4001))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'This text has 4001 characters and the limit is 4000.',
    )
    expect(screen.getByRole('button', { name: 'Correct my text' })).toBeDisabled()
    expect(post(calls, '/productions')).toHaveLength(0)

    // At the limit, it goes.
    await user.clear(screen.getByLabelText('Your text'))
    await user.paste('a'.repeat(4000))
    expect(screen.getByRole('button', { name: 'Correct my text' })).toBeEnabled()
    expect(screen.getByText(/4000 \/ 4000 characters/)).toBeInTheDocument()
  })

  it('counts characters as the backend does (an emoji is one)', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await user.click(screen.getByLabelText('Your text'))
    await user.paste('Hi \u{1F600} there')
    expect(screen.getByText(/3 words/)).toBeInTheDocument()
    expect(screen.getByText(/10 \/ 4000 characters/)).toBeInTheDocument()
  })

  it('leaves the server the last word on the length: text_too_long is shown, the text is kept', async () => {
    const calls = backend({
      create: () => apiErrorResponse(422, 'text_too_long', 'too many sentences'),
    })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'at most 4,000 characters and 40 sentences',
    )
    expect(screen.getByLabelText('Your text')).toHaveValue(PARAGRAPH)
    expect(screen.getByRole('button', { name: 'Correct my text' })).toBeEnabled()
    expect(post(calls, '/productions/5/correct')).toHaveLength(0)
    // The draft is still there: nothing was created.
    expect(window.localStorage.getItem(DRAFT_KEY)).toBe(PARAGRAPH)
  })

  it('shows the English detail of invalid_production under the translated sentence', async () => {
    backend({ create: () => apiErrorResponse(422, 'invalid_production', 'The text is empty.') })
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await writeAndSend(user)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This text cannot be saved.')
    expect(alert).toHaveTextContent('The text is empty.')
  })

  it('keeps the draft in the browser, restores it, and clears it once the text is created', async () => {
    backend()
    const user = userEvent.setup()
    const first = renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    await user.click(screen.getByLabelText('Your text'))
    await user.paste('My unfinished text')
    expect(window.localStorage.getItem(DRAFT_KEY)).toBe('My unfinished text')
    first.unmount()

    renderApp('/writing')
    expect(await screen.findByLabelText('Your text')).toHaveValue('My unfinished text')
    await user.click(screen.getByRole('button', { name: 'Correct my text' }))
    await screen.findByRole('heading', { name: 'Your text and its correction' })
    expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull()
  })

  it('works when the browser storage is unavailable', async () => {
    backend()
    const original = Storage.prototype.getItem
    Storage.prototype.getItem = () => {
      throw new Error('blocked')
    }
    try {
      renderApp('/writing')
      expect(await screen.findByLabelText('Your text')).toHaveValue('')
    } finally {
      Storage.prototype.getItem = original
    }
  })

  it('does not enable the button for an empty or blank text', async () => {
    backend()
    const user = userEvent.setup()
    renderApp('/writing')
    await screen.findByText(FIRST_TOPIC)
    expect(screen.getByRole('button', { name: 'Correct my text' })).toBeDisabled()
    await user.click(screen.getByLabelText('Your text'))
    await user.paste('   \n  ')
    expect(screen.getByRole('button', { name: 'Correct my text' })).toBeDisabled()
  })

  it('does not start a correction by itself when the page is opened or reloaded', async () => {
    const calls = backend({ stored: () => production() })
    renderApp('/writing/5')
    expect(await screen.findByText('Not corrected yet')).toBeInTheDocument()
    expect(post(calls, '/productions/5/correct')).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
  })

  it('shows a stored correction as it is, without any call to /correct', async () => {
    const calls = backend({ stored: () => correctedProduction() })
    renderApp('/writing/5')
    await waitFor(() => expect(marks()).toHaveLength(2))
    expect(post(calls, '/productions/5/correct')).toHaveLength(0)
    expect(screen.queryByText(/Correction ready/)).toBeNull()
    // Labels come from the category tree on a reload (the logged errors are not in the answer).
    expect(await screen.findAllByText(/Past simple or present perfect/)).not.toHaveLength(0)
  })

  it('says so when the text does not exist', async () => {
    mockApi({ ...base, 'GET /productions/9': () => apiErrorResponse(404, 'production_not_found') })
    renderApp('/writing/9')
    expect(await screen.findByRole('alert')).toHaveTextContent('This text does not exist')
  })

  it('is translated: the French interface, with the English text left as it is', async () => {
    backend()
    await i18n.changeLanguage('fr')
    renderApp('/writing')
    expect(await screen.findByRole('heading', { level: 1, name: 'Écriture' })).toBeInTheDocument()
    expect(screen.getByLabelText('Votre texte')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Corriger mon texte' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Mes textes précédents' })).toHaveAttribute(
      'href',
      '/writing/history',
    )
    expect(await screen.findByText(FIRST_TOPIC)).toHaveAttribute('lang', 'en')
    expect(screen.getByLabelText('Thème des sujets')).toBeInTheDocument()
  })
})

describe('Writing history', () => {
  const items = [
    correctedProduction({ id: 7, prompt_text: 'Describe where you live.' }),
    production({
      id: 6,
      text: 'A short text that was never corrected. '.repeat(5),
      prompt_text: null,
    }),
  ]

  it('lists the texts, 20 per page, and opens one that is not corrected', async () => {
    const calls = mockApi({
      ...base,
      'GET /productions': { items, total: 41, limit: 20, offset: 0 },
      'GET /productions/6': items[1],
    })
    const user = userEvent.setup()
    renderApp('/writing/history')
    expect(await screen.findByRole('heading', { level: 1, name: 'My texts' })).toBeInTheDocument()
    const rows = await screen.findAllByRole('row')
    expect(calls.some((c) => c.path === '/productions?kind=writing&limit=20&offset=0')).toBe(true)
    expect(rows).toHaveLength(3)
    expect(within(rows[1]).getByText('Describe where you live.')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Corrected')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Not corrected')).toBeInTheDocument()
    expect(within(rows[2]).getByText('—')).toBeInTheDocument()
    expect(screen.getByText('41 texts')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByText(/also holds the personal sentences of the discovery/)).toBeInTheDocument()

    await user.click(within(rows[2]).getByRole('link'))
    expect(await screen.findByText('Not corrected yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('asks for the next page, kept in the URL', async () => {
    const calls = mockApi({
      ...base,
      'GET /productions': { items, total: 41, limit: 20, offset: 0 },
    })
    const user = userEvent.setup()
    const { router } = renderApp('/writing/history')
    await screen.findAllByRole('row')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/productions?kind=writing&limit=20&offset=20')).toBe(true),
    )
    expect(router.state.location.search).toBe('?page=2')
  })

  it('says when there is nothing yet', async () => {
    mockApi({ ...base, 'GET /productions': { items: [], total: 0, limit: 20, offset: 0 } })
    renderApp('/writing/history')
    expect(await screen.findByText('No text yet. Write the first one.')).toBeInTheDocument()
  })
})
