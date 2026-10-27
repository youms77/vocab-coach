import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { ApiError } from '../../api/client'
import { useGenerateUnit } from '../../api/curriculum'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'

/**
 * "Write this unit with the AI": one request (a few seconds). The ref guard answers a double click
 * (the button stays focusable while it works, so the click still arrives). `incomplete` and
 * `unavailable` are answers with nothing written: the reason, then "Try again". A `409
 * unit_generated` (written meanwhile) is refreshed silently by the hook.
 */
export function GenerateUnitButton({
  code,
  number,
  describedBy,
}: {
  code: string
  number: number
  /** The id of the unit's heading: tells the identical buttons of a list apart. */
  describedBy?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const generate = useGenerateUnit()
  const waited = useElapsedSeconds(generate.isPending, generate.submittedAt)
  const busy = useRef(false)

  function run() {
    if (busy.current) return
    busy.current = true
    generate.mutate(
      { code, number },
      {
        onSuccess: (result) => {
          if (result.status === 'ok' && result.unit !== null) {
            void navigate(`/curriculum/units/${result.unit.id}`)
          }
        },
        onSettled: () => {
          busy.current = false
        },
      },
    )
  }

  const result = generate.data
  const failed = result !== undefined && result.status !== 'ok'
  const silentConflict =
    generate.error instanceof ApiError && generate.error.code === 'unit_generated'

  return (
    <div className="generate-unit">
      <button
        type="button"
        className="button button--primary"
        aria-disabled={generate.isPending}
        aria-describedby={describedBy}
        onClick={run}
      >
        {generate.isPending
          ? t('curriculum.generate.writing', { seconds: waited })
          : failed || (generate.isError && !silentConflict)
            ? t('curriculum.generate.tryAgain')
            : t('curriculum.generate.button')}
      </button>
      <span className="visually-hidden" role="status">
        {generate.isPending ? t('curriculum.generate.status') : ''}
      </span>
      {failed && (
        <div className="form-message form-message--warn" role="alert">
          <p>
            {result.status === 'incomplete'
              ? t('curriculum.generate.incomplete')
              : t('curriculum.generate.unavailable', { reason: aiReasonText(t, result.reason) })}{' '}
            {t('curriculum.generate.nothingWritten')}
          </p>
          {result.status === 'unavailable' && (
            <p>
              <Link to="/settings">{t('curriculum.generate.configure')}</Link>
            </p>
          )}
        </div>
      )}
      {generate.isError && !silentConflict && <ErrorText error={generate.error} />}
    </div>
  )
}
