import { useCallback, useEffect, useRef, useState } from 'react'

import { claimRecording, releaseRecording } from './activeRecording'
import {
  type FailureReason,
  failureReason,
  isTooShort,
  LIMITS,
  now,
  pickAudioType,
  type RecordingUse,
  reportedDuration,
  unsupportedReason,
} from './recorder'
import { cancelSpeech } from './useSpeech'

/** A finished take, ready to listen to and to send. `url` is a `blob:` URL owned by the hook. */
export interface Clip {
  blob: Blob
  url: string
  /** Seconds, measured by the client (a `MediaRecorder` webm often has no duration). */
  durationS: number
  mimeType: string
}

type State =
  | { status: 'idle' }
  | { status: 'requesting' }
  | { status: 'recording' }
  | { status: 'stopped'; clip: Clip; tooShort: boolean }
  | { status: 'error'; reason: FailureReason }

/** One take: what must be released when it ends, however it ends. */
interface Take {
  token: symbol
  stream: MediaStream | null
  recorder: MediaRecorder | null
  chunks: Blob[]
  startedAt: number
  endedAt: number
  tick: number | null
  limit: number | null
  stopping: boolean
}

function releaseTracks(take: Take) {
  take.stream?.getTracks().forEach((track) => track.stop())
}

function stopTimers(take: Take) {
  if (take.tick !== null) window.clearInterval(take.tick)
  if (take.limit !== null) window.clearTimeout(take.limit)
  take.tick = null
  take.limit = null
}

/**
 * Records the microphone (D-193). One recording at a time in the whole app; speech synthesis is
 * cut before the microphone opens (or the synthetic voice would be recorded); the tracks are
 * stopped when the take ends, is cancelled, when the component goes away and on a route change
 * (the browser's microphone indicator must go out). The clip lives in memory and behind a `blob:`
 * URL revoked when replaced or on unmount: nothing is stored anywhere.
 */
export function useRecorder(use: RecordingUse) {
  const limits = LIMITS[use]
  const [state, setState] = useState<State>({ status: 'idle' })
  const [seconds, setSeconds] = useState(0)
  const current = useRef<Take | null>(null)
  const objectUrl = useRef<string | null>(null)

  const revoke = useCallback(() => {
    if (objectUrl.current !== null) URL.revokeObjectURL(objectUrl.current)
    objectUrl.current = null
  }, [])

  const free = useCallback((take: Take) => {
    stopTimers(take)
    releaseTracks(take)
    releaseRecording(take.token)
  }, [])

  /** Throws the take away (Record again, Cancel, leaving the page). */
  const cancel = useCallback(() => {
    const take = current.current
    current.current = null
    if (take !== null) {
      try {
        if (take.recorder !== null && take.recorder.state !== 'inactive') take.recorder.stop()
      } catch {
        // Already stopped: only the tracks matter.
      }
      free(take)
    }
    revoke()
    setState({ status: 'idle' })
    setSeconds(0)
  }, [free, revoke])

  const stop = useCallback(() => {
    const take = current.current
    if (take === null || take.recorder === null || take.stopping) return
    take.stopping = true
    take.endedAt = now()
    stopTimers(take)
    try {
      if (take.recorder.state !== 'inactive') take.recorder.stop()
    } catch {
      // Already stopped: the `stop` event may never come, the tracks are released below anyway.
    }
    // The indicator goes out now; the last chunk still arrives through the recorder's own events.
    releaseTracks(take)
  }, [])

  const start = useCallback(async () => {
    if (current.current !== null) return
    const unsupported = unsupportedReason()
    if (unsupported !== null) {
      setState({ status: 'error', reason: unsupported })
      return
    }
    const take: Take = {
      token: Symbol('recording'),
      stream: null,
      recorder: null,
      chunks: [],
      startedAt: 0,
      endedAt: 0,
      tick: null,
      limit: null,
      stopping: false,
    }
    // One recording at a time: another recorder of the page holds the microphone.
    if (!claimRecording(take.token, cancel)) return
    current.current = take
    // Without this the recording would contain the synthetic voice.
    cancelSpeech()
    revoke()
    setState({ status: 'requesting' })
    setSeconds(0)

    const fail = (error: unknown) => {
      if (current.current !== take) return
      current.current = null
      free(take)
      setState({ status: 'error', reason: failureReason(error) })
    }

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (error) {
      fail(error)
      return
    }
    if (current.current !== take) {
      // Cancelled while the browser was asking: the microphone must not stay open.
      stream.getTracks().forEach((track) => track.stop())
      return
    }
    take.stream = stream

    try {
      const type = pickAudioType(
        (candidate) =>
          typeof MediaRecorder.isTypeSupported === 'function' &&
          MediaRecorder.isTypeSupported(candidate),
      )
      const recorder =
        type === null ? new MediaRecorder(stream) : new MediaRecorder(stream, { mimeType: type })
      take.recorder = recorder
      recorder.addEventListener('dataavailable', (event: BlobEvent) => {
        if (current.current === take && event.data.size > 0) take.chunks.push(event.data)
      })
      recorder.addEventListener('start', () => {
        take.startedAt = now()
      })
      recorder.addEventListener('error', (event) => fail((event as { error?: unknown }).error))
      recorder.addEventListener('stop', () => {
        if (current.current !== take) return
        current.current = null
        free(take)
        const mimeType = take.chunks[0]?.type || recorder.mimeType
        const blob = new Blob(take.chunks, { type: mimeType })
        if (blob.size === 0) {
          setState({ status: 'error', reason: 'failed' })
          return
        }
        const durationS = reportedDuration((take.endedAt - take.startedAt) / 1000, use)
        revoke()
        const url = URL.createObjectURL(blob)
        objectUrl.current = url
        setSeconds(durationS)
        setState({
          status: 'stopped',
          clip: { blob, url, durationS, mimeType },
          tooShort: isTooShort(durationS, use),
        })
      })
      recorder.start(1000)
      take.startedAt = now()
    } catch (error) {
      fail(error)
      return
    }
    take.tick = window.setInterval(() => {
      setSeconds(Math.max(0, (now() - take.startedAt) / 1000))
    }, 250)
    // The maximum: the recorder stops by itself.
    take.limit = window.setTimeout(stop, limits.max * 1000)
    setState({ status: 'recording' })
  }, [cancel, free, limits.max, revoke, stop, use])

  // Leaving the page: the microphone, the timers and the URL are released.
  useEffect(() => cancel, [cancel])

  return {
    status: state.status,
    reason: state.status === 'error' ? state.reason : null,
    clip: state.status === 'stopped' ? state.clip : null,
    tooShort: state.status === 'stopped' && state.tooShort,
    seconds,
    /** The long-take warning of free speaking (120 s): shown while recording past it. */
    warning: state.status === 'recording' && limits.warnAt !== null && seconds >= limits.warnAt,
    limits,
    start: () => void start(),
    stop,
    reset: cancel,
  }
}
