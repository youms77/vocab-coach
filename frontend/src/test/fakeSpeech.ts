/*
 * jsdom has no speech synthesis. This fake stands in for `window.speechSynthesis` and
 * `SpeechSynthesisUtterance`: configurable voices, a `voiceschanged` event the test fires, and a
 * record of every utterance and every `cancel()`.
 */

export interface FakeVoice {
  name: string
  lang: string
  voiceURI: string
  localService: boolean
  default: boolean
}

export class FakeUtterance {
  text: string
  lang = ''
  voice: FakeVoice | null = null
  rate = 1
  pitch = 1
  volume = 1
  onend: ((event: unknown) => void) | null = null
  onerror: ((event: unknown) => void) | null = null

  constructor(text = '') {
    this.text = text
  }
}

export function voice(name: string, lang: string): FakeVoice {
  return { name, lang, voiceURI: name, localService: true, default: false }
}

export const DEFAULT_VOICES = [
  voice('Microsoft Hortense - French (France)', 'fr-FR'),
  voice('Microsoft George - English (United Kingdom)', 'en-GB'),
  voice('Microsoft Zira - English (United States)', 'en-US'),
  voice('Microsoft David - English (United States)', 'en-US'),
]

export class FakeSpeechSynthesis {
  voices: FakeVoice[]
  spoken: FakeUtterance[] = []
  cancelCount = 0
  current: FakeUtterance | null = null
  private listeners = new Set<() => void>()

  constructor(voices: FakeVoice[]) {
    this.voices = voices
  }

  get speaking() {
    return this.current !== null
  }

  getVoices() {
    return this.voices
  }

  speak(utterance: FakeUtterance) {
    this.spoken.push(utterance)
    this.current = utterance
  }

  /** Like the browsers: the utterance being spoken ends with an "interrupted" error. */
  cancel() {
    this.cancelCount += 1
    const utterance = this.current
    this.current = null
    utterance?.onerror?.({ error: 'interrupted' })
  }

  addEventListener(type: string, listener: () => void) {
    if (type === 'voiceschanged') this.listeners.add(listener)
  }

  removeEventListener(type: string, listener: () => void) {
    if (type === 'voiceschanged') this.listeners.delete(listener)
  }

  /** The browser finished loading its voices (wrap in `act`). */
  setVoices(voices: FakeVoice[]) {
    this.voices = voices
    for (const listener of this.listeners) listener()
  }

  /** The current utterance reached its end (wrap in `act`). */
  finish() {
    const utterance = this.current
    this.current = null
    utterance?.onend?.({})
  }
}

export function installFakeSpeech(voices: FakeVoice[] = DEFAULT_VOICES) {
  const fake = new FakeSpeechSynthesis(voices)
  Object.defineProperty(window, 'speechSynthesis', {
    value: fake,
    configurable: true,
    writable: true,
  })
  Object.defineProperty(window, 'SpeechSynthesisUtterance', {
    value: FakeUtterance,
    configurable: true,
    writable: true,
  })
  return fake
}

export function uninstallFakeSpeech() {
  const target = window as unknown as Record<string, unknown>
  delete target.speechSynthesis
  delete target.SpeechSynthesisUtterance
}
