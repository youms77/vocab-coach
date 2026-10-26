import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'

import { useUnit } from '../../api/curriculum'
import { useSpeaking } from '../../api/speech'
import { PageTitle } from '../../components/PageTitle'
import { Recorder } from '../../speech/RecorderPanel'
import { readUnitId } from '../curriculum/unitRules'
import { ErrorText } from '../settings/ErrorText'
import { TopicPicker } from '../writing/TopicPicker'
import { SPEAKING_TOPICS } from './topics'

/** The final task of a scenario unit, shown instead of the topic picker (module H). */
function UnitPrompt({ unitId }: { unitId: number }) {
  const { t } = useTranslation()
  const unit = useUnit(unitId)
  const task = unit.data?.scenario?.final_task
  return (
    <section className="card" aria-labelledby="speak-unit">
      <h2 id="speak-unit">{t('speaking.unit.title')}</h2>
      {unit.isPending && <p className="muted">{t('curriculum.loading')}</p>}
      {unit.isError && <ErrorText error={unit.error} />}
      {task !== undefined && (
        <>
          <p lang="en">{task.prompt_en}</p>
          <p className="muted">{t('curriculum.finalTask.minutes', { count: task.minutes })}</p>
        </>
      )}
      <p>
        <Link to={`/curriculum/units/${unitId}`}>{t('curriculum.backToUnit')}</Link>
      </p>
    </section>
  )
}

/**
 * Free speaking: pick a subject (or your own, or none), speak for one to two minutes, send. The
 * recording is stored and transcribed first, then the page of that production (`/speaking/:id`,
 * history replaced so a reload never sends it again) runs the AI correction and shows it.
 * From a scenario unit (navigation state `{unitId}`, read once and cleared like the shadowing
 * page's, D-196) the unit's prompt replaces the picker and the talk is sent with `unit_id`.
 */
export function SpeakingPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const speak = useSpeaking()
  const [prompt, setPrompt] = useState<string | null>(null)
  const [unitId] = useState(() => readUnitId(location.state))
  const consumed = useRef(false)
  const sending = speak.isPending || speak.isSuccess

  useEffect(() => {
    if (consumed.current || location.state === null || location.state === undefined) return
    consumed.current = true
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])

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

      {unitId !== null ? (
        <UnitPrompt unitId={unitId} />
      ) : (
        <TopicPicker value={prompt} onChange={setPrompt} source={SPEAKING_TOPICS} />
      )}

      <section className="card" aria-labelledby="speak-record">
        <h2 id="speak-record">{t('speaking.step2')}</h2>
        <Recorder
          use="speaking"
          sending={sending}
          sendingLabel={t('speaking.sending')}
          onSend={(clip) =>
            speak.mutate(
              unitId !== null
                ? { blob: clip.blob, durationS: clip.durationS, unitId }
                : { blob: clip.blob, durationS: clip.durationS, promptText: prompt ?? undefined },
              {
                onSuccess: (result) => {
                  // The correction starts on the next page, once. An unavailable transcription is
                  // told there too (the reason only), read once and cleared.
                  const unavailable =
                    result.transcription.status === 'unavailable'
                      ? { unavailableReason: result.transcription.reason ?? 'all_failed' }
                      : {}
                  const unit = unitId !== null ? `?unit=${unitId}` : ''
                  navigate(`/speaking/${result.production_id}${unit}`, {
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
