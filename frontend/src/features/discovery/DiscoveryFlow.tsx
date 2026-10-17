import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '../../api/client'
import { type CompleteResult, useCompleteDiscovery, useStartDiscovery } from '../../api/discovery'
import type { NewItemStep } from '../../api/session'
import { formatDateTime } from '../session/format'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'
import { type ExerciseOutcome, ExercisesStep } from './ExercisesStep'
import { PersonalSentenceStep, RepetitionStep } from './ProductionSteps'
import { ReadAndGuess } from './ReadAndGuess'
import { SheetStep } from './SheetStep'

type Phase = 'read' | 'sheet' | 'exercises' | 'repetition' | 'personal' | 'done'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

function Done({ result, term, onNext }: { result: CompleteResult; term: string; onNext: () => void }) {
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
        <Done result={complete.data} term={started.term} onNext={onNext} />
      ) : null
  }
}
