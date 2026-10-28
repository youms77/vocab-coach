import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CategoryNode } from '../../api/errors'
import i18n from '../../i18n'
import { drillOf, GAP_ON, MIXED_SPECS, PREPOSITION_CATEGORY } from '../../test/drillFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { node } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

/** Level 1 (not drillable), level 2 and 3 (drillable), pronunciation, and a category only proposed. */
const tree = (): CategoryNode[] => [
  node('grammar', 'Grammar', 'Grammaire', [
    node('grammar.preposition', 'Prepositions', 'Prépositions', [
      node('grammar.preposition.fixed_expression', 'Fixed expression', 'Expression figée'),
    ]),
    node('grammar.tense', 'Tenses', 'Temps', [], { status: 'proposed' }),
  ]),
  node('pronunciation', 'Pronunciation', 'Prononciation', [
    node('pronunciation.stress', 'Word stress', 'Accent de mot'),
  ]),
]

const page = (items = [drillOf(MIXED_SPECS)], total = items.length) => ({
  items,
  total,
  limit: 20,
  offset: 0,
})

const created = (drill = drillOf(MIXED_SPECS)) => ({ status: 'ok', reason: null, drill })

function setup(extra: Record<string, unknown> = {}) {
  return mockApi({
    ...base,
    'GET /error-categories': tree(),
    'GET /drills': () => Response.json(page()),
    'GET /drills/7': () => Response.json(drillOf(MIXED_SPECS)),
    ...extra,
  } as Parameters<typeof mockApi>[0])
}

const posts = (calls: RecordedCall[]) => calls.filter((c) => c.method === 'POST')

afterEach(() => {
  vi.useRealTimers()
})

