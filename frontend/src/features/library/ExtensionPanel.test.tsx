import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { ExtensionResult } from '../../api/enrichment'
import { deck, item } from '../../test/fixtures'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const decks = [deck(3, 'Presenting survey results')]

function result(overrides: Partial<ExtensionResult> = {}): ExtensionResult {
  return {
    status: 'ok',
    reason: null,
    created: [],
    suggested: 0,
    dropped_existing: 0,
    dropped_in_batch: 0,
    possible_duplicates: [],
    ...overrides,
  }
}

async function openExtension() {
  await userEvent.click(await screen.findByRole('button', { name: 'Extend this list' }))
}

describe('list extension on the decks page', () => {
  it('creates terms waiting for triage and links to their sorting', async () => {
    const calls = mockApi({
      'GET /decks': decks,
      'POST /decks/3/extension': () =>
        Response.json(
          result({
            created: [
              item(10, 'response rate', { status: 'triage' }),
              item(11, 'nonresponse bias', { status: 'triage' }),
            ],
            suggested: 13,
            dropped_existing: 2,
            dropped_in_batch: 1,
            possible_duplicates: [
              {
                item_id: 11,
                candidates: [
                  {
                    id: 4,
                    term: 'non-response bias',
                    normalized_form: 'non-response bias',
                    status: 'learning',
                    match: 'possible',
                    decks: [],
                  },
                ],
              },
            ],
          }),
          { status: 201 },
        ),
    })
    renderApp('/library/decks')
    await openExtension()
    const count = screen.getByLabelText('Number of suggestions')
    await userEvent.clear(count)
    await userEvent.type(count, '15')
    await userEvent.click(screen.getByRole('button', { name: 'Suggest terms' }))
    const status = await screen.findByText('2 new terms are waiting for your triage.')
    const box = status.closest('div')!
    expect(within(box).getByText('response rate · nonresponse bias')).toBeInTheDocument()
    expect(within(box).getByText(/2 already in your library, 1 repeated/)).toBeInTheDocument()
    expect(within(box).getByRole('link', { name: 'non-response bias' })).toHaveAttribute(
      'href',
      '/library/items/4',
    )
    expect(within(box).getByRole('link', { name: 'Sort them now' })).toHaveAttribute(
      'href',
      '/triage?deck=3',
    )
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ count: 15 })
  })

  it('reports an AI failure without changing the deck', async () => {
    mockApi({
      'GET /decks': decks,
      'POST /decks/3/extension': result({ status: 'unavailable', reason: 'network' }),
    })
    renderApp('/library/decks')
    await openExtension()
    await userEvent.click(screen.getByRole('button', { name: 'Suggest terms' }))
    expect(
      await screen.findByText(
        'No suggestion: the AI provider could not be reached. The deck is unchanged.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Sort them now' })).not.toBeInTheDocument()
  })

  it('keeps the count between 10 and 30', async () => {
    const calls = mockApi({ 'GET /decks': decks })
    renderApp('/library/decks')
    await openExtension()
    const count = screen.getByLabelText('Number of suggestions')
    expect(count).toHaveValue(20)
    await userEvent.clear(count)
    await userEvent.type(count, '31')
    expect(screen.getByRole('button', { name: 'Suggest terms' })).toBeDisabled()
    await userEvent.clear(count)
    await userEvent.type(count, '9')
    expect(screen.getByRole('button', { name: 'Suggest terms' })).toBeDisabled()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('explains a deck with nothing to extend from', async () => {
    mockApi({
      'GET /decks': decks,
      'POST /decks/3/extension': () => apiErrorResponse(422, 'not_enough_context', 'empty'),
    })
    renderApp('/library/decks')
    await openExtension()
    await userEvent.click(screen.getByRole('button', { name: 'Suggest terms' }))
    expect(await screen.findByText(/There is nothing to extend from/)).toBeInTheDocument()
  })
})
