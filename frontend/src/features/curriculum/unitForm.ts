import type { FormulaEdit, Scenario, UnitContentEdit } from '../../api/curriculum'
import { speakerIndex, UNIT_LIMITS as LIMITS } from './unitRules'

/**
 * The unit editor's state (D-092 style): the stored content as a local draft, every text a string.
 * Speakers are kept as 0 or 1 so a renamed speaker keeps its lines; the shadowing lines and the
 * formulas of the final task are flags on the rows, so moving or removing a row keeps them right
 * and the 0-based positions are only computed when the edit is built.
 */
export type FormulaType = FormulaEdit['item_type']

export interface FormulaDraft {
  key: number
  text: string
  item_type: FormulaType
  function_en: string
  function_fr: string
  register: string
  /** The final task asks for this formula. */
  inTask: boolean
}

export interface LineDraft {
  key: number
  speaker: 0 | 1
  text: string
  /** The line is one of the lines to shadow. */
  shadow: boolean
}

export interface UnitDraft {
  formulas: FormulaDraft[]
  setting_en: string
  setting_fr: string
  speakers: [string, string]
  lines: LineDraft[]
  prompt_en: string
  prompt_fr: string
  minutes: 1 | 2
}

let nextKey = 1
const newKey = () => nextKey++

export const FORMULA_TYPES: readonly FormulaType[] = ['spoken_formula', 'collocation', 'phrase']

export function emptyFormula(): FormulaDraft {
  return {
    key: newKey(),
    text: '',
    item_type: 'spoken_formula',
    function_en: '',
    function_fr: '',
    register: '',
    inTask: false,
  }
}

export function emptyLine(speaker: 0 | 1 = 0): LineDraft {
  return { key: newKey(), speaker, text: '', shadow: false }
}

export function fromScenario(scenario: Scenario): UnitDraft {
  const refs = new Set(scenario.final_task.formula_refs)
  const shadowed = new Set(scenario.shadowing.map((line) => line.line_index))
  const { dialogue } = scenario
  return {
    formulas: scenario.formulas.map((formula, index) => ({
      key: newKey(),
      text: formula.text,
      item_type: formula.item_type,
      function_en: formula.function_en,
      function_fr: formula.function_fr,
      register: formula.register,
      inTask: refs.has(index),
    })),
    setting_en: dialogue.setting_en,
    setting_fr: dialogue.setting_fr,
    speakers: [dialogue.speakers[0] ?? '', dialogue.speakers[1] ?? ''],
    lines: dialogue.lines.map((line, index) => ({
      key: newKey(),
      speaker: speakerIndex(dialogue, line.speaker),
      text: line.text,
      shadow: shadowed.has(index),
    })),
    prompt_en: scenario.final_task.prompt_en,
    prompt_fr: scenario.final_task.prompt_fr,
    minutes: scenario.final_task.minutes === 2 ? 2 : 1,
  }
}

// --- Moving rows ---------------------------------------------------------------------------------

export function moved<T>(list: readonly T[], index: number, by: -1 | 1): T[] {
  const target = index + by
  if (target < 0 || target >= list.length) return [...list]
  const next = [...list]
  const [row] = next.splice(index, 1)
  next.splice(target, 0, row as T)
  return next
}

export function removed<T>(list: readonly T[], index: number): T[] {
  return list.filter((_, i) => i !== index)
}

// --- The four parts, as the API takes them -------------------------------------------------------

type Parts = Required<Omit<UnitContentEdit, 'expected_revision'>>

const clean = (value: string) => value.trim()

