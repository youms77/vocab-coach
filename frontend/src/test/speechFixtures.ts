import type { Production } from '../api/productions'
import type { Comparison, ComparisonStep, SpeechOut, StepOp } from '../api/speech'
import { production } from './writingFixtures'

// Fictional test data for the shadowing screens (M6.b1).

export const TARGET = 'We account for regional fixed effects.'
export const HEARD = 'we account regional fix effect really'

export function step(
  op: StepOp,
  target: string | null,
  heard: string | null,
  at: [number, number, number, number],
): ComparisonStep {
  return {
    op,
    target,
    heard,
    target_start: at[0],
    target_end: at[1],
    heard_start: at[2],
    heard_end: at[3],
  }
}

/** A comparison with the five operations: 4 of the 6 target words are recognised. */
export function comparison(overrides: Partial<Comparison> = {}): Comparison {
  return {
    version: 'speech-compare-1',
    word_accuracy: 0.6667,
    target_word_count: 6,
    heard_word_count: 6,
    recognized_count: 4,
    unrecognized: [
      { position: 2, word: 'for', heard: null },
      { position: 4, word: 'fixed', heard: 'fix' },
    ],
    steps: [
      step('match', 'We', 'we', [0, 1, 0, 1]),
      step('match', 'account', 'account', [1, 2, 1, 2]),
      step('missing', 'for', null, [2, 3, 2, 2]),
      step('match', 'regional', 'regional', [3, 4, 2, 3]),
      step('substituted', 'fixed', 'fix', [4, 5, 3, 4]),
      step('close', 'effects', 'effect', [5, 6, 4, 5]),
      step('extra', null, 'really', [6, 6, 5, 6]),
    ],
    ...overrides,
  }
}

/** A stored shadowing (id 7), by default transcribed and compared. */
export function shadowing(overrides: Partial<Production> = {}): Production {
  return production({
    id: 7,
    kind: 'shadowing',
    modality: 'oral',
    prompt_text: TARGET,
    text: HEARD,
    word_count: 0,
    audio_url: '/api/productions/7/audio',
    audio_seconds: 4.2,
    transcription_status: 'ok',
    comparison: comparison(),
    ...overrides,
  })
}

export function speechOut(overrides: Partial<SpeechOut> = {}): SpeechOut {
  return {
    production_id: 7,
    audio_url: '/api/productions/7/audio',
    audio_seconds: 4.2,
    transcription: { status: 'ok', text: HEARD, reason: null },
    comparison: comparison(),
    ...overrides,
  }
}
