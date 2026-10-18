import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import i18n from '../../i18n'
import { describeError } from './errorMessage'

const t = i18n.t.bind(i18n)
const refusal = (status: number, code: string, extra: Record<string, unknown> = {}) =>
  new ApiError(status, 'English text', code, { code, message: 'English text', ...extra })

describe('describeError: transcripts', () => {
  it('says each reason of an invalid transcript in the interface language', () => {
    const described = describeError(
      t,
      refusal(422, 'invalid_transcript', { codes: ['empty_text', 'no_user_turns', 'future_date'] }),
    )
    expect(described.text).toBe('This conversation cannot be used.')
    expect(described.reasons).toEqual([
      'There is no text to analyse.',
      'None of the turns is yours with this choice.',
      'The date of the conversation is in the future.',
    ])
  })

  it('words the two transcript limits, not the 4 000-character one, when codes are present', () => {
    const transcript = describeError(t, refusal(422, 'text_too_long', { codes: ['too_large'] }))
    expect(transcript.text).toContain('60,000 pasted characters')
    expect(transcript.reasons).toEqual([
      'The text is too long: at most 60,000 pasted characters, and at most 6,000 characters in your own turns.',
    ])
    // A written text has no codes: its message is unchanged.
    const writing = describeError(t, refusal(422, 'text_too_long'))
    expect(writing.text).toContain('4,000 characters')
    expect(writing.reasons).toEqual([])
  })

  it('keeps an unknown reason code as it is', () => {
    const described = describeError(t, refusal(422, 'invalid_transcript', { codes: ['brand_new_code'] }))
    expect(described.reasons).toEqual(['brand_new_code'])
  })

  it('has a sentence for a transcript that does not match', () => {
    expect(describeError(t, refusal(409, 'transcript_mismatch')).text).toContain('does not match the turns saved')
  })
})
