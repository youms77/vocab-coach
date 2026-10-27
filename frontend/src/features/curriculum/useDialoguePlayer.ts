import { useCallback, useEffect, useRef, useState } from 'react'

import type { Dialogue } from '../../api/curriculum'
import { useIsRecording } from '../../speech/activeRecording'
import { cancelSpeech, useSpeech } from '../../speech/useSpeech'
import { dialogueVoices } from '../../speech/voices'
import { speakerIndex } from './unitRules'

/**
 * Says a dialogue line after line, each speaker with their own voice (D-195's run token: a late end
 * of a cancelled run does nothing). `current` is the line being said, or null when nothing plays.
 * `unavailable` says why nothing can be played (no synthesis, no English voice, microphone open).
 */
export function useDialoguePlayer(dialogue: Dialogue, slow: boolean) {
  const speech = useSpeech()
  const recording = useIsRecording()
  const [current, setCurrent] = useState<number | null>(null)
  const run = useRef(0)
  const names = dialogueVoices(speech.voices, speech.voice)
  const latest = useRef({ speak: speech.speak, names, dialogue, slow })

  useEffect(() => {
    latest.current = { speak: speech.speak, names, dialogue, slow }
  })

  useEffect(
    () => () => {
      run.current += 1
    },
    [],
  )

  const sayLine = useCallback(function say(index: number, token: number) {
    const { speak, names: voices, dialogue: d, slow: isSlow } = latest.current
    const line = d.lines[index]
    if (line === undefined) {
      setCurrent(null)
      return
    }
    const started = speak(line.text, {
      slow: isSlow,
      voiceName: voices?.[speakerIndex(d, line.speaker)],
      onDone: (completed) => {
        if (run.current !== token) return
        if (completed) say(index + 1, token)
        else setCurrent(null)
      },
    })
    setCurrent(started ? index : null)
  }, [])

  const play = useCallback(() => {
    const token = ++run.current
    sayLine(0, token)
  }, [sayLine])

  const stop = useCallback(() => {
    run.current += 1
    cancelSpeech()
    setCurrent(null)
  }, [])

  /** One line alone, with its speaker's voice (the "Listen" of an expanded text). */
  const sayOne = useCallback((index: number) => {
    run.current += 1
    const { speak, names: voices, dialogue: d, slow: isSlow } = latest.current
    const line = d.lines[index]
    if (line === undefined) return
    setCurrent(null)
    speak(line.text, { slow: isSlow, voiceName: voices?.[speakerIndex(d, line.speaker)] })
  }, [])

  const unavailable: 'unsupported' | 'noEnglishVoice' | 'disabledWhileRecording' | null =
    !speech.supported
      ? 'unsupported'
      : names === null
        ? 'noEnglishVoice'
        : recording
          ? 'disabledWhileRecording'
          : null

  return { current, playing: current !== null, play, stop, sayOne, unavailable }
}
