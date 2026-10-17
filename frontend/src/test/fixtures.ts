import type { Exercise, RunReport, SheetVersion, UsageSheet } from '../api/enrichment'
import type { Deck, Item, ItemDetail } from '../api/library'
import type {
  NewItemEntry,
  Progress,
  ReviewEntry,
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
