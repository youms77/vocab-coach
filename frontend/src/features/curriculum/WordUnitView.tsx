import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Unit } from '../../api/curriculum'
import { PageTitle } from '../../components/PageTitle'
import { termsToTriage } from './unitRules'
import { English } from '../../components/English'

/**
 * A word unit: its terms with their status in words, and the way to triage them. No usage sheet and
 * no definition here: the triage decides without a sheet (D-075), and a word is never shown with
 * its answer before the learner has met it in a review.
 */
export function WordUnitView({ unit }: { unit: Unit }) {
  const { t } = useTranslation()
  const remaining = termsToTriage(unit)

  return (
    <div className="curriculum-page">
      <section className="hero">
        <PageTitle>{unit.title}</PageTitle>
        <p className="muted">{t(`curriculum.state.${unit.state}`)}</p>
        <p className="link-row">
          <Link to={`/curriculum/${unit.track_code}`}>{t('curriculum.backToTrack')}</Link>
          {unit.deck_id !== null && (
            <Link to={`/library?deck=${unit.deck_id}`}>{t('curriculum.deckLink')}</Link>
          )}
        </p>
      </section>

      <section className="card" aria-labelledby="unit-triage">
        <h2 id="unit-triage">{t('curriculum.word.triageTitle')}</h2>
        {remaining > 0 && unit.deck_id !== null ? (
          <p>
            <Link to={`/triage?deck=${unit.deck_id}`} className="button button--primary">
              {t('curriculum.word.triage', { count: remaining })}
            </Link>
          </p>
        ) : (
          <p className="muted">{t('curriculum.word.allSorted')}</p>
        )}
      </section>

      <section className="card" aria-labelledby="unit-terms">
        <h2 id="unit-terms">{t('curriculum.word.terms', { count: unit.terms.length })}</h2>
        <ul className="unit-terms">
          {unit.terms.map((term) => (
            <li key={term.item_id}>
              <Link to={`/library/items/${term.item_id}`} lang="en">
                <English>{term.term}</English>
              </Link>{' '}
              <span className="muted">{t(`library.status.${term.status}`)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
