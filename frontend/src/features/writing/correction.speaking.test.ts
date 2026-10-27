import { describe, expect, it } from 'vitest'

import { PART_1, SPEECH, speakingFeedback } from '../../test/speechFixtures'
import { feedback, PARAGRAPH } from '../../test/writingFixtures'
import { readFeedback } from './correction'

describe('readFeedback: speaking-1', () => {
  it('reads a monologue: the speaking kind, the errors by part, the structure', () => {
    const model = readFeedback({ text: SPEECH, feedback: speakingFeedback() })
    expect(model).not.toBeNull()
    expect(model?.kind).toBe('speaking')
    expect(model?.groups.map((group) => [group.number, group.errors.length])).toEqual([
      [1, 1],
      [2, 1],
    ])
    expect(model?.entries.map((entry) => entry.wrong)).toEqual(['in campus', 'since two years'])
    expect(model?.correctedText).toContain('I live on campus')
    expect(model?.naturalText).toContain('where I have studied')
    expect(model?.overall).toBe('Clear, with two small slips.')
    expect(model?.contextSent).toBeNull()
    expect(model?.structure).toMatchObject({
      connectors_used: ['so', 'first of all'],
      suggestions: [{ text_en: 'Try "In addition," to add a second idea.' }],
    })
  })

  it('puts the marks on the heard words', () => {
    const model = readFeedback({ text: SPEECH, feedback: speakingFeedback() })
    const marked = model?.segments.filter((part) => part.kind === 'mark').map((part) => part.text)
    expect(marked).toEqual(['in campus', 'since two years'])
    expect(model?.segments.map((part) => part.text).join('')).toBe(SPEECH)
    expect(PART_1).toContain('in campus')
  })

  it('reads the answer mode: no structure (null)', () => {
    const model = readFeedback({ text: SPEECH, feedback: speakingFeedback(SPEECH, { structure: null }) })
    expect(model?.kind).toBe('speaking')
    expect(model?.structure).toBeNull()
  })

  it('reads an answer without the key at all', () => {
    const stored = speakingFeedback()
    delete stored.output?.structure
    expect(readFeedback({ text: SPEECH, feedback: stored })?.structure).toBeNull()
  })

  it('leaves the written format without a structure, as it was', () => {
    const model = readFeedback({ text: PARAGRAPH, feedback: feedback(PARAGRAPH) })
    expect(model?.kind).toBe('text')
    expect(model?.structure).toBeNull()
  })

  it('still ignores an unknown format', () => {
    expect(readFeedback({ text: SPEECH, feedback: { ...speakingFeedback(), format: 'speaking-9' } })).toBeNull()
  })
})
