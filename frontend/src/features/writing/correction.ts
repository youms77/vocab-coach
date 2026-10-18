import type { ErrorOut } from '../../api/errors'
import type {
  CorrectionOutput,
  Feedback,
  NaturalnessNote,
  ProductionTarget,
  SentenceStatus,
  TargetCheck,
} from '../../api/productions'
import { type MarkRange, type Segment, segment, toUtf16Ranges } from './spans'

/*
 * The neutral shape the correction view draws. `readFeedback` is the only place that knows the
 * stored format: "correction-1" (a written text) and "transcript-1" (the same keys plus `units`,
 * where units play the part of sentences and are grouped by the user's turn, D-151).
 */

export interface ErrorEntry {
  /** 1-based number shown in the text and in the list. */
  number: number
  sentenceIndex: number
  wrong: string
  correction: string
  alternatives: string[]
  categoryCode: string
  explanationEn: string
  /** Null when there is no French (or the explanation was edited since). */
  explanationFr: string | null
  /** The logged error, when the page has it (category, term, edited explanation). */
  logged: ErrorOut | null
  /** The target term this error is about, when there is one. */
  targetItemId: number | null
}

export interface ErrorGroup {
  /** The sentence number of a text, or the number of your turn (from 1) in a transcript. */
  number: number
  errors: ErrorEntry[]
}

export interface TargetEntry {
  itemId: number
  term: string
  used: boolean | null
  usedCorrectly: boolean | null
  comment: string | null
  disagreement: boolean
}

export interface CorrectionModel {
  /** `text` is a written paragraph; `transcript` is your turns of a conversation. */
  kind: 'text' | 'transcript'
  overall: string
  /** The original text cut into plain and highlighted segments. */
  segments: Segment[]
  /** The highlighted ranges, aligned with `segments` (numbers are `errors + 1`). */
  ranges: MarkRange[]
  entries: ErrorEntry[]
  groups: ErrorGroup[]
  sentenceCount: number
  /** Sentence number (text) or your turn number (transcript) of a unit / sentence index. */
  numberOf: (sentenceIndex: number) => number
  /** Transcript only: whether the other speaker's turns were sent as context (null for a text). */
  contextSent: boolean | null
  notes: NaturalnessNote[]
  correctedText: string
  naturalText: string | null
  targets: TargetEntry[]
  sentenceStatuses: Map<number, SentenceStatus>
}

export interface CorrectionSource {
  text: string
  feedback: Feedback | null
  errors?: ErrorOut[]
  targets?: ProductionTarget[]
}

function targetEntries(
  checks: readonly TargetCheck[],
  known: readonly ProductionTarget[],
): TargetEntry[] {
  return checks.map((check) => ({
    itemId: check.lexical_item_id,
    term: known.find((k) => k.lexical_item_id === check.lexical_item_id)?.term ?? '',
    used: check.used,
    usedCorrectly: check.used_correctly,
    comment: check.comment,
    disagreement: check.disagreement,
  }))
}

function fromOutput(
  source: CorrectionSource,
  feedback: Feedback,
  kind: 'text' | 'transcript',
): CorrectionModel | null {
  const output: CorrectionOutput | undefined = feedback.output
  if (output === undefined || !Array.isArray(output.errors)) return null
  const logged = new Map<number, ErrorOut>()
  const ids = feedback.error_event_ids ?? []
  for (const error of source.errors ?? []) {
    const index = ids.indexOf(error.id)
    if (index >= 0) logged.set(index, error)
  }
  const checks = feedback.targets ?? []
  // A transcript's units are numbered over the whole conversation: the reader sees "Your turn k".
  const turnOf = new Map((feedback.units ?? []).map((unit) => [unit.index, unit.turn + 1]))
  const numberOf = (sentenceIndex: number) =>
    kind === 'transcript' ? (turnOf.get(sentenceIndex) ?? sentenceIndex) : sentenceIndex

  const entries: ErrorEntry[] = output.errors.map((error, index) => {
    const row = logged.get(index) ?? null
    const ref = error.target_ref
    return {
      number: index + 1,
      sentenceIndex: error.sentence_index,
      wrong: error.wrong,
      correction: error.correction,
      alternatives: error.alternatives,
      categoryCode: row?.category.code ?? error.category_code,
      // The logged explanation wins: the user may have edited it (then the French is gone too).
      explanationEn: row?.explanation ?? error.explanation_en,
      explanationFr: row !== null ? row.explanation_fr : error.explanation_fr,
      logged: row,
      targetItemId:
        row?.term?.id ?? (ref !== null ? (checks.find((c) => c.ref === ref)?.lexical_item_id ?? null) : null),
    }
  })

  const groups: ErrorGroup[] = []
  for (const entry of entries) {
    const number = numberOf(entry.sentenceIndex)
    let group = groups.find((g) => g.number === number)
    if (group === undefined) {
      group = { number, errors: [] }
      groups.push(group)
    }
    group.errors.push(entry)
  }
  groups.sort((a, b) => a.number - b.number)

  const ranges = toUtf16Ranges(source.text, feedback.spans ?? [])
  return {
    kind,
    overall: output.overall_comment?.trim() ?? '',
    segments: segment(source.text, ranges),
    ranges,
    entries,
    groups,
    sentenceCount: output.sentences?.length ?? 0,
    numberOf,
    contextSent: kind === 'transcript' ? (feedback.context_sent ?? false) : null,
    notes: output.naturalness_notes ?? [],
    correctedText: output.corrected_text ?? '',
    naturalText: output.natural_text ?? null,
    targets: targetEntries(checks, source.targets ?? []),
    sentenceStatuses: new Map((output.sentences ?? []).map((s) => [s.index, s.status])),
  }
}

/** The model of a stored correction, or null when the format is unknown or the feedback is missing. */
export function readFeedback(source: CorrectionSource): CorrectionModel | null {
  const feedback = source.feedback
  if (feedback === null) return null
  switch (feedback.format) {
    case 'correction-1':
      return fromOutput(source, feedback, 'text')
    case 'transcript-1':
      return fromOutput(source, feedback, 'transcript')
    default:
      return null
  }
}
