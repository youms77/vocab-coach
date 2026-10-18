/*
 * The text being written is kept in the browser until the production is created, so a reload or a
 * closed tab does not lose it. Per-viewer convenience only: every access can fail (private
 * window, blocked storage) and the page works without it.
 */
export const DRAFT_KEY = 'vocab-coach.writing-draft'

export function loadDraft(): string {
  try {
    return window.localStorage.getItem(DRAFT_KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveDraft(text: string): void {
  try {
    if (text === '') window.localStorage.removeItem(DRAFT_KEY)
    else window.localStorage.setItem(DRAFT_KEY, text)
  } catch {
    // Storage unavailable: the draft is simply not kept.
  }
}

export function clearDraft(): void {
  saveDraft('')
}

/** Words (runs of non-space characters) and characters (Unicode code points, as the backend counts). */
export function countText(text: string): { words: number; chars: number } {
  const trimmed = text.trim()
  return {
    words: trimmed === '' ? 0 : trimmed.split(/\s+/).length,
    chars: Array.from(text).length,
  }
}
