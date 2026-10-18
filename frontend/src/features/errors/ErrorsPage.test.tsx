import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ERROR_SOURCES } from '../../api/errors'
import i18n from '../../i18n'
import { errorPage, errorRow, manyErrors } from '../../test/errorFixtures'
import { mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
}

const listCalls = (calls: RecordedCall[]) =>
  calls.filter((c) => c.method === 'GET' && c.path.startsWith('/errors?'))
const lastQuery = (calls: RecordedCall[]) =>
  new URLSearchParams(listCalls(calls).at(-1)?.path.split('?')[1] ?? '')

const rows = [
  errorRow(11),
  errorRow(12, {
    source: 'transcript',
    erroneous_text: 'I am agree',
    correction: 'I agree',
    production_attempt_id: 8,
    term: { id: 7, term: 'drill down' },
  }),
  errorRow(13, { source: 'manual', production_attempt_id: null }),
]

describe('Error log page', () => {
  it('lists the errors with their labels, links and the facets', async () => {
    const calls = mockApi({ ...base, 'GET /errors': errorPage(rows, { total: 3 }) })
    renderApp('/errors')

    expect(await screen.findByRole('heading', { level: 1, name: 'Error log' })).toHaveFocus()
    expect(await screen.findByRole('link', { name: 'I am agree' })).toHaveAttribute('href', '/errors/12')
    expect(screen.getByRole('status')).toHaveTextContent('3 errors')
    const table = screen.getByRole('table')
    // The label of the category, with its code next to it.
    expect(within(table).getAllByText('Fixed expression')).toHaveLength(3)
    expect(within(table).getAllByText('grammar.preposition.fixed_expression')).toHaveLength(3)
    expect(within(table).getByRole('link', { name: 'drill down' })).toHaveAttribute(
      'href',
      '/library/items/7',
    )
    // A written production has a link; a transcript and a manual entry have none.
    expect(within(table).getAllByRole('link', { name: 'Open the text' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Fixed expression (7)' })).toBeInTheDocument()
    expect(lastQuery(calls).get('page')).toBe('1')
    expect(lastQuery(calls).get('page_size')).toBe('25')
  })

  it('applies the filters: exact query string, local-midnight dates and the page URL', async () => {
    const calls = mockApi({ ...base, 'GET /errors': errorPage(rows) })
    const user = userEvent.setup()
    const { router } = renderApp('/errors')
    await screen.findByRole('table')

    await user.selectOptions(screen.getByLabelText('Category'), 'grammar.preposition')
    await user.selectOptions(screen.getByLabelText('Source'), 'writing')
    await user.type(screen.getByLabelText('Search the texts'), 'campus')
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-10-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-18' } })
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(lastQuery(calls).get('category')).toBe('grammar.preposition'))
    const query = lastQuery(calls)
    expect(query.get('source')).toBe('writing')
    expect(query.get('q')).toBe('campus')
    expect(query.get('occurred_from')).toBe(new Date(2026, 9, 1).toISOString())
    // "To" is a day wanted, and the backend's bound is exclusive: the start of the next day.
    expect(query.get('occurred_to')).toBe(new Date(2026, 9, 19).toISOString())
    expect(query.get('page')).toBe('1')

    const url = new URLSearchParams(router.state.location.search)
    expect(Object.fromEntries(url)).toEqual({
      category: 'grammar.preposition',
      source: 'writing',
      q: 'campus',
      from: '2026-10-01',
      to: '2026-10-18',
    })

    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('reads the filters from the URL and shows them in the form', async () => {
    const calls = mockApi({ ...base, 'GET /errors': errorPage(rows) })
    renderApp('/errors?category=grammar.tense&source=review&q=lived&from=2026-10-01')

    expect(await screen.findByLabelText('Source')).toHaveValue('review')
    expect(screen.getByLabelText('Category')).toHaveValue('grammar.tense')
    expect(screen.getByLabelText('Search the texts')).toHaveValue('lived')
    expect(screen.getByLabelText('From')).toHaveValue('2026-10-01')
    await waitFor(() => expect(lastQuery(calls).get('category')).toBe('grammar.tense'))
    expect(lastQuery(calls).get('source')).toBe('review')
  })

  it('offers the seven sources', async () => {
    mockApi({ ...base, 'GET /errors': errorPage(rows) })
    renderApp('/errors')
    const select = await screen.findByLabelText('Source')
    const values = within(select)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value)
    expect(values).toEqual(['', ...ERROR_SOURCES])
    expect(ERROR_SOURCES).toHaveLength(7)
  })

  it('filters by a facet, and clicking the pressed facet clears it', async () => {
    const calls = mockApi({ ...base, 'GET /errors': errorPage(rows) })
    const user = userEvent.setup()
    const { router } = renderApp('/errors')

    const facet = await screen.findByRole('button', { name: 'Past simple or present perfect (3)' })
    expect(facet).toHaveAttribute('aria-pressed', 'false')
    await user.click(facet)
    await waitFor(() =>
      expect(lastQuery(calls).get('category')).toBe('grammar.tense.past_simple_vs_present_perfect'),
    )
    expect(router.state.location.search).toBe(
      '?category=grammar.tense.past_simple_vs_present_perfect',
    )
    const pressed = await screen.findByRole('button', {
      name: 'Past simple or present perfect (3)',
      pressed: true,
    })
    await user.click(pressed)
    await waitFor(() => expect(router.state.location.search).toBe(''))
  })

  it('pages by 25 and keeps the page in the URL', async () => {
    const calls = mockApi({
      ...base,
      'GET /errors': (call) => {
        const page = Number(new URLSearchParams(call.path.split('?')[1]).get('page'))
        return Response.json(
          errorPage(manyErrors(page === 1 ? 25 : 10, page === 1 ? 1 : 26), { total: 35, page }),
        )
      },
    })
    const user = userEvent.setup()
    const { router } = renderApp('/errors')

    expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(26) // header + 25
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument()
    expect(router.state.location.search).toBe('?page=2')
    expect(lastQuery(calls).get('page')).toBe('2')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(11)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('shows the term chip of item_id, and removing it drops the filter', async () => {
    const calls = mockApi({
      ...base,
      'GET /errors': errorPage(rows),
      'GET /items/7': { id: 7, term: 'drill down', status: 'learning', item_type: 'phrase' },
    })
    const user = userEvent.setup()
    const { router } = renderApp('/errors?item_id=7')

    expect(await screen.findByText('Term: drill down')).toBeInTheDocument()
    await waitFor(() => expect(lastQuery(calls).get('item_id')).toBe('7'))
    await user.click(screen.getByRole('button', { name: 'Remove the term filter' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
    await waitFor(() => expect(screen.queryByText('Term: drill down')).not.toBeInTheDocument())
    expect(lastQuery(calls).has('item_id')).toBe(false)
  })

  it('says why the list is empty, with and without filters', async () => {
    mockApi({ ...base, 'GET /errors': errorPage([], { total: 0, facets: [] }) })
    const first = renderApp('/errors')
    expect(await screen.findByText(/Your error log is empty/)).toBeInTheDocument()
    first.unmount()

    renderApp('/errors?q=nothing')
    expect(await screen.findByText('No error matches these filters.')).toBeInTheDocument()
  })

  it('shows an error when the list cannot be loaded', async () => {
    mockApi({ ...base })
    renderApp('/errors')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('is in French when the language is French', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /errors': errorPage(rows, { total: 3 }) })
    renderApp('/errors')
    expect(await screen.findByRole('heading', { level: 1, name: "Journal d'erreurs" })).toBeInTheDocument()
    expect(await screen.findByText('3 erreurs')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expression figée (7)' })).toBeInTheDocument()
    expect(screen.getByLabelText('Origine')).toBeInTheDocument()
    expect(screen.getAllByText('Écriture').length).toBeGreaterThan(0)
  })
})
