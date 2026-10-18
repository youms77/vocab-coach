import type { Drill } from '../../api/drills'

/** The gap of a drill sentence (`domain/drills.py`, `GAP`). */
export const GAP = '___'

/** Same rule as the server (`drillable_category`): level 2 or more, never pronunciation. */
export function isDrillableCode(code: string): boolean {
  if (!code.includes('.')) return false
  return code !== 'pronunciation' && !code.startsWith('pronunciation.')
}

/** A category that can be drilled: active, and its code passes `isDrillableCode`. */
export function isDrillableNode(node: { code: string; status: string }): boolean {
  return node.status === 'active' && isDrillableCode(node.code)
}

/** The sentence around its single gap, or null when it has none (it should not happen). */
export function splitGap(sentence: string): [string, string] | null {
  const at = sentence.indexOf(GAP)
  if (at < 0) return null
  return [sentence.slice(0, at), sentence.slice(at + GAP.length)]
}

/** The sentence with its gap replaced by `text` (the gap itself when `text` is empty). */
export function fillGap(sentence: string, text: string): string {
  const parts = splitGap(sentence)
  if (parts === null) return sentence
  return `${parts[0]}${text.trim() === '' ? GAP : text.trim()}${parts[1]}`
}

/** The first item that was not answered, or `items.length` when the drill is finished. */
export function firstUnanswered(drill: Pick<Drill, 'items'>): number {
  const at = drill.items.findIndex((item) => !item.answered)
  return at < 0 ? drill.items.length : at
}

export type DrillProgress = 'notStarted' | 'inProgress' | 'completed'

export function progressOf(drill: Pick<Drill, 'completed' | 'score'>): DrillProgress {
  if (drill.completed) return 'completed'
  return drill.score.answered === 0 ? 'notStarted' : 'inProgress'
}
