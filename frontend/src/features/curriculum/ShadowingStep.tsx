import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Scenario, Unit } from '../../api/curriculum'

/**
 * Step 3: the lines to shadow. A take counts as soon as it is transcribed, whatever the speech
 * recognition heard: it is not a pronunciation judge. The line travels in the navigation state
 * (cleared on arrival), the unit id with it.
 */
export function ShadowingStep({ unit, scenario }: { unit: Unit; scenario: Scenario }) {
  const { t } = useTranslation()
  return (
    <>
      <p className="muted">{t('curriculum.shadowing.intro')}</p>
      <ol className="unit-shadowing">
        {scenario.shadowing.map((line) => (
          <li key={line.line_index} className="unit-shadow-line">
            <p lang="en">{line.text}</p>
            <p className="muted">
              <strong>{line.done ? t('curriculum.shadowing.done') : t('curriculum.shadowing.todo')}</strong>
              {' · '}
              {t('curriculum.shadowing.takes', { count: line.take_count })}
            </p>
            <p>
              <Link
                to="/speaking/shadowing"
                state={{ target: line.text, unitId: unit.id }}
                className="button button--small"
                aria-label={t('curriculum.shadowing.shadowNamed', { number: line.line_index + 1 })}
              >
                {t('curriculum.shadowing.shadow')}
              </Link>
            </p>
          </li>
        ))}
      </ol>
    </>
  )
}
