import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import { speechKey, useSpeech } from './useSpeech'

/**
 * "Listen" and "Listen slowly" for one English text. `label` names what is read, for the
 * buttons' accessible names (defaults to the text itself). Disabled, with the reason, when the
 * browser has no speech synthesis or no English voice.
 */
export function SpeakButton({ text, label }: { text: string; label?: string }) {
  const { t } = useTranslation()
  const speech = useSpeech()
  const hintId = useId()
  const what = label ?? text

  const reason = !speech.supported
    ? t('speech.unsupported')
    : speech.voice === null
      ? t('speech.noEnglishVoice')
      : null
  const normalSpeaking = speech.speaking === speechKey(text, false)
  const slowSpeaking = speech.speaking === speechKey(text, true)

  return (
    <span className="speak">
      <button
        type="button"
        className="button button--small"
        onClick={() => speech.speak(text)}
        disabled={reason !== null}
        aria-label={t('speech.listenTo', { what })}
        aria-describedby={reason !== null ? hintId : undefined}
      >
        {normalSpeaking ? t('speech.speaking') : t('speech.listen')}
      </button>
      <button
        type="button"
        className="button button--small"
        onClick={() => speech.speak(text, { slow: true })}
        disabled={reason !== null}
        aria-label={t('speech.listenSlowlyTo', { what })}
        aria-describedby={reason !== null ? hintId : undefined}
      >
        {slowSpeaking ? t('speech.speaking') : t('speech.listenSlowly')}
      </button>
      <span className="visually-hidden" role="status">
        {normalSpeaking || slowSpeaking ? t('speech.speakingWhat', { what }) : ''}
      </span>
      {reason !== null && (
        <span id={hintId} className="muted speak__hint">
          {reason}
        </span>
      )}
      {reason === null && !speech.american && speech.voice !== null && (
        <span className="muted speak__hint">
          {t('speech.nonAmerican', { name: speech.voice.name })}
        </span>
      )}
    </span>
  )
}
