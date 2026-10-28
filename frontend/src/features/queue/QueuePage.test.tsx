import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Deck } from '../../api/library'
import i18n from '../../i18n'
import { deck, plan } from '../../test/fixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /session/today': { plan: plan({ study_day: '2026-10-17' }), open_session: null },
}

// In id order, as `GET /api/decks` answers.
const initial = (): Deck[] => [
  deck(1, 'Presenting survey results', { status: 'active', queue_position: 1 }),
  deck(2, 'Causal inference reading', {
    status: 'queued',
    deadline: '2026-11-20',
    queue_position: 2,
    items_by_status: { queued: 30, learning: 4 },
    item_count: 34,
    pace: { deck_id: 2, deadline: '2026-11-20', remaining: 30, days_left: 34, required_per_day: 1 },
    warnings: [
      {
        code: 'deadline_unrealistic',
        params: {
          deck_id: 2,
          deadline: '2026-11-20',
          remaining: 30,
          required_per_day: 9,
          achievable_per_day: 4,
          projected_finish: '2026-12-01',
        },
      },
      { code: 'deadline_triage_pending', params: { deck_id: 2, count: 3 } },
    ],
  }),
  deck(3, 'Job interview phrases', {
    status: 'paused',
    queue_position: 0,
    warnings: [{ code: 'items_without_sheet', params: { count: 2, deck_ids: [3] } }],
  }),
  deck(4, 'Small talk', { status: 'queued', queue_position: null }),
  deck(5, 'Old statistics list', { status: 'done', queue_position: null }),
  deck(6, 'Deadline passed', {
    status: 'queued',
    deadline: '2026-10-01',
    queue_position: 3,
    warnings: [{ code: 'deadline_passed', params: { deck_id: 6, deadline: '2026-10-01', remaining: 5 } }],
  }),
]

/** A small backend: status changes and reorders write to `decks`, like the real routes. */
function server(decks = initial(), overrides: Record<string, unknown> = {}) {
  const calls = mockApi({
    ...base,
    'GET /decks': () => Response.json(decks),
    'PUT /decks/queue': (call: RecordedCall) => {
      const ids = (call.body as { deck_ids: number[] }).deck_ids
      ids.forEach((id, position) => {
        const found = decks.find((d) => d.id === id)
        if (found) found.queue_position = position
      })
      return Response.json(decks)
    },
    ...Object.fromEntries(
      decks.map((d) => [
        `POST /decks/${d.id}/status`,
        (call: RecordedCall) => {
          d.status = (call.body as { to: Deck['status'] }).to
          return Response.json(d)
        },
      ]),
    ),
    ...overrides,
  })
  return { calls, decks }
}

const deckCards = () =>
  within(screen.getByRole('region', { name: 'In the queue' }))
    .getAllByRole('listitem')
    .filter((li) => li.classList.contains('queue-deck'))
const titleOf = (li: HTMLElement) => li.querySelector('.queue-deck__head h3')?.textContent
const names = () => deckCards().map(titleOf)
function cardOf(name: string): HTMLElement {
  const found = [...document.querySelectorAll<HTMLElement>('li.queue-deck')].find(
    (li) => li.querySelector('.queue-deck__head a')?.textContent === name,
  )
  if (found === undefined) throw new Error(`no card for ${name}`)
  return found
}

