import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '../../api/client'
import { useAssess } from '../../api/pronunciation'
import type { Production } from '../../api/productions'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { PronunciationView } from './PronunciationView'

/**
 * The optional pronunciation assessment of a shadowing (M6.c2). Nothing is sent by itself: the
 * button is the only way, it says that the recording goes to Microsoft, and it is greyed out with
 * the backend's reason (`assessable_reason`). The scores of a take already assessed are shown.
 */
export function AssessmentSection({ production }: { production: Production }) {
  const { t } = useTranslation()
  const assess = useAssess()
  const elapsed = useElapsedSeconds(assess.isPending, assess.submittedAt)
  const scores = production.pronunciation ?? null
  const reason = production.assessable_reason ?? null
  const failure =
    assess.data !== undefined && (assess.data.status === 'unavailable' || assess.data.status === 'incomplete')
      ? assess.data
      : null

  // Assessed meanwhile (409): the production is read again, nothing to say.
  const alreadyAssessed =
    assess.error instanceof ApiError && assess.error.code === 'already_assessed'

  // A backend older than M6.c1 sends none of these fields: show nothing rather than a dead button.
  if (production.assessable === undefined && scores === null) return null
  // Not a take the assessment is about at all (no shadowing sentence, no recording): say nothing.
  if (scores === null && (reason === 'not_shadowing' || reason === 'no_audio')) return null

  return (
    <section className="card" aria-labelledby="shadow-pronunciation">
      <h2 id="shadow-pronunciation">{t('pronunciation.title')}</h2>
      {scores !== null ? (
        <PronunciationView scores={scores} />
      ) : (
        <>
          <p>
            <button
              type="button"
              className="button"
              disabled={production.assessable !== true || assess.isPending}
              aria-describedby="assess-hint"
              onClick={() => assess.mutate(production.id)}
            >
              {assess.isPending
                ? t('pronunciation.running', { seconds: elapsed })
                : failure !== null
                  ? t('pronunciation.tryAgain')
                  : t('pronunciation.button')}
            </button>
          </p>
          <p id="assess-hint" className="muted field-hint">
            {production.assessable === true || reason === null
              ? t('pronunciation.privacy')
              : t(`pronunciation.reasons.${reason}`)}{' '}
            {(reason === 'disabled' || reason === 'not_configured') && (
              <Link to="/settings#azure">{t('pronunciation.settingsLink')}</Link>
            )}
          </p>
        </>
      )}
      <div role="status" aria-live="polite">
        {failure !== null && (
          <p className="form-message form-message--warn">
            {failure.status === 'unavailable'
              ? t('pronunciation.unavailable', { reason: aiReasonText(t, failure.reason) })
              : t('pronunciation.incomplete')}
          </p>
        )}
      </div>
      {assess.isError && !alreadyAssessed && <ErrorText error={assess.error} />}
    </section>
  )
}
