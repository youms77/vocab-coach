import { describe, expect, it } from 'vitest'

import python from '../../../../backend/app/domain/curriculum_unit.py?raw'
import { fullScenario } from '../../test/curriculumFixtures'
import {
  clientProblems,
  emptyFormula,
  fromScenario,
  locateProblem,
  moved,
  removed,
  toEdit,
  toParts,
} from './unitForm'
import { UNIT_LIMITS } from './unitRules'

/** The numbers of the Python line `NAME = ...` (or `A, B = x, y`). */
const constant = (names: string): number[] => {
  const line = new RegExp(`^${names} = (.+)$`, 'm').exec(python)?.[1] ?? ''
  return (line.match(/\d+/g) ?? []).map(Number)
}

describe('the limits', () => {
  it('are the constants of backend/app/domain/curriculum_unit.py', () => {
    const range = (r: { min: number; max: number }) => [r.min, r.max]
    expect(range(UNIT_LIMITS.formulas)).toEqual(constant('FORMULAS_MIN, FORMULAS_MAX'))
    expect(range(UNIT_LIMITS.lines)).toEqual(constant('LINES_MIN, LINES_MAX'))
    expect(range(UNIT_LIMITS.shadowing)).toEqual(constant('SHADOWING_MIN, SHADOWING_MAX'))
    expect(range(UNIT_LIMITS.shadowingWords)).toEqual(
      constant('SHADOWING_WORDS_MIN, SHADOWING_WORDS_MAX'),
    )
    expect([UNIT_LIMITS.finalRefsMin]).toEqual(constant('FINAL_REFS_MIN'))
    expect([...UNIT_LIMITS.minutes]).toEqual(constant('FINAL_MINUTES'))
    expect([UNIT_LIMITS.speakers]).toEqual(constant('SPEAKER_COUNT'))
    const max = UNIT_LIMITS.max
    expect([max.formula]).toEqual(constant('FORMULA_MAX'))
    expect([max.function]).toEqual(constant('FUNCTION_MAX'))
    expect([max.register]).toEqual(constant('REGISTER_MAX'))
    expect([max.setting]).toEqual(constant('SETTING_MAX'))
    expect([max.name]).toEqual(constant('NAME_MAX'))
    expect([max.line]).toEqual(constant('LINE_MAX'))
    expect([max.prompt]).toEqual(constant('PROMPT_MAX'))
  })
})

describe('toEdit', () => {
  const original = fullScenario({ revision: 4 })

  it('sends nothing when nothing changed', () => {
    expect(toEdit(fromScenario(original), original, 4)).toBeNull()
  })

  it('sends only the part that changed, with the revision and the key `register`', () => {
    const draft = fromScenario(original)
    draft.lines[1]!.text = 'A new second line for the dialogue.'
    const edit = toEdit(draft, original, 4)!
    expect(Object.keys(edit).sort()).toEqual(['dialogue', 'expected_revision'])
    expect(edit.expected_revision).toBe(4)
    expect(edit.dialogue!.lines[1]).toEqual({
      speaker: 'Dana',
      text: 'A new second line for the dialogue.',
    })

    const reworded = fromScenario(original)
    reworded.formulas[2]!.register = 'formal'
    const formulaEdit = toEdit(reworded, original, 4)!
    expect(formulaEdit.formulas![2]).toMatchObject({ register: 'formal', item_type: 'spoken_formula' })
    expect(formulaEdit.formulas![2]).not.toHaveProperty('style')
  })

  it('sends the final task with the formulas, so reworded ones keep their place', () => {
    const draft = fromScenario(original)
    draft.formulas[0]!.text = 'a reworded formula'
    const edit = toEdit(draft, original, 4)!
    expect(Object.keys(edit).sort()).toEqual(['expected_revision', 'final_task', 'formulas'])
    expect(edit.final_task!.formula_refs).toEqual([0, 1, 2])
  })

  it('counts positions from 0 after a move or a removal', () => {
    const draft = fromScenario(original)
    draft.formulas = moved(draft.formulas, 2, 1) // the ticked formula 2 goes to 3
    draft.formulas = moved(draft.formulas, 1, -1) // the ticked formula 1 goes to 0, formula 0 to 1
    expect(toEdit(draft, original, 4)!.final_task!.formula_refs).toEqual([0, 1, 3])
    const lines = fromScenario(original)
    lines.lines = removed(lines.lines, 0) // the first shadowed line disappears: 1..4 become 0..3
    expect(toEdit(lines, original, 4)!.shadowing).toEqual([0, 1, 2, 3])
  })

  it('trims the texts and keeps the speaker of a line when a speaker is renamed', () => {
    const draft = fromScenario(original)
    draft.speakers = ['Marcus ', 'Dana']
    draft.setting_en = '  A calm office.  '
    const dialogue = toParts(draft).dialogue
    expect(dialogue.setting_en).toBe('A calm office.')
    expect(dialogue.speakers).toEqual(['Marcus', 'Dana'])
    expect(dialogue.lines[0]!.speaker).toBe('Marcus')
    expect(dialogue.lines[1]!.speaker).toBe('Dana')
  })
})

