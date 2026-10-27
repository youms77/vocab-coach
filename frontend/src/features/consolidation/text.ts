import type { Bilingual } from '../../api/consolidation'

/** The text in the interface language (the backend always sends both). */
export function inLanguage(text: Bilingual, language: string): string {
  return language.startsWith('fr') ? text.fr : text.en
}

/** The other language, shown under `lang` so that a screen reader switches voice. */
export function otherLanguage(language: string): 'en' | 'fr' {
  return language.startsWith('fr') ? 'en' : 'fr'
}

export const TASK_DRAFT_PREFIX = 'vocab-coach.consolidation-draft.'

export function loadTaskDraft(taskId: number): string {
  try {
    return window.localStorage.getItem(TASK_DRAFT_PREFIX + taskId) ?? ''
  } catch {
    return ''
  }
}

export function saveTaskDraft(taskId: number, text: string): void {
  try {
    if (text === '') window.localStorage.removeItem(TASK_DRAFT_PREFIX + taskId)
    else window.localStorage.setItem(TASK_DRAFT_PREFIX + taskId, text)
  } catch {
    // Storage unavailable: the draft is simply not kept.
  }
}
