import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type SettingsMap, useSettingsMutation } from '../../api/settings'
import { useSpeech } from '../../speech/useSpeech'
import { ErrorText } from './ErrorText'

// A fixed sentence for the "Test" button.
const TEST_SENTENCE = 'It is worth noting that the results depend on the sample.'

/**
 * `tts_voice`: the list comes from this browser (the server has none, D-108). "" means the first
 * en-US voice. Its own form, since "" is a valid value here and the other groups require a value.
 */
export function VoiceSetting({ settings }: { settings: SettingsMap }) {
  const { t } = useTranslation()
  const speech = useSpeech()
  const mutation = useSettingsMutation()
  const saved = String(settings.tts_voice.value)
  const [draft, setDraft] = useState(saved)
  const [done, setDone] = useState(false)

  const known = speech.voices.some((v) => v.name === draft)
  // A voice chosen in another browser stays listed, marked as missing here.
  const missing = [saved, draft].filter(
    (name, i, all) => name !== '' && all.indexOf(name) === i && !speech.voices.some((v) => v.name === name),
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    if (draft === saved) return
    mutation.mutate({ tts_voice: draft }, { onSuccess: () => setDone(true) })
  }

  return (
    <form className="settings-group" onSubmit={submit} noValidate>
      <fieldset>
        <legend>{t('speech.voice.legend')}</legend>
        <div className="field">
          <label htmlFor="setting-tts_voice">{t('speech.voice.label')}</label>
          <select
            id="setting-tts_voice"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setDone(false)
            }}
            aria-describedby="setting-tts_voice-hint"
          >
            <option value="">{t('speech.voice.automatic')}</option>
            {speech.voices.map((v) => (
              <option key={v.voiceURI || v.name} value={v.name}>
                {v.name} — {v.lang}
              </option>
            ))}
            {missing.map((name) => (
              <option key={`missing-${name}`} value={name}>
                {t('speech.voice.unavailable', { name })}
              </option>
            ))}
          </select>
          <p id="setting-tts_voice-hint" className="muted field-hint">
            {!speech.supported
              ? t('speech.unsupported')
              : speech.voices.length === 0
                ? t('speech.noEnglishVoice')
                : t('speech.voice.hint')}
            {draft !== '' && !known && speech.supported && ` ${t('speech.voice.fallback')}`}
          </p>
        </div>
      </fieldset>
      <div className="button-row">
        <button
          type="button"
          className="button"
          onClick={() => speech.speak(TEST_SENTENCE, { voiceName: draft })}
          disabled={!speech.supported || speech.voice === null}
        >
          {t('speech.voice.test')}
        </button>
        <button
          type="submit"
          className="button button--primary"
          disabled={draft === saved || mutation.isPending}
        >
          {t('settings.general.save')}
        </button>
      </div>
      <div aria-live="polite">
        {done && draft === saved && (
          <p className="form-message form-message--ok">{t('settings.saved')}</p>
        )}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </form>
  )
}
