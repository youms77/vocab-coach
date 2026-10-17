import type { TFunction } from 'i18next'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type { ItemStatus } from '../../api/library'
import {
  type ExerciseType,
  type Rating,
  type RecordResult,
  useGrade,
  useRecordReview,
  useRevealReview,
} from '../../api/reviews'
import type { ReviewStep } from '../../api/session'
import { useSpeech } from '../../speech/useSpeech'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'
import { RatingButtons } from './RatingButtons'
import { initialReviewState, type ReviewAction, reviewReducer, revealedResult } from './reviewMachine'
import { ReviewPrompt } from './ReviewPrompt'
import { ReviewResult } from './ReviewResult'
import { promptOptions, replayText, termOf, text } from './stepText'
import { type ReviewShortcutHandlers, useReviewShortcuts } from './useReviewShortcuts'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

/** Refusals that rating again would not fix: the card is not reviewable now (D-108). */
const CONTINUE_CODES = ['not_due', 'review_not_allowed']
/** The session itself is gone: the page handles these (D-114). */
const SESSION_CODES = ['session_closed', 'session_not_found']

function announcement(t: TFunction, language: string, record: RecordResult, term: string | null) {
  const due = new Date(record.due_after)
  const sameDay = due.toDateString() === new Date().toDateString()
  const saved = sameDay
    ? t('review.saved.today', {
        time: new Intl.DateTimeFormat(language, { timeStyle: 'short' }).format(due),
      })
    : t('review.saved.later', {
        date: new Intl.DateTimeFormat(language, { dateStyle: 'long' }).format(due),
      })
  if (!record.item_status_changed) return saved
  const status = t(`library.status.${record.item_status as ItemStatus}`).toLocaleLowerCase(language)
  const changed =
    term !== null ? t('review.saved.status', { term, status }) : t('review.saved.statusNoTerm', { status })
  return `${saved} ${changed}`
}

function KeyHints({ items }: { items: [string, string][] }) {
  const { t } = useTranslation()
  if (items.length === 0) return null
  return (
    <p className="key-hints">
      <span className="visually-hidden">{t('review.keys.label')}: </span>
      {items.map(([keys, action]) => (
        <span key={keys} className="key-hints__item">
          {keys.split('|').map((key, i) => (
            <span key={key}>
              {i > 0 && ' / '}
              <kbd>{key}</kbd>
            </span>
          ))}{' '}
          {action}
        </span>
      ))}
    </p>
  )
}

/**
 * One review card, from the prompt to the final rating (D-120). Keyed by card and repetition
 * count in the session page, so every card starts fresh. The answer is attempted before anything
 * is revealed: the solution only comes from `grade` (typed or chosen answers, even empty) or
 * `reveal` (self-graded types).
 */
