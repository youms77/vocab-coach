import { useTranslation } from 'react-i18next'

import type { ReviewStep } from '../../api/session'
import { type RecorderApi, RecorderView } from '../../speech/RecorderPanel'
import type { Clip } from '../../speech/useRecorder'
import { ErrorText } from '../settings/ErrorText'
import type { ReviewState } from './reviewMachine'

/**
 * The oral answer of a `spoken_answer` card (D-206): the recorder while the answer is being
 * given. The wait and the way out are the player's (`CheckingPanel`). Nothing of the solution is
 * here: the example answer only comes with the result (D-103).
 *
 * "Answer without recording" is always there (the self-graded path of M4.c), and the primary
 * action when the microphone failed.
 */
export function SpokenAnswer({
  review,
  state,
  recorder,
  tooLarge,
  micFailed,
  onSend,
  onAgain,
  onDecline,
}: {
  review: ReviewStep
  state: ReviewState
  recorder: RecorderApi
  tooLarge: boolean
  /** The microphone is refused, absent or not supported: answering without it is the way on. */
  micFailed: boolean
  onSend: (clip: Clip) => void
  onAgain: () => void
  onDecline: () => void
}) {
  const { t } = useTranslation()
  const phase = state.phase
  if (phase === 'checking') return <p className="muted">{t('review.checking')}</p>
  if (phase !== 'answering' && phase !== 'capturing' && phase !== 'captured') return null
  return (
    <div className="spoken-answer">
      {review.exercise_template_id !== null && (
        <RecorderView
          recorder={recorder}
          use="spoken_answer"
          onSend={onSend}
          tooLarge={tooLarge}
          onAgain={onAgain}
        />
      )}
      {phase === 'captured' && <p className="muted">{t('review.spoken.twoSteps')}</p>}
      {state.error !== null && <ErrorText error={state.error} />}
      <div className="button-row">
        <button
          type="button"
          className={micFailed ? 'button button--primary' : 'button'}
          onClick={onDecline}
        >
          {t('review.spoken.withoutRecording')}
        </button>
      </div>
    </div>
  )
}
