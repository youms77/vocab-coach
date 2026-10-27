import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Scenario, Unit } from '../../api/curriculum'
import { refsOf } from './unitRules'

/**
 * Step 4: the final talk. The prompt is in English (French on demand); "Record my talk" opens the
 * free-speaking page on this unit, which corrects the talk by itself once (D-203).
 */
export function FinalTaskStep({ unit, scenario }: { unit: Unit; scenario: Scenario }) {
  const { t } = useTranslation()
  const [french, setFrench] = useState(false)
  const task = scenario.final_task
  const formulas = refsOf(scenario)

  return (
    <>
      <p lang="en">{task.prompt_en}</p>
      <p>
        <button
          type="button"
          className="button button--small"
          aria-expanded={french}
          onClick={() => setFrench(!french)}
        >
          {french ? t('curriculum.finalTask.hideFrench') : t('curriculum.finalTask.showFrench')}
        </button>
      </p>
      {french && <p lang="fr">{task.prompt_fr}</p>}
      <p className="muted">{t('curriculum.finalTask.minutes', { count: task.minutes })}</p>

      {formulas.length > 0 && (
        <>
          <h3>{t('curriculum.finalTask.formulas')}</h3>
          <ul className="unit-terms" lang="en">
            {formulas.map((formula) => (
              <li key={formula.index}>{formula.text}</li>
            ))}
          </ul>
        </>
      )}

      <p>
        <Link to="/speaking" state={{ unitId: unit.id }} className="button button--primary">
          {t('curriculum.finalTask.record')}
        </Link>
      </p>

      <h3>{t('curriculum.finalTask.attempts', { count: task.attempt_ids.length })}</h3>
      {task.attempt_ids.length > 0 && (
        <>
          <ul className="unit-terms">
            {task.attempt_ids.map((id, index) => (
              <li key={id}>
                <Link to={`/speaking/${id}?unit=${unit.id}`}>
                  {t('curriculum.finalTask.attempt', { number: index + 1 })}
                </Link>
              </li>
            ))}
          </ul>
          <p>
            <strong>
              {task.corrected
                ? t('curriculum.finalTask.corrected')
                : t('curriculum.finalTask.notCorrected')}
            </strong>
          </p>
        </>
      )}
    </>
  )
}