describe('Queue page', () => {
  it('lists the decks in D-027 order, with status, counts, pace and translated warnings', async () => {
    server()
    renderApp('/queue')
    await screen.findByRole('heading', { name: 'Deck queue' })
    await screen.findByText('Causal inference reading')

    expect(names()).toEqual([
      '1. Causal inference reading',
      '2. Job interview phrases',
      '3. Presenting survey results',
      '4. Deadline passed',
      '5. Small talk',
    ])
    const dated = cardOf('Causal inference reading')
    expect(dated).toHaveTextContent('Queued')
    expect(dated).toHaveTextContent('34 terms · Queued: 30 · Learning: 4')
    expect(dated).toHaveTextContent('Deadline: November 20, 2026.')
    expect(dated).toHaveTextContent(
      '30 terms left to discover in 34 days: 1 new term a day is needed.',
    )
    expect(dated).toHaveTextContent('9 new terms a day are needed, but only 4 fit in your budget.')
    expect(dated).toHaveTextContent('At this pace the deck would be finished on December 1, 2026.')
    expect(within(dated).getByRole('link', { name: 'Sort them now' })).toHaveAttribute(
      'href',
      '/triage?deck=2',
    )
    const paused = cardOf('Job interview phrases')
    expect(paused).toHaveTextContent('Paused')
    expect(within(paused).getByRole('link', { name: 'Write or generate the sheets' })).toHaveAttribute(
      'href',
      '/enrichment',
    )
    expect(cardOf('Deadline passed')).toHaveTextContent(/has passed with 5 terms still to discover/)
    expect(screen.getByText(/cards already created keep being reviewed/)).toBeInTheDocument()
  })

  it('keeps done decks in a folded section, with "Reopen" only', async () => {
    const user = userEvent.setup()
    const { calls } = server()
    renderApp('/queue')
    const summary = await screen.findByText('Done (1 deck)')
    const details = summary.closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    await user.click(summary)
    const done = cardOf('Old statistics list')
    expect(within(done).getAllByRole('button').map((b) => b.textContent)).toEqual(['Reopen'])
    await user.click(within(done).getByRole('button', { name: 'Reopen “Old statistics list”' }))
    expect(await screen.findByText('“Old statistics list” is now active.')).toBeInTheDocument()
    expect(calls.find((c) => c.path === '/decks/5/status')?.body).toEqual({ to: 'active' })
  })

  it('shows only the transitions D-026 allows for each status', async () => {
    server()
    renderApp('/queue')
    await screen.findByText('Small talk')
    const actions = (name: string) =>
      within(cardOf(name))
        .getAllByRole('button')
        .map((b) => b.textContent)
        .filter((label) => !['Move up', 'Move down'].includes(label ?? ''))
    expect(actions('Small talk')).toEqual(['Activate', 'Pause', 'Mark as done'])
    expect(actions('Presenting survey results')).toEqual(['Pause', 'Mark as done'])
    expect(actions('Job interview phrases')).toEqual(['Resume', 'Mark as done'])
  })

  it('pauses and resumes a deck without confirmation, announcing each result', async () => {
    const user = userEvent.setup()
    const { calls } = server()
    renderApp('/queue')
    await screen.findByText('Presenting survey results')
    await user.click(screen.getByRole('button', { name: 'Pause “Presenting survey results”' }))
    expect(await screen.findByText('“Presenting survey results” is now paused.')).toHaveAttribute(
      'role',
      'status',
    )
    await user.click(await screen.findByRole('button', { name: 'Resume “Presenting survey results”' }))
    expect(await screen.findByText('“Presenting survey results” is now active.')).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/decks/1/status').map((c) => c.body)).toEqual([
      { to: 'paused' },
      { to: 'active' },
    ])
    // The Today card's plan is refetched after each change.
    expect(calls.filter((c) => c.path === '/session/today').length).toBeGreaterThanOrEqual(3)
  })

  it('moves a deck within the manual group and sends every deck that is not done', async () => {
    const user = userEvent.setup()
    const { calls } = server()
    renderApp('/queue')
    await screen.findByText('Small talk')
    const up = screen.getByRole('button', { name: 'Move “Presenting survey results” up' })
    await user.click(up)
    expect(await screen.findByText('“Presenting survey results” moved up: it is now number 2.')).toBeInTheDocument()
    const puts = calls.filter((c) => c.method === 'PUT')
    expect(puts.map((c) => c.body)).toEqual([{ deck_ids: [2, 1, 3, 6, 4] }])
    await waitFor(() =>
      expect(names()).toEqual([
        '1. Causal inference reading',
        '2. Presenting survey results',
        '3. Job interview phrases',
        '4. Deadline passed',
        '5. Small talk',
      ]),
    )
    // The focus comes back to the button once the list is fresh.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Move “Presenting survey results” down' })).toHaveFocus(),
    )
  })

  it('never moves a deck with a deadline to come, and says why', async () => {
    server()
    renderApp('/queue')
    await screen.findByText('Small talk')
    const dated = cardOf('Causal inference reading')
    expect(within(dated).queryByRole('button', { name: /^Move/ })).toBeNull()
    expect(dated).toHaveTextContent('Placed by its deadline.')
    expect(screen.getByText(/cannot be moved by hand/)).toBeInTheDocument()
    // The first manual deck cannot go above the dated ones; the last cannot go down.
    expect(screen.getByRole('button', { name: 'Move “Job interview phrases” up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move “Small talk” down' })).toBeDisabled()
  })

  it('reloads the list and explains a refused reorder (422) or status change (409)', async () => {
    const user = userEvent.setup()
    const { calls } = server(initial(), {
      'PUT /decks/queue': () => apiErrorResponse(422, 'invalid_queue'),
      'POST /decks/4/status': () =>
        apiErrorResponse(409, 'invalid_transition', 'no', { from_status: 'queued', to_status: 'x' }),
    })
    renderApp('/queue')
    await screen.findByText('Small talk')
    const gets = () => calls.filter((c) => c.method === 'GET' && c.path === '/decks').length
    const before = gets()
    await user.click(screen.getByRole('button', { name: 'Move “Small talk” up' }))
    expect(await screen.findByText('Nothing was changed; the list was loaded again.')).toBeInTheDocument()
    await waitFor(() => expect(gets()).toBe(before + 1))
    await user.click(await screen.findByRole('button', { name: 'Pause “Small talk”' }))
    expect(await screen.findByText('This status change is not allowed.')).toBeInTheDocument()
    await waitFor(() => expect(gets()).toBe(before + 2))
  })

  it('is linked from the Today card and from the decks page', async () => {
    server()
    const home = renderApp('/')
    expect(await screen.findByRole('link', { name: 'Manage the queue' })).toHaveAttribute('href', '/queue')
    home.unmount()
    renderApp('/library/decks')
    expect(await screen.findByRole('link', { name: 'Manage the queue' })).toHaveAttribute('href', '/queue')
  })

  it('is translated into French', async () => {
    await i18n.changeLanguage('fr')
    server()
    renderApp('/queue')
    await screen.findByRole('heading', { name: 'File des paquets' })
    await screen.findByText('Small talk')
    expect(cardOf('Job interview phrases')).toHaveTextContent('En pause')
    expect(screen.getByRole('button', { name: 'Reprendre « Job interview phrases »' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Monter « Small talk »' })).toBeInTheDocument()
    expect(screen.getByText('Terminés (1 paquet)')).toBeInTheDocument()
    expect(cardOf('Causal inference reading')).toHaveTextContent(
      '30 termes à découvrir en 34 jours : il faut 1 nouveau terme par jour.',
    )
  })
})
