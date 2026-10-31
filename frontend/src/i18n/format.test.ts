import { describe, expect, it } from 'vitest'

import { formatInstant, formatNumber, formatPercent, formatStudyDay } from './format'

const plain = (text: string) => text.replace(/[  ]/g, ' ')

describe('numbers', () => {
  it('follow the language', () => {
    expect(formatNumber('en', 2983)).toBe('2,983')
    expect(plain(formatNumber('fr', 2983))).toBe('2 983')
    expect(formatPercent('en', 0.125)).toBe('12.5%')
    expect(plain(formatPercent('fr', 0.125))).toBe('12,5 %')
  })

  it('French percentages use a no-break space', () => {
    expect(formatPercent('fr', 0.5)).toMatch(/^50[  ]%$/)
  })
})

describe('the 24-hour clock', () => {
  it('French has no am/pm, English has', () => {
    const iso = '2026-10-27T15:05:00Z'
    const options = { timeStyle: 'short', timeZone: 'UTC' } as const
    expect(formatInstant('fr', iso, options)).toBe('15:05')
    expect(formatInstant('en', iso, options)).toMatch(/PM/)
  })
})

// A study day is a calendar day: no time zone may move it.
describe.each(['America/Los_Angeles', 'Pacific/Honolulu', 'Africa/Douala', 'Pacific/Kiritimati'])(
  'study days in %s',
  (zone) => {
    it('are formatted without a shift', () => {
      const original = process.env.TZ
      process.env.TZ = zone
      try {
        expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(zone)
        expect(formatStudyDay('en', '2026-10-27', { day: 'numeric', month: 'long' })).toBe(
          'October 27',
        )
        expect(formatStudyDay('fr', '2026-10-27', { day: 'numeric', month: 'long' })).toBe(
          '27 octobre',
        )
        expect(formatStudyDay('fr', '2026-01-01', { dateStyle: 'long' })).toBe('1 janvier 2026')
      } finally {
        if (original === undefined) delete process.env.TZ
        else process.env.TZ = original
      }
    })
  },
)