export function toParts(draft: UnitDraft): Parts {
  const { formulas, lines, speakers } = draft
  return {
    formulas: formulas.map((f) => ({
      text: clean(f.text),
      item_type: f.item_type,
      function_en: clean(f.function_en),
      function_fr: clean(f.function_fr),
      register: clean(f.register),
    })),
    dialogue: {
      setting_en: clean(draft.setting_en),
      setting_fr: clean(draft.setting_fr),
      speakers: [clean(speakers[0]), clean(speakers[1])],
      lines: lines.map((line) => ({
        speaker: clean(speakers[line.speaker]),
        text: clean(line.text),
      })),
    },
    shadowing: lines.flatMap((line, index) => (line.shadow ? [index] : [])),
    final_task: {
      prompt_en: clean(draft.prompt_en),
      prompt_fr: clean(draft.prompt_fr),
      minutes: draft.minutes,
      formula_refs: formulas.flatMap((f, index) => (f.inTask ? [index] : [])),
    },
  }
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/**
 * The edit to send: only the parts that differ from the version the draft started from, with the
 * revision it was opened from; null when nothing changed. Changing the formulas always sends the
 * final task too: the server would find its references again by text (D-250) and lose the ones
 * whose formula was reworded, while the draft knows them by row.
 */
export function toEdit(
  draft: UnitDraft,
  original: Scenario,
  revision: number,
): UnitContentEdit | null {
  const now = toParts(draft)
  const before = toParts(fromScenario(original))
  const edit: UnitContentEdit = { expected_revision: revision }
  const formulasChanged = !same(now.formulas, before.formulas)
  if (formulasChanged) edit.formulas = now.formulas
  if (!same(now.dialogue, before.dialogue)) edit.dialogue = now.dialogue
  if (!same(now.shadowing, before.shadowing)) edit.shadowing = now.shadowing
  if (formulasChanged || !same(now.final_task, before.final_task)) edit.final_task = now.final_task
  return Object.keys(edit).length > 1 ? edit : null
}

// --- Problems, as locations ----------------------------------------------------------------------

/**
 * A problem at a location written like the server's (`formulas[2].text`, `dialogue.lines[0].text`,
 * `shadowing`...). `key` names the client sentence (`curriculum.edit.problems.<key>`).
 */
export interface Problem {
  path: string
  key: 'empty' | 'count' | 'shadowingWords' | 'speakersDiffer' | 'refsMin' | 'tooLong'
  values?: Record<string, number>
}

export const words = (text: string) => text.trim().split(/\s+/).filter((w) => w !== '').length
const out = (n: number, range: { min: number; max: number }) => n < range.min || n > range.max

/** The rules the client can check without the server; the server still decides. */
export function clientProblems(draft: UnitDraft): Problem[] {
  const found: Problem[] = []
  const { formulas, lines } = draft
  const count = (path: string, range: { min: number; max: number }) =>
    found.push({ path, key: 'count', values: { ...range } })
  const empty = (path: string, text: string) => {
    if (text.trim() === '') found.push({ path, key: 'empty' })
  }
  const long = (path: string, text: string, max: number) => {
    if (text.trim().length > max) found.push({ path, key: 'tooLong', values: { max } })
  }

  if (out(formulas.length, LIMITS.formulas)) count('formulas', LIMITS.formulas)
  formulas.forEach((f, i) => {
    for (const [name, max] of [
      ['text', LIMITS.max.formula],
      ['function_en', LIMITS.max.function],
      ['function_fr', LIMITS.max.function],
      ['register', LIMITS.max.register],
    ] as const) {
      empty(`formulas[${i}].${name}`, f[name])
      long(`formulas[${i}].${name}`, f[name], max)
    }
  })

  empty('dialogue.setting_en', draft.setting_en)
  empty('dialogue.setting_fr', draft.setting_fr)
  long('dialogue.setting_en', draft.setting_en, LIMITS.max.setting)
  long('dialogue.setting_fr', draft.setting_fr, LIMITS.max.setting)
  const names = draft.speakers.map((s) => s.trim().toLowerCase())
  if (names.some((n) => n === '')) found.push({ path: 'dialogue.speakers', key: 'empty' })
  else if (names[0] === names[1]) found.push({ path: 'dialogue.speakers', key: 'speakersDiffer' })
  for (const name of draft.speakers) long('dialogue.speakers', name, LIMITS.max.name)
  if (out(lines.length, LIMITS.lines)) count('dialogue.lines', LIMITS.lines)
  lines.forEach((line, i) => {
    empty(`dialogue.lines[${i}].text`, line.text)
    long(`dialogue.lines[${i}].text`, line.text, LIMITS.max.line)
  })

  const shadowed = lines.flatMap((line, i) => (line.shadow ? [i] : []))
  if (out(shadowed.length, LIMITS.shadowing)) count('shadowing', LIMITS.shadowing)
  for (const i of shadowed) {
    const n = words(lines[i]!.text)
    if (n > 0 && out(n, LIMITS.shadowingWords)) {
      found.push({
        path: `dialogue.lines[${i}].shadow`,
        key: 'shadowingWords',
        values: { words: n, ...LIMITS.shadowingWords },
      })
    }
  }

  empty('final_task.prompt_en', draft.prompt_en)
  empty('final_task.prompt_fr', draft.prompt_fr)
  long('final_task.prompt_en', draft.prompt_en, LIMITS.max.prompt)
  long('final_task.prompt_fr', draft.prompt_fr, LIMITS.max.prompt)
  if (formulas.filter((f) => f.inTask).length < LIMITS.finalRefsMin) {
    found.push({ path: 'final_task.formula_refs', key: 'refsMin', values: { min: LIMITS.finalRefsMin } })
  }
  return found
}

/**
 * Where a server problem (`"formulas[2].text: must not be empty"`) belongs in the draft: a path of
 * a field the editor shows, or null (then it goes to the list). `shadowing[p]` and
 * `final_task.formula_refs[p]` count positions in the lists sent: they point to the p-th ticked row.
 */
export function locateProblem(problem: string, draft: UnitDraft): { path: string | null; message: string } {
  const split = problem.indexOf(': ')
  const raw = split < 0 ? '' : problem.slice(0, split)
  const message = split < 0 ? problem : problem.slice(split + 2)
  let path = raw
  const ticked = (rows: { shadow?: boolean; inTask?: boolean }[], flag: 'shadow' | 'inTask') =>
    rows.flatMap((row, i) => (row[flag] ? [i] : []))
  const shadowAt = /^shadowing\[(\d+)\]$/.exec(raw)
  const refAt = /^final_task\.formula_refs\[(\d+)\]$/.exec(raw)
  if (shadowAt) {
    const row = ticked(draft.lines, 'shadow')[Number(shadowAt[1])]
    path = row === undefined ? 'shadowing' : `dialogue.lines[${row}].shadow`
  } else if (refAt) {
    const row = ticked(draft.formulas, 'inTask')[Number(refAt[1])]
    path = row === undefined ? 'final_task.formula_refs' : `formulas[${row}].inTask`
  } else if (/^formulas\[\d+\]$/.test(raw)) {
    path = `${raw}.text` // "repeats formulas[1]"
  }
  return { path: path === '' ? null : path, message }
}

/** Every path a field of the editor answers to (what `locateProblem` may land on). */
export function fieldPaths(draft: UnitDraft): Set<string> {
  const paths = new Set([
    'formulas',
    'dialogue.setting_en',
    'dialogue.setting_fr',
    'dialogue.speakers',
    'dialogue.lines',
    'shadowing',
    'final_task.prompt_en',
    'final_task.prompt_fr',
    'final_task.formula_refs',
  ])
  draft.formulas.forEach((_, i) => {
    for (const name of ['text', 'function_en', 'function_fr', 'register', 'inTask']) {
      paths.add(`formulas[${i}].${name}`)
    }
  })
  draft.lines.forEach((_, i) => {
    paths.add(`dialogue.lines[${i}].text`)
    paths.add(`dialogue.lines[${i}].speaker`)
    paths.add(`dialogue.lines[${i}].shadow`)
  })
  return paths
}
