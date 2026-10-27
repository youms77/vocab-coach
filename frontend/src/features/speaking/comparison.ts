import type { Comparison, ComparisonStep, StepOp } from '../../api/speech'

/*
 * The word-by-word comparison, cut into the marks the view shows (D-197). Pure: it only reads
 * `steps`, the backend's alignment (`speech-compare-1`), so the page never aligns anything itself.
 */

export interface WordMark {
  key: string
  op: StepOp
  /** The words of this step on this row (the target's or the recogniser's). */
  text: string
  /** The words on the other row: what was heard instead, for a close or substituted target. */
  other: string | null
}

const targetOps: StepOp[] = ['match', 'close', 'substituted', 'missing']
const heardOps: StepOp[] = ['match', 'close', 'substituted', 'extra']

function marks(steps: ComparisonStep[], ops: StepOp[], side: 'target' | 'heard'): WordMark[] {
  const marked: WordMark[] = []
  steps.forEach((step, index) => {
    const text = step[side]
    if (text === null || !ops.includes(step.op)) return
    marked.push({
      key: `${side}-${index}`,
      op: step.op,
      text,
      other: side === 'target' ? step.heard : step.target,
    })
  })
  return marked
}

/** The "Target" row: every word of the sentence, marked by what became of it. */
export function targetMarks(comparison: Comparison): WordMark[] {
  return marks(comparison.steps, targetOps, 'target')
}

/** The "Heard" row: the transcription, with the words that are not in the target marked. */
export function heardMarks(comparison: Comparison): WordMark[] {
  return marks(comparison.steps, heardOps, 'heard')
}

/** The step of an unrecognised word (a substituted one has something heard, a missing one not). */
export function isSubstitution(word: { heard: string | null }): boolean {
  return word.heard !== null
}
