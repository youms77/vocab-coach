import { type FormEvent, type KeyboardEvent, useId } from 'react'
import { useTranslation } from 'react-i18next'

import type { ReviewStep } from '../../api/session'
import { SpeakButton } from '../../speech/SpeakButton'
import { highlightTerm } from '../discovery/highlight'
import type { ReviewState } from './reviewMachine'
import { promptOptions, text } from './stepText'

function Sentence({ sentence, term }: { sentence: string; term: string | null }) {
  const parts = term !== null ? highlightTerm(sentence, term) : [{ text: sentence, match: false }]
  return (
    <p className="review-sentence" lang="en">
      {parts.map((part, i) =>
        part.match ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>,
      )}
    </p>
  )
}

/** Numbered options; after the answer, the right one and a wrong choice are marked with a sign and text. */
function Options({
  review,
  state,
  onChoose,
}: {
  review: ReviewStep
  state: ReviewState
  onChoose: (index: number | null) => void
}) {
  const { t } = useTranslation()
  const labelId = useId()
  const answering = state.phase === 'answering'
  const correct = state.result?.solution.correct_index
  return (
    <div className="review-options-block">
      <p id={labelId} className="review-options-label">
        {t('review.options.label')}
      </p>
      <div role="group" aria-labelledby={labelId} className="review-options">
        {promptOptions(review).map((option, index) => {
          const isCorrect = correct === index
          const isWrongChoice = state.result !== null && state.choiceIndex === index && !isCorrect
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
              aria-pressed={state.choiceIndex === index}
            >
              <kbd className="review-option__key">{index + 1}</kbd>{' '}
              <span lang="en" className="review-option__text">
                {option}
              </span>
              {isCorrect && (
                <span className="review-option__mark"> ✓ {t('review.options.correct')}</span>
              )}
              {isWrongChoice && (
                <span className="review-option__mark"> ✗ {t('review.options.yourChoice')}</span>
              )}
            </button>
          )
        })}
      </div>
      {answering && (
        <button type="button" className="button" onClick={() => onChoose(null)}>
          {t('review.options.dontKnow')}
        </button>
      )}
    </div>
  )
}

/** A typed answer: one line (typed recall, gap-fill) or a few (sentence production). */
function TypedAnswer({
  review,
  state,
  onType,
  onSubmit,
}: {
  review: ReviewStep
  state: ReviewState
  onType: (answer: string) => void
  onSubmit: () => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const hintId = useId()
  const answering = state.phase === 'answering'
  const multiline = review.exercise_type === 'sentence_production'
  const label =
    review.exercise_type === 'gap_fill'
      ? t('review.answer.gapLabel')
      : multiline
        ? t('review.answer.sentenceLabel')
        : t('review.answer.termLabel')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (answering) onSubmit()
  }

  // Enter checks the sentence; Shift+Enter starts a new line.
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (answering && !event.repeat) onSubmit()
    }
  }

  return (
    <form className="review-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor={id}>{label}</label>
        {multiline ? (
          <textarea
            id={id}
            lang="en"
            rows={3}
            maxLength={2000}
            value={state.answer}
            onChange={(event) => onType(event.target.value)}
            onKeyDown={onKeyDown}
            readOnly={!answering}
            aria-describedby={hintId}
          />
        ) : (
          <input
            id={id}
            lang="en"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            maxLength={2000}
            value={state.answer}
            onChange={(event) => onType(event.target.value)}
            readOnly={!answering}
            aria-describedby={hintId}
          />
        )}
        <p id={hintId} className="muted field__hint">
          {multiline ? t('review.answer.sentenceHint') : t('review.answer.hint')}
        </p>
      </div>
      {state.phase !== 'answered' && state.phase !== 'recording' && state.phase !== 'recorded' && (
        <button type="submit" className="button button--primary" disabled={!answering}>
          {state.phase === 'checking' ? t('review.checking') : t('review.check')}
        </button>
      )}
    </form>
  )
}

function RevealButton({
  state,
  onReveal,
  label,
}: {
  state: ReviewState
  onReveal: () => void
  label: string
}) {
  const { t } = useTranslation()
  if (state.phase !== 'answering' && state.phase !== 'checking') return null
  return (
    <button
      type="button"
      className="button button--primary"
      onClick={onReveal}
      disabled={state.phase !== 'answering'}
    >
      {state.phase === 'checking' ? t('review.checking') : label}
    </button>
  )
}

/**
 * What the card asks, before and after the answer. Built from the step's prompt only: the
 * solution is never in the step (D-103). The listening sentence is spoken, never written here,
 * and a productive card never shows its term.
 */
