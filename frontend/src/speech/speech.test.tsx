import { act, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { SettingsMap } from '../api/settings'
import { installFakeSpeech, voice } from '../test/fakeSpeech'
import { mockApi } from '../test/mockApi'
import { renderWithProviders } from '../test/renderApp'
import { SpeakButton } from './SpeakButton'
import { englishVoices, MIN_RATE, pickVoice, rateFor, SLOW_FACTOR } from './voices'

const US1 = voice('Microsoft Zira - English (United States)', 'en-US')
const US2 = voice('Microsoft David - English (United States)', 'en-US')
const GB = voice('Microsoft George - English (United Kingdom)', 'en-GB')
const FR = voice('Microsoft Hortense - French (France)', 'fr-FR')

function speechSettings(rate: number, voiceName: string): SettingsMap {
  const base = {
    is_default: false,
    minimum: null,
    maximum: null,
    choices: null,
    item_choices: null,
  }
  return {
    tts_rate: { ...base, value: rate, default: 1, type: 'float', minimum: 0.5, maximum: 2 },
    tts_voice: { ...base, value: voiceName, default: '', type: 'str' },
  }
}

describe('voice choice (pure)', () => {
  it('lists English voices, en-US first, and leaves the others out', () => {
    expect(englishVoices([FR, GB, US1, US2])).toEqual([US1, US2, GB])
    expect(englishVoices([voice('Android', 'en_US'), FR])).toHaveLength(1)
  })

  it('takes the voice named by tts_voice when the browser has it', () => {
    expect(pickVoice([US1, US2, GB], US2.name)).toEqual({ voice: US2, american: true })
    expect(pickVoice([US1, GB], GB.name)).toEqual({ voice: GB, american: false })
  })

  it('falls back to the first en-US voice, then to the first English one', () => {
    expect(pickVoice([GB, US2, US1], '')).toEqual({ voice: US2, american: true })
    expect(pickVoice([GB, US1], 'Gone voice')).toEqual({ voice: US1, american: true })
    expect(pickVoice([FR, GB], '')).toEqual({ voice: GB, american: false })
    expect(pickVoice([FR], '')).toEqual({ voice: null, american: false })
  })

  it('speaks slowly at tts_rate × 0.7, never below 0.5', () => {
    expect(SLOW_FACTOR).toBe(0.7)
    expect(rateFor(1.2, false)).toBe(1.2)
    expect(rateFor(1.2, true)).toBeCloseTo(0.84)
    expect(rateFor(0.6, true)).toBe(MIN_RATE)
  })
})

describe('SpeakButton', () => {
  it('speaks the text in en-US with the chosen voice, at normal and slow speed', async () => {
    const fake = installFakeSpeech([FR, US1, US2])
    mockApi({ 'GET /settings': speechSettings(1.2, US2.name) })
    const user = userEvent.setup()
    renderWithProviders(<SpeakButton text="We account for fixed effects." />)

    const listen = screen.getByRole('button', { name: 'Listen to “We account for fixed effects.”' })
    // Wait for the settings, so the chosen voice and speed apply.
    await screen.findByRole('button', { name: /Listen slowly/ })
    await act(async () => {})
    await user.click(listen)
    expect(fake.spoken).toHaveLength(1)
    expect(fake.spoken[0]).toMatchObject({
      text: 'We account for fixed effects.',
      lang: 'en-US',
      rate: 1.2,
      voice: US2,
    })
    expect(listen).toHaveTextContent('Speaking…')

    await user.click(
      screen.getByRole('button', { name: 'Listen slowly to “We account for fixed effects.”' }),
    )
    expect(fake.spoken[1].rate).toBeCloseTo(0.84)
    // One utterance at a time: cancel() before each one.
    expect(fake.cancelCount).toBe(2)

    act(() => fake.finish())
    expect(listen).toHaveTextContent('Listen')
  })

  it('names what is read in its accessible names', () => {
    installFakeSpeech([US1])
    mockApi({})
    renderWithProviders(<SpeakButton text="The sentence." label="the example sentence" />)

    expect(screen.getByRole('button', { name: 'Listen to “the example sentence”' })).toBeEnabled()
  })

  it('waits for the voices that arrive after the first render', () => {
    const fake = installFakeSpeech([])
    mockApi({})
    renderWithProviders(<SpeakButton text="shed light on" />)

    expect(screen.getByRole('button', { name: 'Listen to “shed light on”' })).toBeDisabled()
    expect(screen.getByText(/No English voice is installed/)).toBeInTheDocument()

    act(() => fake.setVoices([FR, US1]))
    expect(screen.getByRole('button', { name: 'Listen to “shed light on”' })).toBeEnabled()
  })

  it('says when the only English voice is not American', () => {
    installFakeSpeech([FR, GB])
    mockApi({})
    renderWithProviders(<SpeakButton text="shed light on" />)

    expect(screen.getByText(/Non-American voice \(Microsoft George/)).toBeInTheDocument()
  })

  it('is disabled with an explanation when the browser has no speech synthesis', () => {
    mockApi({})
    renderWithProviders(<SpeakButton text="shed light on" />)

    const listen = screen.getByRole('button', { name: 'Listen to “shed light on”' })
    expect(listen).toBeDisabled()
    expect(listen).toHaveAccessibleDescription(/This browser has no speech synthesis/)
    expect(screen.getByRole('button', { name: /Listen slowly/ })).toBeDisabled()
  })
})
