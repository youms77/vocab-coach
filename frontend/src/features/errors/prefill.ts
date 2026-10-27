/**
 * The router state that opens `/errors/new` already filled in (a shadowing's misheard word, D-198).
 * The form only shows it: nothing is created until the user reads it and validates.
 */
export interface ManualErrorPrefill {
  original_text: string
  erroneous_text: string
  correction: string
  category_code: string
  explanation: string
}

/** The code of the category a misheard word is logged under (it exists in the taxonomy). */
export const INTELLIGIBILITY_CODE = 'pronunciation.intelligibility'

/** The prefill held by a navigation state, or null when it holds none (or something else). */
export function readPrefill(state: unknown): ManualErrorPrefill | null {
  if (typeof state !== 'object' || state === null) return null
  const fields = ['original_text', 'erroneous_text', 'correction', 'category_code', 'explanation']
  const record = state as Record<string, unknown>
  if (!fields.every((field) => typeof record[field] === 'string')) return null
  return {
    original_text: record.original_text as string,
    erroneous_text: record.erroneous_text as string,
    correction: record.correction as string,
    category_code: record.category_code as string,
    explanation: record.explanation as string,
  }
}
