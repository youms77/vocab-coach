import { type FormEvent, useCallback, useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { type DrillItem, MAX_ANSWER_CHARS, useAnswerItem } from '../../api/drills'
import { KeyHints } from '../../components/KeyHints'
import { ErrorText } from '../settings/ErrorText'
import { DrillResult } from './DrillResult'
import {
  answerBody,
  type Attempt,
  type DrillItemAction,
  type DrillItemState,
  drillItemReducer,
  initialItemState,
} from './drillMachine'
import { splitGap } from './drillRules'
import { useDrillShortcuts } from './useDrillShortcuts'

const codeOf = (error: unknown) => (error instanceof ApiError ? error.code : null)

/** Refusals that answering again would not fix: the item or the drill is gone, or does not match. */
const BLOCKING_CODES = ['exercise_mismatch', 'item_not_found', 'drill_not_found']

/** The sentence with its gap marked by a line, and the word "blank" for screen readers. */
function Sentence({ sentence, id }: { sentence: string; id: string }) {
  const { t } = useTranslation()
  const parts = splitGap(sentence)
  return (
    <p id={id} className="review-sentence drill-sentence" lang="en">
      {parts === null ? (
        sentence
      ) : (
        <>
          {parts[0]}
          <span className="drill-gap" aria-hidden="true" />
          <span className="visually-hidden">
            {t('drills.player.blank')}
          </span>
          {parts[1]}
        </>
      )}
    </p>
  )
}

/** Numbered options, in the order received; after the answer the right one and a wrong choice are marked. */
function Options({
  item,
  state,
  onChoose,
}: {
  item: DrillItem
  state: DrillItemState
  onChoose: (index: number | null) => void
}) {
  const { t } = useTranslation()
  const labelId = useId()
  const answering = state.phase === 'answering'
  const chosen = state.attempt?.kind === 'choice' ? state.attempt.index : null
  const correct = state.result?.correct_index ?? null
  return (
    <div className="review-options-block">
      <p id={labelId} className="review-options-label">
        {t('drills.player.choices')}
      </p>
      <div role="group" aria-labelledby={labelId} className="review-options">
        {(item.options ?? []).map((option, index) => {
          const isCorrect = correct === index
          const isWrongChoice = state.result !== null && chosen === index && !isCorrect
          const marks = ['review-option']
          if (isCorrect) marks.push('review-option--correct')
          if (isWrongChoice) marks.push('review-option--wrong')
          return (
            <button
              key={index}
              type="button"
              className={marks.join(' ')}
              onClick={() => onChoose(index)}
              disabled={!answering}
              aria-pressed={chosen === index}
            >
              <kbd className="review-option__key">{index + 1}</kbd>{' '}
              <span lang="en" className="review-option__text">
                {option}
              </span>
              {isCorrect && (
                <span className="review-option__mark"> ✓ {t('drills.result.rightOption')}</span>
              )}
              {isWrongChoice && (
                <span className="review-option__mark"> ✗ {t('drills.result.yourOption')}</span>
              )}
            </button>
          )
        })}
      </div>
      {answering && (
        <button type="button" className="button" onClick={() => onChoose(null)}>
          {t('drills.player.dontKnow')}
        </button>
      )}
    </div>
  )
}

/** A typed answer. Enter checks it; an empty field is not sent by Enter (use "I don't know"). */
function TypedAnswer({
  state,
  describedBy,
  autoFocus,
  onType,
  onSubmit,
  onDontKnow,
}: {
  state: DrillItemState
  describedBy: string
  autoFocus: boolean
  onType: (answer: string) => void
  onSubmit: () => void
  onDontKnow: () => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const answering = state.phase === 'answering'
  useEffect(() => {
    if (autoFocus) input.current?.focus()
  }, [autoFocus])

  function submit(event: FormEvent) {
    event.preventDefault()
    if (answering && state.answer.trim() !== '') onSubmit()
  }

  return (
    <form className="review-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor={id}>{t('drills.player.answer')}</label>
        <input
          ref={input}
          id={id}
          lang="en"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          maxLength={MAX_ANSWER_CHARS}
          value={state.answer}
          readOnly={!answering}
          aria-describedby={describedBy}
          onChange={(event) => onType(event.target.value)}
        />
      </div>
      {answering && (
        <div className="drill-actions">
          <button type="submit" className="button button--primary" disabled={state.answer.trim() === ''}>
            {t('drills.player.check')}
          </button>
          <button type="button" className="button" onClick={onDontKnow}>
            {t('drills.player.dontKnow')}
          </button>
        </div>
      )}
    </form>
  )
}

/**
 * One item of a drill, from the sentence to the result (D-120 applied to drills). Keyed by drill,
 * item and reload in the page, so every item starts fresh. The solution only exists in the
 * server's answer to the attempt, so nothing of it is in the page before (D-103, D-136).
 */
export function DrillItemPlayer({
  drillId,
  item,
  total,
  isLast,
  focusInput,
  onNext,
  onReload,
}: {
  drillId: number
  item: DrillItem
  total: number
  isLast: boolean
  /** Move the focus to the field: the user is working through the items with the keyboard. */
  focusInput: boolean
  onNext: () => void
  /** Load the drill again and continue from its first item not answered. */
  onReload: () => void
}) {
  const { t } = useTranslation()
  const answer = useAnswerItem(drillId)
  const sentenceId = useId()
  const titleId = useId()

  // The state lives in a ref too, so a second Enter before React re-renders is refused
  // synchronously: one answer per item.
  const [state, setState] = useState(initialItemState)
  const current = useRef(initialItemState)
  const transition = useCallback((action: DrillItemAction) => {
    const next = drillItemReducer(current.current, action)
    if (next === current.current) return false
    current.current = next
    setState(next)
    return true
  }, [])

  // The response time runs from the item being shown to the answer (D-121).
  const shownAt = useRef(0)
  useEffect(() => {
    shownAt.current = performance.now()
  }, [])
  const elapsed = () => Math.max(0, Math.round(performance.now() - shownAt.current))

  function send(attempt: Attempt) {
    if (!transition({ type: 'submit', attempt, responseTimeMs: elapsed() })) return
    answer.mutate(
      { index: item.index, body: answerBody(attempt, current.current.responseTimeMs ?? 0) },
      {
        onSuccess: (saved) =>
          transition({ type: 'answered', result: saved.result, errorEventId: saved.error_event_id }),
        onError: (error) => {
          transition({ type: 'failed', error })
          // Answered meanwhile (another tab): the drill is read again, at its first free item.
          if (codeOf(error) === 'already_answered') onReload()
        },
      },
    )
  }

  const optionCount = item.options?.length ?? 0
  function choose(index: number | null) {
    if (index !== null && index >= optionCount) return
    send({ kind: 'choice', index })
  }

  // Leaving the item twice (a double click, two Enter) would skip one.
  const left = useRef(false)
  function next() {
    if (left.current) return
    left.current = true
    onNext()
  }

  // The result takes the focus once it is shown.
  const resultRef = useRef<HTMLDivElement>(null)
  const answered = state.result !== null
  useEffect(() => {
    if (answered) resultRef.current?.focus()
  }, [answered])

  const errorCode = codeOf(state.error)
  const blocked = errorCode !== null && BLOCKING_CODES.includes(errorCode)

  const handlers: Parameters<typeof useDrillShortcuts>[0] = {}
  const hints: [string, string][] = []
  if (!blocked && state.phase === 'answering') {
    if (item.kind === 'choice') {
      handlers.choose = choose
      hints.push([`1–${optionCount}`, t('review.keys.choose')])
    } else {
      hints.push([t('review.keys.enter'), t('review.keys.check')])
    }
  }
  if (state.phase === 'answered') {
    handlers.next = next
    hints.push([t('review.keys.enter'), t(isLast ? 'drills.keys.seeScore' : 'drills.keys.next')])
  }
  useDrillShortcuts(handlers)

  return (
    <div className="drill-item">
      <h2 id={titleId} className="drill-item__title">
        {t('drills.player.item', { n: item.index + 1, total })}
      </h2>
      <Sentence sentence={item.sentence} id={sentenceId} />

      {item.kind === 'choice' ? (
        <Options item={item} state={state} onChoose={choose} />
      ) : (
        <TypedAnswer
          state={state}
          describedBy={sentenceId}
          autoFocus={focusInput}
          onType={(typed) => transition({ type: 'type', answer: typed })}
          onSubmit={() => send({ kind: 'text', answer: current.current.answer })}
          onDontKnow={() => send({ kind: 'text', answer: '' })}
        />
      )}

      {state.phase === 'sending' && (
        <p className="muted" role="status">
          {t('drills.player.sending')}
        </p>
      )}
      {state.phase === 'answering' && state.error !== null && <ErrorText error={state.error} />}
      {blocked && (
        <p>
          <button type="button" className="button button--primary" onClick={onReload}>
            {t('drills.player.retry')}
          </button>
        </p>
      )}

      {state.result !== null && (
        <>
          <DrillResult ref={resultRef} result={state.result} errorEventId={state.errorEventId} />
          <p>
            <button type="button" className="button button--primary" onClick={next}>
              {isLast ? t('drills.player.seeScore') : t('drills.player.next')}
            </button>
          </p>
        </>
      )}

      <KeyHints items={hints} />
    </div>
  )
}
