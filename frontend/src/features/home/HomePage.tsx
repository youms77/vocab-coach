import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useHealth } from '../../api/health'
import { formatInstant, formatStudyDay } from '../../i18n/format'
import { useDecks } from '../../api/library'
import { entriesOf, useToday } from '../../api/session'
import { ActionTile } from '../../components/ActionTile'
import { HomeHero } from '../../components/HomeHero'
import { Notice } from '../../components/Notice'
import { StatTile } from '../../components/StatTile'
import { minutesOf } from '../session/format'
import { TodayCard } from '../session/TodayCard'

function ApiStatus() {
  const { t } = useTranslation()
  const health = useHealth()

  if (health.isPending) {
    return <Notice>{t('home.apiChecking')}</Notice>
  }
  if (health.isError) {
    return <Notice tone="danger">{t('home.apiDown')}</Notice>
  }
  return <Notice tone="success">{t('home.apiOk', { version: health.data.version })}</Notice>
}

/** The home page: the hero with the one action, the day's figures, where to continue, the plan. */
export function HomePage() {
  const { t, i18n } = useTranslation()
  const today = useToday()
  const decks = useDecks()
  // Only the greeting's date falls back on the browser clock, while the plan is loading (D-266).
  const [now] = useState(() => new Date())

  const plan = today.data?.plan
  const open = today.data?.open_session ?? null
  const reviews = plan === undefined ? 0 : entriesOf(plan, 'review').length
  const newItems = plan === undefined ? 0 : entriesOf(plan, 'new_item').length
  const minutes = plan === undefined ? 0 : minutesOf(plan.total_seconds)
  const budget = plan === undefined ? 0 : minutesOf(plan.budget_seconds)
  const consolidation =
    plan === undefined ? undefined : entriesOf(plan, 'consolidation')[0]
  const planned = reviews + newItems > 0

  const dateOptions = { weekday: 'long', day: 'numeric', month: 'long' } as const
  const date =
    plan === undefined
      ? formatInstant(i18n.language, now, dateOptions)
      : formatStudyDay(i18n.language, plan.study_day, dateOptions)

  return (
    <div className="home">
      <HomeHero
        date={date}
        title={planned ? t('home.greeting', { minutes }) : t('home.title')}
        text={
          open !== null
            ? t('today.openSession')
            : planned
              ? t('home.heroText', {
                  reviews: t('home.heroReviews', { count: reviews }),
                  newItems: t('home.heroNewItems', { count: newItems }),
                })
              : t('home.intro')
        }
      >
        {(planned || open !== null) && (
          <Link to="/session" className="button button--hero button--large">
            {open !== null ? t('today.resume') : t('today.start')}
          </Link>
        )}
      </HomeHero>

      {plan !== undefined && (
        <div className="tile-grid">
          <StatTile value={reviews} label={t('home.tiles.reviews')} />
          <StatTile value={newItems} label={t('home.tiles.newItems')} />
          <StatTile
            value={minutes}
            label={t('home.tiles.minutes', { budget })}
            progress={budget > 0 ? minutes / budget : undefined}
          />
        </div>
      )}

      <section aria-labelledby="continue-title" className="home__continue">
        <h2 id="continue-title">{t('home.continueTitle')}</h2>
        <div className="tile-grid">
          <ActionTile
            to="/library"
            icon="library"
            title={t('nav.library')}
            text={decks.data === undefined ? '' : t('home.continue.decks', { count: decks.data.length })}
          />
          <ActionTile
            to="/writing"
            icon="writing"
            title={t('nav.writing')}
            text={t('home.continue.writing')}
          />
          <ActionTile
            to="/speaking"
            icon="speaking"
            title={t('nav.speaking')}
            text={t('home.continue.speaking')}
          />
          <ActionTile
            to="/errors"
            icon="errors"
            title={t('nav.errors')}
            text={t('home.continue.errors')}
          />
          {consolidation !== undefined && (
            <ActionTile
              to={`/consolidation/tasks/${consolidation.consolidation_task_id}`}
              icon="consolidation"
              title={t('nav.consolidation')}
              text={t('home.continue.consolidation')}
            />
          )}
        </div>
      </section>

      <TodayCard />

      <section className="card" aria-labelledby="status-title" aria-live="polite">
        <h2 id="status-title">{t('home.statusTitle')}</h2>
        <ApiStatus />
      </section>
    </div>
  )
}
