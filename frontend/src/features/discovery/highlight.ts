export interface SentencePart {
  text: string
  match: boolean
}

/**
 * Splits a sentence around the first occurrence of the term (case-insensitive), so the page can
 * highlight it. "to account for" also matches "account for". No match: the whole sentence.
 */
export function highlightTerm(sentence: string, term: string): SentencePart[] {
  const lower = sentence.toLowerCase()
  const candidates = [term.trim(), term.trim().replace(/^to\s+/i, '')]
  for (const candidate of candidates) {
    if (candidate === '') continue
    const start = lower.indexOf(candidate.toLowerCase())
    if (start === -1) continue
    const end = start + candidate.length
    return [
      { text: sentence.slice(0, start), match: false },
      { text: sentence.slice(start, end), match: true },
      { text: sentence.slice(end), match: false },
    ].filter((part) => part.text !== '')
  }
  return [{ text: sentence, match: false }]
}
