import { describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { rate, share } from '../../test/statsFixtures'
import { formatPercent, formatRate, formatShare } from './format'
import { addDays, defaultPeriod, periodProblem } from './period'

const t = i18n.t.bind(i18n)

describe('formatRate and formatShare', () => {
  it('never shows a number for an insufficient rate, only the count reached', () => {
    const text = formatRate(t, 'en', { value: 3.2, errors: 2, words: 40, insufficient: true })
    expect(text).toBe('Not enough data (40 words so far)')
    expect(text).not.toContain('3.2')
  })

  it('treats a null value as insufficient even if the flag were missing', () => {
    expect(formatRate(t, 'en', { value: null, errors: 0, words: 1, insufficient: false })).toBe(
      'Not enough data (1 word so far)',
    )
  })

  it('writes a sufficient rate per 100 words', () => {
    expect(formatRate(t, 'en', rate(5.75, 92, 1600))).toBe('5.75 per 100 words')
  })

  it('writes a share as a percentage and an insufficient one with its reviews', () => {
    expect(formatShare(t, 'en', share(0.887, 339, 382))).toBe('88.7%')
    expect(formatShare(t, 'en', { value: 0.5, successes: 2, n: 4, insufficient: true })).toBe(
      'Not enough data (4 reviews so far)',
    )
  })

  it('follows the interface language', async () => {
    await i18n.changeLanguage('fr')
    expect(formatRate(i18n.t.bind(i18n), 'fr', rate(5.75, 92, 1600))).toContain('pour 100 mots')
    expect(formatPercent('fr', 0.9, 0)).toContain('90')
  })
})

describe('period', () => {
  it('defaults to the last 30 study days, today included', () => {
    expect(defaultPeriod('2026-09-01')).toEqual({
      from: '2026-08-03',
      to: '2026-09-01',
      granularity: 'day',
    })
  })

  it('adds days across months and years', () => {
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })

  it('refuses what the backend refuses: order, more than 366 days, malformed dates', () => {
    const base = { granularity: 'day' } as const
    expect(periodProblem({ ...base, from: '2026-09-02', to: '2026-09-01' })).toBe('order')
    expect(periodProblem({ ...base, from: '2025-08-31', to: '2026-09-01' })).toBe('tooLong')
    expect(periodProblem({ ...base, from: '2025-09-01', to: '2026-09-01' })).toBeNull()
    expect(periodProblem({ ...base, from: '2026-02-30', to: '2026-03-01' })).toBe('invalid')
    expect(periodProblem({ ...base, from: '', to: '2026-03-01' })).toBe('invalid')
    expect(periodProblem({ ...base, from: '2026-09-01', to: '2026-09-01' })).toBeNull()
  })
})