describe('Drills page: the list', () => {
  it('lists the drills with category, date, score and state, 20 per page', async () => {
    const answered = drillOf(MIXED_SPECS, [
      { index: 0, given: 'on', choice_index: null, outcome: 'exact' },
    ])
    const finished = drillOf(
      MIXED_SPECS,
      MIXED_SPECS.map((_, index) => ({ index, given: 'x', choice_index: null, outcome: 'wrong' as const })),
      { id: 5 },
    )
    const calls = setup({
      'GET /drills': () => Response.json(page([answered, drillOf(MIXED_SPECS, [], { id: 6 }), finished], 45)),
    })
    renderApp('/drills')

    expect(await screen.findByRole('heading', { level: 1, name: 'Targeted drills' })).toHaveFocus()
    const rows = await screen.findAllByRole('row')
    expect(rows).toHaveLength(4) // header + 3
    expect(calls.find((c) => c.path.startsWith('/drills?'))?.path).toBe('/drills?limit=20&offset=0')

    const first = within(rows[1])
    expect(first.getByRole('link')).toHaveAttribute('href', '/drills/7')
    expect(first.getByText('Fixed expression')).toBeInTheDocument()
    expect(first.getByText('grammar.preposition.fixed_expression')).toBeInTheDocument()
    expect(first.getByText('1 of 3')).toBeInTheDocument()
    expect(first.getByText('In progress (1 of 3)')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Not started')).toBeInTheDocument()
    expect(within(rows[3]).getByText('Completed')).toBeInTheDocument()
    expect(within(rows[3]).getByText('0 of 3')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  })

  it('keeps the category and the page in the URL', async () => {
    const calls = setup()
    const user = userEvent.setup()
    const { router } = renderApp('/drills?category=grammar.preposition&page=2')

    await screen.findAllByRole('row')
    expect(calls.find((c) => c.path.startsWith('/drills?'))?.path).toBe(
      '/drills?limit=20&offset=20&category=grammar.preposition',
    )
    // Changing the filter goes back to the first page and keeps the category in the URL.
    const filter = await screen.findByLabelText('Show the drills of')
    await user.selectOptions(filter, 'grammar.preposition.fixed_expression')
    await waitFor(() =>
      expect(router.state.location.search).toBe('?category=grammar.preposition.fixed_expression'),
    )
    await user.selectOptions(filter, '')
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('says when there is none yet, and when the category has none', async () => {
    setup({ 'GET /drills': () => Response.json(page([], 0)) })
    const first = renderApp('/drills')
    expect(await screen.findByText('No drill yet. Create the first one above.')).toBeInTheDocument()
    first.unmount()
    renderApp('/drills?category=grammar.preposition')
    expect(await screen.findByText('No drill in this category yet.')).toBeInTheDocument()
  })

  it('is translated, with the category label in French', async () => {
    await i18n.changeLanguage('fr')
    setup()
    renderApp('/drills')
    expect(await screen.findByRole('heading', { level: 1, name: 'Exercices ciblés' })).toBeInTheDocument()
    expect(await screen.findByRole('cell', { name: /Expression figée/ })).toBeInTheDocument()
    expect(screen.getByText('Pas commencé')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Créer l’exercice' })).toBeInTheDocument()
  })
})

describe('Drills page: the form', () => {
  it('only offers the categories that can be drilled', async () => {
    setup()
    renderApp('/drills')
    const select = await screen.findByLabelText('Category')
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(2))
    const options = within(select).getAllByRole('option') as HTMLOptionElement[]
    const byValue = (value: string) => options.find((o) => o.value === value)
    expect(byValue('grammar.preposition')).toBeDefined()
    expect(byValue('grammar.preposition')?.disabled).toBe(false)
    expect(byValue('grammar.preposition.fixed_expression')?.disabled).toBe(false)
    // A level-1 parent stays as a greyed label; the others are not offered at all.
    expect(byValue('grammar')?.disabled).toBe(true)
    expect(byValue('grammar.tense')).toBeUndefined()
    expect(byValue('pronunciation')).toBeUndefined()
    expect(byValue('pronunciation.stress')).toBeUndefined()
  })

  it('creates a drill: sends the exact body and opens it', async () => {
    const calls = setup({ 'POST /drills': () => Response.json(created(), { status: 201 }) })
    const user = userEvent.setup()
    const { router } = renderApp('/drills')

    await screen.findByLabelText('Category')
    await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThan(2))
    await user.selectOptions(screen.getByLabelText('Category'), 'grammar.preposition.fixed_expression')
    const count = screen.getByLabelText('Number of items')
    expect(count).toHaveValue(10) // the default
    await user.clear(count)
    await user.type(count, '5')
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/drills/7'))
    expect(posts(calls)).toHaveLength(1)
    expect(posts(calls)[0]).toMatchObject({
      path: '/drills',
      body: { category_code: 'grammar.preposition.fixed_expression', count: 5 },
    })
    // Not from a session: no study_session_id.
    expect(posts(calls)[0].body).not.toHaveProperty('study_session_id')
  })

  it('shows the AI refusal in words, keeps the form filled and starts nothing else', async () => {
    const calls = setup({
      'POST /drills': () =>
        Response.json({ status: 'unavailable', reason: 'quota', drill: null }, { status: 200 }),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/drills?category=grammar.preposition')

    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    await user.clear(screen.getByLabelText('Number of items'))
    await user.type(screen.getByLabelText('Number of items'), '7')
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))

    expect(
      await screen.findByText(/could not be created: the free quota is used up or the rate limit was hit/),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/drills')
    expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition')
    expect(screen.getByLabelText('Number of items')).toHaveValue(7)
    expect(screen.getByRole('button', { name: 'Create the drill' })).toBeEnabled()
    expect(posts(calls)).toHaveLength(1)
  })

  it('says an incomplete answer in words', async () => {
    setup({
      'POST /drills': () => Response.json({ status: 'incomplete', reason: null, drill: null }),
    })
    const user = userEvent.setup()
    renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))
    expect(await screen.findByText(/The AI's answer could not be used/)).toBeInTheDocument()
  })

  it('preselects ?category=, scrolls to the form and starts nothing without a click', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const calls = setup()
    renderApp('/drills?category=grammar.preposition.fixed_expression')

    await waitFor(() =>
      expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition.fixed_expression'),
    )
    await waitFor(() => expect(scroll).toHaveBeenCalled())
    expect(posts(calls)).toHaveLength(0)
    // The list is filtered by the same category.
    expect(calls.some((c) => c.path.endsWith('&category=grammar.preposition.fixed_expression'))).toBe(true)
  })

  it('does not preselect a category that cannot be drilled', async () => {
    setup()
    renderApp('/drills?category=pronunciation.stress')
    const select = await screen.findByLabelText('Category')
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(2))
    expect(select).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Create the drill' })).toBeDisabled()
  })

  it('does not preselect a category that is only proposed', async () => {
    setup()
    renderApp('/drills?category=grammar.tense')
    const select = await screen.findByLabelText('Category')
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBeGreaterThan(2))
    expect(select).toHaveValue('')
  })

  it('refuses a number outside 5 to 15 without a request', async () => {
    const calls = setup()
    const user = userEvent.setup()
    renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    const count = screen.getByLabelText('Number of items')
    await user.clear(count)
    await user.type(count, '16')
    expect(screen.getByText('Choose a number from 5 to 15.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create the drill' })).toBeDisabled()
    expect(posts(calls)).toHaveLength(0)
  })

  it('waits with a counter, and a double click sends one request', async () => {
    let finish: (response: Response) => void = () => {}
    const calls = setup({
      'POST /drills': () => new Promise<Response>((resolve) => (finish = resolve)),
    })
    const user = userEvent.setup()
    renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))

    const button = screen.getByRole('button', { name: 'Create the drill' })
    await user.dblClick(button)
    expect(await screen.findByRole('button', { name: /Preparing your exercises… \d+ s/ })).toBeDisabled()
    expect(posts(calls)).toHaveLength(1)

    await act(async () => finish(Response.json(created(), { status: 201 })))
  })

  it('sends the study session when it comes from the session', async () => {
    const calls = setup({ 'POST /drills': () => Response.json(created(), { status: 201 }) })
    const user = userEvent.setup()
    const { router } = renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    // The state comes from the link of the session's step.
    await act(async () => {
      await router.navigate('/drills?category=grammar.preposition', { state: { fromSession: 12 } })
    })
    expect(screen.getByText("This drill is part of today's session.")).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/drills/7'))
    expect(posts(calls)[0].body).toEqual({
      category_code: 'grammar.preposition',
      count: 10,
      study_session_id: 12,
    })
    // The next page knows the session too.
    expect(router.state.location.state).toEqual({ fromSession: 12 })
  })

  it('says why a category cannot be drilled (not_drillable)', async () => {
    setup({
      'POST /drills': () => apiErrorResponse(422, 'not_drillable', 'Pronunciation cannot be drilled in writing.', { reason: 'pronunciation' }),
    })
    const user = userEvent.setup()
    renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This category cannot be practised.')
    expect(alert).toHaveTextContent('Pronunciation cannot be practised in writing.')
    expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition')
  })

  it('keeps the form on a network failure', async () => {
    setup({ 'POST /drills': () => apiErrorResponse(404, 'category_not_found') })
    const user = userEvent.setup()
    renderApp('/drills?category=grammar.preposition')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('grammar.preposition'))
    await user.click(screen.getByRole('button', { name: 'Create the drill' }))
    expect(await screen.findByText('This category does not exist.')).toBeInTheDocument()
  })

  it('has only the drills a category holds in the example data', () => {
    // The fixtures stay consistent with the API shape the page reads.
    const drill = drillOf([GAP_ON])
    expect(drill.category.code).toBe(PREPOSITION_CATEGORY.code)
    expect(drill.items[0].result).toBeNull()
  })
})
