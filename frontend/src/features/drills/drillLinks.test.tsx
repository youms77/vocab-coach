import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { PracticeStep, SessionPlan, Step } from '../../api/session'
import i18n from '../../i18n'
import { drillOf, GAP_ON } from '../../test/drillFixtures'
import { errorPage, errorRow } from '../../test/errorFixtures'
import { plan, progress, studySession } from '../../test/fixtures'
import { mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { node } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /decks': [],
  'GET /error-categories': [
    node('grammar', 'Grammar', 'Grammaire', [
      node('grammar.preposition', 'Prepositions', 'Prépositions', [
        node('grammar.preposition.fixed_expression', 'Fixed expression', 'Expression figée'),
      ]),
      node('grammar.tense', 'Tenses', 'Temps', [], { status: 'proposed' }),
    ]),
    node('pronunciation', 'Pronunciation', 'Prononciation', [
      node('pronunciation.stress', 'Word stress', 'Accent de mot'),
    ]),
  ],
  'GET /drills': { items: [drillOf([GAP_ON])], total: 1, limit: 20, offset: 0 },
}

// --- The session's practice_info step ---------------------------------------------------------------

function sessionRoutes(practice: PracticeStep) {
  const step = {
    session_id: 7,
    progress: progress(),
    type: 'practice_info',
    practice,
  } as Step
  return {
    ...base,
    'GET /session/today': { plan: plan(), open_session: null },
    'POST /session/start': () => Response.json(studySession(7), { status: 201 }),
    'GET /session/7/next': () => Response.json(step),
  }
}

