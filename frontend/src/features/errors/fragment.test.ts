import { describe, expect, it } from 'vitest'

import { findFragment, highlightSegments } from './fragment'

function cut(text: string, fragment: string): string | null {
  const found = findFragment(text, fragment)
  return found === null ? null : text.slice(found[0], found[1])
}

describe('findFragment', () => {
  it('finds an exact fragment', () => {
    expect(findFragment('I lived on campus.', 'lived')).toEqual([2, 7])
  })

  it('ignores runs of spaces and surrounding spaces of the fragment', () => {
    expect(cut('I   lived  in campus.', ' lived in campus ')).toBe('lived  in campus')
  })

  it('treats typographic apostrophes like the straight one, both ways', () => {
    expect(cut('She doesn’t know.', "doesn't")).toBe('doesn’t')
    expect(cut("She doesn't know.", 'doesn’t')).toBe("doesn't")
  })

  it('ignores the case when the exact case is absent', () => {
    expect(cut('Since then, I lived here.', 'SINCE THEN')).toBe('Since then')
  })

  it('ignores Unicode composition', () => {
    const composed = 'Yaoundé is big'
    const decomposed = 'Yaoundé'
    expect(cut(composed, decomposed)).toBe('Yaoundé')
    expect(cut(`Go to ${decomposed} now`, 'Yaoundé')).toBe(decomposed)
  })

  it('returns the first occurrence and keeps surrogate pairs whole', () => {
    expect(findFragment('a 😀 b a', 'a')).toEqual([0, 1])
    expect(cut('say 😀', '😀')).toBe('😀')
  })

  it('returns null when absent or empty', () => {
    expect(findFragment('I lived here.', 'campus')).toBeNull()
    expect(findFragment('I lived here.', '   ')).toBeNull()
  })
})

describe('highlightSegments', () => {
  it('marks the wrong form between plain segments', () => {
    expect(highlightSegments('I lived in campus.', 'lived')).toEqual([
      { kind: 'text', text: 'I ' },
      { kind: 'mark', text: 'lived', errors: [0] },
      { kind: 'text', text: ' in campus.' },
    ])
  })

  it('shows the text as it is when the form is not found, without throwing', () => {
    expect(highlightSegments('I lived here.', 'campus')).toEqual([
      { kind: 'text', text: 'I lived here.' },
    ])
    expect(highlightSegments('', 'x')).toEqual([])
  })
})
