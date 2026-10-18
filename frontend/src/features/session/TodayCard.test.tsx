import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { PlanWarning, SessionPlan } from '../../api/session'
import { deck, newItemEntry, plan, reviewEntry, studySession } from '../../test/fixtures'
import { mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const decks = [
  deck(1, 'Causal inference reading', { deadline: '2026-11-20' }),
  deck(2, 'Job interview phrases'),
]

function routes(todayPlan: SessionPlan, open = false) {
  return {
    'GET /health': { status: 'ok', version: '0.1.0', demo: false },
    'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
    'GET /session/today': { plan: todayPlan, open_session: open ? studySession(5) : null },
    'GET /decks': decks,
  }
}

function card() {
  return screen.getByRole('region', { name: "Today's session" })
}

const busyPlan = plan({
  blocks: [
    { kind: 'reviews', estimated_seconds: 90, entries: [reviewEntry(1, 10), reviewEntry(2, 11), reviewEntry(3, 12)] },
    {
      kind: 'new_items',
      estimated_seconds: 360,
      entries: [newItemEntry(20, 1), newItemEntry(21, 1), newItemEntry(22, 2)],
    },
    {
      kind: 'targeted_practice',
      estimated_seconds: 300,
      entries: [
        {
          kind: 'targeted_practice',
          category_code: 'grammar.preposition',
          error_count: 4,
          estimated_seconds: 300,
          overflow: false,
        },
      ],
    },
  ],
  total_seconds: 750,
})

describe('Today card', () => {
  it('names the targeted category by its label in the interface language', async () => {
    mockApi({ ...routes(busyPlan), 'GET /error-categories': categoryTree() })
    renderApp('/')
    expect(await screen.findByText(/Targeted practice: Prepositions \(4 recent errors\)/)).toBeInTheDocument()
    expect(screen.queryByText(/grammar\.preposition/)).toBeNull()
  })

  it('shows the plan: reviews, new terms per deck, minutes against the budget, practice', async () => {
    mockApi(routes(busyPlan))
    renderApp('/')

    expect(await screen.findByText('3 reviews due')).toBeInTheDocument()
    expect(screen.getByText('3 new terms to discover')).toBeInTheDocument()
    expect(await screen.findByText('Causal inference reading: 2')).toBeInTheDocument()
    expect(screen.getByText('Job interview phrases: 1')).toBeInTheDocument()
    expect(screen.getByText('About 13 min, for a daily budget of 45 min')).toBeInTheDocument()
    expect(screen.getByText(/Targeted practice: grammar.preposition \(4 recent errors\)/)).toBeInTheDocument()
    expect(within(card()).getByRole('link', { name: "Start today's session" })).toHaveAttribute(
      'href',
      '/session',
    )
  })

  it('offers to resume the session already open today', async () => {
    mockApi(routes(busyPlan, true))
    renderApp('/')

    expect(await screen.findByRole('link', { name: "Resume today's session" })).toHaveAttribute(
      'href',
      '/session',
    )
    expect(screen.queryByRole('link', { name: "Start today's session" })).not.toBeInTheDocument()
  })

  it('says clearly when there is nothing to do, with links to the import and the library', async () => {
    mockApi(routes(plan()))
    renderApp('/')

    expect(await screen.findByText(/Nothing to review or discover today/)).toBeInTheDocument()
    expect(within(card()).getByRole('link', { name: 'Import a list' })).toHaveAttribute('href', '/import')
    expect(within(card()).getByRole('link', { name: 'Open the library' })).toHaveAttribute(
      'href',
      '/library',
    )
    expect(within(card()).queryByRole('link', { name: /session/ })).not.toBeInTheDocument()
  })

  it('translates every warning with the data needed to act on it', async () => {
    const warnings: PlanWarning[] = [
      {
        code: 'reviews_over_budget',
        params: { review_seconds: 3000, budget_seconds: 2700, overflow_count: 4 },
      },
      {
        code: 'deadline_unrealistic',
        params: {
          deck_id: 1,
          deadline: '2026-11-20',
          remaining: 80,
          required_per_day: 3,
          achievable_per_day: 2,
          projected_finish: '2026-12-25',
        },
      },
      { code: 'deadline_passed', params: { deck_id: 2, deadline: '2026-10-01', remaining: 1 } },
      { code: 'deadline_triage_pending', params: { deck_id: 1, count: 3 } },
      { code: 'items_without_sheet', params: { count: 2, deck_ids: [2, 1] } },
    ]
    mockApi(
      routes(
        plan({
          warnings,
          deadline_paces: [
            { deck_id: 1, deadline: '2026-11-20', remaining: 80, days_left: 34, required_per_day: 3 },
          ],
        }),
      ),
    )
    renderApp('/')

    const list = await screen.findByRole('region', { name: 'Warnings' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(5)
    await within(list).findAllByText(/Causal inference reading/)
    expect(items[0]).toHaveTextContent(
      'Due reviews need about 50 min, more than your 45 min budget: no new term today.',
    )
    expect(items[1]).toHaveTextContent(
      '“Causal inference reading” (deadline November 20, 2026): 3 new terms a day are needed, but only 2 fit in your budget. At this pace the deck would be finished on December 25, 2026.',
    )
    expect(items[2]).toHaveTextContent(
      'The deadline of “Job interview phrases” (October 1, 2026) has passed with 1 term still to discover.',
    )
    expect(items[3]).toHaveTextContent(
      '“Causal inference reading” (deadline November 20, 2026) still has 3 terms to sort.',
    )
    expect(within(items[3]).getByRole('link', { name: 'Sort them now' })).toHaveAttribute(
      'href',
      '/triage?deck=1',
    )
    expect(items[4]).toHaveTextContent('2 queued terms have no usable sheet yet')
    expect(within(items[4]).getByRole('link', { name: 'Job interview phrases' })).toHaveAttribute(
      'href',
      '/library?deck=2',
    )
    expect(within(items[4]).getByRole('link', { name: 'Causal inference reading' })).toHaveAttribute(
      'href',
      '/library?deck=1',
    )
    expect(within(items[4]).getByRole('link', { name: 'Write or generate the sheets' })).toHaveAttribute(
      'href',
      '/enrichment',
    )
  })

  it('is translated into French', async () => {
    mockApi(
      routes(
        plan({
          blocks: [{ kind: 'reviews', estimated_seconds: 30, entries: [reviewEntry(1, 10)] }],
          total_seconds: 30,
          warnings: [{ code: 'items_without_sheet', params: { count: 1, deck_ids: [1] } }],
        }),
      ),
    )
    const user = userEvent.setup()
    renderApp('/')

    await screen.findByText('1 review due')
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')

    expect(screen.getByRole('heading', { name: 'Séance du jour' })).toBeInTheDocument()
    expect(screen.getByText('1 révision due')).toBeInTheDocument()
    expect(
      screen.getByText(/1 terme en file n'a pas encore de fiche utilisable/),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Démarrer la séance du jour' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Aujourd'hui" })).toBeInTheDocument()
  })
})
