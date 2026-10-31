import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { DiscoveryStart } from '../../api/discovery'
import { SpeakButton } from '../../speech/SpeakButton'
import { StepHeading } from '../session/StepHeading'
import { highlightTerm } from './highlight'
import { Notice } from '../../components/Notice'

export const GUESS_MAX = 1000

/**
 * Steps 1 and 2: the sentence only (no sheet, translation or definition), then the user's guess.
 * "Listen" reads the sentence.
 */
export function ReadAndGuess({
  start,
  onGuess,
}: {
  start: DiscoveryStart
  onGuess: (guess: string | null) => void
}) {
  const { t } = useTranslation()
  const [guess, setGuess] = useState('')
  const sentence = start.sentence

  function submit(event: FormEvent) {
    event.preventDefault()
    const text = guess.trim()
    onGuess(text === '' ? null : text)
  }

  return (
    <>
      <StepHeading>{t('discovery.read.title')}</StepHeading>
      {start.resumed && <Notice tone="warning">{t('discovery.resumed')}</Notice>}
      {sentence !== null ? (
        <figure className="discovery-sentence">
          <blockquote lang="en">
            {highlightTerm(sentence.text, start.term).map((part, i) =>
              part.match ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>,
            )}
          </blockquote>
          <figcaption className="muted">
            {sentence.source === 'origin' ? t('discovery.read.origin') : t('discovery.read.example')}
          </figcaption>
          <SpeakButton text={sentence.text} label={t('discovery.read.sentenceLabel')} />
        </figure>
      ) : (
        <figure className="discovery-sentence">
          <blockquote lang="en">
            <mark>{start.term}</mark>
          </blockquote>
          <figcaption className="muted">{t('discovery.read.noSentence')}</figcaption>
          <SpeakButton text={start.term} />
        </figure>
      )}

      <form className="discovery-form" onSubmit={submit}>
        <h3>{t('discovery.guess.title')}</h3>
        <div className="field">
          <label htmlFor="discovery-guess">{t('discovery.guess.label')}</label>
          <textarea
            id="discovery-guess"
            rows={2}
            maxLength={GUESS_MAX}
            value={guess}
            onChange={(event) => setGuess(event.target.value)}
            aria-describedby="discovery-guess-hint"
          />
          <p id="discovery-guess-hint" className="muted field-hint">
            {t('discovery.guess.hint')}
          </p>
        </div>
        <div className="button-row">
          <button type="submit" className="button button--primary">
            {t('discovery.guess.submit')}
          </button>
          <button type="button" className="button" onClick={() => onGuess(null)}>
            {t('discovery.guess.dontKnow')}
          </button>
        </div>
      </form>
    </>
  )
}
