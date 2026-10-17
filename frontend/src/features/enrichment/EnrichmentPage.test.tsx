import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { deck, report } from '../../test/fixtures'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const pending = {
  count: 7,
  items: [
    { item_id: 1, term: 'to account for', status: 'queued' },
    { item_id: 2, term: 'sampling frame', status: 'learning' },
  ],
}

const decks = [deck(1, 'Causal inference reading')]

describe('batch enrichment page', () => {
  it('runs batches until nothing is left', async () => {
    const reports = [
      report({ generated: 5, remaining: 2, item_ids: [1, 2, 3, 4, 5] }),
      report({ status: 'partial', generated: 1, needs_completion: 1, item_ids: [6, 7] }),
    ]
    const calls = mockApi({
      'GET /decks': decks,
      'GET /enrichment/pending': pending,
      'POST /enrichment/run': () => Response.json(reports.shift()),
    })
    renderApp('/enrichment')
    expect(await screen.findByText('7 terms waiting for a sheet.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Deck'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Generate the sheets' }))
    expect(await screen.findByText('Done: no term is waiting any more.')).toBeInTheDocument()
    expect(
      screen.getByText('Generated: 6 · to complete by hand: 1 · still waiting: 0.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/could not be generated in full/)).toBeInTheDocument()
    const runs = calls.filter((c) => c.path === '/enrichment/run')
    expect(runs.map((c) => c.body)).toEqual([
      { include_incomplete: false, deck_id: 1 },
      { include_incomplete: false, deck_id: 1 },
    ])
  })

  it('stops on an unavailable AI and points to manual entry (degraded mode)', async () => {
    const calls = mockApi({
      'GET /decks': decks,
      'GET /enrichment/pending': pending,
      'POST /enrichment/run': report({
        status: 'unavailable',
        reason: 'no_provider_configured',
        remaining: 7,
        item_ids: [1, 2, 3, 4, 5],
      }),
    })
    renderApp('/enrichment')
    await userEvent.click(await screen.findByRole('button', { name: 'Generate the sheets' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No AI right now: no AI provider is set up.')
    expect(alert).toHaveTextContent(/write its sheet by hand/)
    expect(screen.getByRole('link', { name: 'to account for' })).toHaveAttribute(
      'href',
      '/library/items/1',
    )
    expect(calls.filter((c) => c.path === '/enrichment/run')).toHaveLength(1)
  })

  it('explains that another run holds the lock', async () => {
    mockApi({
      'GET /decks': decks,
      'GET /enrichment/pending': pending,
      'POST /enrichment/run': () => apiErrorResponse(409, 'enrichment_running', 'running'),
    })
    renderApp('/enrichment')
    await userEvent.click(await screen.findByRole('button', { name: 'Generate the sheets' }))
    expect(await screen.findByText(/already being generated/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate the sheets' })).toBeEnabled()
  })

  it('stops after the current batch when asked', async () => {
    let release: () => void = () => undefined
    const calls = mockApi({
      'GET /decks': decks,
      'GET /enrichment/pending': pending,
      'POST /enrichment/run': () =>
        new Promise<Response>((resolve) => {
          release = () => resolve(Response.json(report({ generated: 5, remaining: 2, item_ids: [1] })))
        }),
    })
    renderApp('/enrichment')
    await userEvent.click(await screen.findByRole('button', { name: 'Generate the sheets' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Stop after this batch' }))
    expect(screen.getByRole('button', { name: 'Stopping after this batch…' })).toBeDisabled()
    release()
    expect(await screen.findByText(/Stopped. The remaining terms keep waiting./)).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/enrichment/run')).toHaveLength(1)
  })

  it('asks for the sheets to complete when the box is ticked, and is available in French', async () => {
    const calls = mockApi({ 'GET /decks': decks, 'GET /enrichment/pending': pending })
    renderApp('/enrichment')
    await userEvent.click(await screen.findByLabelText(/Also include the sheets to complete/))
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/enrichment/pending?include_incomplete=true')).toBe(true),
    )
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(await screen.findByRole('button', { name: 'Générer les fiches' })).toBeInTheDocument()
  })

  it('is linked from the library with the waiting count', async () => {
    mockApi({
      'GET /decks': decks,
      'GET /items': { total: 0, items: [] },
      'GET /triage': [],
      'GET /enrichment/pending': pending,
    })
    renderApp('/library')
    expect(await screen.findByRole('link', { name: 'Generate usage sheets (7 waiting)' })).toHaveAttribute(
      'href',
      '/enrichment',
    )
  })
})
