import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Deck, Item, ItemDetail } from '../../api/library'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

function item(id: number, term: string, overrides: Partial<Item> = {}): Item {
  return {
    id,
    term,
    normalized_form: term,
    lemma: null,
    item_type: 'collocation',
    part_of_speech: null,
    origin_sentence: null,
    notes: null,
    status: 'queued',
    status_changed_at: '2026-10-16T10:00:00Z',
    discovered_at: null,
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
    decks: [{ id: 1, name: 'Causal inference reading' }],
    sheet_status: 'none',
    ...overrides,
  }
}

function deck(id: number, name: string): Deck {
  return {
    id,
    name,
    description: null,
    domain: 'econometrics',
    kind: 'topic',
    status: 'queued',
    deadline: null,
    priority: null,
    queue_position: 1,
    source: null,
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
    item_count: 2,
    items_by_status: { queued: 2 },
    pace: null,
    warnings: [],
  }
}

const decks = [deck(1, 'Causal inference reading')]

describe('library page', () => {
  it('lists the terms with their status and sheet state', async () => {
    mockApi({
      'GET /items': {
        total: 2,
        items: [item(1, 'to account for', { sheet_status: 'edited' }), item(2, 'shed light on')],
      },
      'GET /decks': decks,
    })
    renderApp('/library')
    const row = (await screen.findByRole('link', { name: 'to account for' })).closest('tr')!
    expect(within(row).getByText('Queued')).toBeInTheDocument()
    expect(within(row).getByText('Sheet edited by you')).toBeInTheDocument()
    expect(screen.getByText('2 terms')).toBeInTheDocument()
  })

  it('sends the filters to the API and goes back to the first page', async () => {
    const calls = mockApi({
      'GET /items': { total: 0, items: [] },
      'GET /decks': decks,
    })
    renderApp('/library')
    await screen.findByText(/No term matches/)
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'learning')
    await userEvent.selectOptions(screen.getByLabelText('Usage sheet'), 'needs_completion')
    await waitFor(() => {
      const last = calls.filter((c) => c.path.startsWith('/items?')).at(-1)!
      expect(last.path).toContain('status=learning')
      expect(last.path).toContain('sheet=needs_completion')
      expect(last.path).toContain('offset=0')
    })
  })

  it('filters by source: each deck source listed once, sent as source_id', async () => {
    const book = { id: 7, title: 'Mostly Harmless Econometrics' }
    const calls = mockApi({
      'GET /items': { total: 0, items: [] },
      'GET /decks': [
        { ...deck(1, 'Chapter 3'), source: book },
        { ...deck(2, 'Chapter 4'), source: book },
        { ...deck(3, 'Survey course'), source: { id: 9, title: 'Lecture notes' } },
        deck(4, 'Quick adds'),
      ],
    })
    renderApp('/library')
    await screen.findByText(/No term matches/)
    const select = screen.getByLabelText('Source')
    await waitFor(() =>
      expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
        'Any',
        'Lecture notes',
        'Mostly Harmless Econometrics',
      ]),
    )
    await userEvent.selectOptions(select, '7')
    await waitFor(() => {
      const last = calls.filter((c) => c.path.startsWith('/items?')).at(-1)!
      expect(last.path).toContain('source_id=7')
    })
  })

  it('starts on the deck given in the URL', async () => {
    const calls = mockApi({ 'GET /items': { total: 0, items: [] }, 'GET /decks': decks })
    renderApp('/library?deck=1')
    await screen.findByText(/No term matches/)
    expect(calls.some((c) => c.path.includes('deck_id=1'))).toBe(true)
  })

  it('quick add: sends the term and confirms', async () => {
    const calls = mockApi({
      'GET /items': { total: 0, items: [] },
      'GET /decks': decks,
      'POST /items': () =>
        Response.json(
          { item: item(3, 'selection bias'), deck_id: 9, attached: false, duplicates: [] },
          { status: 201 },
        ),
    })
    renderApp('/library')
    await userEvent.type(await screen.findByLabelText('Term'), 'selection bias')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Added “selection bias”.')).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST')!
    expect(post.body).toEqual({ term: 'selection bias' })
  })

  it('quick add: a possible duplicate lets the user attach it or add a new term', async () => {
    let attempt = 0
    const calls = mockApi({
      'GET /items': { total: 0, items: [] },
      'GET /decks': decks,
      'POST /items': () => {
        attempt += 1
        if (attempt === 1) {
          return apiErrorResponse(409, 'duplicate_term', 'duplicate', {
            candidates: [
              {
                id: 7,
                term: 'estimate',
                normalized_form: 'estimate',
                status: 'queued',
                match: 'possible',
                decks: [{ id: 1, name: 'Causal inference reading' }],
              },
            ],
          })
        }
        return Response.json(
          { item: item(7, 'estimate'), deck_id: 1, attached: true, duplicates: [] },
          { status: 201 },
        )
      },
    })
    renderApp('/library')
    await userEvent.type(await screen.findByLabelText('Term'), 'estimates')
    await userEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText(/Similar terms already exist/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Use this one' }))
    await screen.findByText('Added “estimate”.')
    const posts = calls.filter((c) => c.method === 'POST')
    expect(posts[1]!.body).toEqual({ term: 'estimates', on_duplicate: 'attach', attach_to: 7 })
  })

  it('shows a translated message when the server is unreachable', async () => {
    mockApi({ 'GET /decks': decks })
    renderApp('/library')
    expect(await screen.findByText(/Unexpected error|Cannot reach/)).toBeInTheDocument()
  })

  it('is available in French', async () => {
    mockApi({ 'GET /items': { total: 0, items: [] }, 'GET /decks': decks })
    renderApp('/library')
    await screen.findByRole('heading', { name: 'Quick add' })
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getByRole('heading', { name: 'Ajout rapide' })).toBeInTheDocument()
  })
})

