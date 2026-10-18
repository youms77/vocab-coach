import type { Exercise, RunReport, SheetVersion, UsageSheet } from '../api/enrichment'
import type { Deck, Item, ItemDetail } from '../api/library'
import type { GradeResult, RecordResult, RevealResult, SheetSummary } from '../api/reviews'
import type {
  NewItemEntry,
  Progress,
  ReviewEntry,
  ReviewStep,
  SessionPlan,
  StudySession,
} from '../api/session'

// Fictional test data shared by the M3.c3 tests.

export function item(id: number, term: string, overrides: Partial<Item> = {}): Item {
  return {
    id,
    term,
    normalized_form: term,
    lemma: null,
    item_type: 'collocation',
    part_of_speech: null,
    origin_sentence: null,
    notes: null,
    status: 'learning',
    status_changed_at: '2026-10-16T10:00:00Z',
    discovered_at: '2026-10-16T10:00:00Z',
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
    decks: [{ id: 1, name: 'Causal inference reading' }],
    sheet_status: 'complete',
    ...overrides,
  }
}

export function detail(id: number, term: string, overrides: Partial<Item> = {}): ItemDetail {
  return { ...item(id, term, overrides), deck_links: [], has_history: false, duplicates: [] }
}

export function deck(id: number, name: string, overrides: Partial<Deck> = {}): Deck {
  return {
    id,
    name,
    description: null,
    domain: 'econometrics',
    kind: 'topic',
    status: 'queued',
    deadline: null,
    priority: null,
    queue_position: 1,
    source: null,
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
    item_count: 2,
    items_by_status: { queued: 2 },
    pace: null,
    warnings: [],
    ...overrides,
  }
}

export function usageSheet(overrides: Partial<UsageSheet> = {}): UsageSheet {
  return {
    schema_version: 1,
    part_of_speech: 'phrasal verb',
    register_level: 'academic',
    register_note: null,
    meaning_in_context: 'to include a factor in the analysis',
    definition_simple: 'to consider something when you study a situation',
    translation_fr: ['tenir compte de'],
    other_meanings: [],
    usage_notes: null,
    collocations: [{ pattern: 'account for variation', example: null }],
    examples: [{ sentence: 'We account for regional effects.', kind: 'academic' }],
    word_family: [],
    pronunciation: { ipa_us: '/əˈkaʊnt fɔr/', stressed_syllable: 'count', note: null },
    french_speaker_pitfalls: [],
    confusables: [],
    ...overrides,
  }
}

export function sheetVersion(overrides: Partial<SheetVersion> = {}): SheetVersion {
  return {
    enrichment_id: 7,
    version: 1,
    is_current: true,
    status: 'complete',
    sheet_status: 'complete',
    edited_by_user: false,
    edited_at: null,
    provider: 'gemini',
    model: 'test-model',
    prompt_version: 'enrichment.v1',
    schema_version: 1,
    created_at: '2026-10-16T10:00:00Z',
    content: usageSheet(),
    ...overrides,
  }
}

export function report(overrides: Partial<RunReport> = {}): RunReport {
  return {
    status: 'ok',
    reason: null,
    generated: 0,
    needs_completion: 0,
    superseded: 0,
    failed: 0,
    remaining: 0,
    item_ids: [],
    ...overrides,
  }
}

export function exercise(id: number, type: string, content: Record<string, unknown>): Exercise {
  return {
    id,
    lexical_item_id: 1,
    exercise_type: type,
    direction: 'productive',
    origin: 'ai',
    prompt_version: 'enrichment.v1',
    edited_by_user: false,
    content,
    created_at: '2026-10-16T10:00:00Z',
    updated_at: '2026-10-16T10:00:00Z',
  }
}

// --- Today's session (M4.b) -----------------------------------------------------------------------

export function plan(overrides: Partial<SessionPlan> = {}): SessionPlan {
  return {
    study_day: '2026-10-17',
    generated_at: '2026-10-17T08:00:00Z',
    budget_seconds: 2700,
    blocks: [],
    total_seconds: 0,
    new_items_allowed: 0,
    limit: 'nothing_to_learn',
    caps: { quota: 12, budget: 50, anticipation: 50, available: 0 },
    decks_to_activate: [],
    deadline_paces: [],
    warnings: [],
    observed_durations: [],
    ...overrides,
  }
}

