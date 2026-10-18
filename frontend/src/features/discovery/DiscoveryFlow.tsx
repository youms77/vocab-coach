import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '../../api/client'
import { type CompleteResult, useCompleteDiscovery, useStartDiscovery } from '../../api/discovery'
import { useCorrectProduction, useProduction } from '../../api/productions'
import type { NewItemStep } from '../../api/session'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { formatDateTime } from '../session/format'
import { StepHeading } from '../session/StepHeading'
import { aiReasonText } from '../settings/aiReason'
import { ErrorText } from '../settings/ErrorText'
import { CorrectionView } from '../writing/CorrectionView'
import { type ExerciseOutcome, ExercisesStep } from './ExercisesStep'
import { PersonalSentenceStep, RepetitionStep } from './ProductionSteps'
import { ReadAndGuess } from './ReadAndGuess'
import { SheetStep } from './SheetStep'

type Phase = 'read' | 'sheet' | 'exercises' | 'repetition' | 'personal' | 'done'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

/**
 * The optional AI check of the personal sentence (D-104, D-128, D-143). It only calls `/correct` on the
 * production `complete` created; a failure is said and never blocks "Continue". The usage sheet
 * is neither reloaded nor shown on this path.
 */
function SentenceCheck({ productionId, sentence }: { productionId: number; sentence: string }) {
  const { t } = useTranslation()
  const correct = useCorrectProduction()
  const seconds = useElapsedSeconds(correct.isPending, correct.submittedAt)
  // Corrected meanwhile (409 already_corrected): show what is stored.
  const stored = useProduction(productionId, codeOf(correct.error) === 'already_corrected')
  const done = correct.data?.status === 'ok' ? correct.data : null
  const feedback = done?.attempt.feedback ?? stored.data?.feedback ?? null

  let failure: string | null = null
  if (correct.data?.status === 'incomplete') failure = t('discovery.sentenceCheck.incomplete')
  else if (correct.data?.status === 'unavailable') {
    failure = t('discovery.sentenceCheck.unavailable', { reason: aiReasonText(t, correct.data.reason) })
  }

  return (
    <section className="discovery-check" aria-label={t('discovery.sentenceCheck.title')}>
      {feedback === null && (
        <p>
          <button
            type="button"
            className="button"
            disabled={correct.isPending}
            onClick={() => correct.mutate(productionId)}
          >
            {correct.isPending
              ? t('discovery.sentenceCheck.running', { seconds })
              : t('discovery.sentenceCheck.button')}
          </button>
        </p>
      )}
      {feedback === null && <p className="muted field-hint">{t('discovery.sentenceCheck.hint')}</p>}
      <div role="status">
        {failure !== null && <p className="form-message form-message--warn">{failure}</p>}
      </div>
      {correct.isError && codeOf(correct.error) !== 'already_corrected' && <ErrorText error={correct.error} />}
      {feedback !== null && (
        <>
          <h3>{t('discovery.sentenceCheck.title')}</h3>
          <CorrectionView
            compact
            level={3}
            text={sentence}
            feedback={feedback}
            errors={done?.errors}
            proposedCategories={done?.proposed_categories}
          />
        </>
      )}
    </section>
  )
}

function Done({
  result,
  term,
  sentence,
  onNext,
}: {
  result: CompleteResult
  term: string
  /** The personal sentence that was sent, if any. */
  sentence: string | null
  onNext: () => void
}) {
  const { t, i18n } = useTranslation()
  const first = result.cards.map((c) => c.due).sort()[0]
  return (
    <>
      <StepHeading>{t('discovery.done.title')}</StepHeading>
      {first !== undefined && (
        <p>{t('discovery.done.firstReview', { term, date: formatDateTime(first, i18n.language) })}</p>
      )}
      {result.warnings.includes('term_missing') && (
        <p className="form-message form-message--warn">{t('discovery.done.term_missing')}</p>
      )}
      {result.production_attempt_id !== null && sentence !== null && (
        <SentenceCheck productionId={result.production_attempt_id} sentence={sentence} />
      )}
      <button type="button" className="button button--primary" onClick={onNext}>
        {t('discovery.done.continue')}
      </button>
    </>
  )
}

/**
 * Module B, once per term: 1–2 sentence and guess, 3 sheet, 4 immediate exercises, spoken
 * repetition and personal sentence, 5 complete (the term enters spaced repetition). A resumed
 * discovery starts again from step 1. `onNext` asks the session for its next step.
 */
