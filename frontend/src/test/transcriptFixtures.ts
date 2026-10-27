import type { ErrorOut } from '../api/errors'
import type { CorrectionResult, Feedback, Production } from '../api/productions'
import type { LabelCount, PreviewTurn, TranscriptPreview, TranscriptProblem } from '../api/transcripts'
import { correctionError, spanOf } from './writingFixtures'

// Fictional data for the transcript tests (M5.c1). The other speaker's sentences are unmistakable
// strings, so a test can prove that they never leave the page's memory.

export const OTHER_1 = 'Hello! Where do you live at the moment?'
export const USER_1 = 'I live in campus, near the library.'
export const OTHER_2 = 'That sounds convenient. How long have you been studying statistics there?'
export const USER_2 = 'I study here since two years.'

/** What the user pastes: two labelled speakers. */
export const PASTE = `ChatGPT: ${OTHER_1}\nYou: ${USER_1}\nChatGPT: ${OTHER_2}\nYou: ${USER_2}`
/** What the server stores: the user's turns joined by a blank line. */
export const STORED = `${USER_1}\n\n${USER_2}`

/** The same conversation without labels: each paragraph is a turn, the user speaks second. */
export const PASTE_UNLABELLED = `${OTHER_1}\n\n${USER_1}\n\n${OTHER_2}\n\n${USER_2}`

const words = (text: string) => text.split(/\s+/).filter(Boolean).length

const TURNS: [string, string][] = [
  ['ChatGPT', OTHER_1],
  ['You', USER_1],
  ['ChatGPT', OTHER_2],
  ['You', USER_2],
]

function turnsOf(isUser: (label: string, index: number) => boolean | null, labelled = true): PreviewTurn[] {
  return TURNS.map(([label, text], i) => ({
    index: i + 1,
    speaker_label: labelled ? label : null,
    text,
    line_start: i + 1,
    is_user: isUser(label, i),
  }))
}

function labelCounts(): LabelCount[] {
  const count = (label: string, known: 'user' | 'other'): LabelCount => {
    const texts = TURNS.filter(([l]) => l === label).map(([, text]) => text)
    return {
      label,
      turns: texts.length,
      words: texts.reduce((n, text) => n + words(text), 0),
      chars: texts.reduce((n, text) => n + text.length, 0),
      known,
    }
  }
  return [count('ChatGPT', 'other'), count('You', 'user')]
}

function userCounts(flags: (boolean | null)[]) {
  const mine = TURNS.filter((_, i) => flags[i] === true).map(([, text]) => text)
  return {
    turns: mine.length,
    words: mine.reduce((n, text) => n + words(text), 0),
    chars: mine.reduce((n, text) => n + text.length, 0),
  }
}

/** The preview of `PASTE`; `label` is the speaker designated as the user (default: "You"). */
export function labelledPreview(
  label: string | null = 'You',
  problems: TranscriptProblem[] = [],
): TranscriptPreview {
  const flags = TURNS.map(([l]) => (label === null ? null : l === label))
  return {
    turns: turnsOf((l) => (label === null ? null : l === label)),
    labels: labelCounts(),
    labelled: true,
    suggested_user_label: 'You',
    designation: label === null ? null : { label },
    user: label === null ? null : userCounts(flags),
    problems,
  }
}

/** The preview of `PASTE_UNLABELLED`; no user is known until a mode is chosen. */
export function unlabelledPreview(
  mode: 'alternating_user_first' | 'alternating_user_second' | 'all_mine' | null = null,
): TranscriptPreview {
  const isUser = (index: number): boolean | null => {
    if (mode === null) return null
    if (mode === 'all_mine') return true
    return index % 2 === (mode === 'alternating_user_first' ? 0 : 1)
  }
  const flags = TURNS.map((_, i) => isUser(i))
  return {
    turns: TURNS.map(([, text], i) => ({
      index: i + 1,
      speaker_label: null,
      text,
      line_start: i * 2 + 1,
      is_user: isUser(i),
    })),
    labels: [],
    labelled: false,
    suggested_user_label: null,
    designation: mode === null ? null : { mode },
    user: mode === null ? null : userCounts(flags),
    problems: [
      {
        line: null,
        severity: 'warning',
        code: 'no_speaker_labels',
        message: 'No speaker labels: each paragraph is a turn. Say which turns are yours.',
      },
    ],
  }
}

