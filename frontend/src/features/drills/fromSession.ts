/**
 * The study session a drill is started from, carried by the navigation state `{fromSession: id}`
 * (the session's `practice_info` step, or the Today card with a session open). Anything else is
 * ignored.
 */
export function fromSessionOf(state: unknown): number | null {
  if (state === null || typeof state !== 'object' || !('fromSession' in state)) return null
  const id = state.fromSession
  return typeof id === 'number' && Number.isInteger(id) && id > 0 ? id : null
}

/** The navigation state of a link to the drills pages. */
export function sessionState(sessionId: number | null): { fromSession: number } | undefined {
  return sessionId !== null ? { fromSession: sessionId } : undefined
}
