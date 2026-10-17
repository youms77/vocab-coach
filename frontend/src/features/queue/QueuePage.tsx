import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import {
  type Deck,
  type DeckStatus,
  ITEM_STATUSES,
  useDeckStatus,
  useDecks,
  useReorderQueue,
} from '../../api/library'
import { type DeadlinePace, useToday } from '../../api/session'
import { formatDay } from '../session/format'
import { PlanWarnings } from '../session/PlanWarnings'
import { ErrorText } from '../settings/ErrorText'
import {
  DECK_TRANSITIONS,
  effectiveOrder,
  groupOf,
  localDay,
  moveDeck,
  transitionAction,
} from './queueOrder'

/** Where the focus goes back once an action is done (its buttons were disabled meanwhile). */
interface FocusRequest {
  deckId: number
  control: 'up' | 'down' | 'title'
}

function Counts({ deck }: { deck: Deck }) {
  const { t } = useTranslation()
  const parts = ITEM_STATUSES.filter((status) => (deck.items_by_status[status] ?? 0) > 0).map(
    (status) =>
      t('queue.statusCount', {
        status: t(`library.status.${status}`),
        count: deck.items_by_status[status] ?? 0,
      }),
  )
  return (
    <p className="muted">
      {t('library.decks.count', { count: deck.item_count })}
      {parts.length > 0 && ` · ${parts.join(' · ')}`}
    </p>
  )
}

function Pace({ deck }: { deck: Deck }) {
  const { t, i18n } = useTranslation()
  if (deck.deadline === null) return null
  return (
    <p>
      {t('queue.deadline', { date: formatDay(deck.deadline, i18n.language) })}
      {deck.pace !== null && (
        <>
          {' '}
          {t('queue.pace', {
            remaining: deck.pace.remaining,
            days: deck.pace.days_left,
            count: deck.pace.required_per_day,
          })}
        </>
      )}
    </p>
  )
}

function DeckCard({
  deck,
  rank,
  canUp,
  canDown,
  manual,
  busy,
  decks,
  paces,
  focus,
  onFocused,
  onMove,
  onChange,
}: {
  deck: Deck
  /** Its place in the queue; null for a done deck. */
  rank: number | null
  canUp: boolean
  canDown: boolean
  manual: boolean
  busy: boolean
  decks: Deck[]
  paces: DeadlinePace[]
  focus: FocusRequest | null
  onFocused: () => void
  onMove: (deck: Deck, direction: -1 | 1) => void
  onChange: (deck: Deck, to: DeckStatus) => void
}) {
  const { t } = useTranslation()
  const title = useRef<HTMLAnchorElement>(null)
  const up = useRef<HTMLButtonElement>(null)
  const down = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (busy || focus === null || focus.deckId !== deck.id) return
    const wanted = focus.control === 'up' ? up.current : focus.control === 'down' ? down.current : null
    const other = focus.control === 'up' ? down.current : up.current
    const target = [wanted, other].find((b) => b !== null && !b.disabled) ?? title.current
    target?.focus()
    onFocused()
  }, [busy, focus, deck.id, onFocused])

  return (
    <li className="card queue-deck">
      <div className="queue-deck__head">
        <h3>
          {rank !== null && <span className="queue-deck__rank">{rank}. </span>}
          <Link ref={title} to={`/library?deck=${deck.id}`}>
            {deck.name}
          </Link>
        </h3>
        <span className={`badge queue-status queue-status--${deck.status}`}>
          {t(`queue.status.${deck.status}`)}
        </span>
      </div>
      <Counts deck={deck} />
      <Pace deck={deck} />
      {rank !== null && !manual && <p className="muted">{t('queue.byDate')}</p>}
      <PlanWarnings warnings={deck.warnings} decks={decks} paces={paces} />
      <div className="button-row">
        {rank !== null && manual && (
          <>
            <button
              ref={up}
              type="button"
              className="button"
              onClick={() => onMove(deck, -1)}
              disabled={busy || !canUp}
              aria-label={t('queue.moveUpNamed', { deck: deck.name })}
            >
              {t('queue.moveUp')}
            </button>
            <button
              ref={down}
              type="button"
              className="button"
              onClick={() => onMove(deck, 1)}
              disabled={busy || !canDown}
              aria-label={t('queue.moveDownNamed', { deck: deck.name })}
            >
              {t('queue.moveDown')}
            </button>
          </>
        )}
        {DECK_TRANSITIONS[deck.status].map((to) => {
          const action = transitionAction(deck.status, to)
          return (
            <button
              key={to}
              type="button"
              className="button"
              onClick={() => onChange(deck, to)}
              disabled={busy}
              aria-label={t(`queue.actionsNamed.${action}`, { deck: deck.name })}
            >
              {t(`queue.actions.${action}`)}
            </button>
          )
        })}
      </div>
    </li>
  )
}

