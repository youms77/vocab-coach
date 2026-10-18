import { afterEach, describe, expect, it, vi } from 'vitest'

import { type CodePointSpan, segment, toUtf16Ranges } from './spans'

/** The span of `fragment` in `text`, counted in code points, as the backend does. */
function spanOf(text: string, fragment: string, error = 0): CodePointSpan {
  const at = text.indexOf(fragment)
  expect(at).toBeGreaterThanOrEqual(0)
  const start = Array.from(text.slice(0, at)).length
  return { error, start, end: start + Array.from(fragment).length }
}

/** What the page shows highlighted for these spans. */
function marked(text: string, spans: CodePointSpan[]) {
  return segment(text, toUtf16Ranges(text, spans))
    .filter((s) => s.kind === 'mark')
    .map((s) => s.text)
}

afterEach(() => vi.restoreAllMocks())

describe('toUtf16Ranges', () => {
  it('maps ASCII spans one to one', () => {
    const text = 'I lived in campus with two friends.'
    const ranges = toUtf16Ranges(text, [{ error: 0, start: 8, end: 17 }])
    expect(ranges).toEqual([{ start: 8, end: 17, errors: [0] }])
    expect(marked(text, [{ error: 0, start: 8, end: 17 }])).toEqual(['in campus'])
  })

  it.each([
    ['NFC', 'Yaoundé'],
    ['NFD', 'Yaoundé'],
  ])('counts code points in %s text ("Yaoundé")', (_form, city) => {
    const text = `I moved to ${city} and I lived in campus there.`
    // The accent is one code point in NFC and two in NFD: the backend's offsets differ, the result must not.
    expect(marked(text, [spanOf(text, 'in campus')])).toEqual(['in campus'])
    expect(marked(text, [spanOf(text, city)])).toEqual([city])
  })

  it('handles an emoji before the error (2 UTF-16 units, 1 code point)', () => {
    const text = '\u{1F600} Since then, I lived in campus.'
    const span = spanOf(text, 'in campus')
    // The backend's offset is one lower than the raw UTF-16 index: using it as is would shift the mark.
    expect(span.start).toBe(text.indexOf('in campus') - 1)
    expect(marked(text, [span])).toEqual(['in campus'])
    const raw = text.slice(span.start, span.end)
    expect(raw).not.toBe('in campus')
  })

  it('handles several emoji and astral characters inside the marked fragment', () => {
    const text = 'a \u{1F600}\u{1F600} b \u{1D54F} c'
    expect(marked(text, [spanOf(text, '\u{1D54F} c')])).toEqual(['\u{1D54F} c'])
    expect(marked(text, [spanOf(text, '\u{1F600} b')])).toEqual(['\u{1F600} b'])
  })

  it('merges two overlapping errors into one mark that carries both numbers', () => {
    const text = 'Since then, I lived in campus with friends.'
    const a = spanOf(text, 'I lived in campus', 0)
    const b = spanOf(text, 'in campus with', 1)
    const ranges = toUtf16Ranges(text, [b, a])
    expect(ranges).toHaveLength(1)
    expect(ranges[0].errors).toEqual([0, 1])
    expect(marked(text, [a, b])).toEqual(['I lived in campus with'])
  })

  it('keeps touching spans apart', () => {
    const text = 'one two three'
    const spans = [spanOf(text, 'one', 0), { error: 1, start: 3, end: 7 }]
    expect(marked(text, spans)).toEqual(['one', ' two'])
  })

  it('merges a span nested in another one', () => {
    const text = 'I lived in campus yesterday.'
    const outer = spanOf(text, 'lived in campus', 0)
    const inner = spanOf(text, 'campus', 1)
    const ranges = toUtf16Ranges(text, [outer, inner])
    expect(ranges).toHaveLength(1)
    expect(ranges[0].errors).toEqual([0, 1])
    expect(marked(text, [outer, inner])).toEqual(['lived in campus'])
  })

  it('handles an error at the very end of the text', () => {
    const text = 'I like to live in campus'
    const parts = segment(text, toUtf16Ranges(text, [spanOf(text, 'in campus')]))
    expect(parts).toEqual([
      { kind: 'text', text: 'I like to live ' },
      { kind: 'mark', text: 'in campus', errors: [0] },
    ])
  })

  it('handles an error at the very start and no trailing empty text', () => {
    const text = 'Yesterday I go home.'
    const parts = segment(text, toUtf16Ranges(text, [spanOf(text, 'Yesterday')]))
    expect(parts[0]).toEqual({ kind: 'mark', text: 'Yesterday', errors: [0] })
    expect(parts.map((p) => p.text).join('')).toBe(text)
  })

  it('ignores spans out of bounds, empty or malformed, and warns in development', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const text = 'Short text.'
    const spans: CodePointSpan[] = [
      { error: 0, start: 5, end: 99 },
      { error: 1, start: -1, end: 3 },
      { error: 2, start: 4, end: 4 },
      { error: 3, start: 6, end: 2 },
      { error: 4, start: 0.5, end: 3 },
      { error: 5, start: 0, end: 5 },
    ]
    expect(toUtf16Ranges(text, spans)).toEqual([{ start: 0, end: 5, errors: [5] }])
    expect(warn).toHaveBeenCalledTimes(5)
  })

  it('returns the whole text as one plain segment without spans, and nothing for an empty text', () => {
    expect(segment('Hello.', [])).toEqual([{ kind: 'text', text: 'Hello.' }])
    expect(segment('', [])).toEqual([])
    expect(toUtf16Ranges('', [{ error: 0, start: 0, end: 1 }])).toEqual([])
  })
})
