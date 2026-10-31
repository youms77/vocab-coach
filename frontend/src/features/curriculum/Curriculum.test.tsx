import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { GenerationResult, Scenario, Unit } from '../../api/curriculum'
import i18n from '../../i18n'
import {
  detail,
  formula,
  LINE_1,
  LINE_2,
  row,
  scenarioRows,
  scenarioTrack,
  scenarioUnit,
  track,
  wordUnit,
} from '../../test/curriculumFixtures'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const posts = (calls: RecordedCall[], path: string) =>
  calls.filter((call) => call.method === 'POST' && call.path.split('?')[0] === path)

const gets = (calls: RecordedCall[], prefix: string) =>
  calls.filter((call) => call.method === 'GET' && call.path.startsWith(prefix))

const academic = () =>
  track({
    code: 'academic',
    source: 'nawl',
    title: { en: 'Academic English', fr: 'Anglais académique' },
    available: false,
    reason: 'wordlist_missing',
    unit_count: 39,
  })

describe('/curriculum', () => {
  it('lists the tracks, says why a track is unavailable and shows the licence', async () => {
    mockApi({
      ...base,
      'GET /curriculum/tracks': [track(), academic(), scenarioTrack({ opened_units: 2 })],
    })
    renderApp('/curriculum')

    expect(
      await screen.findByRole('heading', { level: 1, name: 'General English tracks' }),
    ).toHaveFocus()
    for (const name of ['General everyday English', 'Academic English', 'Speaking scenarios']) {
      expect(await screen.findByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
    expect(screen.getByText('113 units')).toBeInTheDocument()
    // The track that is not available: a reason in words and a disabled button.
    expect(screen.getByRole('button', { name: 'Start the track “Academic English”' })).toBeDisabled()
    expect(screen.getByText(/word list file is missing from this installation/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start the track “General everyday English”' })).toBeEnabled()
    // A started track: Continue, and the units written.
    expect(screen.getByRole('link', { name: 'Continue the track “Speaking scenarios”' })).toHaveAttribute(
      'href',
      '/curriculum/speaking_scenarios',
    )
    expect(screen.getByText(/2 units written/)).toBeInTheDocument()
    // The licence of the two word lists.
    expect(
      screen.getByText(/NGSL \/ NAWL 1\.2, Browne, Culligan & Phillips, CC BY-SA 4\.0/),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'newgeneralservicelist.com' })).toHaveAttribute(
      'href',
      'https://www.newgeneralservicelist.com',
    )
  })

  it('starts a track from its card, once, and goes to the track page', async () => {
    let started = false
    const calls = mockApi({
      ...base,
      'GET /curriculum/tracks': () => Response.json([track({ started })]),
      'POST /curriculum/tracks/general_everyday/start': () => {
        started = true
        return Response.json({ track: track({ started: true, deck_id: 5 }), created: true })
      },
      'GET /curriculum/tracks/general_everyday': () =>
        Response.json(detail(track({ started: true, deck_id: 5 }), [row()])),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum')
    await user.click(
      await screen.findByRole('button', { name: 'Start the track “General everyday English”' }),
    )

    expect(await screen.findByRole('heading', { level: 1, name: 'General everyday English' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/curriculum/general_everyday')
    expect(posts(calls, '/curriculum/tracks/general_everyday/start')).toHaveLength(1)
    expect(posts(calls, '/curriculum/tracks/general_everyday/start')[0]!.body).toBeUndefined()
  })

  it('has no card for a track the backend does not list, and says an error', async () => {
    mockApi({ ...base, 'GET /curriculum/tracks': () => apiErrorResponse(503, 'syllabus_unavailable') })
    renderApp('/curriculum')
    expect(await screen.findByRole('alert')).toHaveTextContent('syllabus file could not be read')
  })

  it('speaks French', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /curriculum/tracks': [track(), scenarioTrack()] })
    renderApp('/curriculum')
    expect(
      await screen.findByRole('heading', { level: 1, name: "Parcours d’anglais général" }),
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Anglais courant de tous les jours' }),
    ).toBeInTheDocument()
    expect(screen.getByText('113 unités')).toBeInTheDocument()
    // The top bar entry, in both languages.
    expect(screen.getByRole('link', { name: 'Parcours' })).toHaveAttribute('href', '/curriculum')
    expect(screen.getByRole('button', { name: 'Commencer le parcours « Anglais courant de tous les jours »' })).toBeInTheDocument()
  })
})

describe('/curriculum/:code', () => {
  const started = track({ started: true, deck_id: 5, unit_count: 113 })

  function wordBackend() {
    return mockApi({
      ...base,
      'GET /curriculum/tracks/general_everyday': (call) => {
        const offset = Number(new URL(call.path, 'http://x').searchParams.get('offset'))
        const first = offset / 25 + 1
        return Response.json(
          detail(started, [row({ number: first, title: `Words ${first}` })], {
            total_units: 113,
            offset,
          }),
        )
      },
    })
  }

  it('keeps the page in the URL: 25 units per request, Next and Previous', async () => {
    const calls = wordBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum/general_everyday?page=3')

    expect(await screen.findByText('Page 3 of 5')).toBeInTheDocument()
    expect(gets(calls, '/curriculum/tracks/general_everyday')[0]!.path).toBe(
      '/curriculum/tracks/general_everyday?limit=25&offset=50',
    )
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Page 4 of 5')).toBeInTheDocument()
    expect(router.state.location.search).toBe('?page=4')
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    expect(await screen.findByText('Page 1 of 5')).toBeInTheDocument()
    expect(router.state.location.search).toBe('')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  it('offers "Start this track" when it is not started, and starts it once', async () => {
    let isStarted = false
    const calls = mockApi({
      ...base,
      'GET /curriculum/tracks/general_everyday': () =>
        Response.json(detail(track({ started: isStarted }), [row()])),
      'POST /curriculum/tracks/general_everyday/start': () => {
        isStarted = true
        return Response.json({ track: track({ started: true }), created: true })
      },
    })
    const user = userEvent.setup()
    renderApp('/curriculum/general_everyday')

    expect(await screen.findByRole('heading', { name: 'This track is not started' })).toBeInTheDocument()
    // Nothing can be opened before the track is started.
    expect(screen.queryByRole('button', { name: 'Open unit 1' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start this track' }))
    expect(await screen.findByRole('button', { name: 'Open unit 1' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'This track is not started' })).not.toBeInTheDocument()
    expect(posts(calls, '/curriculum/tracks/general_everyday/start')).toHaveLength(1)
  })

  it('opens a word unit once, goes to its page and links to the triage of its deck', async () => {
    let opened = false
    const calls = mockApi({
      ...base,
      'GET /curriculum/tracks/general_everyday': () =>
        Response.json(
          detail(started, [
            opened
              ? row({ state: 'opened', unit_id: 11 })
              : row({ state: 'not_opened', unit_id: null }),
          ]),
        ),
      'POST /curriculum/tracks/general_everyday/units/1/open': () => {
        opened = true
        return Response.json({ created: true, imported: 3, attached: 0, skipped: 0, unit: wordUnit() })
      },
      'GET /curriculum/units/11': () => Response.json(wordUnit()),
    })
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum/general_everyday')
    // A word unit says its state in words and shows no content status.
    expect(await screen.findByText(/Not opened/)).toBeInTheDocument()
    expect(screen.queryByText(/generated/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open unit 1' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Words 1 to 25' })).toHaveFocus()
    expect(router.state.location.pathname).toBe('/curriculum/units/11')
    expect(posts(calls, '/curriculum/tracks/general_everyday/units/1/open')).toHaveLength(1)
    // The words, with their status in words, linked to the library; no usage sheet, no definition.
    expect(screen.getByRole('link', { name: 'the' })).toHaveAttribute('href', '/library/items/101')
    expect(screen.getByText('Learning')).toBeInTheDocument()
    expect(screen.queryByText(/generated/i)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Triage these words (2 left)' })).toHaveAttribute(
      'href',
      '/triage?deck=5',
    )
    expect(screen.getByRole('link', { name: 'Open the deck of this track' })).toHaveAttribute(
      'href',
      '/library?deck=5',
    )

    // Back on the track, the unit is a link: opening it again writes nothing.
    await user.click(screen.getByRole('link', { name: 'Back to the track' }))
    const again = await screen.findByRole('link', { name: 'Open unit 1' })
    await user.click(again)
    await screen.findByRole('heading', { level: 1, name: 'Words 1 to 25' })
    expect(posts(calls, '/curriculum/tracks/general_everyday/units/1/open')).toHaveLength(1)
  })

  it('says when every word of a unit is sorted', async () => {
    mockApi({
      ...base,
      'GET /curriculum/units/11': wordUnit({
        state: 'triaged',
        terms: [{ item_id: 101, term: 'the', status: 'learning' }],
      }),
    })
    renderApp('/curriculum/units/11')
    expect(await screen.findByText('Every word of this unit is sorted.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Triage these words/ })).not.toBeInTheDocument()
  })

  it('answers a track that does not exist', async () => {
    mockApi({
      ...base,
      'GET /curriculum/tracks/nope': () => apiErrorResponse(404, 'track_not_found'),
    })
    renderApp('/curriculum/nope')
    expect(await screen.findByRole('alert')).toHaveTextContent('This track does not exist.')
  })
})

describe('Writing a scenario unit with the AI', () => {
  const trackDetail = () =>
    detail(scenarioTrack(), [
      row({
        number: 1,
        code: 'job_interview_1',
        title: 'Job interview 1',
        title_fr: "Entretien d'embauche 1",
        state: 'opened',
        unit_id: 21,
        progress: 'in_progress',
        first_rank: null,
        last_rank: null,
        word_count: null,
      }),
      row({
        number: 2,
        code: 'job_interview_2',
        title: 'Job interview 2',
        title_fr: "Entretien d'embauche 2",
        unit_id: null,
        content_status: 'pending',
        first_rank: null,
        last_rank: null,
        word_count: null,
      }),
    ])

  function generationBackend(answers: (() => Response | Promise<Response>)[]) {
    let attempt = 0
    return mockApi({
      ...base,
      'GET /curriculum/tracks/speaking_scenarios': () => Response.json(trackDetail()),
      'GET /curriculum/units/22': () => Response.json(scenarioUnit({ id: 22, number: 2 })),
      'POST /curriculum/tracks/speaking_scenarios/units/2/generate': () => {
        const answer = answers[Math.min(attempt, answers.length - 1)]!
        attempt += 1
        return answer()
      },
    })
  }

  const unavailable: GenerationResult = { status: 'unavailable', reason: 'quota', detail: null, unit: null }
  const incomplete: GenerationResult = { status: 'incomplete', reason: null, detail: null, unit: null }

  it('lists the written unit with its progress in words and the unwritten one with its button', async () => {
    generationBackend([() => Response.json(unavailable)])
    renderApp('/curriculum/speaking_scenarios')
    expect(await screen.findByText(/In progress/)).toBeInTheDocument()
    expect(screen.getByText('Not written yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open unit 1' })).toHaveAttribute('href', '/curriculum/units/21')
    expect(screen.getByRole('button', { name: 'Write this unit with the AI' })).toBeInTheDocument()
  })

  it('sends one request on a double click, counts the seconds, then says nothing was written and tries again', async () => {
    let release: (response: Response) => void = () => undefined
    const calls = generationBackend([
      () => new Promise<Response>((resolve) => (release = resolve)),
      () => Response.json(incomplete),
      () => Response.json({ status: 'ok', reason: null, detail: null, unit: scenarioUnit({ id: 22, number: 2 }) }),
    ])
    const user = userEvent.setup()
    const { router } = renderApp('/curriculum/speaking_scenarios')
    const button = await screen.findByRole('button', { name: 'Write this unit with the AI' })
    await user.dblClick(button)

    expect(await screen.findByText(/Writing the unit… \d+ s/)).toBeInTheDocument()
    // The counter ticks.
    await waitFor(() => expect(screen.getByText(/Writing the unit… [1-9]\d* s/)).toBeInTheDocument(), {
      timeout: 4000,
    })
    const generate = posts(calls, '/curriculum/tracks/speaking_scenarios/units/2/generate')
    expect(generate).toHaveLength(1)
    expect(generate[0]!.body).toBeUndefined()

    await act(async () => release(Response.json(unavailable)))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The AI is unavailable: the free quota is used up')
    expect(alert).toHaveTextContent('Nothing was written.')
    expect(within(alert).getByRole('link', { name: 'Configure the AI' })).toHaveAttribute('href', '/settings')
    expect(router.state.location.pathname).toBe('/curriculum/speaking_scenarios')

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('The AI did not return a usable unit. Nothing was written.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Configure the AI' })).not.toBeInTheDocument()
    expect(posts(calls, '/curriculum/tracks/speaking_scenarios/units/2/generate')).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Job interview 2' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/curriculum/units/22')
  })

  it('refreshes silently when the unit was written meanwhile (409 unit_generated)', async () => {
    const calls = generationBackend([() => apiErrorResponse(409, 'unit_generated')])
    const user = userEvent.setup()
    renderApp('/curriculum/speaking_scenarios')
    await user.click(await screen.findByRole('button', { name: 'Write this unit with the AI' }))

    await waitFor(() =>
      expect(gets(calls, '/curriculum/tracks/speaking_scenarios').length).toBeGreaterThan(1),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('A scenario unit', () => {
  const rows = (number: number) => detail(scenarioTrack(), scenarioRows(number), { total_units: 16 })

  function unitBackend(unit: () => Unit, extra: Record<string, unknown> = {}) {
    return mockApi({
      ...base,
      'GET /curriculum/units/21': () => Response.json(unit()),
      'GET /curriculum/tracks/speaking_scenarios': () => Response.json(rows(1)),
      ...extra,
    })
  }

  const withSteps = (steps: Partial<Scenario['steps']>, next: Scenario['next_step']) => ({
    steps: { formulas: false, dialogue: false, shadowing: false, final_task: false, ...steps },
    next_step: next,
  })

  it('shows the header, the four steps in words and the next step highlighted', async () => {
    unitBackend(() => scenarioUnit({ progress: 'in_progress' }, withSteps({ formulas: true }, 'dialogue')))
    renderApp('/curriculum/units/21')

    expect(await screen.findByRole('heading', { level: 1, name: 'Job interview 1' })).toHaveFocus()
    expect(screen.getByText(/Level B1 · 1 of 4 steps · In progress/)).toBeInTheDocument()
    expect(screen.getByText('Next step: dialogue')).toBeInTheDocument()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual([
      'Step 1: Formulas',
      'Step 2: Dialogue',
      'Step 3: Shadowing',
      'Step 4: Final task',
    ])
    const dialogue = screen.getByRole('region', { name: 'Step 2: Dialogue' })
    expect(within(dialogue).getByText('Next step')).toBeInTheDocument()
    expect(within(dialogue).getByText('To do')).toBeInTheDocument()
    const formulas = screen.getByRole('region', { name: 'Step 1: Formulas' })
    expect(within(formulas).getByText('Done')).toBeInTheDocument()
    expect(within(formulas).queryByText('Next step')).not.toBeInTheDocument()
  })

  it('titles the unit in French when the track gives a French title', async () => {
    await i18n.changeLanguage('fr')
    unitBackend(() => scenarioUnit())
    renderApp('/curriculum/units/21')
    expect(
      await screen.findByRole('heading', { level: 1, name: "Entretien d'embauche 1" }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Étape 1 : formules' })).toBeInTheDocument()
    expect(screen.getByText(/0 étapes sur 4/)).toBeInTheDocument()
    expect(screen.getByText('Un entretien dans une petite entreprise.')).toBeInTheDocument()
    // The English setting on demand.
    await userEvent.setup().click(screen.getByRole('button', { name: 'Afficher en anglais' }))
    expect(screen.getByText('A job interview at a small company.')).toBeInTheDocument()
  })

  it('marks the formulas and the dialogue as done, one request each', async () => {
    let unit = scenarioUnit({}, withSteps({}, 'formulas'))
    const calls = unitBackend(() => unit, {
      'POST /curriculum/units/21/steps/formulas': () => {
        unit = scenarioUnit({ progress: 'in_progress' }, withSteps({ formulas: true }, 'dialogue'))
        return Response.json({ changed: true, unit })
      },
      'POST /curriculum/units/21/steps/dialogue': () => {
        unit = scenarioUnit(
          { progress: 'in_progress' },
          withSteps({ formulas: true, dialogue: true }, 'shadowing'),
        )
        return Response.json({ changed: true, unit })
      },
    })
    installFakeSpeech()
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')

    await user.click(await screen.findByRole('button', { name: 'I have read the formulas' }))
    expect(await screen.findByText('Next step: dialogue')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'I have read the formulas' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'I listened to the dialogue' }))
    expect(await screen.findByText('Next step: shadowing')).toBeInTheDocument()
    expect(screen.getByText(/2 of 4 steps/)).toBeInTheDocument()

    expect(posts(calls, '/curriculum/units/21/steps/formulas')).toHaveLength(1)
    expect(posts(calls, '/curriculum/units/21/steps/dialogue')).toHaveLength(1)
    expect(posts(calls, '/curriculum/units/21/steps/formulas')[0]!.body).toBeUndefined()
  })

  it('adds the checked formulas to the library and links to their triage', async () => {
    let unit = scenarioUnit({ deck_id: 7 }, { formulas: [formula(0), formula(1), formula(2, { item_id: 303 })] })
    const calls = unitBackend(() => unit, {
      'POST /curriculum/units/21/terms': () => {
        unit = scenarioUnit(
          { deck_id: 7 },
          { formulas: [formula(0, { item_id: 300 }), formula(1), formula(2, { item_id: 303 })] },
        )
        return Response.json({ imported: 1, attached: 0, skipped: 0, unit })
      },
    })
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')

    // A formula already in the library is not checkable: it links to its term.
    await screen.findByRole('heading', { level: 1, name: 'Job interview 1' })
    expect(screen.getAllByRole('checkbox')).toHaveLength(2)
    expect(screen.getByRole('link', { name: 'In your library' })).toHaveAttribute('href', '/library/items/303')
    for (const box of screen.getAllByRole('checkbox')) expect(box).toBeChecked()
    expect(screen.getByText('2 formulas selected.')).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: 'Add to my library: “formula number 2”' }))
    expect(screen.getByText('1 formula selected.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add these formulas to my library' }))

    expect(await screen.findByText('Added: 1 new, 0 already in your library, 0 skipped.')).toBeInTheDocument()
    expect(posts(calls, '/curriculum/units/21/terms')[0]!.body).toEqual({ indices: [0] })
    expect(screen.getByRole('link', { name: 'Sort these terms now' })).toHaveAttribute('href', '/triage?deck=7')
    // The formula that was added is no longer checkable; the unchecked one still is, unchecked.
    expect(screen.getAllByRole('checkbox')).toHaveLength(1)
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Add these formulas to my library' })).toBeDisabled()
  })

  it('shows the French of a formula on demand only', async () => {
    unitBackend(() => scenarioUnit())
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')
    await screen.findByText('Says thing 1.')
    expect(screen.queryByText('Dit la chose 1.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'In French: “formula number 1”' }))
    expect(screen.getByText('Dit la chose 1.')).toBeInTheDocument()
    expect(screen.queryByText('Dit la chose 2.')).not.toBeInTheDocument()
    // One listen button pair per formula.
    expect(screen.getByRole('button', { name: 'Listen to “formula number 1”' })).toBeInTheDocument()
  })

  it('plays the dialogue line after line with two voices, stops, and keeps the text collapsed until asked', async () => {
    const speech = installFakeSpeech()
    unitBackend(() => scenarioUnit())
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')

    await screen.findByRole('heading', { level: 1, name: 'Job interview 1' })
    // Collapsed: no line of the dialogue is in its step (the shadowing step lists its own lines).
    const step = screen.getByRole('region', { name: 'Step 2: Dialogue' })
    expect(within(step).queryByText(LINE_1, { exact: false })).not.toBeInTheDocument()
    expect(within(step).queryByText('Tell me about yourself.', { exact: false })).not.toBeInTheDocument()
    expect(screen.getByText('Listen first, then check the text.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show the text' })).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() => expect(speech.getVoices().length).toBeGreaterThan(0))

    await user.click(screen.getByRole('button', { name: 'Listen to the whole dialogue' }))
    expect(speech.spoken.map((u) => u.text)).toEqual([LINE_1])
    expect(speech.spoken[0]!.voice?.name).toBe('Microsoft Zira - English (United States)')
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()

    act(() => speech.finish())
    expect(speech.spoken.map((u) => u.text)).toEqual([LINE_1, LINE_2])
    // The second speaker has another en-US voice.
    expect(speech.spoken[1]!.voice?.name).toBe('Microsoft David - English (United States)')
    act(() => speech.finish())
    expect(speech.spoken).toHaveLength(3)
    act(() => speech.finish())
    expect(speech.spoken).toHaveLength(3)
    expect(await screen.findByRole('button', { name: 'Listen to the whole dialogue' })).toBeInTheDocument()

    // Stop: nothing goes on after it.
    await user.click(screen.getByRole('button', { name: 'Listen to the whole dialogue' }))
    expect(speech.spoken).toHaveLength(4)
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    act(() => speech.finish())
    expect(speech.spoken).toHaveLength(4)
    expect(screen.getByRole('button', { name: 'Listen to the whole dialogue' })).toBeInTheDocument()

    // Slow speed.
    await user.click(screen.getByRole('radio', { name: 'Slow' }))
    await user.click(screen.getByRole('button', { name: 'Listen to the whole dialogue' }))
    expect(speech.spoken[4]!.rate).toBeLessThan(1)
    await user.click(screen.getByRole('button', { name: 'Stop' }))

    // Expanded: the text, with one listen button per line.
    await user.click(screen.getByRole('button', { name: 'Show the text' }))
    expect(within(step).getByText(LINE_1, { exact: false })).toBeInTheDocument()
    expect(within(step).getByText('Tell me about yourself.', { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide the text' })).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('button', { name: 'Listen to line 2' }))
    expect(speech.spoken.at(-1)!.text).toBe(LINE_2)
    expect(speech.spoken.at(-1)!.voice?.name).toBe('Microsoft David - English (United States)')
  })

  it('says why the dialogue cannot be played without speech synthesis', async () => {
    unitBackend(() => scenarioUnit())
    renderApp('/curriculum/units/21')
    await screen.findByRole('heading', { level: 1, name: 'Job interview 1' })
    expect(screen.getByRole('button', { name: 'Listen to the whole dialogue' })).toBeDisabled()
    expect(screen.getAllByText(/no speech synthesis/).length).toBeGreaterThan(0)
  })

  it('lists the shadowing lines with their takes and a worded done mark', async () => {
    unitBackend(() => scenarioUnit())
    renderApp('/curriculum/units/21')
    const step = await screen.findByRole('region', { name: 'Step 3: Shadowing' })
    const items = within(step).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Not done yet')
    expect(items[0]).toHaveTextContent('0 takes')
    expect(items[1]).toHaveTextContent('Done')
    expect(items[1]).toHaveTextContent('2 takes')
    expect(within(step).getByText(/not a pronunciation judge/)).toBeInTheDocument()
  })

  it('shows the final task, its formulas, the French on demand and the takes', async () => {
    unitBackend(() =>
      scenarioUnit(
        {},
        {
          final_task: {
            prompt_en: 'Introduce yourself for one minute.',
            prompt_fr: 'Présentez-vous pendant une minute.',
            minutes: 1,
            formula_refs: [0, 2],
            target_item_ids: [],
            attempt_ids: [31, 32],
            corrected: true,
          },
        },
      ),
    )
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')
    const step = await screen.findByRole('region', { name: 'Step 4: Final task' })
    expect(within(step).getByText('Introduce yourself for one minute.')).toBeInTheDocument()
    expect(within(step).getByText('About 1 minute')).toBeInTheDocument()
    expect(within(step).getByText('formula number 1')).toBeInTheDocument()
    expect(within(step).getByText('formula number 3')).toBeInTheDocument()
    expect(within(step).queryByText('formula number 2')).not.toBeInTheDocument()
    expect(within(step).queryByText('Présentez-vous pendant une minute.')).not.toBeInTheDocument()
    await user.click(within(step).getByRole('button', { name: 'Show in French' }))
    expect(within(step).getByText('Présentez-vous pendant une minute.')).toBeInTheDocument()
    expect(within(step).getByRole('link', { name: 'Record my talk' })).toHaveAttribute('href', '/speaking')
    expect(within(step).getByRole('link', { name: 'Talk 2' })).toHaveAttribute('href', '/speaking/32?unit=21')
    expect(within(step).getByText('Corrected')).toBeInTheDocument()
  })

  it('says the unit is completed, links to the next one and announces it once on the transition', async () => {
    let unit = scenarioUnit({ progress: 'in_progress' }, withSteps({ formulas: true }, 'dialogue'))
    unitBackend(() => unit, {
      'POST /curriculum/units/21/steps/dialogue': () => {
        unit = scenarioUnit(
          { progress: 'done' },
          withSteps({ formulas: true, dialogue: true, shadowing: true, final_task: true }, null),
        )
        return Response.json({ changed: true, unit })
      },
    })
    installFakeSpeech()
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')
    await screen.findByRole('heading', { level: 1, name: 'Job interview 1' })
    expect(screen.queryByText('Unit completed')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'I listened to the dialogue' }))
    expect(await screen.findByText('Unit completed')).toBeInTheDocument()
    expect(screen.getByText('Unit completed.', { selector: '[role="status"]' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Next unit: Job interview 2' })).toHaveAttribute(
      'href',
      '/curriculum/units/22',
    )
  })

  it('shows "Unit completed" for a unit that was already done, without announcing it', async () => {
    unitBackend(() =>
      scenarioUnit(
        { progress: 'done' },
        withSteps({ formulas: true, dialogue: true, shadowing: true, final_task: true }, null),
      ),
    )
    renderApp('/curriculum/units/21')
    expect(await screen.findByText('Unit completed')).toBeInTheDocument()
    expect(screen.queryByText('Unit completed.', { selector: '[role="status"]' })).not.toBeInTheDocument()
  })

  it('answers a unit that does not exist', async () => {
    mockApi({ ...base, 'GET /curriculum/units/99': () => apiErrorResponse(404, 'unit_not_found') })
    renderApp('/curriculum/units/99')
    expect(await screen.findByRole('alert')).toHaveTextContent('This unit does not exist.')
  })

  it('shows the problems of a refused content', async () => {
    unitBackend(() => scenarioUnit(), {
      'POST /curriculum/units/21/steps/formulas': () =>
        apiErrorResponse(422, 'invalid_content', 'bad', { problems: ['formulas[2]: must not be empty'] }),
    })
    installFakeSpeech()
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')
    await user.click(await screen.findByRole('button', { name: 'I have read the formulas' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The content of the unit was refused:')
    expect(alert).toHaveTextContent('formulas[2]: must not be empty')
  })
})
