import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CategoryNode } from '../../api/errors'
import { installFakeRecorder, recordTake } from '../../test/fakeRecorder'
import { errorRow } from '../../test/errorFixtures'
import { detail, sheetVersion } from '../../test/fixtures'
import { mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp, renderAppInBrowser } from '../../test/renderApp'
import { comparison, HEARD, shadowing, TARGET } from '../../test/speechFixtures'
import { categoryTree } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

/** The writing fixtures' tree plus the pronunciation branch the logged word goes to. */
function withPronunciation(): CategoryNode[] {
  const leaf = (code: string, parent: string | null, id: number, children: CategoryNode[] = []) => ({
    id,
    code,
    parent_code: parent,
    label_en: code === 'pronunciation' ? 'Pronunciation' : 'Intelligibility',
    label_fr: code === 'pronunciation' ? 'Prononciation' : 'Intelligibilité',
    description_en: '',
    description_fr: '',
    status: 'active' as const,
    origin: 'builtin' as const,
    count: 0,
    count_recent: 0,
    children,
  })
  return [
    ...categoryTree(),
    leaf('pronunciation', null, 800, [leaf('pronunciation.intelligibility', 'pronunciation', 801)]),
  ]
}

const errorPosts = (calls: RecordedCall[]) =>
  calls.filter((call) => call.method === 'POST' && call.path === '/errors')

