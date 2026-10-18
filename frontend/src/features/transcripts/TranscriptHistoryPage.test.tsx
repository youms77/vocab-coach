import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Production } from '../../api/productions'
import i18n from '../../i18n'
import { mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { analysedTranscript, transcriptProduction } from '../../test/transcriptFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

function listing(items: Production[], total = items.length) {
  return mockApi({
    ...base,
    'GET /productions': () => Response.json({ items, total, limit: 20, offset: 0 }),
  })
}

const listCalls = (calls: RecordedCall[]) => calls.filter((c) => c.path.startsWith('/productions'))

describe('Transcript history', () => {
  it('lists the conversations with date, title, words and state in words', async () => {
    const calls = listing([
      analysedTranscript({ id: 7, prompt_text: 'Chat about campus', word_count: 13 }),
      transcriptProduction({ id: 6, prompt_text: null, word_count: 40 }),
    ])
    renderApp('/transcripts/history')

    expect(await screen.findByRole('heading', { level: 1, name: 'My conversations' })).toHaveFocus()
    const rows = await screen.findAllByRole('row')
    expect(rows).toHaveLength(3) // header + 2
    expect(listCalls(calls)[0].path).toBe('/productions?kind=transcript_analysis&limit=20&offset=0')

    const first = within(rows[1])
    expect(first.getByRole('link')).toHaveAttribute('href', '/transcripts/7')
    expect(first.getByText('Chat about campus')).toBeInTheDocument()
    expect(first.getByText('13')).toBeInTheDocument()
    expect(first.getByText('Analysed')).toBeInTheDocument()
    const second = within(rows[2])
    expect(second.getByText('Untitled conversation')).toBeInTheDocument()
    expect(second.getByText('Not analysed')).toBeInTheDocument()
  })

  it('pages by 20 with the page in the URL', async () => {
    const calls = listing([transcriptProduction({ id: 7 })], 45)
    const user = userEvent.setup()
    const { router } = renderApp('/transcripts/history?page=2')

    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument()
    expect(listCalls(calls)[0].path).toBe('/productions?kind=transcript_analysis&limit=20&offset=20')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(router.state.location.search).toBe('?page=3'))
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('says when there is none yet, and is translated', async () => {
    await i18n.changeLanguage('fr')
    listing([])
    renderApp('/transcripts/history')
    expect(await screen.findByRole('heading', { level: 1, name: 'Mes conversations' })).toBeInTheDocument()
    expect(await screen.findByText('Aucune conversation pour l\'instant. Collez la première.')).toBeInTheDocument()
  })
})
