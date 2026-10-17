import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { TriageEntry } from '../../api/triage'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

function entry(id: number, term: string, sentence: string | null = null): TriageEntry {
  return {
    item_id: id,
    term,
    item_type: 'collocation',
    sentence,
    decks: [{ id: 6, name: 'Presenting survey results' }],
  }
}

const entries = [
  entry(1, 'sampling frame', 'The sampling frame excluded students.'),
  entry(2, 'response rate'),
  entry(3, 'margin of error'),
]

function card(term: string) {
  return screen.getByRole('group', { name: new RegExp(term) })
}

describe('triage page', () => {
  it('sends one decision per term, all at once, and shows the counts', async () => {
    const calls = mockApi({
      'GET /decks': [],
      'GET /triage': entries,
      'POST /triage': { learn: 1, unsure: 1, known: 1 },
    })
    renderApp('/triage')
    await screen.findByText('“The sampling frame excluded students.”')
    expect(screen.getByText('3 terms waiting')).toBeInTheDocument()
    await userEvent.click(within(card('sampling frame')).getByLabelText(/Learn it/))
    await userEvent.click(within(card('response rate')).getByLabelText(/Not sure/))
    await userEvent.click(within(card('margin of error')).getByLabelText(/I know it/))
    await userEvent.click(screen.getByRole('button', { name: 'Save 3 choices' }))
    expect(await screen.findByText('Saved. To learn: 1 · not sure: 1 · known: 1.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({
      decisions: [
        { item_id: 1, decision: 'learn' },
        { item_id: 2, decision: 'unsure' },
        { item_id: 3, decision: 'known' },
      ],
    })
  })

  it('keys 1, 2 and 3 decide for the next open term, but not while typing', async () => {
    const calls = mockApi({
      'GET /decks': [],
      'GET /triage': entries,
      'POST /triage': { learn: 1, unsure: 0, known: 1 },
    })
    renderApp('/triage')
    await screen.findByText('sampling frame')
    await userEvent.keyboard('3')
    expect(within(card('sampling frame')).getByLabelText(/I know it/)).toBeChecked()
    await userEvent.keyboard('1')
    expect(within(card('response rate')).getByLabelText(/Learn it/)).toBeChecked()
    // Typed inside a field (here the deck filter): not a shortcut.
    const select = screen.getByLabelText('Deck')
    fireEvent.keyDown(select, { key: '2' })
    expect(within(card('margin of error')).getByLabelText(/Not sure/)).not.toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Save 2 choices' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'POST')!.body).toEqual({
        decisions: [
          { item_id: 1, decision: 'known' },
          { item_id: 2, decision: 'learn' },
        ],
      }),
    )
  })

  it('a term no longer in triage refuses the batch and reloads the list', async () => {
    let gets = 0
    mockApi({
      'GET /decks': [],
      'GET /triage': () => {
        gets += 1
        return Response.json(gets === 1 ? entries : entries.slice(1))
      },
      'POST /triage': () => apiErrorResponse(409, 'not_in_triage', 'gone', { item_ids: [1] }),
    })
    renderApp('/triage')
    await screen.findByText('sampling frame')
    await userEvent.click(within(card('sampling frame')).getByLabelText(/Learn it/))
    await userEvent.click(within(card('response rate')).getByLabelText(/Learn it/))
    await userEvent.click(screen.getByRole('button', { name: 'Save 2 choices' }))
    expect(
      await screen.findByText('Some of these terms are no longer waiting for triage.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/The list was reloaded/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('sampling frame')).not.toBeInTheDocument())
    // The choice for the remaining term is kept.
    expect(screen.getByRole('button', { name: 'Save 1 choice' })).toBeEnabled()
  })

  it('filters by the deck given in the URL', async () => {
    const calls = mockApi({ 'GET /decks': [], 'GET /triage': [] })
    renderApp('/triage?deck=6')
    expect(await screen.findByText('Nothing is waiting for triage.')).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/triage?deck_id=6')).toBe(true)
  })

  it('shows the count of terms to sort on the library page', async () => {
    mockApi({ 'GET /decks': [], 'GET /items': { total: 0, items: [] }, 'GET /triage': entries })
    renderApp('/library')
    expect(await screen.findByRole('link', { name: 'Sort new terms (3 to sort)' })).toHaveAttribute(
      'href',
      '/triage',
    )
  })

  it('is available in French', async () => {
    mockApi({ 'GET /decks': [], 'GET /triage': entries })
    renderApp('/triage')
    await screen.findByText('sampling frame')
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getAllByLabelText(/Je le connais/)).toHaveLength(3)
  })
})
