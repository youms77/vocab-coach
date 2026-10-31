import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type DiscoveryExercise, useDiscoveryExercises } from '../../api/discovery'
import { useSheet } from '../../api/enrichment'
import { type GradeResult as Result, type Outcome, useGrade } from '../../api/reviews'
import { SheetView } from '../library/SheetView'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'
import { GradeResult } from './GradeResult'
import { Notice } from '../../components/Notice'

const ORDER = ['typed_recall', 'gap_fill'] as const

export interface ExerciseOutcome {
  exercise_type: string
  outcome: Outcome
}

const ordered = (exercises: DiscoveryExercise[]) =>
  ORDER.flatMap((type) => exercises.filter((e) => e.exercise_type === type))

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

/**
 * One immediate exercise. It never receives the sheet or the solution: the solution comes only
 * from the answer of `grade`, sent even with an empty field (outcome `empty`).
 */
function Exercise({
  itemId,
  exercise,
  onGraded,
}: {
  itemId: number
  exercise: DiscoveryExercise
  onGraded: (result: Result) => void
}) {
  const { t } = useTranslation()
  const grade = useGrade()
  const [answer, setAnswer] = useState('')
  const [shownAt] = useState(() => Date.now())
  const id = `exercise-${exercise.exercise_template_id}`
  const prompt = exercise.prompt

  function submit(event: FormEvent) {
    event.preventDefault()
    if (grade.isPending || grade.isSuccess) return
    grade.mutate(
      {
        item_id: itemId,
        exercise_type: exercise.exercise_type,
        exercise_template_id: exercise.exercise_template_id,
        answer: answer.trim() === '' ? null : answer,
        choice_index: null,
        response_time_ms: Math.max(0, Date.now() - shownAt),
      },
      { onSuccess: onGraded },
    )
  }

  return (
    <form className="discovery-form" onSubmit={submit}>
      <h3>{t(`discovery.exercises.${exercise.exercise_type}`)}</h3>
      {exercise.exercise_type === 'typed_recall' ? (
        <ul className="exercise-cues">
          {text(prompt.cue_fr) !== null && (
            <li lang="fr">{t('discovery.exercises.cueFr', { cue: text(prompt.cue_fr) })}</li>
          )}
          {text(prompt.cue_definition) !== null && (
            <li>{t('discovery.exercises.cueDefinition', { cue: text(prompt.cue_definition) })}</li>
          )}
        </ul>
      ) : (
        <p className="exercise-gap" lang="en">
          {text(prompt.sentence)}
        </p>
      )}
      <div className="field">
        <label htmlFor={id}>
          {exercise.exercise_type === 'gap_fill'
            ? t('discovery.exercises.gapLabel')
            : t('discovery.exercises.answerLabel')}
        </label>
        <input
          id={id}
          lang="en"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          maxLength={2000}
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          readOnly={grade.isSuccess}
        />
      </div>
      {!grade.isSuccess && (
        <button type="submit" className="button button--primary" disabled={grade.isPending}>
          {t('discovery.exercises.check')}
        </button>
      )}
      {grade.isError && <ErrorText error={grade.error} />}
    </form>
  )
}

/**
 * Step 4a: typed recall, then gap-fill, when the term has them (a missing one is skipped without
 * a message). The sheet stays folded during an exercise and can be reopened after its answer.
 */
export function ExercisesStep({
  itemId,
  onDone,
}: {
  itemId: number
  onDone: (results: ExerciseOutcome[]) => void
}) {
  const { t } = useTranslation()
  const exercises = useDiscoveryExercises(itemId, true)
  const [index, setIndex] = useState(0)
  const [results, setResults] = useState<ExerciseOutcome[]>([])
  const [graded, setGraded] = useState<Result | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  // Read from the cache only once the current exercise is answered.
  const sheet = useSheet(itemId, graded !== null && sheetOpen)

  // No exercise for this term: straight to the spoken repetition, without a message.
  const skipped = useRef(false)
  const none = exercises.isSuccess && ordered(exercises.data).length === 0
  useEffect(() => {
    if (none && !skipped.current) {
      skipped.current = true
      onDone([])
    }
  }, [none, onDone])

  if (exercises.isPending) {
    return (
      <>
        <StepHeading>{t('discovery.exercises.title')}</StepHeading>
        <p className="muted">{t('discovery.exercises.loading')}</p>
      </>
    )
  }
  if (exercises.isError) {
    return (
      <>
        <StepHeading>{t('discovery.exercises.title')}</StepHeading>
        <Notice tone="danger">{t('discovery.exercises.loadError')}</Notice>
        <ErrorText error={exercises.error} />
        <button type="button" className="button" onClick={() => onDone([])}>
          {t('discovery.exercises.skip')}
        </button>
      </>
    )
  }

  const list = ordered(exercises.data)
  if (list.length === 0) return null
  const current = list[Math.min(index, list.length - 1)]
  const last = index >= list.length - 1

  function nextExercise() {
    if (last) {
      onDone(results)
      return
    }
    setIndex(index + 1)
    setGraded(null)
    setSheetOpen(false)
  }

  return (
    <>
      <StepHeading>{t('discovery.exercises.title')}</StepHeading>
      <p className="muted">
        {t('discovery.exercises.counter', { index: index + 1, total: list.length })}
      </p>
      <Exercise
        key={current.exercise_template_id}
        itemId={itemId}
        exercise={current}
        onGraded={(result) => {
          setGraded(result)
          if (result.outcome !== null) {
            setResults([...results, { exercise_type: current.exercise_type, outcome: result.outcome }])
          }
        }}
      />
      {graded !== null && (
        <>
          <GradeResult result={graded} />
          <div className="button-row">
            <button type="button" className="button button--primary" onClick={nextExercise}>
              {last ? t('discovery.exercises.done') : t('discovery.exercises.next')}
            </button>
            <button
              type="button"
              className="button"
              aria-expanded={sheetOpen}
              onClick={() => setSheetOpen(!sheetOpen)}
            >
              {sheetOpen ? t('discovery.exercises.hideSheet') : t('discovery.exercises.showSheet')}
            </button>
          </div>
          {sheetOpen && sheet.data != null && <SheetView sheet={sheet.data.content} />}
        </>
      )}
    </>
  )
}
