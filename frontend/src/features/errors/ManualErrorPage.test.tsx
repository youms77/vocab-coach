import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { errorRow, ORIGINAL } from '../../test/errorFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
}

const posts = (calls: RecordedCall[]) => calls.filter((c) => c.method === 'POST' && c.path === '/errors')

async function fill(
  user: ReturnType<typeof userEvent.setup>,
  { original = ORIGINAL, wrong = 'in campus', correction = 'on campus' } = {},
) {
  await screen.findByLabelText('The incorrect form')
  if (original !== '') {
    await user.click(screen.getByLabelText('The sentence where you made it (optional)'))
    await user.paste(original)
  }
  await user.type(screen.getByLabelText('The incorrect form'), wrong)
  await user.type(screen.getByLabelText('The correction'), correction)
  await user.selectOptions(screen.getByLabelText('Category'), 'grammar.preposition.fixed_expression')
}

describe('Manual error entry', () => {
  it('sends the exact body and offers to open the new error', async () => {
    const calls = mockApi({
      ...base,
      'POST /errors': () => Response.json(errorRow(31, { source: 'manual' }), { status: 201 }),
    })
    const user = userEvent.setup()
    renderApp('/errors/new')
    expect(await screen.findByRole('heading', { level: 1, name: 'Add an error' })).toHaveFocus()

    await fill(user)
    await user.type(screen.getByLabelText('Why it is wrong (optional)'), 'Fixed expression.')
    await user.click(screen.getByRole('button', { name: 'Add an option' }))
    await user.type(screen.getByLabelText('Other natural option 1'), 'at university')
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))

    expect(await screen.findByText('Added to your error log.')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(1)
    expect(posts(calls)[0].body).toEqual({
      original_text: ORIGINAL,
      erroneous_text: 'in campus',
      correction: 'on campus',
      alternatives: ['at university'],
      category_code: 'grammar.preposition.fixed_expression',
      explanation: 'Fixed expression.',
      lexical_item_id: null,
    })
    expect(screen.getByRole('link', { name: 'Open it' })).toHaveAttribute('href', '/errors/31')
    // The form is empty again for the next entry.
    expect(screen.getByLabelText('The incorrect form')).toHaveValue('')
  })

  it('sends a null original when the sentence is left empty', async () => {
    const calls = mockApi({
      ...base,
      'POST /errors': () => Response.json(errorRow(32, { source: 'manual' }), { status: 201 }),
    })
    const user = userEvent.setup()
    renderApp('/errors/new')
    await fill(user, { original: '', wrong: 'I am agree', correction: 'I agree' })
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))

    await waitFor(() => expect(posts(calls)).toHaveLength(1))
    expect(posts(calls)[0].body).toMatchObject({ original_text: null, alternatives: [], explanation: '' })
  })

  it('refuses a wrong form that is not in the sentence, without calling the server', async () => {
    const calls = mockApi({ ...base })
    const user = userEvent.setup()
    renderApp('/errors/new')
    await fill(user, { wrong: 'on the campus', correction: 'on campus' })
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))

    expect(await screen.findByText('The incorrect form must appear in the sentence.')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
  })

  it('accepts a differently spaced, cased or apostrophed form like the server does', async () => {
    const calls = mockApi({
      ...base,
      'POST /errors': () => Response.json(errorRow(33, { source: 'manual' }), { status: 201 }),
    })
    const user = userEvent.setup()
    renderApp('/errors/new')
    await fill(user, { original: 'She doesn’t   know.', wrong: "DOESN'T know", correction: "doesn't know" })
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))
    await waitFor(() => expect(posts(calls)).toHaveLength(1))
  })

  it('refuses a correction equal to the wrong form', async () => {
    const calls = mockApi({ ...base })
    const user = userEvent.setup()
    renderApp('/errors/new')
    await fill(user, { wrong: 'in campus', correction: 'in campus' })
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))

    expect(await screen.findByText('The correction must differ from the incorrect form.')).toBeInTheDocument()
    expect(posts(calls)).toHaveLength(0)
  })

  it('shows what the server refuses: invalid_error with its detail, unknown_category', async () => {
    let answer = apiErrorResponse(422, 'invalid_error', 'The wrong form is not in the original text.')
    mockApi({ ...base, 'POST /errors': () => answer })
    const user = userEvent.setup()
    renderApp('/errors/new')
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))

    expect(await screen.findByText('This error cannot be saved.')).toBeInTheDocument()
    expect(screen.getByText('The wrong form is not in the original text.')).toBeInTheDocument()

    answer = apiErrorResponse(422, 'unknown_category')
    await user.click(screen.getByRole('button', { name: 'Add to my log' }))
    expect(
      await screen.findByText('This category cannot be used: choose an active one.'),
    ).toBeInTheDocument()
    // Nothing is lost: the fields still hold what was typed.
    expect(screen.getByLabelText('The incorrect form')).toHaveValue('in campus')
  })
})
