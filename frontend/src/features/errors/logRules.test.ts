import { describe, expect, it } from 'vitest'

import type { ErrorOut } from '../../api/errors'
import { loggedTranscriptErrors } from '../../test/transcriptFixtures'
import { productionLink } from './logRules'

const row = (overrides: Partial<ErrorOut>): ErrorOut => ({ ...loggedTranscriptErrors()[0], ...overrides })

describe('productionLink', () => {
  it('opens a written production for writing and review errors', () => {
    expect(productionLink(row({ source: 'writing', production_attempt_id: 5 }))).toBe('/writing/5')
    expect(productionLink(row({ source: 'review', production_attempt_id: 6 }))).toBe('/writing/6')
  })

  it('opens the analysed conversation of a transcript error', () => {
    expect(productionLink(row({ source: 'transcript', production_attempt_id: 9 }))).toBe('/transcripts/9')
  })

  it('has no link without a production or for the sources that have no page yet', () => {
    expect(productionLink(row({ source: 'transcript', production_attempt_id: null }))).toBeNull()
    expect(productionLink(row({ source: 'manual', production_attempt_id: null }))).toBeNull()
    expect(productionLink(row({ source: 'drill', production_attempt_id: 3 }))).toBeNull()
    expect(productionLink(row({ source: 'speaking', production_attempt_id: 3 }))).toBeNull()
  })
})
