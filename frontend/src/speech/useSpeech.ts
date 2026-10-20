import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router'

import { useSettings } from '../api/settings'
import { isRecording } from './activeRecording'
import { englishVoices, pickVoice, rateFor } from './voices'

/*
 * A small store over `window.speechSynthesis` (Web Speech API, SPEC section 7: free and offline).
 * The synthesis object is read on every call, never cached, so a browser without it (or jsdom)
 * simply reports `supported: false`. Voices arrive asynchronously (`voiceschanged`): the list is
 * empty on the first render in Chrome.
 */

function synth(): SpeechSynthesis | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null
  return window.speechSynthesis ?? null
}

// --- Voices ---------------------------------------------------------------------------------------

let voicesSnapshot: readonly SpeechSynthesisVoice[] = []

function readVoices(): readonly SpeechSynthesisVoice[] {
  const next = synth()?.getVoices() ?? []
  const same =
    next.length === voicesSnapshot.length && next.every((v, i) => v === voicesSnapshot[i])
  if (!same) voicesSnapshot = [...next]
  return voicesSnapshot
}

const noVoices: readonly SpeechSynthesisVoice[] = []

function subscribeVoices(onChange: () => void) {
  const s = synth()
  s?.addEventListener('voiceschanged', onChange)
  return () => s?.removeEventListener('voiceschanged', onChange)
}

// --- The utterance being spoken -------------------------------------------------------------------

let speakingKey: string | null = null
let token = 0
const speakingListeners = new Set<() => void>()

function setSpeaking(key: string | null) {
  speakingKey = key
  for (const listener of speakingListeners) listener()
}

function subscribeSpeaking(onChange: () => void) {
  speakingListeners.add(onChange)
  return () => speakingListeners.delete(onChange)
}

/** Stops whatever is being said. Safe without speech synthesis. */
export function cancelSpeech() {
  synth()?.cancel()
  if (speakingKey !== null) setSpeaking(null)
}

/** The key `speak` uses for a text and a speed, to tell which button is speaking. */
export const speechKey = (text: string, slow: boolean) => `${slow ? 'slow' : 'normal'}:${text}`

// --- Hooks ----------------------------------------------------------------------------------------

export interface SpeakOptions {
  slow?: boolean
  /** Use this voice name instead of the setting (the settings page's "Test" button). */
  voiceName?: string
  /**
   * Called once when this utterance ends: `true` when it was said to the end, `false` when it was
   * cancelled, replaced or failed ("Play both" goes on to the recording only on `true`, D-195).
   */
  onDone?: (completed: boolean) => void
}

export function useSpeech() {
  const settings = useSettings()
  const allVoices = useSyncExternalStore(subscribeVoices, readVoices, () => noVoices)
  const speaking = useSyncExternalStore(subscribeSpeaking, () => speakingKey, () => null)

  // Defaults (normal speed, first en-US voice) when the settings cannot be read.
  const rateSetting = settings.data?.tts_rate?.value
  const rate = typeof rateSetting === 'number' ? rateSetting : 1
  const voiceSetting = settings.data?.tts_voice?.value
  const voiceName = typeof voiceSetting === 'string' ? voiceSetting : ''
  const { voice, american } = pickVoice(allVoices, voiceName)

  const speak = useCallback(
    (text: string, options: SpeakOptions = {}): boolean => {
      const s = synth()
      const slow = options.slow ?? false
      const chosen =
        options.voiceName === undefined ? voice : pickVoice(allVoices, options.voiceName).voice
      // Nothing is said while the microphone is open: it would be recorded (D-193).
      if (s === null || chosen === null || isRecording()) return false
      // One utterance at a time.
      s.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'en-US'
      utterance.voice = chosen
      utterance.rate = rateFor(rate, slow)
      const mine = ++token
      let reported = false
      const done = (completed: boolean) => {
        if (mine === token) setSpeaking(null)
        if (reported) return
        reported = true
        options.onDone?.(completed)
      }
      utterance.onend = () => done(true)
      utterance.onerror = () => done(false)
      setSpeaking(speechKey(text, slow))
      s.speak(utterance)
      return true
    },
    [allVoices, rate, voice],
  )

  return {
    supported: synth() !== null,
    /** The English voices of this browser, en-US first. */
    voices: englishVoices(allVoices),
    voice,
    american,
    speaking,
    speak,
    cancel: cancelSpeech,
  }
}

/** Stops speech when the route changes (mounted once, in the layout). */
export function useCancelSpeechOnLeave() {
  const { pathname } = useLocation()
  useEffect(() => cancelSpeech, [pathname])
}
