import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import {
  created,
  readyDeck,
  task,
  taskPage,
  waitingDeck,
} from '../../test/consolidationFixtures'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /consolidation/tasks': taskPage(),
  'GET /consolidation/tasks/4': task(),
}

describe('Consolidation page', () => {
  it('lists ready decks and says why the others are not ready', async () => {
    mockApi({
      ...base,
      'GET /consolidation/decks': [
        readyDeck(),
        waitingDeck('below_ratio'),
        waitingDeck('task_open', { deck_id: 3, name: 'Interview prep', open_task_id: 4 }),
      ],
    })
    renderApp('/consolidation')

    expect(await screen.findByRole('heading', { level: 1, name: 'Consolidation' })).toHaveFocus()
    const ready = await screen.findByRole('heading', { name: 'Causal inference reading' })
    expect(ready).toBeInTheDocument()
    expect(screen.getByText(/90 % of its productive cards are stable|90\s?% of its productive/)).toBeInTheDocument()
    const waiting = screen.getByRole('region', { name: 'Decks not ready yet' })
    expect(within(waiting).getByText(/50\s?% of its productive cards are stable/)).toBeInTheDocument()
    expect(within(waiting).getByRole('link', { name: 'Open the task' })).toHaveAttribute(
      'href',
      '/consolidation/tasks/4',
    )
  })

  it('says when no deck is ready', async () => {
    mockApi({ ...base, 'GET /consolidation/decks': [waitingDeck('not_enough_candidates', { candidates: 5 })] })
    renderApp('/consolidation')
    expect(await screen.findByText(/No deck is ready yet/)).toBeInTheDocument()
    expect(screen.getByText(/Only 5 terms are usable/)).toBeInTheDocument()
  })

  it('creates a task with the chosen type and count, then opens it', async () => {
    const calls = mockApi({
      ...base,
      'GET /consolidation/tasks/4': task({ source: 'template' }),
      'GET /consolidation/decks': [readyDeck()],
      'POST /consolidation/tasks': () =>
        Response.json(created({ source: 'template', reason: 'no_provider_configured' }), { status: 201 }),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/consolidation')

    await user.selectOptions(await screen.findByLabelText('Type of task'), 'Speech')
    const count = screen.getByLabelText('Number of terms')
    await user.clear(count)
    await user.type(count, '12')
    await user.click(screen.getByRole('button', { name: 'Create a task' }))

    expect(await screen.findByText(/made from a template, not by the AI/)).toBeInTheDocument()
    expect(screen.getByText(/no AI provider is set up/)).toBeInTheDocument()
    const post = calls.filter((call) => call.method === 'POST')
    expect(post).toHaveLength(1)
    expect(post[0]!.body).toEqual({ deck_id: 1, task_type: 'speech', term_count: 12 })
    expect(router.state.location.pathname).toBe('/consolidation/tasks/4')
  })

  it('refuses a count out of range without calling the backend', async () => {
    const calls = mockApi({ ...base, 'GET /consolidation/decks': [readyDeck()] })
    const user = userEvent.setup()
    renderApp('/consolidation')
    const count = await screen.findByLabelText('Number of terms')
    await user.clear(count)
    await user.type(count, '3')
    expect(screen.getByRole('button', { name: 'Create a task' })).toBeDisabled()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('links to the open task on a task_open conflict', async () => {
    mockApi({
      ...base,
      'GET /consolidation/decks': [readyDeck()],
      'POST /consolidation/tasks': () => apiErrorResponse(409, 'task_open', 'open', { task_id: 9 }),
    })
    const user = userEvent.setup()
    renderApp('/consolidation')
    await user.click(await screen.findByRole('button', { name: 'Create a task' }))
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText(/already has an open task/)).toBeInTheDocument()
    expect(within(alert).getByRole('link', { name: 'Open the task' })).toHaveAttribute(
      'href',
      '/consolidation/tasks/9',
    )
  })

  it('lists the tasks and is translated', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /consolidation/decks': [readyDeck()] })
    renderApp('/consolidation')
    expect(await screen.findByRole('link', { name: 'Expliquer une étude causale' })).toHaveAttribute(
      'href',
      '/consolidation/tasks/4',
    )
    expect(screen.getByRole('button', { name: 'Créer une tâche' })).toBeInTheDocument()
  })
})
