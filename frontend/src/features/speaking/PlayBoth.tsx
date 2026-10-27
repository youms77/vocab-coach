import { type RefObject, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useIsRecording } from '../../speech/activeRecording'
import { cancelSpeech, useSpeech } from '../../speech/useSpeech'

type Phase = 'idle' | 'voice' | 'recording'

function rewind(element: HTMLAudioElement) {
  element.currentTime = 0
}

/**
 * "Play both": the synthetic voice says the sentence, then the recording plays, one after the
 * other (D-195). Cancellable at any moment. Without a speech synthesis or an English voice the
 * recording plays alone. `audio` is the page's own `<audio>` element.
 */
export function PlayBoth({
  target,
  audio,
}: {
  target: string
  audio: RefObject<HTMLAudioElement | null>
}) {
  const { t } = useTranslation()
  const speech = useSpeech()
  const recording = useIsRecording()
  const [phase, setPhase] = useState<Phase>('idle')
  // Each run has its own number: a late end of speech or audio of a cancelled run does nothing.
  const run = useRef(0)

  // The audio element tells when the recording is over (or was stopped from its own controls).
  useEffect(() => {
    const element = audio.current
    if (element === null) return
    const ended = () => setPhase('idle')
    element.addEventListener('ended', ended)
    return () => element.removeEventListener('ended', ended)
  }, [audio])

  useEffect(
    () => () => {
      run.current += 1
    },
    [],
  )

  function playRecording(token: number) {
    const element = audio.current
    if (element === null || run.current !== token) return
    rewind(element)
    setPhase('recording')
    void Promise.resolve(element.play()).catch(() => {
      if (run.current === token) setPhase('idle')
    })
  }

  function start() {
    const token = ++run.current
    audio.current?.pause()
    setPhase('voice')
    const started = speech.speak(target, {
      onDone: (completed) => {
        if (run.current !== token) return
        if (completed) playRecording(token)
        else setPhase('idle')
      },
    })
    if (!started) playRecording(token)
  }

  function stop() {
    run.current += 1
    cancelSpeech()
    audio.current?.pause()
    setPhase('idle')
  }

  const playing = phase !== 'idle'
  return (
    <span className="play-both">
      <button
        type="button"
        className="button"
        onClick={playing ? stop : start}
        disabled={recording}
      >
        {playing ? t('shadowing.detail.stopBoth') : t('shadowing.detail.playBoth')}
      </button>
      <span className="visually-hidden" role="status">
        {phase === 'voice' && t('shadowing.detail.playingVoice')}
        {phase === 'recording' && t('shadowing.detail.playingRecording')}
      </span>
      {playing && (
        <span className="muted field-hint" aria-hidden="true">
          {phase === 'voice' ? t('shadowing.detail.playingVoice') : t('shadowing.detail.playingRecording')}
        </span>
      )}
    </span>
  )
}
