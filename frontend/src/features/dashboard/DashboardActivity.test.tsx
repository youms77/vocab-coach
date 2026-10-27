import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'
import {
  aiStats,
  errorStats,
  memoryStats,
  overview,
  practiceStats,
  progressStats,
  providerDay,
} from '../../test/statsFixtures'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
  'GET /error-categories': categoryTree(),
  'GET /stats/overview': overview(),
  'GET /stats/errors': errorStats(),
  'GET /stats/memory': memoryStats(),
  'GET /stats/progress': progressStats(),
  'GET /stats/practice': practiceStats(),
  'GET /stats/ai': aiStats(),
}

const calls = (recorded: RecordedCall[], name: string) =>
  recorded.filter((call) => call.path.startsWith(`/stats/${name}`))

describe('/stats progress', () => {
  it('shows the funnel now with the counts, and the statuses outside it', async () => {
    mockApi(base)
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    const queued = (await within(progress).findByText('Queued', { selector: '.bar-list__label' })).closest(
      'li',
    ) as HTMLElement
    expect(within(queued).getByText('40')).toBeInTheDocument()
    expect(within(progress).getByText(/Outside the funnel:/)).toHaveTextContent(
      'Draft 1 · To sort 6 · Known 3 · Archived 2',
    )
  })

  it('draws the rebuilt statuses and the active terms, each with its numbers table', async () => {
    mockApi(base)
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    expect(
      await within(progress).findByRole('img', {
        name: 'Number of terms by status at the end of each period',
      }),
    ).toBeInTheDocument()
    expect(within(progress).getByRole('img', { name: 'Active terms over the period' })).toBeInTheDocument()
    expect(within(progress).getAllByText('Show the numbers')).toHaveLength(3)
  })

  it('lists the decks with their state and the terms consolidated or beyond', async () => {
    mockApi(base)
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    const row = (await within(progress).findByText('Econometrics core')).closest('tr') as HTMLElement
    expect(within(row).getByText('Active')).toBeInTheDocument()
    expect(within(row).getByText('30')).toBeInTheDocument()
    // 12 consolidated + 5 active + 3 known.
    expect(within(row).getByText('20 of 30')).toBeInTheDocument()
    const empty = within(progress).getByText('Meeting phrases').closest('tr') as HTMLElement
    expect(within(empty).getByText('–')).toBeInTheDocument()
  })

  it('shows the tracks in the interface language and what is not started', async () => {
    mockApi(base)
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    const row = (await within(progress).findByText('General everyday English')).closest('tr') as HTMLElement
    expect(within(row).getByText('50')).toBeInTheDocument()
    expect(within(row).getByText('4')).toBeInTheDocument()
    expect(within(progress).getByText(/not started/)).toBeInTheDocument()
  })

  it('totals the forecast of the next days', async () => {
    mockApi(base)
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    expect(await within(progress).findByText('42 cards, about 14 minutes')).toBeInTheDocument()
  })

  it('says a failure of its own section with a retry, the others stay', async () => {
    let refuse = true
    const recorded = mockApi({
      ...base,
      'GET /stats/progress': () =>
        refuse ? apiErrorResponse(422, 'invalid_request', 'bad period') : Response.json(progressStats()),
    })
    renderApp('/stats')
    const progress = await screen.findByRole('region', { name: 'Progress' })
    expect(await within(progress).findByRole('alert')).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'Practice' })).toBeInTheDocument()
    refuse = false
    await userEvent.click(within(progress).getByRole('button', { name: 'Try again' }))
    expect(await within(progress).findByText('Terms by status, now')).toBeInTheDocument()
    expect(calls(recorded, 'progress')).toHaveLength(2)
  })

  it('follows the period of the URL', async () => {
    const recorded = mockApi(base)
    renderApp('/stats?from=2026-07-01&to=2026-07-31&granularity=week')
    await waitFor(() => expect(calls(recorded, 'progress')).toHaveLength(1))
    expect(calls(recorded, 'progress')[0]?.path).toBe(
      '/stats/progress?from=2026-07-01&to=2026-07-31&granularity=week',
    )
    expect(calls(recorded, 'practice')[0]?.path).toBe(
      '/stats/practice?from=2026-07-01&to=2026-07-31&granularity=week',
    )
    expect(calls(recorded, 'ai')[0]?.path).toBe(
      '/stats/ai?from=2026-07-01&to=2026-07-31&granularity=week',
    )
  })
})

