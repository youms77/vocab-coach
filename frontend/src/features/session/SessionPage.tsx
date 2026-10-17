import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

import { ApiError } from '../../api/client'
import {
  type StudySession,
  useEndSession,
  useNextStep,
  useStartSession,
} from '../../api/session'
import { cancelSpeech } from '../../speech/useSpeech'
import { DiscoveryFlow } from '../discovery/DiscoveryFlow'
import { ErrorText } from '../settings/ErrorText'
import { SessionProgress } from './SessionProgress'
import { StepHeading } from './StepHeading'
import { PracticeInfoPanel, ReviewPlaceholder, SessionSummary, WaitPanel } from './StepPanels'

const isCode = (error: unknown, code: string) => error instanceof ApiError && error.code === code

/** "End the session", always visible, behind an inline confirmation (no browser dialog). */
function EndControl({
  confirming,
  setConfirming,
  onEnd,
  ending,
}: {
  confirming: boolean
  setConfirming: (value: boolean) => void
  onEnd: () => void
  ending: boolean
}) {
  const { t } = useTranslation()
  // The question can be asked from the review panel, far below: bring focus (and the view) to it,
  // on the choice that changes nothing.
  const keepGoing = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (confirming) keepGoing.current?.focus()
  }, [confirming])
  if (!confirming) {
    return (
      <button type="button" className="button" onClick={() => setConfirming(true)}>
        {t('session.end')}
      </button>
    )
  }
  return (
    <div className="confirm" role="alertdialog" aria-label={t('session.end')}>
      <p>{t('session.endConfirm')}</p>
      <button type="button" className="button button--primary" onClick={onEnd} disabled={ending}>
        {ending ? t('session.ending') : t('session.endYes')}
      </button>
      <button
        ref={keepGoing}
        type="button"
        className="button"
        onClick={() => setConfirming(false)}
        disabled={ending}
      >
        {t('session.endNo')}
      </button>
    </div>
  )
}

/**
 * `/session`: opens today's session (idempotent), then follows the steps that `next` returns,
 * one at a time, until `done`, which ends the session and shows its summary.
 */
export function SessionPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const start = useStartSession()
  const end = useEndSession()
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [practiceSeen, setPracticeSeen] = useState(false)
  const [ended, setEnded] = useState<StudySession | null>(null)
  const [confirming, setConfirming] = useState(false)
  const next = useNextStep(ended === null ? sessionId : null, practiceSeen)

  const openSession = useCallback(() => {
    setSessionId(null)
    setPracticeSeen(false)
    setEnded(null)
    start.reset()
    end.reset()
    start.mutate(undefined, { onSuccess: (session) => setSessionId(session.id) })
  }, [start, end])

  // Once per visit (React's development double effect included); `start` is idempotent anyway.
  const opened = useRef(false)
  useEffect(() => {
    if (opened.current) return
    opened.current = true
    openSession()
  }, [openSession])

  // Nothing keeps speaking after the player is gone.
  useEffect(() => cancelSpeech, [])

  const endSession = useCallback(() => {
    if (sessionId === null || end.isPending) return
    cancelSpeech()
    end.mutate(sessionId, {
      onSuccess: (session) => {
        setEnded(session)
        setConfirming(false)
      },
    })
  }, [end, sessionId])

  // `done` ends the session by itself, once.
  const autoEnded = useRef<number | null>(null)
  const step = next.data
  useEffect(() => {
    if (step?.type === 'done' && autoEnded.current !== step.session_id) {
      autoEnded.current = step.session_id
      endSession()
    }
  }, [step, endSession])

  const notFound = isCode(next.error, 'session_not_found') || isCode(end.error, 'session_not_found')
  useEffect(() => {
    if (notFound) navigate('/', { replace: true })
  }, [notFound, navigate])

  const advance = useCallback(() => {
    void next.refetch()
  }, [next])

  const closed = isCode(next.error, 'session_closed') || isCode(end.error, 'session_closed')
  const busy = next.isFetching

  let content
  if (ended !== null) {
    content = ended.summary !== null ? <SessionSummary summary={ended.summary} /> : null
  } else if (closed) {
    content = (
      <>
        <StepHeading>{t('session.closed')}</StepHeading>
        <button type="button" className="button button--primary" onClick={openSession}>
          {t('session.restart')}
        </button>
      </>
    )
  } else if (start.isError) {
    content = (
      <>
        <p className="form-message form-message--error">{t('session.startError')}</p>
        <ErrorText error={start.error} />
        <button type="button" className="button" onClick={openSession}>
          {t('session.retry')}
        </button>
      </>
    )
  } else if (next.isError && !notFound) {
    content = (
      <>
        <ErrorText error={next.error} />
        <button type="button" className="button" onClick={advance} disabled={busy}>
          {t('session.retry')}
        </button>
      </>
    )
  } else if (end.isError && !notFound) {
    content = (
      <>
        <ErrorText error={end.error} />
        <button type="button" className="button" onClick={endSession}>
          {t('session.retry')}
        </button>
      </>
    )
  } else if (step === undefined) {
    content = <p className="muted">{sessionId === null ? t('session.starting') : t('session.loading')}</p>
  } else if (step.type === 'review') {
    content = (
      <ReviewPlaceholder count={step.progress.reviews_remaining} onEnd={() => setConfirming(true)} />
    )
  } else if (step.type === 'new_item') {
    content = (
      <DiscoveryFlow
        key={step.new_item.item_id}
        sessionId={step.session_id}
        newItem={step.new_item}
        onNext={advance}
      />
    )
  } else if (step.type === 'wait') {
    content = <WaitPanel until={step.wait.until} onCheck={advance} checking={busy} />
  } else if (step.type === 'practice_info') {
    content = (
      <PracticeInfoPanel
        practice={step.practice}
        onContinue={() => setPracticeSeen(true)}
        busy={busy}
      />
    )
  } else {
    content = <p className="muted">{t('session.ending')}</p>
  }

  return (
    <div className="session">
      <header className="session__header">
        <h1>{t('session.title')}</h1>
        {sessionId !== null && ended === null && !closed && (
          <EndControl
            confirming={confirming}
            setConfirming={setConfirming}
            onEnd={endSession}
            ending={end.isPending}
          />
        )}
      </header>
      {step !== undefined && ended === null && !closed && <SessionProgress progress={step.progress} />}
      <section className="card session-step" key={step?.type ?? 'none'}>
        {content}
      </section>
    </div>
  )
}
