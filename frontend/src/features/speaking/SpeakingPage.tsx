import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { useSpeaking } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { Recorder } from '../../speech/RecorderPanel'
import { ErrorText } from '../settings/ErrorText'
import { TopicPicker } from '../writing/TopicPicker'
import { SPEAKING_TOPICS } from './topics'

/**
 * Free speaking: pick a subject (or your own, or none), speak for one to two minutes, send. The
 * recording is stored and transcribed first, then the page of that production (`/speaking/:id`,
 * history replaced so a reload never sends it again) runs the AI correction and shows it.
 */
export function SpeakingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const speak = useSpeaking()
  const [prompt, setPrompt] = useState<string | null>(null)
  const sending = speak.isPending || speak.isSuccess

  return (
    <div className="speaking-page">
      <section className="hero">
        <PageTitle>{t('speaking.title')}</PageTitle>
        <p className="muted">{t('speaking.intro')}</p>
        <p className="link-row">
          <Link to="/speaking/history">{t('speaking.historyLink')}</Link>
          <Link to="/speaking/shadowing">{t('speaking.shadowingLink')}</Link>
        </p>
      </section>

      <TopicPicker value={prompt} onChange={setPrompt} source={SPEAKING_TOPICS} />

      <section className="card" aria-labelledby="speak-record">
        <h2 id="speak-record">{t('speaking.step2')}</h2>
        <Recorder
          use="speaking"
          sending={sending}
          sendingLabel={t('speaking.sending')}
          onSend={(clip) =>
            speak.mutate(
              { blob: clip.blob, durationS: clip.durationS, promptText: prompt ?? undefined },
              {
                onSuccess: (result) => {
                  // The correction starts on the next page, once. An unavailable transcription is
                  // told there too (the reason only), read once and cleared.
                  const unavailable =
                    result.transcription.status === 'unavailable'
                      ? { unavailableReason: result.transcription.reason ?? 'all_failed' }
                      : {}
                  navigate(`/speaking/${result.production_id}`, {
                    replace: true,
                    state: { autoCorrect: true, ...unavailable },
                  })
                },
              },
            )
          }
        />
        {speak.isError && <ErrorText error={speak.error} />}
        <p className="muted field-hint">{t('speaking.submitHint')}</p>
        <p className="muted field-hint">{t('speaking.privacy')}</p>
      </section>
    </div>
  )
}
