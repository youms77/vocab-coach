import type { TFunction } from 'i18next'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Deck } from '../../api/library'
import type { DeadlinePace, PlanWarning } from '../../api/session'
import { formatDay, minutesOf } from './format'

function deckName(t: TFunction, decks: Deck[] | undefined, id: number) {
  return decks?.find((d) => d.id === id)?.name ?? t('today.unknownDeck', { id })
}

function WarningText({
  warning,
  decks,
  paces,
}: {
  warning: PlanWarning
  decks: Deck[] | undefined
  paces: DeadlinePace[]
}): ReactNode {
  const { t, i18n } = useTranslation()
  const day = (value: string) => formatDay(value, i18n.language)

  switch (warning.code) {
    case 'reviews_over_budget':
      return t('plan.warnings.reviews_over_budget', {
        minutes: minutesOf(warning.params.review_seconds),
        budget: minutesOf(warning.params.budget_seconds),
      })
    case 'deadline_unrealistic': {
      const p = warning.params
      return (
        <>
          {t('plan.warnings.deadline_unrealistic', {
            deck: deckName(t, decks, p.deck_id),
            deadline: day(p.deadline),
            required: p.required_per_day,
            achievable: p.achievable_per_day,
          })}{' '}
          {p.projected_finish !== null
            ? t('plan.warnings.deadline_unrealistic_finish', { date: day(p.projected_finish) })
            : t('plan.warnings.deadline_unrealistic_never')}
        </>
      )
    }
    case 'deadline_passed':
      return t('plan.warnings.deadline_passed', {
        deck: deckName(t, decks, warning.params.deck_id),
        deadline: day(warning.params.deadline),
        count: warning.params.remaining,
      })
    case 'deadline_triage_pending': {
      const { deck_id: deckId, count } = warning.params
      // The planner warns only for a deck with a future deadline, which always has a pace.
      const deadline =
        paces.find((p) => p.deck_id === deckId)?.deadline ??
        decks?.find((d) => d.id === deckId)?.deadline
      return (
        <>
          {t('plan.warnings.deadline_triage_pending', {
            deck: deckName(t, decks, deckId),
            deadline: deadline != null ? day(deadline) : '–',
            count,
          })}{' '}
          <Link to={`/triage?deck=${deckId}`}>{t('plan.sortTerms')}</Link>
        </>
      )
    }
    case 'items_without_sheet':
      return (
        <>
          {t('plan.warnings.items_without_sheet', { count: warning.params.count })}
          {warning.params.deck_ids.length > 0 && (
            <span className="link-row plan-warning__links">
              {t('plan.decksConcerned')}
              {warning.params.deck_ids.map((id) => (
                <Link key={id} to={`/library?deck=${id}`}>
                  {deckName(t, decks, id)}
                </Link>
              ))}
            </span>
          )}
          <span className="link-row plan-warning__links">
            <Link to="/enrichment">{t('plan.writeSheets')}</Link>
          </span>
        </>
      )
  }
}

/** The plan's warnings, translated, each with the data the user needs to act. */
export function PlanWarnings({
  warnings,
  decks,
  paces,
}: {
  warnings: PlanWarning[]
  decks: Deck[] | undefined
  paces: DeadlinePace[]
}) {
  const { t } = useTranslation()
  if (warnings.length === 0) return null
  return (
    <section className="plan-warnings" aria-labelledby="plan-warnings-title">
      <h3 id="plan-warnings-title">{t('plan.warningsTitle')}</h3>
      <ul>
        {warnings.map((warning, i) => (
          <li key={`${warning.code}-${i}`} className="form-message form-message--warn">
            <WarningText warning={warning} decks={decks} paces={paces} />
          </li>
        ))}
      </ul>
    </section>
  )
}
