import type { TFunction } from 'i18next'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '../../api/client'
import type { ItemStatus } from '../../api/library'
import {
  checkProduction,
  type ExerciseType,
  type Rating,
  type RecordResult,
  useGrade,
  useRecordReview,
  useRevealReview,
} from '../../api/reviews'
import type { ReviewStep } from '../../api/session'
import { reviewAnswer } from '../../api/speech'
import { KeyHints } from '../../components/KeyHints'
import { unsupportedReason } from '../../speech/recorder'
import { useClipSender } from '../../speech/useClipSender'
import { type Clip, useRecorder } from '../../speech/useRecorder'
import { useSpeech } from '../../speech/useSpeech'
import { StepHeading } from '../session/StepHeading'
import { ErrorText } from '../settings/ErrorText'
import { RatingButtons } from './RatingButtons'
import {
  type CheckNotice,
  initialReviewState,
  type ReviewAction,
  type ReviewState,
  reviewReducer,
  revealedResult,
} from './reviewMachine'
import { ReviewPrompt } from './ReviewPrompt'
import { ReviewResult } from './ReviewResult'
import { SpokenAnswer } from './SpokenAnswer'
import { promptOptions, replayText, termOf, text } from './stepText'
import { type ReviewShortcutHandlers, useReviewShortcuts } from './useReviewShortcuts'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

/** Refusals that rating again would not fix: the card is not reviewable now (D-108). */
const CONTINUE_CODES = ['not_due', 'review_not_allowed']
/** The session itself is gone: the page handles these (D-114). */
const SESSION_CODES = ['session_closed', 'session_not_found']
/** Refusals of the AI check that a self-graded fallback would not fix: handled as for `grade`. */
const CHECK_BLOCKING_CODES = [...CONTINUE_CODES, ...SESSION_CODES, 'exercise_mismatch']
/** The server refused the recording itself: record again (nothing was stored, D-183). */
const AUDIO_CODES = [
  'audio_too_short',
  'audio_too_long',
  'audio_empty',
  'unsupported_audio',
  'audio_too_large',
]
/** After this many seconds of waiting for the AI, the user may rate the sentence themselves (D-142). */
export const SKIP_AFTER_SECONDS = 5

function announcement(
  t: TFunction,
  language: string,
  record: RecordResult,
  term: string | null,
): ReactNode {
  const due = new Date(record.due_after)
  const sameDay = due.toDateString() === new Date().toDateString()
  const saved = sameDay
    ? t('review.saved.today', {
        time: new Intl.DateTimeFormat(language, { timeStyle: 'short' }).format(due),
      })
    : t('review.saved.later', {
        date: new Intl.DateTimeFormat(language, { dateStyle: 'long' }).format(due),
      })
  let message = saved
  if (record.item_status_changed) {
    const status = t(`library.status.${record.item_status as ItemStatus}`).toLocaleLowerCase(language)
    const changed =
      term !== null ? t('review.saved.status', { term, status }) : t('review.saved.statusNoTerm', { status })
    message = `${saved} ${changed}`
  }
  if (record.error_event_id === null) return message
  // A lexical confusion in a typed answer was logged as an error (M5.a1): say so, politely.
  return (
    <>
      {message} {t('review.errorLogged.text')}{' '}
      <Link to={`/errors/${record.error_event_id}`}>{t('review.errorLogged.link')}</Link>
    </>
  )
}

/**
 * The wait for the AI check: a counter, and after a few seconds a way out (D-142). A spoken
 * answer has two AI steps and says so (D-206).
 */