describe('item page', () => {
  const detail: ItemDetail = {
    ...item(1, 'to account for'),
    deck_links: [
      {
        deck_id: 1,
        deck_name: 'Causal inference reading',
        position: 1,
        context_sentence: 'We account for fixed effects.',
        added_at: '2026-10-16T10:00:00Z',
      },
    ],
    has_history: false,
    duplicates: [
      {
        id: 2,
        term: 'account for',
        normalized_form: 'account for',
        status: 'queued',
        match: 'exact',
        decks: [],
      },
    ],
  }

  it('edits the term and saves only through PATCH', async () => {
    const calls = mockApi({
      'GET /items/1': detail,
      'PATCH /items/1': () => Response.json({ ...detail, notes: 'Careful with the preposition.' }),
      'GET /items': { total: 0, items: [] },
      'GET /decks': decks,
    })
    renderApp('/library/items/1')
    await userEvent.type(await screen.findByLabelText('Notes'), 'Careful with the preposition.')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    const patch = calls.find((c) => c.method === 'PATCH')!
    expect(patch.body).toMatchObject({ term: 'to account for', notes: 'Careful with the preposition.' })
    expect(screen.getByText('We account for fixed effects.', { exact: false })).toBeInTheDocument()
  })

  it('refuses to delete a term with history and explains why', async () => {
    mockApi({
      'GET /items/1': detail,
      'DELETE /items/1': () =>
        apiErrorResponse(409, 'item_has_history', 'history', { suggestion: 'archive' }),
    })
    renderApp('/library/items/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Yes, delete' }))
    expect(await screen.findByText(/study history/)).toBeInTheDocument()
  })

  it('deletes a term after confirmation and goes back to the library', async () => {
    const calls = mockApi({
      'GET /items/1': detail,
      'DELETE /items/1': () => new Response(null, { status: 204 }),
      'GET /items': { total: 0, items: [] },
      'GET /decks': decks,
    })
    renderApp('/library/items/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(screen.getByText('Delete “to account for” for good?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Yes, delete' }))
    expect(await screen.findByRole('heading', { name: 'Library' })).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(true)
  })

  it('merges into a similar term and shows the conflict message', async () => {
    mockApi({
      'GET /items/1': detail,
      'POST /items/1/merge': () => apiErrorResponse(409, 'merge_conflict', 'cards', { item_ids: [1, 2] }),
    })
    renderApp('/library/items/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Merge this term into it' }))
    expect(await screen.findByText(/cannot be merged/)).toBeInTheDocument()
  })

  it('archives, then offers to restore', async () => {
    const calls = mockApi({
      'GET /items/1': detail,
      'POST /items/1/status': () => Response.json(item(1, 'to account for', { status: 'archived' })),
    })
    renderApp('/library/items/1')
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    await waitFor(() =>
      expect(calls.find((c) => c.path === '/items/1/status')!.body).toEqual({ to: 'archived' }),
    )
  })
})

describe('decks page', () => {
  it('creates a deck', async () => {
    const calls = mockApi({
      'GET /decks': decks,
      'POST /decks': () => Response.json(deck(2, 'Statistics course'), { status: 201 }),
    })
    renderApp('/library/decks')
    await userEvent.type(await screen.findByLabelText('Name'), 'Statistics course')
    await userEvent.click(screen.getByRole('button', { name: 'Create deck' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({
      name: 'Statistics course',
      domain: null,
    })
  })

  it('explains why a deck with history cannot be deleted', async () => {
    mockApi({
      'GET /decks': decks,
      'DELETE /decks/1': () => apiErrorResponse(409, 'deck_has_history', 'history'),
    })
    renderApp('/library/decks')
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await userEvent.click(screen.getByRole('button', { name: 'Yes, delete' }))
    expect(await screen.findByText(/already been studied/)).toBeInTheDocument()
  })

  it('renames a deck', async () => {
    const calls = mockApi({
      'GET /decks': decks,
      'PATCH /decks/1': () => Response.json(deck(1, 'Renamed')),
    })
    renderApp('/library/decks')
    await userEvent.click(await screen.findByRole('button', { name: 'Rename' }))
    const input = screen.getByDisplayValue('Causal inference reading')
    await userEvent.clear(input)
    await userEvent.type(input, 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ name: 'Renamed' }),
    )
  })
})
