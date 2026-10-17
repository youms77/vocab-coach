import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { DuplicateGroup } from '../../api/duplicates'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const group: DuplicateGroup = {
  match: 'exact',
  key: 'shed light on',
  items: [
    {
      id: 4,
      term: 'shed light on',
      normalized_form: 'shed light on',
      status: 'queued',
      has_cards: false,
      decks: [{ id: 6, name: 'Presenting survey results' }],
    },
    {
      id: 5,
      term: 'to shed light on',
      normalized_form: 'shed light on',
      status: 'learning',
      has_cards: true,
      decks: [{ id: 2, name: 'Thesis writing' }],
    },
  ],
}

describe('duplicates page', () => {
  it('keeps the term with cards by default and merges the other into it', async () => {
    let gets = 0
    const calls = mockApi({
      'GET /duplicates': () => {
        gets += 1
        return Response.json(gets === 1 ? [group] : [])
      },
      'POST /items/4/merge': { kept_id: 5, removed_id: 4, inverted: false },
    })
    renderApp('/duplicates')
    expect(await screen.findByRole('radio', { name: 'to shed light on' })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Merge into “to shed light on”' }))
    expect(
      await screen.findByText('Merged: “shed light on” is now part of “to shed light on”.'),
    ).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ into: 5 })
    expect(await screen.findByText('No duplicates found.')).toBeInTheDocument()
  })

  it('lets the user keep the other term', async () => {
    const calls = mockApi({
      'GET /duplicates': [group],
      'POST /items/5/merge': { kept_id: 5, removed_id: 4, inverted: true },
    })
    renderApp('/duplicates')
    await userEvent.click(await screen.findByRole('radio', { name: 'shed light on' }))
    await userEvent.click(screen.getByRole('button', { name: 'Merge into “shed light on”' }))
    expect(await screen.findByText(/The term with review cards was kept/)).toBeInTheDocument()
    expect(screen.getByText(/“shed light on” is now part of “to shed light on”/)).toBeInTheDocument()
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ into: 4 }))
  })

  it('explains why two terms with cards cannot be merged', async () => {
    mockApi({
      'GET /duplicates': [group],
      'POST /items/4/merge': () =>
        apiErrorResponse(409, 'merge_conflict', 'cards', { item_ids: [4, 5] }),
    })
    renderApp('/duplicates')
    await userEvent.click(
      await screen.findByRole('button', { name: 'Merge into “to shed light on”' }),
    )
    expect(
      await screen.findByText('Both terms already have review cards: they cannot be merged.'),
    ).toBeInTheDocument()
  })

  it('says when there is nothing to merge', async () => {
    mockApi({ 'GET /duplicates': [] })
    renderApp('/duplicates')
    expect(await screen.findByText('No duplicates found.')).toBeInTheDocument()
  })
})
