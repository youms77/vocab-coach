import type { ErrorOut } from '../api/errors'
import type { CorrectionError, CorrectionResult, Feedback, Production } from '../api/productions'
import type { Comparison, ComparisonStep, SpeechOut, StepOp } from '../api/speech'
import { correctionError, loggedErrors, production, spanOf } from './writingFixtures'

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

// --- Free speaking (M6.b2) ------------------------------------------------------------------------

export const PART_1 = 'I live in campus and I study here.'
export const PART_2 = 'I study here since two years, so, first of all, I like it.'
export const SPEECH = `${PART_1} ${PART_2}`
export const SPEECH_TOPIC = 'Describe where you study and for how long.'

export const SPEAKING_ERRORS: CorrectionError[] = [
  correctionError({ sentence_index: 1 }),
  correctionError({
    sentence_index: 2,
    wrong: 'since two years',
    correction: 'for two years',
    alternatives: [],
    category_code: 'grammar.preposition.by_for_since',
    explanation_en: 'A duration takes "for", not "since".',
    explanation_fr: 'Une durée se construit avec « for », pas « since ».',
  }),
]

/** A `speaking-1` feedback: the keys of `correction-1` plus `output.structure`. */
export function speakingFeedback(
  text = SPEECH,
  overrides: { errors?: CorrectionError[]; structure?: object | null } = {},
): Feedback {
  const errors = overrides.errors ?? SPEAKING_ERRORS
  const structure =
    overrides.structure === undefined
      ? {
          comment_en: 'Easy to follow, but the parts are joined only by "and" and "so".',
          comment_fr: 'Facile à suivre, mais les parties ne sont reliées que par « and » et « so ».',
          connectors_used: ['so', 'first of all'],
          suggestions: [
            {
              text_en: 'Try "In addition," to add a second idea.',
              text_fr: 'Essayez « In addition, » pour ajouter une deuxième idée.',
            },
          ],
        }
      : overrides.structure
  return {
    format: 'speaking-1',
    prompt_version: 'speaking_correction@1',
    provider: 'gemini',
    model: 'gemini-test',
    output: {
      sentences: [
        { index: 1, corrected: 'I live on campus and I study here.', status: 'corrected' },
        {
          index: 2,
          corrected: 'I have studied here for two years, so, first of all, I like it.',
          status: 'corrected',
        },
      ],
      corrected_text:
        'I live on campus and I study here. I have studied here for two years, so, first of all, I like it.',
      natural_text: 'I live on campus, where I have studied for two years, and I like it.',
      errors,
      naturalness_notes: [],
      targets: [],
      overall_comment: 'Clear, with two small slips.',
      structure,
    } as Feedback['output'],
    spans: errors.map((error, index) => spanOf(text, error.wrong, index, error.sentence_index)),
    error_event_ids: errors.map((_, index) => 31 + index),
    targets: [],
  }
}

/** A stored free speech (id 9), by default transcribed and not corrected yet. */
export function speech(overrides: Partial<Production> = {}): Production {
  return production({
    id: 9,
    kind: 'speaking',
    modality: 'oral',
    prompt_text: SPEECH_TOPIC,
    text: SPEECH,
    word_count: 20,
    audio_url: '/api/productions/9/audio',
    audio_seconds: 62,
    transcription_status: 'ok',
    ...overrides,
  })
}

export const correctedSpeech = (overrides: Partial<Production> = {}) =>
  speech({ corrected: true, feedback: speakingFeedback(overrides.text ?? SPEECH), ...overrides })

export function loggedSpeakingErrors(errors: CorrectionError[] = SPEAKING_ERRORS): ErrorOut[] {
  return loggedErrors(errors).map((row, index) => ({
    ...row,
    id: 31 + index,
    source: 'speaking',
    original_text: SPEECH,
    production_attempt_id: 9,
  }))
}

export function speakingCorrection(overrides: Partial<CorrectionResult> = {}): CorrectionResult {
  return {
    status: 'ok',
    reason: null,
    attempt: correctedSpeech(),
    errors: loggedSpeakingErrors(),
    proposed_categories: [],
    ...overrides,
  }
}

/** What `POST /speech/speaking` answers for a transcribed take. */
export const speakingOut = (overrides: Partial<SpeechOut> = {}): SpeechOut =>
  speechOut({
    production_id: 9,
    audio_url: '/api/productions/9/audio',
    audio_seconds: 62,
    transcription: { status: 'ok', text: SPEECH, reason: null },
    comparison: null,
    ...overrides,
  })
