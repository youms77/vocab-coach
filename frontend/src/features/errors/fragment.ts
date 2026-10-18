import { type Segment, segment } from '../writing/spans'

/*
 * Where a wrong form sits in the original sentence of a logged error. A look-alike of the backend's
 * `find_fragment` (backend/app/domain/sentences.py): it ignores runs of spaces, typographic
 * apostrophes, Unicode composition and, when the exact case is not found, case. Pure: no DOM.
 * Positions are UTF-16 offsets (what `String.slice` takes), not code points.
 */

const APOSTROPHES = new Set(Array.from('‘’‚‛′ʼ´`'))

/** `text` with the comparable normalisation, and for each character the offset it comes from. */
function comparable(text: string, fold: boolean): { chars: string; origin: number[] } {
  let chars = ''
  const origin: number[] = []
  let index = 0
  for (const char of text) {
    let pieces: string
    if (/\s/u.test(char)) {
      if (chars.endsWith(' ')) {
        index += char.length
        continue
      }
      pieces = ' '
    } else if (APOSTROPHES.has(char)) {
      pieces = "'"
    } else {
      pieces = char.normalize('NFD')
      if (fold) pieces = pieces.toLowerCase()
    }
    for (let i = 0; i < pieces.length; i++) origin.push(index)
    chars += pieces
    index += char.length
  }
  return { chars, origin }
}

/** `[start, end)` of `fragment` in `sentence`, or null when it is absent (or empty). Never throws. */
export function findFragment(sentence: string, fragment: string): [number, number] | null {
  for (const fold of [false, true]) {
    const haystack = comparable(sentence, fold)
    const needle = comparable(fragment.trim(), fold).chars
    if (needle === '') return null
    const found = haystack.chars.indexOf(needle)
    if (found >= 0) {
      const last = haystack.origin[found + needle.length - 1]
      // End of the last matched character: a surrogate pair is two UTF-16 units long.
      const lastChar = String.fromCodePoint(sentence.codePointAt(last) ?? 0)
      return [haystack.origin[found], last + lastChar.length]
    }
  }
  return null
}

/** The original cut into plain and marked segments; one plain segment when the form is not found. */
export function highlightSegments(original: string, wrong: string): Segment[] {
  const found = findFragment(original, wrong)
  if (found === null) return original === '' ? [] : [{ kind: 'text', text: original }]
  return segment(original, [{ start: found[0], end: found[1], errors: [0] }])
}