describe('A misheard word, logged by hand', () => {
  function backend() {
    return mockApi({
      ...base,
      'GET /productions/7': () => Response.json(shadowing()),
      'GET /error-categories': withPronunciation(),
      'POST /errors': () =>
        Response.json(errorRow(31, { source: 'manual' }), { status: 201 }),
    })
  }

  it('opens the manual form already filled in, and creates nothing until the user validates', async () => {
    installFakeRecorder()
    const calls = backend()
    const user = userEvent.setup()
    const { router } = renderApp('/speaking/shadowing/7')

    await screen.findByText('4 of 6 words recognised')
    // "for" was not heard (no wrong form): one button only, for "fixed".
    await user.click(screen.getByRole('button', { name: /Log as an intelligibility error/ }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Add an error' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/errors/new')
    expect(screen.getByLabelText('The sentence where you made it (optional)')).toHaveValue(HEARD)
    expect(screen.getByLabelText('The incorrect form')).toHaveValue('fix')
    expect(screen.getByLabelText('The correction')).toHaveValue('fixed')
    await waitFor(() =>
      expect(screen.getByLabelText('Category')).toHaveValue('pronunciation.intelligibility'),
    )
    expect(screen.getByLabelText('Why it is wrong (optional)')).toHaveValue(
      'Speech recognition heard “fix” instead of “fixed”. Check how you say it before keeping this entry.',
    )
    expect(screen.getByText(/Filled in from your shadowing/)).toBeInTheDocument()
    // Nothing is created without a click.
    expect(errorPosts(calls)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Add to my log' }))
    expect(await screen.findByText('Added to your error log.')).toBeInTheDocument()
    expect(errorPosts(calls)).toHaveLength(1)
    expect(errorPosts(calls)[0]!.body).toEqual({
      original_text: HEARD,
      erroneous_text: 'fix',
      correction: 'fixed',
      alternatives: [],
      category_code: 'pronunciation.intelligibility',
      explanation:
        'Speech recognition heard “fix” instead of “fixed”. Check how you say it before keeping this entry.',
      lexical_item_id: null,
    })
    // The next entry starts empty.
    expect(screen.getByLabelText('The incorrect form')).toHaveValue('')
    expect(screen.queryByText(/Filled in from your shadowing/)).not.toBeInTheDocument()
  })

  it('reads the proposal once: the router state is cleared, so a reload shows an empty form', async () => {
    installFakeRecorder()
    backend()
    const { router } = renderAppInBrowser('/')
    await act(() =>
      router.navigate('/errors/new', {
        state: {
          original_text: HEARD,
          erroneous_text: 'fix',
          correction: 'fixed',
          category_code: 'pronunciation.intelligibility',
          explanation: 'x',
        },
      }),
    )
    expect(await screen.findByLabelText('The incorrect form')).toHaveValue('fix')
    await waitFor(() => expect(window.history.state?.usr ?? null).toBeNull())
    expect(JSON.stringify(window.history.state)).not.toContain('fixed')
  })

  it('ignores a navigation state that is not a proposal', async () => {
    backend()
    renderApp({ pathname: '/errors/new', state: { something: 'else' } })
    expect(await screen.findByLabelText('The incorrect form')).toHaveValue('')
    expect(screen.queryByText(/Filled in from your shadowing/)).not.toBeInTheDocument()
  })
})

describe('"Shadow this sentence" on the term page', () => {
  const origin = 'We account for regional fixed effects in all specifications.'
  const item = detail(20, 'account for', { origin_sentence: origin })

  function backend() {
    return mockApi({
      ...base,
      'GET /items/20': item,
      'GET /items/20/sheet': sheetVersion(),
      'GET /items/20/exercises': [],
      'GET /productions': { items: [], total: 0, limit: 20, offset: 0 },
    })
  }

  it('stays behind the reveal button, then opens the shadowing page with the sentence and the term', async () => {
    installFakeRecorder()
    backend()
    const user = userEvent.setup()
    const { router } = renderApp('/library/items/20')

    await screen.findByRole('button', { name: 'Show the usage sheet' })
    // Nothing of the sheet, and no shadow button, before the reveal (D-091).
    expect(screen.queryByRole('link', { name: /Shadow this sentence/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show the usage sheet' }))

    const links = await screen.findAllByRole('link', { name: /Shadow this sentence/ })
    // The original sentence, then the sheet's example.
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAccessibleName('Shadow this sentence (original sentence)')
    expect(links[1]).toHaveAccessibleName('Shadow this sentence (example 1)')

    await user.click(links[1]!)
    expect(await screen.findByLabelText('Sentence to repeat')).toHaveValue(
      'We account for regional effects.',
    )
    expect(router.state.location.pathname).toBe('/speaking/shadowing')
  })

  it('carries the term: the take is sent with its item_id', async () => {
    const kit = installFakeRecorder()
    const calls = mockApi({
      ...base,
      'GET /items/20': item,
      'GET /items/20/sheet': sheetVersion(),
      'GET /items/20/exercises': [],
      'POST /speech/shadowing': () =>
        Response.json(
          {
            production_id: 7,
            audio_url: '/api/productions/7/audio',
            audio_seconds: 2,
            transcription: { status: 'ok', text: HEARD, reason: null },
            comparison: comparison(),
          },
          { status: 201 },
        ),
      'GET /productions/7': () => Response.json(shadowing()),
    })
    const user = userEvent.setup()
    renderApp('/library/items/20')
    await user.click(await screen.findByRole('button', { name: 'Show the usage sheet' }))
    await user.click((await screen.findAllByRole('link', { name: /Shadow this sentence/ }))[0]!)
    expect(await screen.findByLabelText('Sentence to repeat')).toHaveValue(origin)

    await recordTake(user, kit)
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByRole('heading', { level: 1, name: 'Your shadowing' })
    const sent = calls.find((c) => c.method === 'POST' && c.path.startsWith('/speech/shadowing'))!
    expect(Object.fromEntries(new URL(sent.path, 'http://x').searchParams)).toMatchObject({
      target_text: origin,
      item_id: '20',
      origin: 'shadowing',
    })
    expect(TARGET.length).toBeGreaterThan(0)
  })

  it('has no shadow button on a term without an original sentence, only on its examples', async () => {
    installFakeRecorder()
    mockApi({
      ...base,
      'GET /items/20': detail(20, 'account for'),
      'GET /items/20/sheet': sheetVersion(),
      'GET /items/20/exercises': [],
    })
    const user = userEvent.setup()
    renderApp('/library/items/20')
    await user.click(await screen.findByRole('button', { name: 'Show the usage sheet' }))
    const links = await screen.findAllByRole('link', { name: /Shadow this sentence/ })
    expect(links).toHaveLength(1)
    expect(within(links[0]!.closest('li') as HTMLElement).getByText(/We account for regional effects/)).toBeInTheDocument()
  })
})