export function ReviewPrompt({
  review,
  state,
  onType,
  onSubmitText,
  onChoose,
  onReveal,
}: {
  review: ReviewStep
  state: ReviewState
  onType: (answer: string) => void
  onSubmitText: () => void
  onChoose: (index: number | null) => void
  onReveal: () => void
}) {
  const { t } = useTranslation()
  const prompt = review.prompt
  const term = review.term
  const sentence = text(prompt.sentence)
  const sentenceLabel = t('review.sentenceLabel')

  switch (review.exercise_type) {
    case 'recognition_in_sentence':
      return (
        <>
          <p>
            {term !== null
              ? t('review.prompt.recognition', { term })
              : t('review.prompt.recognitionNoTerm')}
          </p>
          {sentence !== null && (
            <>
              <Sentence sentence={sentence} term={term} />
              <SpeakButton text={sentence} label={sentenceLabel} />
            </>
          )}
          <Options review={review} state={state} onChoose={onChoose} />
        </>
      )
    case 'listening_comprehension':
      return (
        <>
          <p>{t('review.prompt.listening')}</p>
          {/* The sentence is only spoken: it must not be readable before the answer. */}
          {sentence !== null && <SpeakButton text={sentence} label={sentenceLabel} />}
          <Options review={review} state={state} onChoose={onChoose} />
        </>
      )
    case 'typed_recall':
      return (
        <>
          <p>{t('review.prompt.typedRecall')}</p>
          <Cues cueFr={text(prompt.cue_fr)} cueDefinition={text(prompt.cue_definition)} />
          <TypedAnswer review={review} state={state} onType={onType} onSubmit={onSubmitText} />
        </>
      )
    case 'gap_fill':
      return (
        <>
          <p>{t('review.prompt.gapFill')}</p>
          {sentence !== null && <p className="review-sentence exercise-gap" lang="en">{sentence}</p>}
          <TypedAnswer review={review} state={state} onType={onType} onSubmit={onSubmitText} />
        </>
      )
    case 'sentence_production':
      return (
        <>
          <p>{t('review.prompt.sentenceProduction')}</p>
          <p className="review-situation" lang="en">
            {text(prompt.situation)}
          </p>
          <p className="muted">{t('review.prompt.selfGradedLater')}</p>
          <TypedAnswer review={review} state={state} onType={onType} onSubmit={onSubmitText} />
        </>
      )
    case 'spoken_answer':
      return (
        <>
          <p>{t('review.prompt.spokenAnswer')}</p>
          <p className="review-situation" lang="en">
            {text(prompt.question)}
          </p>
          <p className="muted">{t('review.prompt.recordingLater')}</p>
          <RevealButton state={state} onReveal={onReveal} label={t('review.showExample')} />
        </>
      )
    default: {
      // self_assessment (D-101): receptive shows the term, productive shows the cues.
      if (review.direction === 'receptive') {
        const shownTerm = text(prompt.term) ?? term
        return (
          <>
            <p>{t('review.prompt.selfReceptive')}</p>
            {shownTerm !== null && (
              <p className="review-term">
                <strong lang="en">{shownTerm}</strong>{' '}
                <SpeakButton text={shownTerm} label={t('review.termLabel')} />
              </p>
            )}
            {sentence !== null && <Sentence sentence={sentence} term={shownTerm} />}
            <RevealButton state={state} onReveal={onReveal} label={t('review.showAnswer')} />
          </>
        )
      }
      const gapped = text(prompt.sentence_gapped)
      return (
        <>
          <p>{t('review.prompt.selfProductive')}</p>
          <Cues cueFr={text(prompt.cue_fr)} cueDefinition={text(prompt.cue_definition)} />
          {gapped !== null && <p className="review-sentence exercise-gap" lang="en">{gapped}</p>}
          {review.warnings.includes('no_cue') && (
            <p className="form-message form-message--warn">{t('review.noCue')}</p>
          )}
          <RevealButton state={state} onReveal={onReveal} label={t('review.showAnswer')} />
        </>
      )
    }
  }
}

function Cues({ cueFr, cueDefinition }: { cueFr: string | null; cueDefinition: string | null }) {
  const { t } = useTranslation()
  if (cueFr === null && cueDefinition === null) return null
  return (
    <ul className="exercise-cues">
      {cueFr !== null && <li lang="fr">{t('review.cueFr', { cue: cueFr })}</li>}
      {cueDefinition !== null && <li>{t('review.cueDefinition', { cue: cueDefinition })}</li>}
    </ul>
  )
}
