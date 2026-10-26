import { describe, expect, it } from 'vitest'

import { dialogueVoices, type VoiceLike } from './voices'

const voice = (name: string, lang: string): VoiceLike => ({ name, lang })
const zira = voice('Zira', 'en-US')
const david = voice('David', 'en-US')
const george = voice('George', 'en-GB')
const hortense = voice('Hortense', 'fr-FR')

describe('dialogueVoices', () => {
  it('gives two different en-US voices when the browser has two', () => {
    expect(dialogueVoices([hortense, george, zira, david], zira)).toEqual(['Zira', 'David'])
  })

  it('keeps the preferred voice for the first speaker and picks another one for the second', () => {
    expect(dialogueVoices([zira, david], david)).toEqual(['David', 'Zira'])
  })

  it('uses the first en-US voices when nothing is preferred', () => {
    expect(dialogueVoices([george, zira, david], null)).toEqual(['Zira', 'David'])
  })

  it('gives the same voice twice when there is only one en-US voice, even with other English ones', () => {
    expect(dialogueVoices([george, zira], zira)).toEqual(['Zira', 'Zira'])
  })

  it('falls back to the first English voice for both speakers', () => {
    expect(dialogueVoices([hortense, george], null)).toEqual(['George', 'George'])
  })

  it('has no voices without an English voice', () => {
    expect(dialogueVoices([hortense], null)).toBeNull()
    expect(dialogueVoices([], null)).toBeNull()
  })

  it('understands en_US written with an underscore', () => {
    expect(dialogueVoices([voice('A', 'en_US'), voice('B', 'en_US')], null)).toEqual(['A', 'B'])
  })
})
