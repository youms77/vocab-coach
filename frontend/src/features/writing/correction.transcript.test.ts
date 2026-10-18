import { describe, expect, it } from 'vitest'

import {
  OTHER_1,
  STORED,
  transcriptFeedback,
  USER_1,
  USER_2,
} from '../../test/transcriptFixtures'
import { feedback, PARAGRAPH } from '../../test/writingFixtures'
import { readFeedback } from './correction'

describe('readFeedback: transcript-1', () => {
  it('reads your turns: kind, groups by your turn, no natural version, no targets', () => {
    const model = readFeedback({ text: STORED, feedback: transcriptFeedback() })
    expect(model).not.toBeNull()
    expect(model?.kind).toBe('transcript')
    expect(model?.groups.map((group) => [group.number, group.errors.length])).toEqual([
      [1, 1],
      [2, 1],
    ])
    expect(model?.entries.map((entry) => entry.wrong)).toEqual(['in campus', 'since two years'])
    expect(model?.naturalText).toBeNull()
    expect(model?.targets).toEqual([])
    expect(model?.correctedText).toContain('I live on campus')
    expect(model?.overall).toBe('Two small slips in four turns.')
  })

  it('numbers by turn, not by unit: two units of one long turn are one group', () => {
    const stored = transcriptFeedback()
    // The second unit is the second piece of the first turn.
    stored.units = [
      { index: 1, turn: 0, start: 0, end: 36, opens_turn: true },
      { index: 2, turn: 0, start: 37, end: 66, opens_turn: false },
    ]
    const model = readFeedback({ text: STORED, feedback: stored })
    expect(model?.groups.map((group) => [group.number, group.errors.length])).toEqual([[1, 2]])
    expect(model?.numberOf(2)).toBe(1)
    // An unknown unit keeps its own index rather than disappearing.
    expect(model?.numberOf(9)).toBe(9)
  })

  it('puts the marks on the right words after an emoji (code points to UTF-16)', () => {
    const text = `😀 ${USER_1}\n\n${USER_2}`
    const model = readFeedback({ text, feedback: transcriptFeedback({ text }) })
    const marked = model?.segments.filter((part) => part.kind === 'mark').map((part) => part.text)
    expect(marked).toEqual(['in campus', 'since two years'])
    // The whole text is kept, turns separated by a blank line (shown with pre-wrap).
    expect(model?.segments.map((part) => part.text).join('')).toBe(text)
    expect(model?.segments.map((part) => part.text).join('')).toContain('\n\n')
  })

  it('tells whether the other speaker context was sent', () => {
    expect(readFeedback({ text: STORED, feedback: transcriptFeedback({ contextSent: true }) })?.contextSent).toBe(true)
    expect(readFeedback({ text: STORED, feedback: transcriptFeedback({ contextSent: false }) })?.contextSent).toBe(false)
    // A written text has no such notion; and a missing flag reads as "not sent".
    expect(readFeedback({ text: PARAGRAPH, feedback: feedback(PARAGRAPH) })?.contextSent).toBeNull()
    const noFlag = transcriptFeedback()
    delete noFlag.context_sent
    expect(readFeedback({ text: STORED, feedback: noFlag })?.contextSent).toBe(false)
  })

  it('never contains the other speaker (it is not stored)', () => {
    const model = readFeedback({ text: STORED, feedback: transcriptFeedback() })
    expect(JSON.stringify(model)).not.toContain(OTHER_1)
  })

  it('leaves the written format as it was', () => {
    const model = readFeedback({ text: PARAGRAPH, feedback: feedback(PARAGRAPH) })
    expect(model?.kind).toBe('text')
    expect(model?.groups.map((group) => group.number)).toEqual([2])
    expect(model?.numberOf(2)).toBe(2)
  })

  it('still ignores an unknown format', () => {
    expect(readFeedback({ text: STORED, feedback: { ...transcriptFeedback(), format: 'transcript-9' } })).toBeNull()
  })
})
