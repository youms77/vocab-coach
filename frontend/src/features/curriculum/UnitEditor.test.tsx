import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { Scenario, Unit } from '../../api/curriculum'
import i18n from '../../i18n'
import {
  detail,
  fullScenario,
  scenarioRows,
  scenarioTrack,
  scenarioUnit,
} from '../../test/curriculumFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const puts = (calls: RecordedCall[]) =>
  calls.filter((call) => call.method === 'PUT' && call.path === '/curriculum/units/21/content')

const unitWith = (content: Partial<Scenario> = {}, overrides: Partial<Unit> = {}) =>
  scenarioUnit(overrides, fullScenario({ revision: 3, ...content }))

/** A backend with one unit; `put` answers the edit and may change what `GET` returns after. */
function editorBackend(
  put: (call: RecordedCall, set: (unit: Unit) => void) => Response,
  start: Unit = unitWith(),
) {
  let current = start
  const calls = mockApi({
    ...base,
    'GET /curriculum/units/21': () => Response.json(current),
    'GET /curriculum/tracks/speaking_scenarios': () =>
      Response.json(detail(scenarioTrack(), scenarioRows(1), { total_units: 16 })),
    'PUT /curriculum/units/21/content': (call) => put(call, (unit) => (current = unit)),
  })
  return { calls }
}

/** The answer of a successful edit: the revision goes up and the unit is "edited by you". */
const saved = (_call: RecordedCall, set: (unit: Unit) => void) => {
  const unit = unitWith({ revision: 4, edited: true }, { content_status: 'edited' })
  set(unit)
  return Response.json(unit)
}

const group = (name: string) => within(screen.getByRole('group', { name }))

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  renderApp('/curriculum/units/21')
  await user.click(await screen.findByRole('button', { name: 'Edit the unit' }))
  return screen.findByRole('heading', { level: 2, name: 'Edit the unit' })
}

async function retype(user: ReturnType<typeof userEvent.setup>, field: HTMLElement, text: string) {
  await user.clear(field)
  await user.paste(text)
}

