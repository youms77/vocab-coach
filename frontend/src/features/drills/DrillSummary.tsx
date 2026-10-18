import { forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Drill } from '../../api/drills'
import { fillGap } from './drillRules'
import { sessionState } from './fromSession'

const SIGNS = { exact: '✓', wrong: '✗', empty: '–' } as const

/**
 * The end of a drill: the score, a recap of every item, and where to go next. The recap is shown
 * only now, once every item was answered (D-103).
 */
export const DrillSummary = forwardRef<HTMLDivElement, { drill: Drill; fromSession: number | null }>(
  function DrillSummary({ drill, fromSession }, ref) {
    const { t } = useTranslation()
    const { score, category } = drill
    const code = encodeURIComponent(category.code)
    return (
      <section ref={ref} tabIndex={-1} className="card drill-summary" aria-labelledby="drill-summary-title">
        <h2 id="drill-summary-title">{t('drills.summary.title')}</h2>
        <p className="drill-score" role="status">
          <strong>{t('drills.summary.score', { correct: score.correct, total: score.total })}</strong>
        </p>
        <p className="muted">
          {t('drills.summary.detail', { correct: score.correct, wrong: score.wrong, empty: score.empty })}
        </p>

        <h3>{t('drills.summary.recap')}</h3>
        <ol className="drill-recap">
          {drill.items.map((item) => (
            <li key={item.index} className={`drill-recap__item drill-recap__item--${item.result?.outcome ?? 'empty'}`}>
              {item.result !== null && (
                <>
                  <p lang="en">{fillGap(item.sentence, item.result.expected)}</p>
                  <p className="muted">
                    <span aria-hidden="true">{SIGNS[item.result.outcome]}</span>{' '}
                    {t(`drills.result.${item.result.outcome}`)}
                    {item.result.outcome !== 'exact' && (
                      <>
                        {' · '}
                        {t('drills.result.given')}:{' '}
                        <span lang="en">
                          {item.result.given === '' ? t('drills.result.noneGiven') : item.result.given}
                        </span>
                      </>
                    )}
                  </p>
                </>
              )}
            </li>
          ))}
        </ol>

        <p className="drill-actions">
          <Link
            to={`/drills?category=${code}`}
            state={sessionState(fromSession)}
            className="button button--primary"
          >
            {t('drills.summary.newDrill')}
          </Link>
          <Link to={`/errors?source=drill&category=${code}`} className="button">
            {t('drills.summary.seeErrors')}
          </Link>
          {fromSession !== null && (
            <Link to="/session" className="button">
              {t('drills.summary.backToSession')}
            </Link>
          )}
          <Link to="/drills" className="button">
            {t('drills.summary.allDrills')}
          </Link>
        </p>
      </section>
    )
  },
)
