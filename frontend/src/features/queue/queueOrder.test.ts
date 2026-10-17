import { describe, expect, it } from 'vitest'

import { deck } from '../../test/fixtures'
import {
  DECK_TRANSITIONS,
  effectiveOrder,
  groupOf,
  hasFutureDeadline,
  localDay,
  moveDeck,
  transitionAction,
} from './queueOrder'

const TODAY = '2026-10-17'
const ids = (decks: { id: number }[]) => decks.map((d) => d.id)

describe('effectiveOrder (D-027)', () => {
  it('puts future deadlines first, earliest first, then positions, unset last, then id', () => {
    const decks = [
      deck(1, 'No position, low id', { queue_position: null }),
      deck(2, 'Position 1', { queue_position: 1 }),
      deck(3, 'Late deadline', { deadline: '2026-12-01', queue_position: 0 }),
      deck(4, 'Position 0', { queue_position: 0 }),
      deck(5, 'Early deadline', { deadline: '2026-10-20', queue_position: 5 }),
      deck(6, 'No position, high id', { queue_position: null }),
      deck(7, 'Same position as 2, higher id', { queue_position: 1 }),
    ]
    expect(ids(effectiveOrder(decks, TODAY))).toEqual([5, 3, 4, 2, 7, 1, 6])
  })

  it('treats a deadline today or in the past like no deadline (it keeps its normal place)', () => {
    const decks = [
      deck(1, 'Passed', { deadline: '2026-10-01', queue_position: 2 }),
      deck(2, 'Today', { deadline: TODAY, queue_position: 0 }),
      deck(3, 'Tomorrow', { deadline: '2026-10-18', queue_position: 9 }),
      deck(4, 'Plain', { queue_position: 1 }),
    ]
    expect(ids(effectiveOrder(decks, TODAY))).toEqual([3, 2, 4, 1])
    expect(hasFutureDeadline(decks[1], TODAY)).toBe(false)
    expect(groupOf(decks[0], TODAY)).toBe('manual')
    expect(groupOf(decks[2], TODAY)).toBe('deadline')
  })

  it('leaves done decks out and keeps paused ones in place', () => {
    const decks = [
      deck(1, 'Done', { status: 'done', queue_position: 0 }),
      deck(2, 'Paused', { status: 'paused', queue_position: 1 }),
      deck(3, 'Active', { status: 'active', queue_position: 2 }),
    ]
    expect(ids(effectiveOrder(decks, TODAY))).toEqual([2, 3])
  })
})

describe('moveDeck', () => {
  const ordered = effectiveOrder(
    [
      deck(1, 'Dated', { deadline: '2026-11-01', queue_position: null }),
      deck(2, 'A', { queue_position: 0 }),
      deck(3, 'B', { queue_position: 1 }),
      deck(4, 'C', { queue_position: null, status: 'paused' }),
    ],
    TODAY,
  )

  it('swaps two decks of the manual group and returns every deck that is not done', () => {
    expect(moveDeck(ordered, 3, -1, TODAY)).toEqual([1, 3, 2, 4])
    expect(moveDeck(ordered, 3, 1, TODAY)).toEqual([1, 2, 4, 3])
  })

  it('never moves a dated deck, nor a manual deck past the dated ones or the end', () => {
    expect(moveDeck(ordered, 1, 1, TODAY)).toBeNull()
    expect(moveDeck(ordered, 2, -1, TODAY)).toBeNull()
    expect(moveDeck(ordered, 4, 1, TODAY)).toBeNull()
    expect(moveDeck(ordered, 99, 1, TODAY)).toBeNull()
  })
})

describe('status transitions (D-026)', () => {
  it('lists only the allowed changes, with the right action names', () => {
    expect(DECK_TRANSITIONS).toEqual({
      queued: ['active', 'paused', 'done'],
      active: ['paused', 'done'],
      paused: ['active', 'done'],
      done: ['active'],
    })
    expect(transitionAction('queued', 'active')).toBe('activate')
    expect(transitionAction('paused', 'active')).toBe('resume')
    expect(transitionAction('done', 'active')).toBe('reopen')
    expect(transitionAction('active', 'paused')).toBe('pause')
    expect(transitionAction('active', 'done')).toBe('finish')
  })
})

describe('localDay', () => {
  it('formats the local calendar day', () => {
    expect(localDay(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
  })
})
