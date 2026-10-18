/*
 * Error spans (D-128). The backend counts Unicode code points ("Yaoundé" is 7 or 8 depending on its
 * normalisation form, an emoji is 1); JavaScript strings count UTF-16 units (an emoji is 2). The
 * conversion walks the code points once. Pure: no DOM, no React.
 */

/** A span as the backend stores it: `error` is the index into `output.errors`. */
export interface CodePointSpan {
  error: number
  start: number
  end: number
}

/** A highlighted range in UTF-16 units of the text; `errors` are 0-based indices, ascending. */
export interface MarkRange {
  start: number
  end: number
  errors: number[]
}

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'mark'; text: string; errors: number[] }

function warn(message: string) {
  if (import.meta.env.DEV) console.warn(`[spans] ${message}`)
}

/**
 * The ranges of the spans in UTF-16 units. A span out of bounds, not made of integers or with
 * `start >= end` is ignored (and reported in development): a wrong highlight is better than a
 * crash. Spans that overlap are merged into one range that carries every error number; spans that
 * only touch stay separate.
 */
export function toUtf16Ranges(text: string, spans: readonly CodePointSpan[]): MarkRange[] {
  const points = Array.from(text)
  // offsets[i] = UTF-16 offset of code point i; offsets[points.length] = text.length.
  const offsets = new Array<number>(points.length + 1)
  let sum = 0
  for (let i = 0; i < points.length; i++) {
    offsets[i] = sum
    sum += points[i].length
  }
  offsets[points.length] = sum

  const valid: MarkRange[] = []
  for (const span of spans) {
    const { start, end } = span
    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      start < 0 ||
      end > points.length ||
      start >= end
    ) {
      warn(`ignored span ${JSON.stringify(span)} for a text of ${points.length} characters`)
      continue
    }
    valid.push({ start: offsets[start], end: offsets[end], errors: [span.error] })
  }

  valid.sort((a, b) => a.start - b.start || a.end - b.end)
  const merged: MarkRange[] = []
  for (const range of valid) {
    const last = merged.at(-1)
    if (last !== undefined && range.start < last.end) {
      last.end = Math.max(last.end, range.end)
      last.errors.push(...range.errors)
    } else {
      merged.push({ ...range, errors: [...range.errors] })
    }
  }
  for (const range of merged) range.errors.sort((a, b) => a - b)
  return merged
}

/** The text cut into plain and marked segments, in order. `ranges` come from `toUtf16Ranges`. */
export function segment(text: string, ranges: readonly MarkRange[]): Segment[] {
  const out: Segment[] = []
  let at = 0
  for (const range of ranges) {
    if (range.start > at) out.push({ kind: 'text', text: text.slice(at, range.start) })
    out.push({ kind: 'mark', text: text.slice(range.start, range.end), errors: range.errors })
    at = range.end
  }
  if (at < text.length) out.push({ kind: 'text', text: text.slice(at) })
  return out
}
