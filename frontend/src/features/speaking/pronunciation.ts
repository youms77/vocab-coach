import type { PronunciationScores, WordScore } from '../../api/speech'

/** A phoneme below this score is a candidate for "weakest sounds". */
export const WEAK_PHONEME_BELOW = 80
export const WEAKEST_COUNT = 5
/** A word below this score is marked as needing attention, even without an error type. */
export const WEAK_WORD_BELOW = 60

export interface WeakPhoneme {
  phoneme: string
  word: string
  accuracy: number
}

/** The lowest-scored sounds across the sentence (below 80), worst first; at most five. */
export function weakestPhonemes(scores: PronunciationScores): WeakPhoneme[] {
  const found: WeakPhoneme[] = []
  for (const word of scores.words) {
    for (const p of word.phonemes) {
      if (p.accuracy !== null && p.accuracy < WEAK_PHONEME_BELOW) {
        found.push({ phoneme: p.phoneme, word: word.word, accuracy: p.accuracy })
      }
    }
  }
  return found.sort((a, b) => a.accuracy - b.accuracy).slice(0, WEAKEST_COUNT)
}

export type KnownErrorType = 'None' | 'Mispronunciation' | 'Omission' | 'Insertion'

/** `other` for a type this version does not know (Azure may add some). */
export function errorTypeKey(type: string): KnownErrorType | 'other' {
  return type === 'None' || type === 'Mispronunciation' || type === 'Omission' || type === 'Insertion'
    ? type
    : 'other'
}

/** A word that deserves a look: an error type other than None, or a low score. */
export function needsAttention(word: WordScore): boolean {
  return (
    errorTypeKey(word.error_type) !== 'None' ||
    (word.accuracy !== null && word.accuracy < WEAK_WORD_BELOW)
  )
}