describe('clientProblems', () => {
  it('accepts a full unit', () => {
    expect(clientProblems(fromScenario(fullScenario()))).toEqual([])
  })

  it('checks the counts, the empty texts, the shadowing lines and the references', () => {
    const draft = fromScenario(fullScenario())
    draft.formulas = draft.formulas.slice(0, 7)
    draft.formulas[0]!.text = ' '
    draft.lines[0]!.shadow = false
    draft.lines[5]!.shadow = true
    draft.lines[5]!.text = 'Too short.'
    draft.formulas.forEach((f) => (f.inTask = false))
    const found = clientProblems(draft).map((p) => `${p.path}:${p.key}`)
    expect(found).toEqual(
      expect.arrayContaining([
        'formulas:count',
        'formulas[0].text:empty',
        'dialogue.lines[5].shadow:shadowingWords',
        'final_task.formula_refs:refsMin',
      ]),
    )
    draft.formulas.push(emptyFormula())
    expect(clientProblems(draft).some((p) => p.path === 'formulas')).toBe(false)
  })

  it('wants two different speaker names and the number of lines and of shadowed lines', () => {
    const draft = fromScenario(fullScenario())
    draft.speakers = ['Dana', ' dana']
    draft.lines.forEach((line) => (line.shadow = true))
    draft.lines = [...draft.lines, ...draft.lines, ...draft.lines.slice(0, 1)] // 17 lines
    const found = clientProblems(draft).map((p) => `${p.path}:${p.key}`)
    expect(found).toContain('dialogue.speakers:speakersDiffer')
    expect(found).toContain('dialogue.lines:count')
    expect(found).toContain('shadowing:count')
  })
})

describe('locateProblem', () => {
  it('maps the positions of the lists sent back to the ticked rows', () => {
    const draft = fromScenario(fullScenario())
    draft.lines[0]!.shadow = false // shadowing is now lines 1, 2, 3, 4
    expect(locateProblem('shadowing[0]: the line has 3 words, 4 to 25 are needed', draft).path).toBe(
      'dialogue.lines[1].shadow',
    )
    expect(locateProblem('final_task.formula_refs[2]: not a formula of the unit', draft).path).toBe(
      'formulas[2].inTask',
    )
    expect(locateProblem('formulas[3]: repeats formulas[1]', draft).path).toBe('formulas[3].text')
    expect(locateProblem('formulas[3].text: must not be empty', draft)).toEqual({
      path: 'formulas[3].text',
      message: 'must not be empty',
    })
    expect(
      locateProblem('dialogue: only 2 of 8 formulas are used (at least half are needed)', draft).path,
    ).toBe('dialogue')
  })
})
