import type {
  ConsolidationDeck,
  ConsolidationTask,
  CreatedTask,
  TaskPage,
} from '../api/consolidation'
import type { ConsolidationSummary, CorrectionResult, Production } from '../api/productions'
import { correctedProduction, loggedErrors, PARAGRAPH, production } from './writingFixtures'

// Fictional data for the module G screens (M7.b). Terms come from the demo's reading list.

export const TALK = PARAGRAPH

export function readyDeck(overrides: Partial<ConsolidationDeck> = {}): ConsolidationDeck {
  return {
    deck_id: 1,
    name: 'Causal inference reading',
    ready: true,
    reason: null,
    ratio: 0.9,
    stable_cards: 18,
    productive_cards: 20,
    threshold_ratio: 0.8,
    min_stability_days: 7,
    candidates: 15,
    open_task_id: null,
    ...overrides,
  }
}

export function waitingDeck(
  reason: NonNullable<ConsolidationDeck['reason']>,
  overrides: Partial<ConsolidationDeck> = {},
): ConsolidationDeck {
  return readyDeck({ deck_id: 2, name: 'Campus life', ready: false, reason, ratio: 0.5, ...overrides })
}

export function task(overrides: Partial<ConsolidationTask> = {}): ConsolidationTask {
  return {
    id: 4,
    deck: { id: 1, name: 'Causal inference reading' },
    status: 'proposed',
    task_type: 'talk',
    source: 'ai',
    title: { en: 'Explaining a causal study', fr: 'Expliquer une étude causale' },
    prompt: {
      en: 'Give a talk about a study where you had to separate cause from correlation.',
      fr: 'Faites un exposé sur une étude où il fallait séparer cause et corrélation.',
    },
    audience: { en: 'Fellow students', fr: 'Des étudiants' },
    target_minutes: 3,
    sections: [
      {
        heading: { en: 'Context', fr: 'Contexte' },
        guidance: { en: 'Say what the question was.', fr: 'Dites quelle était la question.' },
        item_ids: [11],
      },
      {
        heading: { en: 'Method', fr: 'Méthode' },
        guidance: { en: 'Explain how you estimated the effect.', fr: "Expliquez comment l'effet a été estimé." },
        item_ids: [],
      },
    ],
    targets: [
      { item_id: 11, term: 'confounding variable', item_status: 'consolidated', used_correctly_count: 0 },
      { item_id: 12, term: 'noisy estimate', item_status: 'learning', used_correctly_count: 0 },
    ],
    attempts: [],
    created_at: '2026-10-20T09:00:00Z',
    ...overrides,
  }
}

export const taskPage = (items: ConsolidationTask[] = [task()]): TaskPage => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
})

export function created(overrides: Partial<CreatedTask> = {}): CreatedTask {
  return { status: 'ok', source: 'ai', reason: null, task: task(), ...overrides }
}

/** A consolidation production (id 21) in a given state. */
export function attempt(overrides: Partial<Production> = {}): Production {
  return production({
    id: 21,
    kind: 'consolidation',
    modality: 'written',
    prompt_text: null,
    text: TALK,
    word_count: 14,
    targets: [],
    ...overrides,
  })
}

const checked = [
  { lexical_item_id: 11, term: 'confounding variable', used: true, used_correctly: true },
  { lexical_item_id: 12, term: 'noisy estimate', used: true, used_correctly: false },
  { lexical_item_id: 13, term: 'instrumental variable', used: false, used_correctly: null },
]

export const correctedAttempt = (overrides: Partial<Production> = {}) =>
  correctedProduction({
    id: 21,
    kind: 'consolidation',
    modality: 'written',
    prompt_text: null,
    text: TALK,
    targets: checked,
    ...overrides,
  })

export function summary(overrides: Partial<ConsolidationSummary> = {}): ConsolidationSummary {
  return {
    task_id: 4,
    production_attempt_id: 21,
    modality: 'written',
    targets: 3,
    used: 2,
    used_correctly: 1,
    misused: 1,
    absent: 1,
    activated_item_ids: [11],
    reinforced_card_ids: [31],
    ...overrides,
  }
}

export function consolidationCorrection(overrides: Partial<CorrectionResult> = {}): CorrectionResult {
  return {
    status: 'ok',
    reason: null,
    attempt: correctedAttempt(),
    errors: loggedErrors().slice(0, 1),
    proposed_categories: [],
    consolidation: summary(),
    ...overrides,
  }
}
