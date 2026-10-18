import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { ErrorOut } from '../../api/errors'
import { errorPage, errorRow } from '../../test/errorFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
}

const calledWith = (calls: RecordedCall[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path)

/** A backend where error 11 can be read, patched (the answer merges the patch) and deleted. */
function backend(stored: ErrorOut = errorRow(11), extra: Record<string, unknown> = {}) {
  let current = stored
  return mockApi({
    ...base,
    'GET /errors/11': () => Response.json(current),
    'PATCH /errors/11': (call) => {
      const body = call.body as Record<string, unknown>
      const { category_code: code, lexical_item_id: itemId, ...fields } = body
      current = {
        ...current,
        ...fields,
        category:
          code === undefined
            ? current.category
            : { code: String(code), label_en: 'Past simple', label_fr: 'Prétérit', status: 'active' },
        term:
          itemId === undefined
            ? current.term
            : itemId === null
              ? null
              : { id: Number(itemId), term: 'drill down' },
        updated_at: '2026-10-19T09:00:00Z',
      } as ErrorOut
      return Response.json(current)
    },
    'DELETE /errors/11': () => new Response(null, { status: 204 }),
    'GET /errors': errorPage([errorRow(11)]),
    ...extra,
  })
}

describe('Error detail page', () => {
  it('marks the wrong form in the original sentence, with text and not only colour', async () => {
    backend()
    renderApp('/errors/11')

    expect(await screen.findByRole('heading', { level: 1, name: 'An error in your log' })).toHaveFocus()
    const mark = await screen.findByText('in campus', { selector: 'mark' })
    expect(mark.closest('p')).toHaveTextContent(
      'Since then, I lived in campus with two friends.',
    )
    // The incorrect form is also named in words, so the mark is not the only cue.
    expect(screen.getByText('Incorrect:')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the text it comes from' })).toHaveAttribute(
      'href',
      '/writing/5',
    )
  })

  it('does not fail when the wrong form is not in the sentence', async () => {
    backend(errorRow(11, { erroneous_text: 'on the campus' }))
    renderApp('/errors/11')

    expect(await screen.findByText('The incorrect form could not be located in the sentence.')).toBeInTheDocument()
    expect(screen.getByText(/Since then, I lived in campus/)).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('says so when no sentence was stored', async () => {
    backend(errorRow(11, { original_text: '' }))
    renderApp('/errors/11')
    expect(await screen.findByText('No sentence was stored with this error.')).toBeInTheDocument()
  })

  it('sends only the fields that changed', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/errors/11')

    const correction = await screen.findByLabelText('Correction')
    await user.clear(correction)
    await user.type(correction, 'on the campus')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    expect(calledWith(calls, 'PATCH', '/errors/11').map((c) => c.body)).toEqual([
      { correction: 'on the campus' },
    ])

    await user.selectOptions(
      screen.getByLabelText('Category'),
      'grammar.tense.past_simple_vs_present_perfect',
    )
    await user.click(screen.getByRole('button', { name: 'Add an option' }))
    await user.type(screen.getByLabelText('Other natural option 1'), 'at university')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calledWith(calls, 'PATCH', '/errors/11')).toHaveLength(2))
    expect(calledWith(calls, 'PATCH', '/errors/11')[1].body).toEqual({
      alternatives: ['at university'],
      category_code: 'grammar.tense.past_simple_vs_present_perfect',
    })
  })

  it('sends nothing when no field changed', async () => {
    const calls = backend()
    const user = userEvent.setup()
    renderApp('/errors/11')

    await user.click(await screen.findByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Nothing to save: no field has changed.')).toBeInTheDocument()
    expect(calledWith(calls, 'PATCH', '/errors/11')).toHaveLength(0)
  })

  it('warns that editing the explanation drops its French version', async () => {
    backend(errorRow(11, { explanation_fr: 'On dit « on campus ».' }))
    renderApp('/errors/11')
    expect(await screen.findByText('On dit « on campus ».')).toBeInTheDocument()
    expect(screen.getByText('Changing the explanation removes its French translation.')).toBeInTheDocument()
  })

  it('shows the English detail of invalid_error and the message of unknown_category', async () => {
    let answer = apiErrorResponse(422, 'invalid_error', 'The correction must differ from the wrong form.')
    backend(errorRow(11), { 'PATCH /errors/11': () => answer })
    const user = userEvent.setup()
    renderApp('/errors/11')

    const correction = await screen.findByLabelText('Correction')
    await user.type(correction, '!')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('This error cannot be saved.')).toBeInTheDocument()
    expect(screen.getByText('The correction must differ from the wrong form.')).toBeInTheDocument()

    answer = apiErrorResponse(422, 'unknown_category')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(
      await screen.findByText('This category cannot be used: choose an active one.'),
    ).toBeInTheDocument()
  })

  it('links a term found by search, and unlinks it', async () => {
    const calls = backend(errorRow(11), {
      'GET /items': {
        total: 1,
        items: [{ id: 7, term: 'drill down', status: 'learning', item_type: 'phrase' }],
      },
    })
    const user = userEvent.setup()
    renderApp('/errors/11')

    expect(await screen.findByText('No term is linked.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Search a term to link'), 'drill')
    await user.click(await screen.findByRole('button', { name: 'Link “drill down”' }))
    expect(screen.getByRole('link', { name: 'drill down' })).toHaveAttribute('href', '/library/items/7')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calledWith(calls, 'PATCH', '/errors/11')).toHaveLength(1))
    expect(calledWith(calls, 'PATCH', '/errors/11')[0].body).toEqual({ lexical_item_id: 7 })

    await user.click(await screen.findByRole('button', { name: 'Unlink the term' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calledWith(calls, 'PATCH', '/errors/11')).toHaveLength(2))
    expect(calledWith(calls, 'PATCH', '/errors/11')[1].body).toEqual({ lexical_item_id: null })
  })

  it('says when no term matches the search', async () => {
    backend(errorRow(11), { 'GET /items': { total: 0, items: [] } })
    const user = userEvent.setup()
    renderApp('/errors/11')
    await user.type(await screen.findByLabelText('Search a term to link'), 'zzz')
    expect(await screen.findByText('No term matches.')).toBeInTheDocument()
  })

  it('deletes after a confirmation (focus on "Keep it"), then returns to the filtered list', async () => {
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/errors?q=campus')

    await user.click(await screen.findByRole('link', { name: 'in campus' }))
    await user.click(await screen.findByRole('button', { name: 'Delete this error' }))
    const keep = screen.getByRole('button', { name: 'Keep it' })
    expect(keep).toHaveFocus()
    expect(calledWith(calls, 'DELETE', '/errors/11')).toHaveLength(0)

    await user.click(keep)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Delete this error' }))
    await user.click(screen.getByRole('button', { name: 'Yes, delete it' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/errors'))
    expect(router.state.location.search).toBe('?q=campus')
    expect(calledWith(calls, 'DELETE', '/errors/11')).toHaveLength(1)
    // The deleted error's own page is not asked for again (it would answer 404).
    expect(calledWith(calls, 'GET', '/errors/11')).toHaveLength(1)
  })

  it('goes back to the list with its filters from the back link', async () => {
    backend()
    const user = userEvent.setup()
    const { router } = renderApp('/errors?source=writing')
    await user.click(await screen.findByRole('link', { name: 'in campus' }))
    await user.click(await screen.findByRole('link', { name: '← Back to the error log' }))
    expect(router.state.location.pathname + router.state.location.search).toBe('/errors?source=writing')
  })

  it('shows a message when the error does not exist', async () => {
    mockApi({
      ...base,
      'GET /errors/99': () => apiErrorResponse(404, 'error_not_found'),
    })
    renderApp('/errors/99')
    expect(
      await screen.findByText('This error is not in your log (it may have been deleted).'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← Back to the error log' })).toBeInTheDocument()
  })
})