export function reviewEntry(cardId: number, itemId: number): ReviewEntry {
  return {
    kind: 'review',
    card_id: cardId,
    lexical_item_id: itemId,
    direction: 'productive',
    state: 'review',
    due: '2026-10-16T09:00:00Z',
    retrievability: 0.85,
    estimated_seconds: 30,
    overflow: false,
  }
}

export function newItemEntry(itemId: number, deckId: number | null): NewItemEntry {
  return {
    kind: 'new_item',
    lexical_item_id: itemId,
    deck_id: deckId,
    resumed: false,
    estimated_seconds: 120,
  }
}

export function studySession(id: number, overrides: Partial<StudySession> = {}): StudySession {
  return {
    id,
    started_at: '2026-10-17T08:00:00Z',
    ended_at: null,
    study_day: '2026-10-17',
    planned: { format: 'session-1', plan: plan() },
    summary: null,
    ...overrides,
  }
}

export const progress = (overrides: Partial<Progress> = {}): Progress => ({
  reviews_done: 0,
  reviews_remaining: 0,
  new_done: 0,
  new_remaining: 1,
  estimated_seconds_remaining: 120,
  ...overrides,
})

// --- Reviews (M4.c) -------------------------------------------------------------------------------

const TERM = 'drill down into'

export const sheetSummary = (): SheetSummary => ({
  term: TERM,
  part_of_speech: 'phrasal verb',
  definition_simple: 'to look at something more closely',
  translation_fr: ['examiner en détail'],
  pronunciation: { ipa_us: '/ˌdrɪl ˈdaʊn ˈɪntu/', stressed_syllable: 'down', note: null },
  examples: ['Let us drill down into the regional figures.'],
})

export function reviewStep(overrides: Partial<ReviewStep> = {}): ReviewStep {
  return {
    card_id: 21,
    lexical_item_id: 5,
    direction: 'productive',
    srs_state: 'review',
    expected_reps: 4,
    exercise_type: 'typed_recall',
    exercise_template_id: 31,
    input: 'text',
    self_graded: false,
    term: null,
    prompt: { cue_fr: 'examiner en détail', cue_definition: 'to look at something more closely' },
    warnings: [],
    ...overrides,
  }
}

export function gradeAnswer(overrides: Partial<GradeResult> = {}): GradeResult {
  return {
    outcome: 'exact',
    proposed_rating: 3,
    expected: TERM,
    accepted: [],
    diff: null,
    warnings: [],
    solution: { answer: TERM, accepted: [] },
    sheet_summary: sheetSummary(),
    ...overrides,
  }
}

export const recordAnswer = (overrides: Partial<RecordResult> = {}): RecordResult => ({
  review_log_id: 900,
  due_after: '2026-10-25T08:00:00Z',
  state_after: 'review',
  item_status: 'learning',
  item_status_changed: false,
  error_event_id: null,
  ...overrides,
})

/**
 * One case per exercise type: the step, the answer of `grade` or `reveal`, and the solution
 * strings that must not be in the page before the attempt (D-103).
 */
export interface ReviewCase {
  name: string
  step: ReviewStep
  grade?: GradeResult
  reveal?: RevealResult
  secrets: string[]
}

const CHOICE_OPTIONS = [
  'to summarise quickly',
  'to reject an idea',
  'to examine something in more detail',
  'to stop working on something',
]
const choiceSolution = (sentence: string) => ({
  correct_index: 2,
  meaning: 'to examine something in more detail',
  meaning_fr: 'examiner en détail',
  sentence,
})
const RECOGNITION_SENTENCE = 'Let us drill down into the regional figures.'
const LISTENING_SENTENCE = 'We need to drill down into these unexpected numbers.'