export function problem(
  code: string,
  severity: TranscriptProblem['severity'],
  line: number | null = null,
): TranscriptProblem {
  return { line, severity, code, message: `backend text for ${code}` }
}

// --- The stored production and its analysis ------------------------------------------------------

export function transcriptProduction(overrides: Partial<Production> = {}): Production {
  return {
    id: 5,
    kind: 'transcript_analysis',
    modality: 'oral',
    prompt_text: 'Chat about campus',
    text: STORED,
    word_count: words(USER_1) + words(USER_2),
    corrected: false,
    feedback: null,
    ai_call_id: null,
    study_session_id: null,
    targets: [],
    created_at: '2026-10-18T09:00:00Z',
    updated_at: '2026-10-18T09:00:00Z',
    audio_url: null,
    audio_seconds: null,
    transcription_status: null,
    comparison: null,
    ...overrides,
  }
}

const ERROR_1 = correctionError({
  sentence_index: 1,
  wrong: 'in campus',
  correction: 'on campus',
  alternatives: [],
})
const ERROR_2 = correctionError({
  sentence_index: 2,
  wrong: 'since two years',
  correction: 'for two years',
  alternatives: [],
  category_code: 'grammar.preposition.by_for_since',
  explanation_en: 'A duration takes "for", not "since".',
  explanation_fr: 'Une durée se construit avec « for », pas « since ».',
})

/** The stored `transcript-1` feedback of `STORED` (two units, one per turn). */
export function transcriptFeedback(
  overrides: { contextSent?: boolean; text?: string; noNatural?: boolean } = {},
): Feedback {
  const text = overrides.text ?? STORED
  const first = Array.from(USER_1).length
  return {
    format: 'transcript-1',
    prompt_version: 'transcript_analysis@1',
    provider: 'gemini',
    model: 'gemini-test',
    output: {
      sentences: [
        { index: 1, corrected: 'I live on campus, near the library.', status: 'corrected' },
        { index: 2, corrected: 'I have studied here for two years.', status: 'corrected' },
      ],
      corrected_text: 'I live on campus, near the library.\n\nI have studied here for two years.',
      natural_text: null,
      errors: [ERROR_1, ERROR_2],
      naturalness_notes: [],
      targets: [],
      overall_comment: 'Two small slips in four turns.',
    },
    spans: [spanOf(text, ERROR_1.wrong, 0, 1), spanOf(text, ERROR_2.wrong, 1, 2)],
    error_event_ids: [21, 22],
    targets: [],
    units: [
      { index: 1, turn: 0, start: 0, end: first, opens_turn: true },
      {
        index: 2,
        turn: 1,
        start: first + 2,
        end: first + 2 + Array.from(USER_2).length,
        opens_turn: true,
      },
    ],
    context_sent: overrides.contextSent ?? true,
    calls: [{ ai_call_id: 9, provider: 'gemini', model: 'gemini-test', units: [1, 2] }],
  }
}

export function analysedTranscript(overrides: Partial<Production> = {}): Production {
  return transcriptProduction({
    corrected: true,
    feedback: transcriptFeedback(),
    ...overrides,
  })
}

export function loggedTranscriptErrors(): ErrorOut[] {
  return [ERROR_1, ERROR_2].map((error, index) => ({
    id: 21 + index,
    source: 'transcript',
    original_text: index === 0 ? USER_1 : USER_2,
    erroneous_text: error.wrong,
    correction: error.correction,
    alternatives: error.alternatives,
    explanation: error.explanation_en,
    explanation_fr: error.explanation_fr,
    category: {
      code: error.category_code,
      label_en: index === 0 ? 'Fixed expression' : 'By, for, since',
      label_fr: index === 0 ? 'Expression figée' : 'By, for, since',
      status: 'active',
    },
    term: null,
    production_attempt_id: 5,
    review_log_id: null,
    occurred_at: '2026-10-18T09:00:00Z',
    updated_at: '2026-10-18T09:00:00Z',
  }))
}

export function analysisResult(overrides: Partial<CorrectionResult> = {}): CorrectionResult {
  return {
    status: 'ok',
    reason: null,
    attempt: analysedTranscript(),
    errors: loggedTranscriptErrors(),
    proposed_categories: [],
    ...overrides,
  }
}

export const unavailableAnalysis = (
  reason: string | null = 'no_provider_configured',
): CorrectionResult =>
  analysisResult({ status: 'unavailable', reason, attempt: transcriptProduction(), errors: [] })
