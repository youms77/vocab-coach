/** The server refuses a topic over 500 characters (`invalid_production`, code points). */
export const SPEAKING_PROMPT_MAX_CHARS = 500

/** True when the page that sent the recording asked for the correction to start by itself. */
export function readAutoCorrect(state: unknown): boolean {
  return (
    typeof state === 'object' &&
    state !== null &&
    (state as Record<string, unknown>).autoCorrect === true
  )
}
