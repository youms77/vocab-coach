import type {
  Formula,
  Scenario,
  TrackDetail,
  TrackSummary,
  Unit,
  UnitRow,
  UnitStep,
} from '../api/curriculum'

// Fictional test data for the curriculum screens (M8.b1).

export function track(overrides: Partial<TrackSummary> = {}): TrackSummary {
  return {
    code: 'general_everyday',
    kind: 'wordlist',
    source: 'ngsl',
    title: { en: 'General everyday English', fr: "Anglais courant de tous les jours" },
    description: { en: 'The most frequent words.', fr: 'Les mots les plus fréquents.' },
    unit_size: 25,
    unit_count: 113,
    available: true,
    reason: null,
    started: false,
    deck_id: null,
    opened_units: 0,
    triaged_units: 0,
    syllabus_version: 1,
    ...overrides,
  }
}

export function scenarioTrack(overrides: Partial<TrackSummary> = {}): TrackSummary {
  return track({
    code: 'speaking_scenarios',
    kind: 'scenarios',
    source: null,
    title: { en: 'Speaking scenarios', fr: "Scénarios à l'oral" },
    description: { en: 'Short talks for real situations.', fr: 'De courts exposés.' },
    unit_size: null,
    unit_count: 16,
    started: true,
    ...overrides,
  })
}

export function row(overrides: Partial<UnitRow> = {}): UnitRow {
  return {
    number: 1,
    code: 'ngsl_001',
    title: 'Words 1 to 25',
    title_fr: null,
    state: 'not_opened',
    unit_id: null,
    first_rank: 1,
    last_rank: 25,
    word_count: 25,
    content_status: 'generated',
    progress: 'not_started',
    ...overrides,
  }
}

export function detail(
  summary: TrackSummary,
  units: UnitRow[],
  overrides: Partial<TrackDetail> = {},
): TrackDetail {
  return { track: summary, total_units: units.length, limit: 25, offset: 0, units, ...overrides }
}

export function wordUnit(overrides: Partial<Unit> = {}): Unit {
  return {
    id: 11,
    track_code: 'general_everyday',
    number: 1,
    code: 'ngsl_001',
    title: 'Words 1 to 25',
    state: 'opened',
    progress: 'not_started',
    content_status: 'generated',
    deck_id: 5,
    first_rank: 1,
    last_rank: 25,
    terms: [
      { item_id: 101, term: 'the', status: 'triage' },
      { item_id: 102, term: 'be', status: 'triage' },
      { item_id: 103, term: 'and', status: 'learning' },
    ],
    scenario: null,
    ...overrides,
  }
}

export function formula(index: number, overrides: Partial<Formula> = {}): Formula {
  return {
    index,
    text: `formula number ${index + 1}`,
    item_type: 'spoken_formula',
    function_en: `Says thing ${index + 1}.`,
    function_fr: `Dit la chose ${index + 1}.`,
    register: 'neutral',
    item_id: null,
    ...overrides,
  }
}

export const LINE_1 = 'Good morning, Dana. Thanks for coming in.'
export const LINE_2 = 'Thank you, Marc. I am glad to be here.'

export function scenario(overrides: Partial<Scenario> = {}): Scenario {
  const steps: Record<UnitStep, boolean> = {
    formulas: false,
    dialogue: false,
    shadowing: false,
    final_task: false,
  }
  return {
    revision: 1,
    edited: false,
    format: 'curriculum-unit-1',
    provider: 'fake',
    model: 'fake-model',
    prompt_version: 'curriculum_unit.v1',
    level: 'B1',
    formulas: [formula(0), formula(1), formula(2)],
    dialogue: {
      setting_en: 'A job interview at a small company.',
      setting_fr: 'Un entretien dans une petite entreprise.',
      speakers: ['Marc', 'Dana'],
      lines: [
        { speaker: 'Marc', text: LINE_1 },
        { speaker: 'Dana', text: LINE_2 },
        { speaker: 'Marc', text: 'Tell me about yourself.' },
      ],
    },
    shadowing: [
      { line_index: 0, text: LINE_1, take_count: 0, done: false },
      { line_index: 1, text: LINE_2, take_count: 2, done: true },
    ],
    final_task: {
      prompt_en: 'Introduce yourself for one minute.',
      prompt_fr: 'Présentez-vous pendant une minute.',
      minutes: 1,
      formula_refs: [0, 2],
      target_item_ids: [],
      attempt_ids: [],
      corrected: false,
    },
    steps,
    next_step: 'formulas',
    ...overrides,
  }
}

export function scenarioUnit(
  overrides: Partial<Unit> = {},
  content: Partial<Scenario> = {},
): Unit {
  return {
    id: 21,
    track_code: 'speaking_scenarios',
    number: 1,
    code: 'job_interview_1',
    title: 'Job interview 1',
    state: 'opened',
    progress: 'not_started',
    content_status: 'generated',
    deck_id: null,
    first_rank: null,
    last_rank: null,
    terms: [],
    scenario: scenario(content),
    ...overrides,
  }
}

/** The slice `GET /curriculum/tracks/speaking_scenarios?limit=2&offset=number-1` answers. */
export function scenarioRows(number: number, nextWritten = true): UnitRow[] {
  const make = (n: number, written: boolean): UnitRow =>
    row({
      number: n,
      code: `job_interview_${n}`,
      title: `Job interview ${n}`,
      title_fr: `Entretien d'embauche ${n}`,
      first_rank: null,
      last_rank: null,
      word_count: null,
      unit_id: written ? 20 + n : null,
      content_status: written ? 'generated' : 'pending',
    })
  return [make(number, true), make(number + 1, nextWritten)]
}

/** A scenario that meets every limit of a unit (8 formulas, 8 lines, 5 to shadow, 3 in the task). */
export function fullScenario(overrides: Partial<Scenario> = {}): Scenario {
  const lines = Array.from({ length: 8 }, (_, i) => ({
    speaker: i % 2 === 0 ? 'Marc' : 'Dana',
    text: `This is line number ${i + 1} of the dialogue.`,
  }))
  return scenario({
    formulas: Array.from({ length: 8 }, (_, i) => formula(i)),
    dialogue: {
      setting_en: 'A job interview at a small company.',
      setting_fr: 'Un entretien dans une petite entreprise.',
      speakers: ['Marc', 'Dana'],
      lines,
    },
    shadowing: [0, 1, 2, 3, 4].map((i) => ({
      line_index: i,
      text: lines[i]!.text,
      take_count: 0,
      done: false,
    })),
    final_task: {
      prompt_en: 'Introduce yourself for one minute.',
      prompt_fr: 'Présentez-vous pendant une minute.',
      minutes: 1,
      formula_refs: [0, 1, 2],
      target_item_ids: [],
      attempt_ids: [],
      corrected: false,
    },
    ...overrides,
  })
}