export function DiscoveryFlow({
  sessionId,
  newItem,
  onNext,
}: {
  sessionId: number
  newItem: NewItemStep
  onNext: () => void
}) {
  const { t } = useTranslation()
  const itemId = newItem.item_id
  const start = useStartDiscovery(itemId)
  const complete = useCompleteDiscovery(itemId)
  const [phase, setPhase] = useState<Phase>('read')
  const [guess, setGuess] = useState<string | null>(null)
  const [results, setResults] = useState<ExerciseOutcome[]>([])
  // The personal sentence as sent, to show it with its correction on the last screen.
  const [personal, setPersonal] = useState<string | null>(null)
  // From the moment step 1 is shown to the moment `complete` is sent.
  const shownAt = useRef<number | null>(null)

  const begin = useCallback(() => {
    start.mutate(
      { session_id: sessionId, deck_id: newItem.deck_id },
      {
        onSuccess: () => {
          shownAt.current = Date.now()
        },
      },
    )
  }, [start, sessionId, newItem.deck_id])

  // Once per term (React's development double effect included): a second start would say
  // `resumed: true` for nothing.
  const begun = useRef(false)
  useEffect(() => {
    if (begun.current) return
    begun.current = true
    begin()
  }, [begin])

  // Already discovered (another tab, a double click): the session goes on, nothing to show.
  const alreadyDone =
    codeOf(start.error) === 'already_discovered' || codeOf(complete.error) === 'already_discovered'
  const skipped = useRef(false)
  useEffect(() => {
    if (alreadyDone && !skipped.current) {
      skipped.current = true
      onNext()
    }
  }, [alreadyDone, onNext])

  const onExercisesDone = useCallback((outcomes: ExerciseOutcome[]) => {
    setResults(outcomes)
    setPhase('repetition')
  }, [])

  function finish(personalSentence: string | null) {
    if (complete.isPending || complete.isSuccess) return
    setPersonal(personalSentence)
    complete.mutate(
      {
        session_id: sessionId,
        duration_ms: shownAt.current !== null ? Math.max(0, Date.now() - shownAt.current) : null,
        guess,
        exercise_results: results,
        personal_sentence: personalSentence,
      },
      { onSuccess: () => setPhase('done') },
    )
  }

  if (start.isPending || start.isIdle || alreadyDone) {
    return <p className="muted">{t('discovery.starting')}</p>
  }
  if (start.isError) {
    const code = codeOf(start.error)
    return (
      <>
        <StepHeading>{t('steps.new_item')}</StepHeading>
        <ErrorText error={start.error} />
        {code === 'sheet_required' && (
          <>
            <p>
              <Link to={`/library/items/${itemId}`}>
                {t('discovery.error.writeSheet', { term: newItem.term })}
              </Link>
            </p>
            <p className="muted">{t('discovery.error.blocked')}</p>
          </>
        )}
        <div className="button-row">
          {code === null && (
            <button type="button" className="button" onClick={begin}>
              {t('discovery.error.retry')}
            </button>
          )}
          <button type="button" className="button button--primary" onClick={onNext}>
            {t('discovery.error.continue')}
          </button>
        </div>
      </>
    )
  }

  const started = start.data
  switch (phase) {
    case 'read':
      return (
        <ReadAndGuess
          start={started}
          onGuess={(value) => {
            setGuess(value)
            setPhase('sheet')
          }}
        />
      )
    case 'sheet':
      return (
        <SheetStep
          itemId={itemId}
          term={started.term}
          guess={guess}
          onContinue={() => setPhase('exercises')}
        />
      )
    case 'exercises':
      return <ExercisesStep itemId={itemId} onDone={onExercisesDone} />
    case 'repetition':
      return (
        <RepetitionStep
          text={started.sentence?.text ?? started.term}
          onDone={() => setPhase('personal')}
        />
      )
    case 'personal':
      return (
        <>
          <PersonalSentenceStep
            term={started.term}
            onFinish={finish}
            sending={complete.isPending}
            error={complete.isError ? complete.error : null}
          />
          {/* Refused for good (deck paused, term moved...): the session goes on without it. */}
          {codeOf(complete.error) !== null && (
            <button type="button" className="button" onClick={onNext}>
              {t('discovery.error.continue')}
            </button>
          )}
        </>
      )
    case 'done':
      return complete.data !== undefined ? (
        <Done result={complete.data} term={started.term} sentence={personal} onNext={onNext} />
      ) : null
  }
}
