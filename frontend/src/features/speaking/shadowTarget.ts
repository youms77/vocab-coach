/** The server refuses a target over 400 characters (`invalid_target`, code points). */
export const SHADOW_MAX_CHARS = 400

/** What a usage sheet gives to the shadowing page through the navigation state. */
export interface ShadowTarget {
  target: string
  itemId?: number
}

/** The target held by a navigation state, or null when it holds none (a reload, a direct visit). */
export function readShadowTarget(state: unknown): ShadowTarget | null {
  if (typeof state !== 'object' || state === null) return null
  const record = state as Record<string, unknown>
  if (typeof record.target !== 'string') return null
  const itemId = record.itemId
  return {
    target: record.target,
    itemId: typeof itemId === 'number' && Number.isInteger(itemId) ? itemId : undefined,
  }
}

/** The reason a first transcription failed, handed over by the page that sent the recording. */
export function readUnavailableReason(state: unknown): string | null {
  if (typeof state !== 'object' || state === null) return null
  const reason = (state as Record<string, unknown>).unavailableReason
  return typeof reason === 'string' ? reason : null
}