describe('Practise now: the session step', () => {
  it('links the targeted practice to the drills page and carries the session', async () => {
    mockApi(
      sessionRoutes({
        targeted_practice: { category_code: 'grammar.preposition', error_count: 5 },
        consolidation_task_id: null,
      }),
    )
    const user = userEvent.setup()
    const { router } = renderApp('/session')

    const link = await screen.findByRole('link', { name: 'Practise now' })
    expect(link).toHaveAttribute('href', '/drills?category=grammar.preposition')
    // "Continue" is still there and unchanged.
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    // The text no longer says that nothing can be done now.
    expect(screen.queryByText(/available in a later version/)).toBeNull()

    await user.click(link)
    await waitFor(() => expect(router.state.location.pathname).toBe('/drills'))
    expect(router.state.location.search).toBe('?category=grammar.preposition')
    expect(router.state.location.state).toEqual({ fromSession: 7 })
    expect(await screen.findByText("This drill is part of today's session.")).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
  })

  it('has no link for a consolidation task alone, nor for a category that cannot be drilled', async () => {
    mockApi(sessionRoutes({ targeted_practice: null, consolidation_task_id: 3 }))
    const first = renderApp('/session')
    await screen.findByText(/A consolidation task/)
    expect(screen.queryByRole('link', { name: 'Practise now' })).toBeNull()
    expect(screen.getByText(/available in a later version/)).toBeInTheDocument()
    first.unmount()

    mockApi(
      sessionRoutes({
        targeted_practice: { category_code: 'pronunciation.stress', error_count: 3 },
        consolidation_task_id: null,
      }),
    )
    renderApp('/session')
    await screen.findByText(/Targeted practice on your most frequent errors/)
    expect(screen.queryByRole('link', { name: 'Practise now' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument()
  })

  it('is translated', async () => {
    await i18n.changeLanguage('fr')
    mockApi(
      sessionRoutes({
        targeted_practice: { category_code: 'grammar.preposition', error_count: 5 },
        consolidation_task_id: null,
      }),
    )
    renderApp('/session')
    expect(await screen.findByRole('link', { name: "S'entraîner maintenant" })).toHaveAttribute(
      'href',
      '/drills?category=grammar.preposition',
    )
  })
})

// --- The Today card ---------------------------------------------------------------------------------

const todayPlan = (code = 'grammar.preposition'): SessionPlan =>
  plan({
    blocks: [
      {
        kind: 'targeted_practice',
        estimated_seconds: 300,
        entries: [
          {
            kind: 'targeted_practice',
            category_code: code,
            error_count: 4,
            estimated_seconds: 300,
            overflow: false,
          },
        ],
      },
    ],
    total_seconds: 300,
  })

describe('Practise now: the Today card', () => {
  it('links the targeted category, with the session when one is open', async () => {
    mockApi({ ...base, 'GET /session/today': { plan: todayPlan(), open_session: studySession(5) } })
    const user = userEvent.setup()
    const { router } = renderApp('/')

    const card = await screen.findByRole('region', { name: "Today's session" })
    const link = await within(card).findByRole('link', { name: 'Practise now' })
    expect(link).toHaveAttribute('href', '/drills?category=grammar.preposition')
    await user.click(link)
    await waitFor(() => expect(router.state.location.pathname).toBe('/drills'))
    expect(router.state.location.state).toEqual({ fromSession: 5 })
  })

  it('carries no session when none is open', async () => {
    mockApi({ ...base, 'GET /session/today': { plan: todayPlan(), open_session: null } })
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await user.click(await screen.findByRole('link', { name: 'Practise now' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/drills'))
    expect(router.state.location.state).toBeNull()
    expect(screen.queryByText("This drill is part of today's session.")).toBeNull()
  })

  it('has no link for a category that cannot be drilled', async () => {
    mockApi({ ...base, 'GET /session/today': { plan: todayPlan('pronunciation.stress'), open_session: null } })
    renderApp('/')
    await screen.findByText(/Targeted practice: /)
    expect(screen.queryByRole('link', { name: 'Practise now' })).toBeNull()
  })
})

// --- The categories page and the error log ----------------------------------------------------------

describe('Practise this category: the categories page', () => {
  it('links the active categories that can be drilled, and only those', async () => {
    mockApi(base)
    renderApp('/errors/categories')
    const taxonomy = (await screen.findByRole('heading', { name: 'Taxonomy' })).closest('section') as HTMLElement

    const links = await within(taxonomy).findAllByRole('link', { name: /^Practise this category/ })
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/drills?category=grammar.preposition',
      '/drills?category=grammar.preposition.fixed_expression',
    ])
    expect(links[0]).toHaveAccessibleName('Practise this category: Prepositions')
    // Not the level-1 Grammar, not the proposed Tenses, not pronunciation.
    expect(within(taxonomy).getAllByText('Practise this category')).toHaveLength(2)
  })

  it('is translated', async () => {
    await i18n.changeLanguage('fr')
    mockApi(base)
    renderApp('/errors/categories')
    const links = await screen.findAllByRole('link', { name: /^S'entraîner sur cette catégorie/ })
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAccessibleName('S\'entraîner sur cette catégorie : Prépositions')
  })

  it('opens the drills page with the category chosen and nothing started', async () => {
    const calls = mockApi(base)
    const user = userEvent.setup()
    const { router } = renderApp('/errors/categories')
    const taxonomy = (await screen.findByRole('heading', { name: 'Taxonomy' })).closest('section') as HTMLElement
    await user.click(await within(taxonomy).findByRole('link', { name: 'Practise this category: Fixed expression' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/drills'))
    await waitFor(() =>
      expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition.fixed_expression'),
    )
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })
})

describe('The error log and the drills', () => {
  const drillError = errorRow(21, { source: 'drill', production_attempt_id: 7 })

  it('links "Targeted drills" and opens the drill of a drill error', async () => {
    mockApi({ ...base, 'GET /errors': errorPage([drillError, errorRow(22)], { total: 2 }) })
    renderApp('/errors')

    expect(await screen.findByRole('link', { name: 'Targeted drills' })).toHaveAttribute('href', '/drills')
    const table = await screen.findByRole('table')
    const link = within(table).getByRole('link', { name: 'Open the drill' })
    expect(link).toHaveAttribute('href', '/drills/7')
    // The written error keeps its own link.
    expect(within(table).getByRole('link', { name: 'Open the text' })).toHaveAttribute('href', '/writing/5')
  })

  it('opens the drill from the detail of a drill error', async () => {
    mockApi({ ...base, 'GET /errors/21': drillError })
    renderApp('/errors/21')
    expect(await screen.findByRole('link', { name: 'Open the drill it comes from' })).toHaveAttribute(
      'href',
      '/drills/7',
    )
  })

  it('is translated', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /errors': errorPage([drillError], { total: 1 }) })
    renderApp('/errors')
    expect(await screen.findByRole('link', { name: 'Exercices ciblés' })).toHaveAttribute('href', '/drills')
    expect(await screen.findByRole('link', { name: "Ouvrir l'exercice" })).toHaveAttribute('href', '/drills/7')
  })
})
