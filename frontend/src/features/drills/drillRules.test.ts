import { describe, expect, it } from 'vitest'

import {
  fillGap,
  firstUnanswered,
  isDrillableCode,
  isDrillableNode,
  progressOf,
  splitGap,
} from './drillRules'

describe('drillable categories', () => {
  it('needs level 2 or more and rejects pronunciation', () => {
    expect(isDrillableCode('grammar')).toBe(false)
    expect(isDrillableCode('grammar.preposition')).toBe(true)
    expect(isDrillableCode('grammar.preposition.fixed_expression')).toBe(true)
    expect(isDrillableCode('pronunciation')).toBe(false)
    expect(isDrillableCode('pronunciation.stress')).toBe(false)
    // Only the whole first segment counts, as on the server.
    expect(isDrillableCode('pronunciation_tips.x')).toBe(true)
  })

  it('wants an active category as well', () => {
    expect(isDrillableNode({ code: 'grammar.tense', status: 'active' })).toBe(true)
    expect(isDrillableNode({ code: 'grammar.tense', status: 'proposed' })).toBe(false)
    expect(isDrillableNode({ code: 'grammar.tense', status: 'rejected' })).toBe(false)
    expect(isDrillableNode({ code: 'grammar', status: 'active' })).toBe(false)
  })
})

describe('the gap', () => {
  it('splits the sentence around its gap', () => {
    expect(splitGap('We live ___ campus.')).toEqual(['We live ', ' campus.'])
    expect(splitGap('No gap here.')).toBeNull()
  })

  it('fills the gap, or keeps it when nothing was given', () => {
    expect(fillGap('We live ___ campus.', ' on ')).toBe('We live on campus.')
    expect(fillGap('We live ___ campus.', '')).toBe('We live ___ campus.')
    expect(fillGap('No gap here.', 'on')).toBe('No gap here.')
  })
})

describe('progress', () => {
  const item = (index: number, answered: boolean) => ({ index, answered })

  it('finds the first item not answered, or the end', () => {
    expect(firstUnanswered({ items: [item(0, true), item(1, false), item(2, false)] } as never)).toBe(1)
    expect(firstUnanswered({ items: [item(0, true), item(1, true)] } as never)).toBe(2)
    // The first hole wins even if a later item was answered.
    expect(firstUnanswered({ items: [item(0, false), item(1, true)] } as never)).toBe(0)
  })

  it('names the state of a drill', () => {
    const score = (answered: number) => ({ correct: 0, wrong: 0, empty: 0, answered, total: 5 })
    expect(progressOf({ completed: false, score: score(0) })).toBe('notStarted')
    expect(progressOf({ completed: false, score: score(2) })).toBe('inProgress')
    expect(progressOf({ completed: true, score: score(5) })).toBe('completed')
  })
})
