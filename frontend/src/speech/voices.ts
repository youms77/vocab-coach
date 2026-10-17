/**
 * Voice choice and speed for the browser's speech synthesis (SPEC module F, "Listening"). Pure: no
 * access to `window`, so the rules are unit-tested without a browser.
 */

/** "Listen slowly" speaks at the user's speed times this factor. */
export const SLOW_FACTOR = 0.7
/** Never slower than this, whatever the user's speed (below it the voices sound broken). */
export const MIN_RATE = 0.5

export interface VoiceLike {
  name: string
  lang: string
}

// Some browsers write "en_US" instead of "en-US".
const normalized = (lang: string) => lang.replace('_', '-').toLowerCase()

export const isAmerican = (voice: VoiceLike) => normalized(voice.lang) === 'en-us'
export const isEnglish = (voice: VoiceLike) => /^en(-|$)/.test(normalized(voice.lang))

/** The English voices, en-US first, otherwise in the browser's order. */
export function englishVoices<V extends VoiceLike>(voices: readonly V[]): V[] {
  const english = voices.filter(isEnglish)
  return [...english.filter(isAmerican), ...english.filter((v) => !isAmerican(v))]
}

/**
 * The voice named `name` (the `tts_voice` setting) when this browser has it; else the first en-US
 * voice; else the first English one, flagged as not American; else none.
 */
export function pickVoice<V extends VoiceLike>(
  voices: readonly V[],
  name: string,
): { voice: V | null; american: boolean } {
  const named = name === '' ? undefined : voices.find((v) => v.name === name)
  const voice = named ?? englishVoices(voices)[0] ?? null
  return { voice, american: voice !== null && isAmerican(voice) }
}

export function rateFor(rate: number, slow: boolean): number {
  return slow ? Math.max(MIN_RATE, rate * SLOW_FACTOR) : rate
}
