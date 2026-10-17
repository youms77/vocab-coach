import type { Deck, DeckStatus } from '../../api/library'

/*
 * The deck queue as the planner reads it (D-027), computed in the page because `GET /api/decks`
 * answers in id order (D-124). Dates are ISO calendar days ("2026-11-20"), which compare as
 * strings.
 */

/** A deadline strictly after today, as `DeckSnapshot.has_future_deadline` (deadline > today). */
export function hasFutureDeadline(deck: Pick<Deck, 'deadline'>, today: string): boolean {
  return deck.deadline !== null && deck.deadline > today
}

/** Decks with a future deadline are ordered by date; the others by hand. */
export type QueueGroup = 'deadline' | 'manual'

export function groupOf(deck: Pick<Deck, 'deadline'>, today: string): QueueGroup {
  return hasFutureDeadline(deck, today) ? 'deadline' : 'manual'
}

type Key = [number, string, number, number, number]

function orderKey(deck: Deck, today: string): Key {
  const future = hasFutureDeadline(deck, today)
  const position = deck.queue_position
  return [
    future ? 0 : 1,
    future && deck.deadline !== null ? deck.deadline : '9999-12-31',
    position !== null ? 0 : 1,
    position ?? 0,
    deck.id,
  ]
}

function compareKeys(a: Key, b: Key): number {
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] < b[i]) return -1
    if (a[i] > b[i]) return 1
  }
  return 0
}

/**
 * The decks that are not done, in D-027 order: future deadline first (earliest first), then the
 * manual `queue_position` (unset last), then id. Paused decks keep their place in the list (they
 * are part of the order the backend rewrites), although the planner skips them.
 */
export function effectiveOrder(decks: Deck[], today: string): Deck[] {
  return decks
    .filter((deck) => deck.status !== 'done')
    .map((deck) => ({ deck, key: orderKey(deck, today) }))
    .sort((a, b) => compareKeys(a.key, b.key))
    .map(({ deck }) => deck)
}

/**
 * The full list of ids to send to `PUT /api/decks/queue` after moving one deck up (-1) or down
 * (+1) among the decks of its group, or null when it cannot move: a deck with a future deadline
 * is placed by its date, and a deck at the edge of its group stays.
 */
export function moveDeck(
  ordered: Deck[],
  id: number,
  direction: -1 | 1,
  today: string,
): number[] | null {
  const index = ordered.findIndex((deck) => deck.id === id)
  if (index < 0 || groupOf(ordered[index], today) === 'deadline') return null
  const other = index + direction
  const inGroup = other >= 0 && other < ordered.length && groupOf(ordered[other], today) === 'manual'
  if (!inGroup) return null
  const ids = ordered.map((deck) => deck.id)
  ;[ids[index], ids[other]] = [ids[other], ids[index]]
  return ids
}

/** The status changes D-026 allows from each status, in the order the page shows them. */
export const DECK_TRANSITIONS: Record<DeckStatus, DeckStatus[]> = {
  queued: ['active', 'paused', 'done'],
  active: ['paused', 'done'],
  paused: ['active', 'done'],
  done: ['active'],
}

/** "Activate", "Resume" and "Reopen" all go to `active`: the label depends on where it starts. */
export type TransitionAction = 'activate' | 'resume' | 'reopen' | 'pause' | 'finish'

export function transitionAction(from: DeckStatus, to: DeckStatus): TransitionAction {
  if (to === 'active') return from === 'queued' ? 'activate' : from === 'paused' ? 'resume' : 'reopen'
  return to === 'paused' ? 'pause' : 'finish'
}

/** Today's local calendar day, when the plan's study day is not known yet. */
export function localDay(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
