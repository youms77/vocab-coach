import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { Production } from '../../api/productions'
import i18n from '../../i18n'
import {
  attempt,
  consolidationCorrection,
  correctedAttempt,
  summary,
  task,
} from '../../test/consolidationFixtures'
import { mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree, unavailableResult } from '../../test/writingFixtures'
import { speakingOut } from '../../test/speechFixtures'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
  'GET /consolidation/tasks/4': task({ status: 'accepted' }),
  'GET /consolidation/tasks': { items: [], total: 0, limit: 20, offset: 0 },
}

const correctCalls = (calls: RecordedCall[]) =>
  calls.filter((call) => call.method === 'POST' && call.path === '/productions/21/correct')

describe('Consolidation attempt page', () => {
  it('corrects once on arrival and groups the terms', async () => {
    let stored: Production = attempt()
    const calls = mockApi({
      ...base,
      'GET /productions/21': () => Response.json(stored),
      'POST /productions/21/correct': () => {
        const result = consolidationCorrection()
        stored = result.attempt
        return Response.json(result)
      },
    })
    const { router } = renderApp({
      pathname: '/consolidation/attempts/21',
      search: '?task=4',
      state: { autoCorrect: true },
    } as never)

    expect(await screen.findByRole('heading', { name: 'The terms of the task' })).toBeInTheDocument()
    expect(correctCalls(calls)).toHaveLength(1)
    expect(router.state.location.state).toBeNull()
    expect(router.state.location.search).toBe('?task=4')
    expect(screen.getByText(/3 terms: 1 used correctly, 1 used wrongly, 1 not used/)).toBeInTheDocument()
    const summaryCard = screen.getByRole('heading', { name: 'The terms of the task' }).closest('section') as HTMLElement
    expect(within(summaryCard).getByRole('heading', { name: 'Used correctly (1)' })).toBeInTheDocument()
    expect(within(summaryCard).getByText('now active')).toBeInTheDocument()
    expect(within(summaryCard).getByRole('heading', { name: 'Used wrongly (1)' })).toBeInTheDocument()
    expect(within(summaryCard).getByRole('heading', { name: 'Not used (1)' })).toBeInTheDocument()
    expect(within(summaryCard).getByText(/1 term became active\. 1 review card was reinforced\./)).toBeInTheDocument()
    // The task is accepted: finishing it is offered, never done by itself.
    expect(screen.getByRole('button', { name: 'Yes, mark as completed' })).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST' && call.path.endsWith('/status'))).toBe(false)
  })

  it('a reload shows the stored groups, without the "now active" marks, and corrects nothing', async () => {
    const calls = mockApi({ ...base, 'GET /productions/21': correctedAttempt() })
    renderApp('/consolidation/attempts/21?task=4')

    expect(await screen.findByRole('heading', { name: 'Used correctly (1)' })).toBeInTheDocument()
    expect(screen.queryByText('now active')).toBeNull()
    expect(correctCalls(calls)).toHaveLength(0)
    expect(screen.getByRole('link', { name: 'Back to the task' })).toHaveAttribute(
      'href',
      '/consolidation/tasks/4',
    )
  })

  it('shows nothing about the terms before the attempt is corrected', async () => {
    mockApi({ ...base, 'GET /productions/21': attempt() })
    renderApp('/consolidation/attempts/21')
    expect(await screen.findByRole('button', { name: 'Correct my text' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'The terms of the task' })).toBeNull()
  })

  it('tells an AI failure and offers to try again', async () => {
    const calls = mockApi({
      ...base,
      'GET /productions/21': attempt(),
      'POST /productions/21/correct': () => Response.json(unavailableResult('quota')),
    })
    const user = userEvent.setup()
    renderApp('/consolidation/attempts/21')
    await user.click(await screen.findByRole('button', { name: 'Correct my text' }))
    expect(await screen.findByText(/free quota is used up/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expect(correctCalls(calls)).toHaveLength(1)
  })

  it('transcribes a recording that has no text yet, then corrects', async () => {
    let stored: Production = attempt({
      modality: 'oral',
      text: '',
      audio_url: '/api/productions/21/audio',
      transcription_status: 'pending',
    })
    const calls = mockApi({
      ...base,
      'GET /productions/21': () => Response.json(stored),
      'POST /productions/21/transcribe': () => {
        stored = attempt({ modality: 'oral', audio_url: '/api/productions/21/audio', transcription_status: 'ok' })
        return Response.json(speakingOut({ production_id: 21 }))
      },
      'POST /productions/21/correct': () => {
        const result = consolidationCorrection({
          attempt: correctedAttempt({ modality: 'oral', audio_url: '/api/productions/21/audio', transcription_status: 'ok' }),
          consolidation: summary({ modality: 'oral' }),
        })
        stored = result.attempt
        return Response.json(result)
      },
    })
    const user = userEvent.setup()
    renderApp('/consolidation/attempts/21?task=4')
    await user.click(await screen.findByRole('button', { name: 'Transcribe' }))
    expect(await screen.findByRole('heading', { name: 'The terms of the task' })).toBeInTheDocument()
    expect(correctCalls(calls)).toHaveLength(1)
  })

  it('redirects a consolidation production opened as a writing', async () => {
    mockApi({ ...base, 'GET /productions/21': attempt() })
    const { router } = renderApp('/writing/21')
    await screen.findByRole('heading', { level: 1, name: 'Consolidation attempt' })
    expect(router.state.location.pathname).toBe('/consolidation/attempts/21')
  })

  it('redirects a writing production opened here', async () => {
    mockApi({ ...base, 'GET /productions/21': attempt({ kind: 'writing' }) })
    const { router } = renderApp('/consolidation/attempts/21')
    await screen.findByRole('heading', { level: 1, name: 'Your text and its correction' })
    expect(router.state.location.pathname).toBe('/writing/21')
  })

  it('is translated', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /productions/21': correctedAttempt() })
    renderApp('/consolidation/attempts/21')
    expect(await screen.findByRole('heading', { name: 'Les termes de la tâche' })).toBeInTheDocument()
  })
})
