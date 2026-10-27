import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { categoryTree } from '../../test/writingFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import {
  aiStats,
  errorStats,
  memoryStats,
  overview,
  practiceStats,
  progressStats,
  rate,
  share,
  STUDY_DAY,
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

const statsCalls = (calls: RecordedCall[], name: string) =>
  calls.filter((call) => call.path.startsWith(`/stats/${name}`))

const section = (name: string) => screen.getByRole('region', { name })

describe('/stats overview', () => {
  it('shows the headline figures with the counts behind them and the CSV link', async () => {
    mockApi(base)
    renderApp('/stats')
    const overviewSection = await screen.findByRole('region', { name: 'Overview' })
    await within(overviewSection).findByText('5.75 per 100 words')
    expect(within(overviewSection).getByText('The 28 days before: 6.67 per 100 words')).toBeInTheDocument()
    expect(within(overviewSection).getByText('90%')).toBeInTheDocument()
    expect(within(overviewSection).getByText('188 of 209 · target 90%')).toBeInTheDocument()
    expect(within(overviewSection).getByText('12 days')).toBeInTheDocument()
    expect(within(overviewSection).getByText('74 minutes')).toBeInTheDocument()
    const link = within(overviewSection).getByRole('link', { name: 'Download the CSV export' })
    expect(link).toHaveAttribute('href', '/api/export/csv')
  })

  it('says "not enough data" with the count instead of a number', async () => {
    mockApi({
      ...base,
      'GET /stats/overview': overview({
        error_rate_last_28: rate(null, 2, 40),
        retention_last_28: share(null, 3, 4),
      }),
    })
    renderApp('/stats')
    const overviewSection = await screen.findByRole('region', { name: 'Overview' })
    expect(await within(overviewSection).findByText('Not enough data (40 words so far)')).toBeInTheDocument()
    expect(within(overviewSection).getByText('Not enough data (4 reviews so far)')).toBeInTheDocument()
    expect(within(overviewSection).queryByText(/per 100 words$/)).not.toHaveTextContent(/^\d/)
  })

  it('has a French version', async () => {
    await i18n.changeLanguage('fr')
    mockApi(base)
    renderApp('/stats')
    expect(await screen.findByRole('heading', { name: 'Statistiques' })).toBeInTheDocument()
    expect(await screen.findByText('5,75 pour 100 mots')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Télécharger l'export CSV" })).toBeInTheDocument()
  })
})

describe('the period', () => {
  it('asks the last 30 days by day first, then follows the picker and the URL', async () => {
    const calls = mockApi(base)
    const { router } = renderApp('/stats')
    await screen.findByText(/Errors per 100 words you produced/)
    await waitFor(() => expect(statsCalls(calls, 'errors')).toHaveLength(1))
    expect(statsCalls(calls, 'errors')[0]?.path).toBe(
      `/stats/errors?from=2026-08-03&to=${STUDY_DAY}&granularity=day`,
    )
    await userEvent.selectOptions(screen.getByLabelText('Group by'), 'week')
    await waitFor(() =>
      expect(statsCalls(calls, 'memory').at(-1)?.path).toBe(
        `/stats/memory?from=2026-08-03&to=${STUDY_DAY}&granularity=week`,
      ),
    )
    expect(router.state.location.search).toContain('granularity=week')
  })

  it('reads the period of the URL', async () => {
    const calls = mockApi(base)
    renderApp('/stats?from=2026-07-01&to=2026-07-31&granularity=week')
    await waitFor(() => expect(statsCalls(calls, 'errors')).toHaveLength(1))
    expect(statsCalls(calls, 'errors')[0]?.path).toBe(
      '/stats/errors?from=2026-07-01&to=2026-07-31&granularity=week',
    )
    expect(screen.getByLabelText('From')).toHaveValue('2026-07-01')
  })

  it('refuses an invalid period at once and asks nothing for it', async () => {
    const calls = mockApi(base)
    renderApp('/stats?from=2026-09-02&to=2026-09-01')
    expect(await screen.findByText('The start date must not be after the end date.')).toBeInTheDocument()
    await screen.findByRole('heading', { name: 'Overview' })
    expect(statsCalls(calls, 'errors')).toHaveLength(0)
    expect(statsCalls(calls, 'memory')).toHaveLength(0)
    expect(screen.getByLabelText('From')).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows a refusal of the backend with a way to try again', async () => {
    let refuse = true
    const calls = mockApi({
      ...base,
      'GET /stats/errors': () =>
        refuse ? apiErrorResponse(422, 'invalid_request', 'bad period') : Response.json(errorStats()),
    })
    renderApp('/stats')
    const errorsSection = await screen.findByRole('region', { name: 'Errors' })
    expect(await within(errorsSection).findByRole('alert')).toHaveTextContent(
      'The request was not in the expected shape.',
    )
    refuse = false
    await userEvent.click(within(errorsSection).getByRole('button', { name: 'Try again' }))
    expect(await within(errorsSection).findByText('Your five most recurring errors')).toBeInTheDocument()
    expect(statsCalls(calls, 'errors')).toHaveLength(2)
  })
})

describe('/stats errors', () => {
  it('draws the chart with a table of the same numbers, a gap for too few words', async () => {
    mockApi(base)
    renderApp('/stats')
    const errorsSection = await screen.findByRole('region', { name: 'Errors' })
    await within(errorsSection).findByText('Your five most recurring errors')
    expect(
      within(errorsSection).getByRole('img', { name: 'Errors per 100 words over the period' }),
    ).toBeInTheDocument()
    const table = within(errorsSection).getAllByRole('table')[0] as HTMLElement
    const rows = within(table).getAllByRole('row')
    // Header, then one row per bucket: 6.5 for the first, no value for the second.
    expect(rows).toHaveLength(3)
    expect(within(rows[1] as HTMLElement).getAllByText('6.5').length).toBeGreaterThan(0)
    expect(within(rows[2] as HTMLElement).getAllByText('Not enough data').length).toBeGreaterThan(0)
  })

  it('lists the top recurring errors, shortening a long example but keeping it in the title', async () => {
    mockApi(base)
    renderApp('/stats')
    const errorsSection = await screen.findByRole('region', { name: 'Errors' })
    await within(errorsSection).findByText('in campus')
    expect(within(errorsSection).getByText(/7 times/)).toBeInTheDocument()
    expect(within(errorsSection).getByText(/already has a card/)).toBeInTheDocument()
    const long = errorStats().top_recurring[0]?.examples[1] as string
    const shown = within(errorsSection).getByTitle(long)
    expect(shown.textContent?.length).toBeLessThanOrEqual(140)
    expect(shown.textContent?.endsWith('…')).toBe(true)
    expect(within(errorsSection).getByText('I live in campus.')).toBeInTheDocument()
  })

  it('shows declining and rising trends in the open and the stable ones on demand', async () => {
    mockApi(base)
    renderApp('/stats')
    const errorsSection = await screen.findByRole('region', { name: 'Errors' })
    await within(errorsSection).findByRole('heading', { name: 'Declining (1)' })
    expect(within(errorsSection).getByRole('heading', { name: 'Rising (1)' })).toBeInTheDocument()
    expect(await within(errorsSection).findByText('Fixed expression')).toBeVisible()
    const stable = within(errorsSection).getByText('Stable (1)')
    expect(stable.closest('details')).not.toHaveAttribute('open')
    expect(within(errorsSection).getByText('10.5%')).toBeInTheDocument()
    expect(within(errorsSection).getByText(/Not in these rates: 3 errors/)).toBeInTheDocument()
  })
})

describe('/stats memory', () => {
  it('shows retention against the target, and an insufficient share without a number', async () => {
    mockApi(base)
    renderApp('/stats')
    const memory = await screen.findByRole('region', { name: 'Memory' })
    await within(memory).findByText('88.7%')
    expect(within(memory).getByText(/339 of 382/)).toBeInTheDocument()
    expect(
      within(memory).getByRole('img', { name: 'Observed retention and target over the period' }),
    ).toBeInTheDocument()
    // The exercise whose share is insufficient says so with its count; the other shows 90%.
    const spoken = within(memory).getByText('Spoken answer').closest('li') as HTMLElement
    expect(within(spoken).getByText('Not enough data (3 reviews so far)')).toBeInTheDocument()
    const gap = within(memory).getByText('Gap-fill').closest('li') as HTMLElement
    expect(within(gap).getByText('90% (90 of 100)')).toBeInTheDocument()
  })

  it('links the lapsed terms to the library and names a term that is gone', async () => {
    mockApi(base)
    renderApp('/stats')
    const memory = await screen.findByRole('region', { name: 'Memory' })
    const link = await within(memory).findByRole('link', { name: 'mitigate' })
    expect(link).toHaveAttribute('href', '/library/items/7')
    expect(within(memory).getByText('A term that no longer exists')).toBeInTheDocument()
  })

  it('says when no term was consolidated, and shows the quartiles when some were', async () => {
    mockApi(base)
    renderApp('/stats')
    const memory = await screen.findByRole('region', { name: 'Memory' })
    expect(await within(memory).findByText('No term was consolidated in this period.')).toBeInTheDocument()
  })

  it('shows the quartiles of the time before consolidation', async () => {
    mockApi({
      ...base,
      'GET /stats/memory': memoryStats({
        time_to_consolidation: {
          n: 58,
          days: { n: 58, q1: 3, median: 5.5, q3: 9, minimum: 1, maximum: 30 },
          reviews: { n: 58, q1: 4, median: 6, q3: 8, minimum: 2, maximum: 15 },
          distribution: [{ low: 0, high: 7, count: 40 }, { low: 7, high: null, count: 18 }],
          items: [],
        },
      }),
    })
    renderApp('/stats')
    const memory = await screen.findByRole('region', { name: 'Memory' })
    expect(await within(memory).findByText('58 terms consolidated')).toBeInTheDocument()
    const row = within(memory).getByText('Study days since the discovery').closest('tr') as HTMLElement
    expect(within(row).getByText('5.5')).toBeInTheDocument()
    expect(within(memory).getByText('7 days or more')).toBeInTheDocument()
  })
})

describe('section', () => {
  it('has a link for each section in a labelled navigation', async () => {
    mockApi(base)
    renderApp('/stats')
    const nav = await screen.findByRole('navigation', { name: 'Sections of the page' })
    expect(within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '#overview',
      '#errors',
      '#memory',
      '#progress',
      '#practice',
      '#ai',
    ])
    expect(section('Overview')).toBeInTheDocument()
  })
})
