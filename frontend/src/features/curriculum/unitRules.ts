import type { Dialogue, Formula, Scenario, Unit, UnitRow, UnitStep } from '../../api/curriculum'
import { UNIT_STEPS } from '../../api/curriculum'

/** The unit's title in the interface language: `title_fr` in French when the syllabus has one. */
export function unitTitle(row: Pick<UnitRow, 'title' | 'title_fr'>, language: string): string {
  return language.startsWith('fr') && row.title_fr !== null && row.title_fr !== ''
    ? row.title_fr
    : row.title
}

export function stepsDone(steps: Scenario['steps']): number {
  return UNIT_STEPS.filter((step) => steps[step]).length
}

/** Words of a unit still waiting for triage (a word unit's terms). */
export function termsToTriage(unit: Unit): number {
  return unit.terms.filter((term) => term.status === 'triage').length
}

/** The row of unit `number` and the one after it, in a slice that starts at `number`. */
export function neighbours(
  rows: readonly UnitRow[] | undefined,
  number: number,
): { current: UnitRow | null; next: UnitRow | null } {
  return {
    current: rows?.find((row) => row.number === number) ?? null,
    next: rows?.find((row) => row.number === number + 1) ?? null,
  }
}

/** 0 or 1: which of the two speakers says a line (an unknown name reads as the first). */
export function speakerIndex(dialogue: Dialogue, speaker: string): 0 | 1 {
  return dialogue.speakers.indexOf(speaker) === 1 ? 1 : 0
}

/** The formulas the final task asks for, in the order of `formula_refs`. */
export function refsOf(scenario: Scenario): Formula[] {
  return scenario.final_task.formula_refs
    .map((ref) => scenario.formulas.find((formula) => formula.index === ref))
    .filter((formula): formula is Formula => formula !== undefined)
}

/** The 1-based page of a track that holds unit `number`. */
export function pageOfUnit(number: number, pageSize: number): number {
  return Math.floor((number - 1) / pageSize) + 1
}

export function isStep(value: string | null): value is UnitStep {
  return (UNIT_STEPS as readonly (string | null)[]).includes(value)
}

/** The page number from `?page=` (1-based in the URL), as a 0-based index. */
export function pageFromParam(value: string | null): number {
  const requested = Number(value)
  return Number.isInteger(requested) && requested > 1 ? requested - 1 : 0
}

/** `?unit=ID` of the shadowing and speaking pages: the unit to go back to, or null. */
export function unitFromParam(value: string | null): number | null {
  const id = Number(value)
  return value !== null && Number.isInteger(id) && id > 0 ? id : null
}

/** A positive integer carried by a navigation state, or null (a reload, a direct visit). */
export function readUnitId(state: unknown): number | null {
  if (typeof state !== 'object' || state === null) return null
  const id = (state as Record<string, unknown>).unitId
  return typeof id === 'number' && Number.isInteger(id) && id > 0 ? id : null
}
