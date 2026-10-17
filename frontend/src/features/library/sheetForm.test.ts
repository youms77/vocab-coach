import { describe, expect, it } from 'vitest'

import { usageSheet } from '../../test/fixtures'
import { fromSheet, hasMeaning, toSheet } from './sheetForm'

describe('sheet form helpers', () => {
  it('round-trips a stored sheet', () => {
    const sheet = usageSheet({
      collocations: [{ pattern: 'account for variation', example: 'It accounts for 40 %.' }],
      confusables: [{ term: 'explain', difference: 'more general' }],
    })
    expect(toSheet(fromSheet(sheet))).toEqual(sheet)
  })

  it('trims, empties to null and drops incomplete rows', () => {
    const draft = fromSheet(null, 'verb')
    draft.definition_simple = '  to consider  '
    draft.register_note = '   '
    draft.translation_fr = [' tenir compte de ', '']
    draft.word_family = [
      { form: 'accountable', part_of_speech: 'adjective' },
      { form: 'accounting', part_of_speech: '' },
    ]
    draft.examples = [{ sentence: '  ', kind: 'spoken' }]
    draft.collocations = [{ pattern: 'account for', example: ' ' }]
    const sheet = toSheet(draft)
    expect(sheet).toMatchObject({
      part_of_speech: 'verb',
      definition_simple: 'to consider',
      register_note: null,
      register_level: null,
      translation_fr: ['tenir compte de'],
      word_family: [{ form: 'accountable', part_of_speech: 'adjective' }],
      examples: [],
      collocations: [{ pattern: 'account for', example: null }],
      pronunciation: null,
    })
  })

  it('needs a definition or a translation', () => {
    expect(hasMeaning(toSheet(fromSheet(null)))).toBe(false)
    expect(hasMeaning(usageSheet({ definition_simple: null }))).toBe(true)
    expect(hasMeaning(usageSheet({ translation_fr: [] }))).toBe(true)
  })
})
