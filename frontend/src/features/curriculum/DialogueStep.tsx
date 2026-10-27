import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type Scenario, type Unit, useMarkStep } from '../../api/curriculum'
import { ErrorText } from '../settings/ErrorText'
import { useDialoguePlayer } from './useDialoguePlayer'

/**
 * Step 2: listen to the whole dialogue (each speaker has a voice), the text stays collapsed until
 * the learner asks for it ("Listen first"), then "I listened to the dialogue".
 */
export function DialogueStep({ unit, scenario }: { unit: Unit; scenario: Scenario }) {
  const { t, i18n } = useTranslation()
  const mark = useMarkStep()
  const textId = useId()
  const { dialogue } = scenario
  const [slow, setSlow] = useState(false)
  const [shown, setShown] = useState(false)
  const [english, setEnglish] = useState(false)
  const player = useDialoguePlayer(dialogue, slow)
  const french = i18n.language.startsWith('fr')
  const reason = player.unavailable

  return (
    <>
      <p>
        {french && !english ? dialogue.setting_fr : dialogue.setting_en}{' '}
        {french && (
          <button
            type="button"
            className="button button--small"
            aria-pressed={english}
            onClick={() => setEnglish(!english)}
          >
            {english ? t('curriculum.dialogue.hideEnglish') : t('curriculum.dialogue.showEnglish')}
          </button>
        )}
      </p>
      <p className="muted" lang="en">
        {t('curriculum.dialogue.speakers', { first: dialogue.speakers[0], second: dialogue.speakers[1] })}
      </p>

      <div className="unit-step__actions">
        <p className="link-row">
          {player.playing ? (
            <button type="button" className="button" onClick={player.stop}>
              {t('curriculum.dialogue.stop')}
            </button>
          ) : (
            <button
              type="button"
              className="button button--primary"
              disabled={reason !== null}
              onClick={player.play}
            >
              {t('curriculum.dialogue.play')}
            </button>
          )}
          <fieldset className="speed-choice">
            <legend className="visually-hidden">{t('curriculum.dialogue.speed')}</legend>
            <label className="checkbox-row">
              <input type="radio" name={`${textId}-speed`} checked={!slow} onChange={() => setSlow(false)} />
              {t('curriculum.dialogue.normal')}
            </label>
            <label className="checkbox-row">
              <input type="radio" name={`${textId}-speed`} checked={slow} onChange={() => setSlow(true)} />
              {t('curriculum.dialogue.slow')}
            </label>
          </fieldset>
        </p>
        <span className="visually-hidden" role="status">
          {player.playing ? t('curriculum.dialogue.playing') : ''}
        </span>
        {reason !== null && <p className="muted field-hint">{t(`speech.${reason}`)}</p>}

        <p>
          <button
            type="button"
            className="button"
            aria-expanded={shown}
            aria-controls={textId}
            onClick={() => setShown(!shown)}
          >
            {shown ? t('curriculum.dialogue.hideText') : t('curriculum.dialogue.showText')}
          </button>{' '}
          {!shown && <span className="muted field-hint">{t('curriculum.dialogue.listenFirst')}</span>}
        </p>
        <div id={textId}>
          {shown && (
            <ol className="unit-dialogue" lang="en">
              {dialogue.lines.map((line, index) => (
                <li key={index} aria-current={player.current === index ? 'true' : undefined}>
                  <strong>{line.speaker}:</strong> {line.text}{' '}
                  <button
                    type="button"
                    className="button button--small"
                    disabled={reason !== null}
                    aria-label={t('curriculum.dialogue.listenLine', { number: index + 1 })}
                    onClick={() => player.sayOne(index)}
                  >
                    {t('speech.listen')}
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>

        {!scenario.steps.dialogue && (
          <p>
            <button
              type="button"
              className="button"
              disabled={mark.isPending}
              onClick={() => mark.mutate({ unitId: unit.id, step: 'dialogue' })}
            >
              {t('curriculum.dialogue.markListened')}
            </button>
          </p>
        )}
        {mark.isError && <ErrorText error={mark.error} />}
      </div>
    </>
  )
}