export function ReviewPlayer({
  sessionId,
  review,
  onRecorded,
  onCardChanged,
  onNext,
  onSessionError,
}: {
  sessionId: number
  review: ReviewStep
  /** Saved: the page announces `message` and asks for the next step. */
  onRecorded: (message: string) => void
  /** Already rated elsewhere (another tab): the page says so and asks for the next step. */
  onCardChanged: () => void
  /** Ask the backend for the current step again. */
  onNext: () => void
  onSessionError: (error: unknown) => void
}) {
  const { t, i18n } = useTranslation()
  const grade = useGrade()
  const reveal = useRevealReview()
  const record = useRecordReview()
  const speech = useSpeech()

  // The state lives in a ref too, so a second key press before React re-renders is refused
  // synchronously (one `grade` and one `POST /reviews` per card).
  const [state, setState] = useState(initialReviewState)
  const current = useRef(initialReviewState)
  const transition = useCallback((action: ReviewAction) => {
    const next = reviewReducer(current.current, action)
    if (next === current.current) return false
    current.current = next
    setState(next)
    return true
  }, [])

  // The response time runs from the prompt being shown to the answer (D-121).
  const shownAt = useRef(0)
  useEffect(() => {
    shownAt.current = performance.now()
  }, [])
  const elapsed = () => Math.max(0, Math.round(performance.now() - shownAt.current))

  const restart = useCallback(() => {
    current.current = initialReviewState
    setState(initialReviewState)
    shownAt.current = performance.now()
    grade.reset()
    reveal.reset()
    record.reset()
    onNext()
  }, [grade, reveal, record, onNext])

  const failed = (error: unknown) => {
    if (SESSION_CODES.includes(codeOf(error) ?? '')) onSessionError(error)
  }

  function submitText() {
    const answer = current.current.answer
    if (!transition({ type: 'submit', choiceIndex: null, responseTimeMs: elapsed() })) return
    gradeWith(answer.trim() === '' ? null : answer, null)
  }

  function choose(index: number | null) {
    if (index !== null && index >= optionCount) return
    if (!transition({ type: 'submit', choiceIndex: index, responseTimeMs: elapsed() })) return
    gradeWith(null, index)
  }

  function gradeWith(answer: string | null, choiceIndex: number | null) {
    grade.mutate(
      {
        card_id: review.card_id,
        exercise_type: review.exercise_type,
        exercise_template_id: review.exercise_template_id,
        answer,
        choice_index: choiceIndex,
        response_time_ms: current.current.responseTimeMs ?? 0,
      },
      {
        onSuccess: (result) => transition({ type: 'checked', result }),
        onError: (error) => {
          transition({ type: 'checkFailed', error })
          failed(error)
        },
      },
    )
  }

  function showAnswer() {
    if (!transition({ type: 'submit', choiceIndex: null, responseTimeMs: elapsed() })) return
    reveal.mutate(
      {
        card_id: review.card_id,
        exercise_type: review.exercise_type,
        exercise_template_id: review.exercise_template_id,
      },
      {
        onSuccess: (revealed) => transition({ type: 'checked', result: revealedResult(revealed) }),
        onError: (error) => {
          transition({ type: 'checkFailed', error })
          failed(error)
        },
      },
    )
  }

  function rate(rating: Rating) {
    const before = current.current
    if (!transition({ type: 'rate', rating })) return
    const answer = review.input === 'text' && before.answer.trim() !== '' ? before.answer : null
    record.mutate(
      {
        card_id: review.card_id,
        session_id: sessionId,
        exercise_type: review.exercise_type,
        exercise_template_id: review.exercise_template_id,
        answer,
        choice_index: before.choiceIndex,
        response_time_ms: before.responseTimeMs ?? 0,
        final_rating: rating,
        expected_reps: review.expected_reps,
      },
      {
        onSuccess: (saved) => {
          transition({ type: 'recorded' })
          onRecorded(announcement(t, i18n.language, saved, termOf(review, before.result)))
        },
        onError: (error) => {
          if (codeOf(error) === 'card_changed') {
            onCardChanged()
            return
          }
          transition({ type: 'recordFailed', error })
          failed(error)
        },
      },
    )
  }

  // Focus: the card's title on a new card (StepHeading), the result once the answer is shown.
  const resultRef = useRef<HTMLDivElement>(null)
  const answered = state.result !== null
  useEffect(() => {
    if (answered) resultRef.current?.focus()
  }, [answered])

  // Listening: try to speak the sentence as soon as a voice is available; silent on failure.
  const sentenceToHear =
    review.exercise_type === 'listening_comprehension' ? text(review.prompt.sentence) : null
  const autoplayed = useRef(false)
  const canSpeak = speech.voice !== null
  const { speak } = speech
  useEffect(() => {
    if (sentenceToHear === null || autoplayed.current || !canSpeak) return
    autoplayed.current = true
    try {
      speak(sentenceToHear)
    } catch {
      // Autoplay may be refused by the browser: the "Listen" button stays.
    }
  }, [sentenceToHear, canSpeak, speak])

  const optionCount = promptOptions(review).length
  const audio = replayText(review, state.result)
  const proposed = (state.result?.proposed_rating ?? null) as Rating | null
  const errorCode = codeOf(state.error)
  const blocked = errorCode !== null && [...CONTINUE_CODES, 'exercise_mismatch'].includes(errorCode)

  const handlers: ReviewShortcutHandlers = {}
  const hints: [string, string][] = []
  if (!blocked && state.phase === 'answering') {
    if (review.input === 'choice') {
      handlers.choose = choose
      hints.push([`1–${optionCount}`, t('review.keys.choose')])
    } else if (review.input === 'none') {
      handlers.reveal = showAnswer
      hints.push([`${t('review.keys.space')}|${t('review.keys.enter')}`, t('review.keys.show')])
    } else {
      hints.push([t('review.keys.enter'), t('review.keys.check')])
      if (review.exercise_type === 'sentence_production') {
        hints.push([`${t('review.keys.shift')}+${t('review.keys.enter')}`, t('review.keys.newLine')])
      }
    }
  }
  if (!blocked && state.phase === 'answered') {
    handlers.rate = rate
    hints.push(['1–4', t('review.keys.rate')])
    if (proposed !== null) {
      handlers.acceptProposed = () => rate(proposed)
      hints.push([t('review.keys.enter'), t('review.keys.accept')])
    }
  }
  if (audio !== null) {
    handlers.replay = (slow) => speak(audio, { slow })
    hints.push(['R', t('review.keys.replay')], [`${t('review.keys.shift')}+R`, t('review.keys.replaySlow')])
  }
  useReviewShortcuts(handlers)

  return (
    <div className="review">
      <StepHeading>{t(`review.types.${review.exercise_type as ExerciseType}`)}</StepHeading>
      <p className="muted review__direction">
        {review.direction === 'receptive' ? t('review.receptive') : t('review.productive')}
      </p>

      <ReviewPrompt
        review={review}
        state={state}
        onType={(answer) => transition({ type: 'type', answer })}
        onSubmitText={submitText}
        onChoose={choose}
        onReveal={showAnswer}
      />
      {state.phase === 'answering' && state.error !== null && !blocked && <ErrorText error={state.error} />}

      {state.result !== null && (
        <div ref={resultRef} tabIndex={-1} className="review-result" aria-label={t('review.result.label')} role="region">
          <ReviewResult review={review} result={state.result} answer={state.answer} />
        </div>
      )}

      {blocked ? (
        <div className="review-blocked">
          <ErrorText error={state.error} />
          <button type="button" className="button button--primary" onClick={restart}>
            {errorCode === 'exercise_mismatch' ? t('session.retry') : t('discovery.error.continue')}
          </button>
        </div>
      ) : (
        state.result !== null && (
          <>
            <RatingButtons
              proposed={proposed}
              selfGraded={review.self_graded}
              pending={state.phase === 'recording' || state.phase === 'recorded' ? state.rating : null}
              onRate={rate}
            />
            {state.phase === 'answered' && state.error !== null && <ErrorText error={state.error} />}
            {state.phase === 'recorded' && <p className="muted">{t('session.loading')}</p>}
          </>
        )
      )}

      <KeyHints items={hints} />
    </div>
  )
}
