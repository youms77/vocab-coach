import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useDecks } from '../../api/library'
import { entriesOf, useToday } from '../../api/session'
import { ErrorText } from '../settings/ErrorText'
import { minutesOf } from './format'
import { PlanWarnings } from './PlanWarnings'

/** The home page's "Today's session" card: the plan, its warnings, and Start / Resume. */
export function TodayCard() {
  const { t } = useTranslation()
  const today = useToday()
  const decks = useDecks()

  let body
  if (today.isPending) {
    body = <p className="muted">{t('today.loading')}</p>
  } else if (today.isError) {
    body = (
      <>
        <p className="form-message form-message--error">{t('today.loadError')}</p>
        <ErrorText error={today.error} />
      </>
    )
  } else {
    const { plan, open_session: open } = today.data
    const reviews = entriesOf(plan, 'review')
    const newItems = entriesOf(plan, 'new_item')
    const targeted = entriesOf(plan, 'targeted_practice')[0]
    const consolidation = entriesOf(plan, 'consolidation')[0]
    const empty =
      reviews.length === 0 &&
      newItems.length === 0 &&
      targeted === undefined &&
      consolidation === undefined

    const perDeck = new Map<number | null, number>()
    for (const entry of newItems) perDeck.set(entry.deck_id, (perDeck.get(entry.deck_id) ?? 0) + 1)
    const deckName = (id: number | null) =>
      id === null
        ? t('today.noDeck')
        : (decks.data?.find((d) => d.id === id)?.name ?? t('today.unknownDeck', { id }))

    body = (
      <>
        {empty ? (
          <>
            <p className="muted">{t('today.empty')}</p>
            <p className="link-row">
              <Link to="/import">{t('library.importLink')}</Link>
              <Link to="/library">{t('home.libraryLink')}</Link>
            </p>
          </>
        ) : (
          <ul className="today-plan">
            <li>{t('today.reviews', { count: reviews.length })}</li>
            <li>
              {t('today.newItems', { count: newItems.length })}
              {perDeck.size > 0 && (
                <ul>
                  {[...perDeck].map(([id, count]) => (
                    <li key={id ?? 'none'}>{t('today.deckCount', { deck: deckName(id), count })}</li>
                  ))}
                </ul>
              )}
            </li>
            <li>
              {t('today.minutes', {
                minutes: minutesOf(plan.total_seconds),
                budget: minutesOf(plan.budget_seconds),
              })}
            </li>
            {targeted !== undefined && (
              <li className="muted">
                {t('today.targeted', { category: targeted.category_code, count: targeted.error_count })}
              </li>
            )}
            {consolidation !== undefined && <li className="muted">{t('today.consolidation')}</li>}
          </ul>
        )}
        <PlanWarnings warnings={plan.warnings} decks={decks.data} paces={plan.deadline_paces} />
        <p className="link-row">
          <Link to="/queue">{t('queue.manageLink')}</Link>
        </p>
        {(!empty || open !== null) && (
          <p className="today-actions">
            {open !== null && <span className="muted">{t('today.openSession')} </span>}
            <Link to="/session" className="button button--primary">
              {open !== null ? t('today.resume') : t('today.start')}
            </Link>
          </p>
        )}
      </>
    )
  }

  return (
    <section className="card today-card" aria-labelledby="today-title">
      <h2 id="today-title">{t('home.todayTitle')}</h2>
      {body}
    </section>
  )
}