export const reviewCases: ReviewCase[] = [
  {
    name: 'recognition_in_sentence',
    step: reviewStep({
      direction: 'receptive',
      exercise_type: 'recognition_in_sentence',
      input: 'choice',
      term: TERM,
      prompt: { sentence: RECOGNITION_SENTENCE, options: CHOICE_OPTIONS },
    }),
    grade: gradeAnswer({
      expected: CHOICE_OPTIONS[2],
      solution: choiceSolution(RECOGNITION_SENTENCE),
    }),
    secrets: ['examiner en détail', 'Right answer', 'to look at something more closely'],
  },
  {
    name: 'listening_comprehension',
    step: reviewStep({
      direction: 'receptive',
      exercise_type: 'listening_comprehension',
      input: 'choice',
      term: null,
      prompt: { sentence: LISTENING_SENTENCE, options: CHOICE_OPTIONS },
    }),
    grade: gradeAnswer({
      expected: CHOICE_OPTIONS[2],
      solution: choiceSolution(LISTENING_SENTENCE),
    }),
    secrets: [LISTENING_SENTENCE, 'unexpected numbers', 'examiner en détail', TERM],
  },
  {
    name: 'typed_recall',
    step: reviewStep(),
    grade: gradeAnswer({
      outcome: 'typo',
      proposed_rating: 2,
      accepted: ['drill into'],
      diff: [
        { op: 'equal', given: 'drill down in', expected: 'drill down in' },
        { op: 'replace', given: 'ot', expected: 'to' },
      ],
      solution: { answer: TERM, accepted: ['drill into'] },
    }),
    secrets: [TERM, 'drill into'],
  },
  {
    name: 'gap_fill',
    step: reviewStep({
      exercise_type: 'gap_fill',
      exercise_template_id: 32,
      prompt: { sentence: 'Let us ___ the regional figures.' },
    }),
    grade: gradeAnswer({
      solution: { answer: TERM, accepted: [], sentence: RECOGNITION_SENTENCE },
    }),
    secrets: [TERM, RECOGNITION_SENTENCE],
  },
  {
    name: 'sentence_production',
    step: reviewStep({
      srs_state: 'review',
      exercise_type: 'sentence_production',
      exercise_template_id: 33,
      self_graded: true,
      prompt: { situation: 'Your manager asks how you will analyse a drop in sales.' },
    }),
    grade: gradeAnswer({
      outcome: null,
      proposed_rating: null,
      expected: null,
      warnings: ['term_missing'],
      solution: { example_answer: 'I will drill down into the sales data region by region.' },
    }),
    secrets: [TERM, 'region by region'],
  },
  {
    name: 'spoken_answer',
    step: reviewStep({
      exercise_type: 'spoken_answer',
      exercise_template_id: 34,
      input: 'none',
      self_graded: true,
      prompt: { question: 'How would you explore an unexpected result?' },
    }),
    reveal: {
      solution: { example_answer: 'I would drill down into the data to find the cause.' },
      sheet_summary: sheetSummary(),
    },
    secrets: [TERM, 'find the cause'],
  },
  {
    name: 'self_assessment (receptive)',
    step: reviewStep({
      direction: 'receptive',
      exercise_type: 'self_assessment',
      exercise_template_id: null,
      input: 'none',
      self_graded: true,
      term: TERM,
      prompt: { term: TERM, sentence: RECOGNITION_SENTENCE },
    }),
    reveal: {
      solution: {
        term: TERM,
        definition_simple: 'to look at something more closely',
        translation_fr: ['examiner en détail'],
        sentence: RECOGNITION_SENTENCE,
      },
      sheet_summary: sheetSummary(),
    },
    secrets: ['examiner en détail', 'to look at something more closely'],
  },
  {
    name: 'self_assessment (productive)',
    step: reviewStep({
      exercise_type: 'self_assessment',
      exercise_template_id: null,
      input: 'none',
      self_graded: true,
      prompt: {
        cue_fr: 'examiner en détail',
        cue_definition: 'to look at something more closely',
        sentence_gapped: 'Let us ___ the regional figures.',
      },
    }),
    reveal: {
      solution: {
        term: TERM,
        definition_simple: 'to look at something more closely',
        translation_fr: ['examiner en détail'],
        sentence: RECOGNITION_SENTENCE,
      },
      sheet_summary: sheetSummary(),
    },
    secrets: [TERM, RECOGNITION_SENTENCE],
  },
]