// The form has about 60 fields and re-renders as a whole: a test takes a few seconds, more on a busy machine.
describe('The unit editor', { timeout: 30_000 }, () => {
  it('sends only what changed, with the revision, 0-based positions and the key register', async () => {
    const { calls } = editorBackend(saved)
    const user = userEvent.setup()
    const heading = await openEditor(user)
    expect(heading).toHaveFocus()
    expect(screen.queryByText('Edited by you')).not.toBeInTheDocument()

    await retype(user, group('formula 2').getByLabelText('Register'), 'formal')
    await retype(user, screen.getByLabelText('Text of line 2'), 'Thank you, Marc. It is a pleasure.')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    await waitFor(() => expect(puts(calls)).toHaveLength(1))
    const body = puts(calls)[0]!.body as Record<string, unknown>
    expect(Object.keys(body).sort()).toEqual(['dialogue', 'expected_revision', 'final_task', 'formulas'])
    expect(body.expected_revision).toBe(3)
    expect((body.formulas as { register: string }[])[1]!.register).toBe('formal')
    expect(body.formulas).not.toEqual(expect.arrayContaining([expect.objectContaining({ style: 'formal' })]))
    const dialogue = body.dialogue as { lines: { speaker: string; text: string }[] }
    expect(dialogue.lines[1]).toEqual({ speaker: 'Dana', text: 'Thank you, Marc. It is a pleasure.' })
    expect(body.shadowing).toBeUndefined()
    expect((body.final_task as { formula_refs: number[] }).formula_refs).toEqual([0, 1, 2])

    // After the save: the badge, a word of confirmation, the steps are back and the button has the focus.
    expect(await screen.findByText('Edited by you')).toBeInTheDocument()
    expect(screen.getByText('The unit was saved.')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toContain('Step 1: Formulas')
    expect(screen.getByRole('button', { name: 'Edit the unit' })).toHaveFocus()
  })

  it('sends a single part when a single part changed, and nothing when nothing did', async () => {
    const { calls } = editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)
    expect(screen.getByRole('button', { name: 'Save the unit' })).toBeDisabled()
    expect(screen.getByText('Nothing has changed yet.')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Length'), '2')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))
    await waitFor(() => expect(puts(calls)).toHaveLength(1))
    const body = puts(calls)[0]!.body as Record<string, unknown>
    expect(Object.keys(body).sort()).toEqual(['expected_revision', 'final_task'])
    expect((body.final_task as { minutes: number }).minutes).toBe(2)
  })

  it('moves, removes and adds rows, and sends the new positions', async () => {
    const { calls } = editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)

    // Shadowing keeps following its lines: line 1 (shadowed) goes down, so lines 0 and 1 swap.
    await user.click(screen.getByRole('button', { name: 'Move line 1 down' }))
    expect(screen.getByRole('button', { name: 'Move line 2 down' })).toHaveFocus() // the row followed
    await user.click(screen.getByRole('button', { name: 'Remove line 8' }))
    expect(screen.getByRole('button', { name: 'Add a line' })).toHaveFocus()
    expect(screen.queryByLabelText('Text of line 8')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add a line' }))
    expect(screen.getByLabelText('Text of line 8')).toHaveFocus()
    await user.paste('Well, that is all for today.')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    await waitFor(() => expect(puts(calls)).toHaveLength(1))
    const body = puts(calls)[0]!.body as { dialogue: { lines: { text: string }[] }; shadowing?: number[] }
    expect(body.dialogue.lines).toHaveLength(8)
    expect(body.dialogue.lines[0]!.text).toBe('This is line number 2 of the dialogue.')
    expect(body.dialogue.lines[7]!.text).toBe('Well, that is all for today.')
    // The shadowed lines were 0 to 4: the same five rows, so the list does not change.
    expect(body.shadowing).toBeUndefined()
  })

  it('checks the limits itself, says where, and sends nothing', async () => {
    const { calls } = editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)

    await user.click(screen.getByRole('button', { name: 'Remove formula 8' }))
    await user.clear(screen.getByLabelText('Text of line 1'))
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The unit was not saved: 2 problems to fix.')
    expect(screen.getByText('8 to 15 are needed.')).toBeInTheDocument()
    const line = screen.getByLabelText('Text of line 1')
    expect(line).toBeInvalid()
    expect(line).toHaveFocus()
    expect(line).toHaveAccessibleDescription('Must not be empty.')
    expect(puts(calls)).toHaveLength(0)
    // The texts are limited as the server limits them.
    expect(line).toHaveAttribute('maxlength', '300')
    expect(group('formula 1').getByLabelText('Formula')).toHaveAttribute('maxlength', '120')
  })

  it('refuses a shadowing line of the wrong length and fewer than three formulas in the task', async () => {
    editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)

    await retype(user, screen.getByLabelText('Text of line 1'), 'Too short.')
    await user.click(screen.getByRole('checkbox', { name: /^1\. Too short\./ }))
    await user.click(screen.getByRole('checkbox', { name: /^1\. formula number 1$/ }))
    await user.click(screen.getByRole('checkbox', { name: /^2\. formula number 2$/ }))
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    expect(await screen.findByText('Tick at least 3 formulas.')).toBeInTheDocument()
    // Line 1 is no longer ticked for shadowing: 4 lines left, 5 to 8 are needed.
    expect(screen.getByText('5 to 8 are needed.')).toBeInTheDocument()
  })

  it('shows the 422 problems at their field, or in a list when no field matches', async () => {
    const { calls } = editorBackend(() =>
      apiErrorResponse(422, 'invalid_content', 'bad', {
        problems: [
          'formulas[1].function_en: must not be empty',
          'shadowing[0]: the line has 3 words, 4 to 25 are needed',
          'dialogue: only 2 of 8 formulas are used (at least half are needed)',
        ],
      }),
    )
    const user = userEvent.setup()
    await openEditor(user)
    await retype(user, group('formula 2').getByLabelText('Register'), 'formal')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The unit was not saved: 3 problems to fix.')
    expect(within(alert).getByText(/only 2 of 8 formulas are used/)).toBeInTheDocument()
    expect(within(alert).queryByText(/must not be empty/)).not.toBeInTheDocument()
    const english = group('formula 2').getByLabelText('What it does (English)')
    expect(english).toBeInvalid()
    expect(english).toHaveAccessibleDescription('must not be empty')
    // `shadowing[0]` is the first ticked line, which is line 1 here.
    expect(screen.getByRole('checkbox', { name: /^1\. This is line number 1/ })).toBeInvalid()
    // The edit is still on screen.
    expect(group('formula 2').getByLabelText('Register')).toHaveValue('formal')
    expect(puts(calls)).toHaveLength(1)
  })

  it('keeps the edits on a 409 and replaces them only after a confirmation', async () => {
    const { calls } = editorBackend(
      (_, set) => {
        // Saved from another tab meanwhile.
        const latest = unitWith(
          { revision: 5, edited: true, final_task: { ...fullScenario().final_task, prompt_en: 'Their prompt.' } },
          { content_status: 'edited' },
        )
        set(latest)
        return apiErrorResponse(409, 'unit_changed', 'changed', { revision: 5 })
      },
    )
    const user = userEvent.setup()
    await openEditor(user)
    await retype(user, screen.getByLabelText('Prompt (English)'), 'My own prompt.')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))

    expect(await screen.findByText(/The unit changed since you opened the editor/)).toBeInTheDocument()
    expect(screen.getByLabelText('Prompt (English)')).toHaveValue('My own prompt.')
    expect(puts(calls)[0]!.body).toMatchObject({ expected_revision: 3 })

    const load = await screen.findByRole('button', { name: 'Load the latest version' })
    await waitFor(() => expect(load).toBeEnabled())
    await user.click(load)
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Replace your edits with the latest version of the unit?')
    // Still the edits: nothing was replaced yet.
    expect(screen.getByLabelText('Prompt (English)')).toHaveValue('My own prompt.')

    await user.click(within(dialog).getByRole('button', { name: 'Keep editing' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Prompt (English)')).toHaveValue('My own prompt.')

    await user.click(screen.getByRole('button', { name: 'Load the latest version' }))
    await user.click(screen.getByRole('button', { name: 'Replace my edits' }))
    expect(screen.getByLabelText('Prompt (English)')).toHaveValue('Their prompt.')
    expect(screen.queryByText(/The unit changed since/)).not.toBeInTheDocument()
    // The next save starts from the latest revision.
    await user.selectOptions(screen.getByLabelText('Length'), '2')
    await user.click(screen.getByRole('button', { name: 'Save the unit' }))
    await waitFor(() => expect(puts(calls)).toHaveLength(2))
    expect(puts(calls)[1]!.body).toMatchObject({ expected_revision: 5 })
  })

  it('warns, before the save, that editing a shadowing line makes its takes stop counting', async () => {
    editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)
    const shadowing = group('Lines to shadow')
    expect(shadowing.getByText(/the takes recorded for the old line stop counting/)).toBeVisible()
    expect(shadowing.getByText(/can go back to “in progress”/)).toBeVisible()
  })

  it('cancels without sending anything', async () => {
    const { calls } = editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)
    await retype(user, screen.getByLabelText('Prompt (English)'), 'Something else.')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Edit the unit' })).toHaveFocus()
    expect(puts(calls)).toHaveLength(0)
  })

  it('is in French, with "vous"', async () => {
    await i18n.changeLanguage('fr')
    editorBackend(saved, unitWith({ edited: true }, { content_status: 'edited' }))
    const user = userEvent.setup()
    renderApp('/curriculum/units/21')
    expect(await screen.findByText('Modifiée par vous')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: "Modifier l’unité" }))
    expect(screen.getByText(/Changez ce que vous voulez/)).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Phrases à répéter' })).toBeInTheDocument()
    expect(screen.getByText(/ne comptent plus/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: "Enregistrer l’unité" })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Monter la réplique 2' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Supprimer la formule 8' }))
    await user.click(screen.getByRole('button', { name: "Enregistrer l’unité" }))
    expect(await screen.findByRole('alert')).toHaveTextContent("L’unité n’a pas été enregistrée : 1 problème à corriger.")
    expect(screen.getByText('8 à 15 sont attendues.')).toBeInTheDocument()
  })

  it('has no "Write this unit with the AI" button on a written unit', async () => {
    editorBackend(saved)
    const user = userEvent.setup()
    await openEditor(user)
    expect(screen.queryByRole('button', { name: /with the AI/ })).not.toBeInTheDocument()
  })
})