/**
 * `/queue` (module D): the decks in the order the planner reads them (D-027), their status,
 * deadline pace and warnings; the manual order by "Move up" / "Move down" (no drag and drop), and
 * the status changes D-026 allows. Nothing asks for confirmation: every change can be undone.
 */
export function QueuePage() {
  const { t, i18n } = useTranslation()
  const decks = useDecks()
  const today = useToday()
  const setStatus = useDeckStatus()
  const reorder = useReorderQueue()
  const [message, setMessage] = useState('')
  const [focus, setFocus] = useState<FocusRequest | null>(null)
  const clearFocus = useCallback(() => setFocus(null), [])

  const day = today.data?.plan.study_day ?? localDay()
  const all = decks.data ?? []
  const ordered = effectiveOrder(all, day)
  const done = all.filter((deck) => deck.status === 'done')
  const paces = all.flatMap((deck) => (deck.pace !== null ? [deck.pace] : []))
  // Busy until the list is fresh again, so the next move is computed on the new order.
  const busy = setStatus.isPending || reorder.isPending || decks.isFetching
  const error = setStatus.error ?? reorder.error

  function move(deck: Deck, direction: -1 | 1) {
    const ids = moveDeck(ordered, deck.id, direction, day)
    if (ids === null || busy) return
    setStatus.reset()
    setMessage('')
    reorder.mutate(ids, {
      onSuccess: () => {
        setMessage(
          t(direction < 0 ? 'queue.announce.movedUp' : 'queue.announce.movedDown', {
            deck: deck.name,
            position: ids.indexOf(deck.id) + 1,
          }),
        )
        setFocus({ deckId: deck.id, control: direction < 0 ? 'up' : 'down' })
      },
    })
  }

  function change(deck: Deck, to: DeckStatus) {
    if (busy) return
    reorder.reset()
    setMessage('')
    setStatus.mutate(
      { id: deck.id, to },
      {
        onSuccess: (saved) => {
          setMessage(
            t('queue.announce.status', {
              deck: saved.name,
              status: t(`queue.status.${saved.status}`).toLocaleLowerCase(i18n.language),
            }),
          )
          setFocus({ deckId: deck.id, control: 'title' })
        },
      },
    )
  }

  const card = (deck: Deck, rank: number | null) => (
    <DeckCard
      key={deck.id}
      deck={deck}
      rank={rank}
      manual={groupOf(deck, day) === 'manual'}
      canUp={moveDeck(ordered, deck.id, -1, day) !== null}
      canDown={moveDeck(ordered, deck.id, 1, day) !== null}
      busy={busy}
      decks={all}
      paces={paces}
      focus={focus}
      onFocused={clearFocus}
      onMove={move}
      onChange={change}
    />
  )

  let body
  if (decks.isPending) {
    body = <p className="muted">{t('queue.loading')}</p>
  } else if (decks.isError) {
    body = <ErrorText error={decks.error} />
  } else if (all.length === 0) {
    body = (
      <p className="muted">
        {t('queue.empty')} <Link to="/import">{t('library.importLink')}</Link>
      </p>
    )
  } else {
    body = (
      <>
        <section aria-labelledby="queue-list-title">
          <h2 id="queue-list-title">{t('queue.listTitle')}</h2>
          {ordered.length === 0 ? (
            <p className="muted">{t('queue.allDone')}</p>
          ) : (
            <ol className="queue-list">{ordered.map((deck, index) => card(deck, index + 1))}</ol>
          )}
        </section>
        {done.length > 0 && (
          <details className="queue-done">
            <summary>{t('queue.doneTitle', { count: done.length })}</summary>
            <ul className="queue-list">{done.map((deck) => card(deck, null))}</ul>
          </details>
        )}
      </>
    )
  }

  return (
    <div className="queue-page">
      <p className="link-row">
        <Link to="/">{t('queue.backHome')}</Link>
        <Link to="/library/decks">{t('queue.decksLink')}</Link>
      </p>
      <section className="hero">
        <h1>{t('queue.title')}</h1>
        <p>{t('queue.intro')}</p>
        <p className="muted">{t('queue.orderHelp')}</p>
        <p className="muted">{t('queue.pauseNote')}</p>
      </section>
      <p className="queue-announce" role="status">
        {message}
      </p>
      {error !== null && (
        <div className="form-message form-message--error">
          <ErrorText error={error} />
          <p>{t('queue.reloaded')}</p>
        </div>
      )}
      {body}
    </div>
  )
}
