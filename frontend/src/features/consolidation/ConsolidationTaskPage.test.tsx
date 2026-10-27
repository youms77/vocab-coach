import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import i18n from '../../i18n'
import { installFakeRecorder, recordTake } from '../../test/fakeRecorder'
import { attempt, task } from '../../test/consolidationFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { speakingOut } from '../../test/speechFixtures'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const posts = (calls: RecordedCall[], path: string) =>
  calls.filter((call) => call.method === 'POST' && call.path.split('?')[0] === path)

describe('Consolidation task page', () => {
  it('shows the brief, the structure and the terms; the other language on request', async () => {
    mockApi({ ...base, 'GET /consolidation/tasks/4': task() })
    const user = userEvent.setup()
    renderApp('/consolidation/tasks/4')

    expect(await screen.findByRole('heading', { level: 1, name: 'Explaining a causal study' })).toHaveFocus()
    expect(screen.getByText(/separate cause from correlation/)).toBeInTheDocument()
    expect(screen.getByText('Fellow students')).toBeInTheDocument()
    expect(screen.getByText('Context')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'confounding variable' })).toHaveAttribute(
      'href',
      '/library/items/11',
    )
    expect(screen.queryByText(/Faites un exposé/)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Also show in French' }))
    expect(screen.getByText(/Faites un exposé/)).toHaveAttribute('lang', 'fr')
  })

  it('accepts a proposed task, then offers completion with a confirmation', async () => {
    let current = task()
    const calls = mockApi({
      ...base,
      'GET /consolidation/tasks/4': () => Response.json(current),
      'GET /consolidation/tasks': { items: [], total: 0, limit: 20, offset: 0 },
      'POST /consolidation/tasks/4/status': (call) => {
        current = task({ status: (call.body as { to: 'accepted' }).to })
        return Response.json(current)
      },
    })
    const user = userEvent.setup()
    renderApp('/consolidation/tasks/4')

    await user.click(await screen.findByRole('button', { name: 'Accept' }))
    expect(await screen.findByRole('button', { name: 'Mark as completed' })).toBeInTheDocument()
    expect(posts(calls, '/consolidation/tasks/4/status')[0]!.body).toEqual({ to: 'accepted' })

    await user.click(screen.getByRole('button', { name: 'Mark as completed' }))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    // Nothing is sent until the confirmation.
    expect(posts(calls, '/consolidation/tasks/4/status')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('a closed task takes no production and has no action', async () => {
    mockApi({ ...base, 'GET /consolidation/tasks/4': task({ status: 'completed' }) })
    renderApp('/consolidation/tasks/4')
    expect(await screen.findByText('This task is completed.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Your production' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull()
  })

  it('sends the written text, keeps the draft until then, and goes to the attempt page', async () => {
    const calls = mockApi({
      ...base,
      'GET /consolidation/tasks/4': task({ status: 'accepted' }),
      'POST /consolidation/tasks/4/attempts/written': () =>
        Response.json(attempt(), { status: 201 }),
      'GET /productions/21': attempt(),
      'POST /productions/21/correct': () => apiErrorResponse(409, 'already_corrected'),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/consolidation/tasks/4')

    const field = await screen.findByLabelText('Your text')
    const send = screen.getByRole('button', { name: 'Send for correction' })
    expect(send).toBeDisabled()
    await user.type(field, 'The noisy estimate was a problem.')
    expect(window.localStorage.getItem('vocab-coach.consolidation-draft.4')).toBe(
      'The noisy estimate was a problem.',
    )
    expect(screen.getByText(/6 words/)).toBeInTheDocument()
    await user.click(send)

    await waitFor(() => expect(router.state.location.pathname).toBe('/consolidation/attempts/21'))
    expect(posts(calls, '/consolidation/tasks/4/attempts/written')[0]!.body).toEqual({
      text: 'The noisy estimate was a problem.',
    })
    expect(window.localStorage.getItem('vocab-coach.consolidation-draft.4')).toBeNull()
    expect(router.state.location.search).toBe('?task=4')
  })

  it('records a talk (20 s minimum) and sends it as the task audio', async () => {
    const kit = installFakeRecorder()
    const calls = mockApi({
      ...base,
      'GET /consolidation/tasks/4': task({ status: 'accepted' }),
      'POST /speech/consolidation': () => Response.json(speakingOut({ production_id: 21 }), { status: 201 }),
      'GET /productions/21': attempt({ modality: 'oral', audio_url: '/api/productions/21/audio', transcription_status: 'ok' }),
      'POST /productions/21/correct': () => apiErrorResponse(409, 'already_corrected'),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/consolidation/tasks/4')

    await user.click(await screen.findByRole('button', { name: 'Record it' }))
    await recordTake(user, kit, { ms: 25000 })
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/consolidation/attempts/21'))
    const sent = posts(calls, '/speech/consolidation')
    expect(sent).toHaveLength(1)
    const query = Object.fromEntries(new URL(sent[0]!.path, 'http://x').searchParams)
    expect(query).toEqual({ task_id: '4', duration_s: '25' })
  })

  it('downloads the export in the chosen language', async () => {
    const calls = mockApi({
      ...base,
      'GET /consolidation/tasks/4': task(),
      'GET /consolidation/tasks/4/export': () =>
        new Response('# Task', {
          headers: {
            'Content-Type': 'text/markdown',
            'Content-Disposition': 'attachment; filename="consolidation-task-4-fr.md"',
          },
        }),
    })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const user = userEvent.setup()
    renderApp('/consolidation/tasks/4')

    await user.click(await screen.findByRole('button', { name: 'Download in French (.md)' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(calls.some((call) => call.path === '/consolidation/tasks/4/export?lang=fr')).toBe(true)
  })

  it('says when the task does not exist', async () => {
    mockApi({ ...base, 'GET /consolidation/tasks/4': () => apiErrorResponse(404, 'task_not_found') })
    renderApp('/consolidation/tasks/4')
    expect(await screen.findByText(/does not exist/)).toBeInTheDocument()
  })
})