describe('/stats practice', () => {
  it('shows the study time from the actions, with the sessions only alongside', async () => {
    mockApi(base)
    renderApp('/stats')
    const practice = await screen.findByRole('region', { name: 'Practice' })
    expect(await within(practice).findByText('90 minutes')).toBeInTheDocument()
    expect(within(practice).getByText('over 18 active days')).toBeInTheDocument()
    expect(within(practice).queryByText('100 minutes')).not.toBeInTheDocument()
    expect(
      within(practice).getByRole('img', { name: 'Study time in minutes over the period' }),
    ).toBeInTheDocument()
  })

  it('shows the streaks of the whole history and when the longest ended', async () => {
    mockApi(base)
    renderApp('/stats')
    const practice = await screen.findByRole('region', { name: 'Practice' })
    expect(await within(practice).findByText('Current streak: 4 days')).toBeInTheDocument()
    expect(within(practice).getByText(/Longest streak: 12 days/)).toHaveTextContent('ended on')
    expect(within(practice).getByText('21 active days in the last 30')).toBeInTheDocument()
  })

  it('counts the words written and said apart, and the speech by kind', async () => {
    mockApi(base)
    renderApp('/stats')
    const practice = await screen.findByRole('region', { name: 'Practice' })
    expect(await within(practice).findByText('650 words written')).toBeInTheDocument()
    expect(within(practice).getByText('150 words said')).toBeInTheDocument()
    expect(within(practice).getByText('10 minutes of speech')).toBeInTheDocument()
    const shadowing = within(practice).getByText('Shadowing', { selector: '.bar-list__label' }).closest(
      'li',
    ) as HTMLElement
    expect(within(shadowing).getByText('6.7 min')).toBeInTheDocument()
  })

  it('says when nothing was recorded', async () => {
    mockApi({
      ...base,
      'GET /stats/practice': practiceStats({ speech_seconds: 0, speech_by_kind: {}, speech: [] }),
    })
    renderApp('/stats')
    const practice = await screen.findByRole('region', { name: 'Practice' })
    expect(await within(practice).findByText('No recording in this period.')).toBeInTheDocument()
  })
})

describe('/stats AI', () => {
  it('shows the calls per provider with the rate limits and quotas apart from the errors', async () => {
    mockApi(base)
    renderApp('/stats')
    const ai = await screen.findByRole('region', { name: 'AI use' })
    expect(await within(ai).findByText('43 requests')).toBeInTheDocument()
    const gemini = within(ai)
      .getByText('Google Gemini', { exact: false, selector: 'th[scope="row"]' })
      .closest('tr') as HTMLElement
    expect(within(gemini).getByText('35 of 40')).toBeInTheDocument()
    // 3 rate limits and 2 timeouts: the table counts the errors, rate limits and quota in their own columns.
    const cells = within(gemini).getAllByRole('cell')
    expect(cells.map((c) => c.textContent)).toEqual([
      '35 of 40',
      '5',
      '3',
      '1',
      '12,000 / 4,000',
      '850 ms',
    ])
    const groq = within(ai)
      .getByText('Groq', { selector: 'th[scope="row"]' })
      .closest('tr') as HTMLElement
    expect(within(groq).getByText('–')).toBeInTheDocument()
  })

  it('lists the errors by code and the requests per day in a chart with a table', async () => {
    mockApi(base)
    renderApp('/stats')
    const ai = await screen.findByRole('region', { name: 'AI use' })
    expect(await within(ai).findByText('rate_limit')).toBeInTheDocument()
    expect(within(ai).getByText('timeout')).toBeInTheDocument()
    expect(
      within(ai).getByRole('img', { name: 'AI requests per day and provider' }),
    ).toBeInTheDocument()
  })

  it('shows the Azure month with its audio minutes and assessments, and no invented limit', async () => {
    mockApi(base)
    renderApp('/stats')
    const ai = await screen.findByRole('region', { name: 'AI use' })
    expect(
      await within(ai).findByText('2026-09 (UTC): 5 minutes of audio, 12 assessments.'),
    ).toBeInTheDocument()
    expect(ai.textContent).not.toMatch(/\b5 ?hours\b/i)
  })

  it('says so when no call was made, without an empty table', async () => {
    mockApi({
      ...base,
      'GET /stats/ai': aiStats({
        totals: [providerDay({ requests: 0, successes: 0, errors: {} })],
        days: [{ day: '2026-09-01', requests: 0, successes: 0, providers: [] }],
      }),
    })
    renderApp('/stats')
    const ai = await screen.findByRole('region', { name: 'AI use' })
    expect(await within(ai).findByText('No AI call in this period.')).toBeInTheDocument()
    expect(within(ai).queryByText('Mean duration')).not.toBeInTheDocument()
  })

  it('has a French version of the three sections', async () => {
    await i18n.changeLanguage('fr')
    mockApi(base)
    renderApp('/stats')
    expect(await screen.findByRole('region', { name: 'Progression' })).toBeInTheDocument()
    expect(await screen.findByText('650 mots écrits')).toBeInTheDocument()
    expect(await screen.findByText('Anglais courant')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: "Usage de l'IA" })).toBeInTheDocument()
  })
})
