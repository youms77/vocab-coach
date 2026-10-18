import { forwardRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { ItemResult } from '../../api/drills'

const SIGNS = { exact: '✓', wrong: '✗', empty: '–' } as const

/**
 * The solution of an answered item: a sign and a word (never colour alone), what was given, the
 * right answer, the accepted forms and the explanation (French on request). Rendered only after
 * the server's answer (D-103). `errorEventId` says the wrong answer went into the error log.
 */
export const DrillResult = forwardRef<
  HTMLDivElement,
  { result: ItemResult; errorEventId: number | null }
>(function DrillResult({ result, errorEventId }, ref) {
  const { t } = useTranslation()
  const [french, setFrench] = useState(false)
  return (
    <div ref={ref} tabIndex={-1} className="drill-result" role="region" aria-label={t('drills.result.label')}>
      <p className={`grade-result grade-result--${result.outcome}`}>
        <span aria-hidden="true">{SIGNS[result.outcome]}</span>{' '}
        <strong className="grade-result__outcome">{t(`drills.result.${result.outcome}`)}</strong>
      </p>
      <dl className="drill-facts">
        <div>
          <dt>{t('drills.result.given')}</dt>
          <dd lang="en">{result.given === '' ? t('drills.result.noneGiven') : result.given}</dd>
        </div>
        <div>
          <dt>{t('drills.result.expected')}</dt>
          <dd lang="en">{result.expected}</dd>
        </div>
        {result.accepted.length > 0 && (
          <div>
            <dt>{t('drills.result.accepted')}</dt>
            <dd lang="en">{result.accepted.join(', ')}</dd>
          </div>
        )}
      </dl>
      <p lang="en">
        <strong>{t('drills.result.why')}:</strong> {result.explanation_en}
      </p>
      <p>
        <button
          type="button"
          className="button button--small"
          aria-expanded={french}
          onClick={() => setFrench(!french)}
        >
          {french ? t('drills.result.hideFrench') : t('drills.result.showFrench')}
        </button>
      </p>
      {french && <p lang="fr">{result.explanation_fr}</p>}
      {errorEventId !== null && (
        <div className="review-summary">
          <p>
            {t('drills.result.errorLogged')}{' '}
            <Link to={`/errors/${errorEventId}`}>{t('drills.result.errorLink')}</Link>
          </p>
          <p className="muted">{t('drills.result.errorNote')}</p>
        </div>
      )}
    </div>
  )
})
