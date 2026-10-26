import { describe, expect, it } from 'vitest'

import { row, scenario, scenarioRows, wordUnit } from '../../test/curriculumFixtures'
import {
  neighbours,
  pageFromParam,
  pageOfUnit,
  readUnitId,
  refsOf,
  speakerIndex,
  stepsDone,
  termsToTriage,
  unitFromParam,
  unitTitle,
} from './unitRules'

describe('unitTitle', () => {
  it('uses title_fr in French when there is one, else the English title', () => {
    const titled = row({ title: 'Job interview 1', title_fr: "Entretien d'embauche 1" })
    expect(unitTitle(titled, 'fr')).toBe("Entretien d'embauche 1")
    expect(unitTitle(titled, 'fr-FR')).toBe("Entretien d'embauche 1")
    expect(unitTitle(titled, 'en')).toBe('Job interview 1')
    expect(unitTitle(row({ title: 'Words 1 to 25', title_fr: null }), 'fr')).toBe('Words 1 to 25')
    expect(unitTitle(row({ title: 'Words 1 to 25', title_fr: '' }), 'fr')).toBe('Words 1 to 25')
  })
})

describe('steps and terms', () => {
  it('counts the steps done', () => {
    expect(stepsDone({ formulas: true, dialogue: false, shadowing: true, final_task: false })).toBe(2)
    expect(stepsDone(scenario().steps)).toBe(0)
  })

  it('counts the terms of a word unit still to triage', () => {
    expect(termsToTriage(wordUnit())).toBe(2)
  })

  it('gives the formulas of the final task in the order of its references', () => {
    const task = scenario({
      final_task: { ...scenario().final_task, formula_refs: [2, 0, 9] },
    })
    expect(refsOf(task).map((f) => f.index)).toEqual([2, 0])
  })

  it('tells the two speakers apart, an unknown name reading as the first', () => {
    const { dialogue } = scenario()
    expect(speakerIndex(dialogue, 'Marc')).toBe(0)
    expect(speakerIndex(dialogue, 'Dana')).toBe(1)
    expect(speakerIndex(dialogue, 'Someone')).toBe(0)
  })
})

describe('neighbours', () => {
  it('finds a unit and the next one in a slice of two rows', () => {
    const { current, next } = neighbours(scenarioRows(3), 3)
    expect(current?.number).toBe(3)
    expect(next?.number).toBe(4)
  })

  it('finds no next unit at the end of a track, nor anything before the data arrives', () => {
    expect(neighbours([row({ number: 16 })], 16).next).toBeNull()
    expect(neighbours(undefined, 1)).toEqual({ current: null, next: null })
  })
})

describe('numbers from the URL and the navigation state', () => {
  it('reads a page (1-based in the URL) as an index', () => {
    expect(pageFromParam(null)).toBe(0)
    expect(pageFromParam('1')).toBe(0)
    expect(pageFromParam('3')).toBe(2)
    expect(pageFromParam('0')).toBe(0)
    expect(pageFromParam('x')).toBe(0)
    expect(pageFromParam('2.5')).toBe(0)
  })

  it('finds the page of a unit', () => {
    expect(pageOfUnit(1, 25)).toBe(1)
    expect(pageOfUnit(25, 25)).toBe(1)
    expect(pageOfUnit(26, 25)).toBe(2)
  })

  it('accepts a positive integer unit id only', () => {
    expect(unitFromParam('21')).toBe(21)
    for (const bad of [null, '', '0', '-1', 'x', '1.5']) expect(unitFromParam(bad)).toBeNull()
    expect(readUnitId({ unitId: 21 })).toBe(21)
    for (const bad of [null, undefined, 'x', {}, { unitId: '21' }, { unitId: 0 }, { unitId: 2.5 }]) {
      expect(readUnitId(bad)).toBeNull()
    }
  })
})