function CheckingPanel({ onSkip, spoken = false }: { onSkip: () => void; spoken?: boolean }) {
  const { t } = useTranslation()
  // Mounted when the wait begins: it counts its own seconds.
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((n) => n + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="review-checking">
      {/* The counter ticks every second: it is hidden from screen readers, the status is not. */}
      <p className="visually-hidden" role="status">
        {spoken ? t('review.spoken.checking') : t('review.aiCheck.checking')}
      </p>
      <p aria-hidden="true">
        <span className="spinner" />{' '}
        {spoken
          ? t('review.spoken.elapsed', { seconds })
          : t('review.aiCheck.elapsed', { seconds })}
      </p>
      <p className="muted">{spoken ? t('review.spoken.twoSteps') : t('review.aiCheck.hint')}</p>
      {seconds >= SKIP_AFTER_SECONDS && (
        <button type="button" className="button" onClick={onSkip}>
          {spoken ? t('review.spoken.skip') : t('review.aiCheck.skip')}
        </button>
      )}
    </div>
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
  onRecorded: (message: ReactNode) => void
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

  // The microphone of a spoken answer (D-206). The player owns the hook: Space and Enter drive it.
  const recorder = useRecorder('spoken_answer')
  const spokenCard = review.exercise_type === 'spoken_answer'

  // The AI check of a typed sentence or a spoken answer (D-129, D-142): how to stop waiting for it.
  const checkAbort = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      checkAbort.current?.abort()
    }
  }, [])
  // Shown when the server did not recognise the checked sentence and the rating went without it.
  const [unlinked, setUnlinked] = useState(false)

  // The response time runs from the prompt being shown to the answer (D-121).
  const shownAt = useRef(0)
  useEffect(() => {
    shownAt.current = performance.now()
  }, [])
  const elapsed = () => Math.max(0, Math.round(performance.now() - shownAt.current))

  const restart = useCallback(() => {
    current.current = initialReviewState
    setState(initialReviewState)
    setUnlinked(false)
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
    // A typed sentence is checked by the AI; an empty one stays on the self-graded path (M4.c).
    if (
      review.exercise_type === 'sentence_production' &&
      review.exercise_template_id !== null &&
      answer.trim() !== ''
    ) {
      checkSentence(answer, review.exercise_template_id)
      return
    }
    if (!transition({ type: 'submit', choiceIndex: null, responseTimeMs: elapsed() })) return
    gradeWith(answer.trim() === '' ? null : answer, null)
  }

  /** The AI's answer, or the way back to the self-graded path of M4.c (`grade` writes nothing). */
  function checkSentence(answer: string, templateId: number) {
    if (!transition({ type: 'submitProduction', responseTimeMs: elapsed() })) return
    const controller = new AbortController()
    checkAbort.current = controller
    checkProduction(
      {
        card_id: review.card_id,
        session_id: sessionId,
        exercise_template_id: templateId,
        answer,
        response_time_ms: current.current.responseTimeMs ?? 0,
      },
      controller.signal,
    ).then(
      (checked) => {
        if (!mounted.current) return
        if (checked.status === 'ok') {
          transition({ type: 'productionChecked', check: checked })
        } else if (
          transition({
            type: 'productionUnchecked',
            notice:
              checked.status === 'incomplete'
                ? { kind: 'incomplete' }
                : { kind: 'unavailable', reason: checked.reason },
          })
        ) {
          gradeWith(answer, null)
        }
      },
      (error: unknown) => {
        // After "Skip the check" the phase has moved on: a late answer or the abort changes nothing.
        if (!mounted.current || current.current.phase !== 'checking_production') return
        if (CHECK_BLOCKING_CODES.includes(codeOf(error) ?? '')) {
          transition({ type: 'checkFailed', error })
          failed(error)
        } else if (transition({ type: 'productionUnchecked', notice: { kind: 'failed', error } })) {
          gradeWith(answer, null)
        }
      },
    )
  }

  /** Stop waiting. The sentence stays recorded on the server; the user rates it themselves. */
  function skipCheck() {
    const answer = current.current.answer
    if (!transition({ type: 'productionUnchecked', notice: { kind: 'skipped' } })) return
    checkAbort.current?.abort()
    gradeWith(answer, null)
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
    revealSolution()
  }

  /** The solution of a self-graded card; the phase is `checking` already. */
  function revealSolution() {
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

  /** Space, or the Start button: opens the microphone once per take (the reducer is the guard). */
  function startCapture() {
    if (!transition({ type: 'startCapture' })) return
    recorder.start()
  }

  function toggleRecording() {
    const phase = current.current.phase
    if (phase === 'answering') startCapture()
    else if (phase === 'capturing') recorder.stop()
  }

  /** Enter: one upload per take (the second press is refused by the reducer). */
  function sendTake() {
    const clip = recorder.clip
    if (clip === null || recorder.tooShort) return
    sender.send(clip)
  }

  /** The recording to `review-answer`: transcription and correction, up to about 90 s (D-183). */
  function sendSpoken(clip: Clip) {
    const templateId = review.exercise_template_id
    if (templateId === null) return
    if (!transition({ type: 'submitSpoken' })) return
    const controller = new AbortController()
    checkAbort.current = controller
    reviewAnswer(
      {
        blob: clip.blob,
        card_id: review.card_id,
        session_id: sessionId,
        exercise_template_id: templateId,
        durationS: clip.durationS,
        response_time_ms: current.current.responseTimeMs ?? 0,
      },
      controller.signal,
    ).then(
      (answer) => {
        // After "Skip the check" the phase has moved on: a late answer changes nothing.
        if (mounted.current) transition({ type: 'spokenChecked', answer })
      },
      (error: unknown) => {
        if (!mounted.current || current.current.phase !== 'checking_spoken') return
        const code = codeOf(error) ?? ''
        if (AUDIO_CODES.includes(code)) {
          // Nothing was stored: the same take can be sent again, or recorded again.
          transition({ type: 'spokenFailed', error })
        } else if (CHECK_BLOCKING_CODES.includes(code)) {
          recorder.reset()
          transition({ type: 'checkFailed', error })
          failed(error)
        } else {
          fallBackToReveal({ kind: 'spoken_failed', error })
        }
      },
    )
  }

  /** The self-graded path of M4.c for a spoken card; a recording, if any, is not rated. */
  function fallBackToReveal(notice: CheckNotice | null) {
    if (!transition({ type: 'spokenFallback', notice, responseTimeMs: elapsed() })) return
    recorder.reset()
    checkAbort.current?.abort()
    revealSolution()
  }

  const sender = useClipSender(sendSpoken)

  function rate(rating: Rating) {
    const before = current.current
    if (!transition({ type: 'rate', rating })) return
    send(rating, before, before.productionAttemptId)
  }

  /** `POST /reviews`; `productionAttemptId` is the AI-checked sentence, when there is one (D-129). */
  function send(rating: Rating, before: ReviewState, productionAttemptId: number | null) {
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
        ...(productionAttemptId !== null ? { production_attempt_id: productionAttemptId } : {}),
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
          if (codeOf(error) === 'production_mismatch' && productionAttemptId !== null) {
            // The server does not recognise the checked sentence: send the rating once without it.
            transition({ type: 'productionDropped' })
            setUnlinked(true)
            send(rating, before, null)
            return
          }
          transition({ type: 'recordFailed', error })
          failed(error)
        },
      },
    )
  }

  // The recorder and the phase tell the same story: the machine follows the hook (D-206).
  const recording = recorder.status
  const clip = recorder.clip
  const phase = state.phase
  useEffect(() => {
    if (!spokenCard) return
    if (recording === 'stopped' && clip !== null) {
      // The answer ends with the recording: that is the response time (D-121).
      transition({ type: 'captured', responseTimeMs: elapsed() })
    } else if (recording === 'idle' || recording === 'error') {
      // Cancelled, "Record again", refused or absent microphone: back to the start.
      transition({ type: 'discardCapture' })
    }
  }, [spokenCard, recording, clip, phase, transition])

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
  // The microphone is refused, absent or unsupported: "Answer without recording" is the way on.
  const unsupported = unsupportedReason() !== null
  const micFailed = recorder.reason !== null || unsupported
  // Space and Enter only drive a recorder that can exist (a template, a browser that records).
  const hasRecorder = review.exercise_template_id !== null && !unsupported
  // The recorder as the spoken answer sees it: the Start button goes through the machine.
  const machineRecorder = { ...recorder, start: startCapture }

  const handlers: ReviewShortcutHandlers = {}
  const hints: [string, string][] = []
  if (!blocked && state.phase === 'answering') {
    if (review.input === 'choice') {
      handlers.choose = choose
      hints.push([`1–${optionCount}`, t('review.keys.choose')])
    } else if (spokenCard) {
      if (hasRecorder) {
        handlers.record = toggleRecording
        hints.push([t('review.keys.space'), t('review.keys.record')])
      }
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
  if (!blocked && spokenCard && hasRecorder) {
    if (state.phase === 'capturing') {
      handlers.record = toggleRecording
      hints.push([t('review.keys.space'), t('review.keys.stop')])
    }
    if (state.phase === 'captured') {
      handlers.send = sendTake
      hints.push([t('review.keys.enter'), t('review.keys.send')])
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
      {state.phase === 'checking_production' && <CheckingPanel onSkip={skipCheck} />}
      {spokenCard && !blocked && state.result === null && (
        <SpokenAnswer
          review={review}
          state={state}
          recorder={machineRecorder}
          tooLarge={sender.tooLarge}
          micFailed={micFailed}
          onSend={sender.send}
          onAgain={sender.clear}
          onDecline={() => fallBackToReveal(null)}
        />
      )}
      {state.phase === 'checking_spoken' && (
        <CheckingPanel spoken onSkip={() => fallBackToReveal({ kind: 'spoken_skipped' })} />
      )}

      {state.result !== null && (
        <div
          ref={resultRef}
          tabIndex={-1}
          className="review-result"
          role="region"
          aria-label={t('review.result.label')}
        >
          <ReviewResult
            review={review}
            result={state.result}
            answer={state.answer}
            check={state.check}
            spoken={state.spoken}
            notice={state.notice}
          />
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
            {unlinked && <p className="muted">{t('errors.production_mismatch')}</p>}
            {state.phase === 'recorded' && <p className="muted">{t('session.loading')}</p>}
          </>
        )
      )}

      <KeyHints items={hints} />
    </div>
  )
}
