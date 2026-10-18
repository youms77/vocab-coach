import type { TranscriptBody } from '../../api/transcripts'

/*
 * The pasted conversation, kept in memory only (D-151). The server stores your turns but not the
 * other speaker's, so `/correct` needs the paste again to give the AI the context of each of your
 * turns. It lives in this module's variable: never in localStorage, sessionStorage, the router's
 * state (which is written to `history.state`) or the URL. A reload empties it; the detail page
 * then offers to analyse without context or to paste the conversation again.
 */
const memory = new Map<number, TranscriptBody>()

/** Keeps the pasted conversation of a recorded transcript, by production id. */
export function remember(id: number, body: TranscriptBody): void {
  memory.set(id, body)
}

export function recall(id: number): TranscriptBody | undefined {
  return memory.get(id)
}

/** Drops it: after a successful analysis, or when the transcript turned out to be analysed already. */
export function forget(id: number): void {
  memory.delete(id)
}

/** Empties the store (tests). */
export function forgetAll(): void {
  memory.clear()
}
