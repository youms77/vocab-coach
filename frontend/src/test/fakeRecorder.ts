import { act, screen } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'
import { type MockInstance, vi } from 'vitest'

/*
 * jsdom has no microphone. This fake stands in for `navigator.mediaDevices.getUserMedia`,
 * `MediaRecorder`, `URL.createObjectURL` and the audio element's `play()`: the permission can be
 * refused with each kind of error or held pending, the recorder's `dataavailable` and `stop` events
 * are fired by the test, and every track records its `stop()` (the microphone indicator).
 */

export class FakeTrack {
  stopCount = 0

  get stopped() {
    return this.stopCount > 0
  }

  stop() {
    this.stopCount += 1
  }
}

export class FakeStream {
  tracks = [new FakeTrack()]

  getTracks() {
    return this.tracks
  }
}

export class FakeMediaRecorder extends EventTarget {
  /** The types `isTypeSupported` accepts (set by `installFakeRecorder`). */
  static supported: string[] = []
  static instances: FakeMediaRecorder[] = []

  static isTypeSupported(type: string) {
    return FakeMediaRecorder.supported.includes(type)
  }

  state: 'inactive' | 'recording' = 'inactive'
  mimeType: string
  timeslice: number | undefined
  readonly stream: FakeStream

  constructor(stream: FakeStream, options?: { mimeType?: string }) {
    super()
    this.stream = stream
    // Like the browsers: without a type, the recorder reports the one it chose.
    this.mimeType = options?.mimeType ?? 'audio/webm;codecs=opus'
    FakeMediaRecorder.instances.push(this)
  }

  start(timeslice?: number) {
    this.state = 'recording'
    this.timeslice = timeslice
    this.dispatchEvent(new Event('start'))
  }

  /** Like the browsers, stopping a recorder that is not recording throws. */
  stop() {
    if (this.state === 'inactive') throw new DOMException('Not recording', 'InvalidStateError')
    this.state = 'inactive'
  }

  /** A chunk arrived (wrap in `act`). */
  emitData(blob: Blob) {
    this.dispatchEvent(Object.assign(new Event('dataavailable'), { data: blob }))
  }

  /** The recorder ended: the last chunk, then `stop` (wrap in `act`). */
  finish(blob: Blob = new Blob(['voice'], { type: this.mimeType })) {
    this.emitData(blob)
    this.dispatchEvent(new Event('stop'))
  }
}

export interface PendingPermission {
  allow: () => void
  refuse: (name: string) => void
}

export interface RecorderKit {
  getUserMedia: ReturnType<typeof vi.fn>
  streams: FakeStream[]
  createdUrls: string[]
  revokedUrls: string[]
  play: ReturnType<typeof vi.fn>
  pause: ReturnType<typeof vi.fn>
  /** The recorder created last, or null. */
  recorder: () => FakeMediaRecorder | null
  /** The next `getUserMedia` fails with this `DOMException` name. */
  refuseNext: (name: string) => void
  /** The next `getUserMedia` waits until the test allows or refuses it. */
  holdNext: () => PendingPermission
  /** Moves the recorder's clock (`performance.now()`) forward, in milliseconds. */
  advance: (ms: number) => void
}

interface Saved {
  mediaDevices: PropertyDescriptor | undefined
  mediaRecorder: unknown
  hadMediaRecorder: boolean
  createObjectURL: unknown
  revokeObjectURL: unknown
  play: unknown
  pause: unknown
  clock: MockInstance<() => number> | null
}

let saved: Saved | null = null

export const OPUS = 'audio/webm;codecs=opus'

export function installFakeRecorder(supported: string[] = [OPUS, 'audio/webm']): RecorderKit {
  uninstallFakeRecorder()
  const target = globalThis as unknown as Record<string, unknown>
  const media = HTMLMediaElement.prototype as unknown as Record<string, unknown>
  saved = {
    mediaDevices: Object.getOwnPropertyDescriptor(navigator, 'mediaDevices'),
    mediaRecorder: target.MediaRecorder,
    hadMediaRecorder: 'MediaRecorder' in target,
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
    play: media.play,
    pause: media.pause,
    clock: null,
  }

  FakeMediaRecorder.supported = supported
  FakeMediaRecorder.instances = []
  const streams: FakeStream[] = []
  const createdUrls: string[] = []
  const revokedUrls: string[] = []
  let refusal: string | null = null
  let heldPromise: Promise<FakeStream> | null = null

  const getUserMedia = vi.fn((): Promise<FakeStream> => {
    if (heldPromise !== null) {
      const promise = heldPromise
      heldPromise = null
      return promise
    }
    if (refusal !== null) {
      const name = refusal
      refusal = null
      return Promise.reject(new DOMException('refused', name))
    }
    const stream = new FakeStream()
    streams.push(stream)
    return Promise.resolve(stream)
  })

  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
  })
  target.MediaRecorder = FakeMediaRecorder
  URL.createObjectURL = vi.fn(() => {
    const url = `blob:fake-${createdUrls.length + 1}`
    createdUrls.push(url)
    return url
  })
  URL.revokeObjectURL = vi.fn((url: string) => {
    revokedUrls.push(url)
  })
  const play = vi.fn(() => Promise.resolve())
  const pause = vi.fn()
  media.play = play
  media.pause = pause
  // The recorder measures the duration with performance.now(): the tests move that clock by hand.
  let clock = 0
  saved.clock = vi.spyOn(performance, 'now').mockImplementation(() => clock)

  return {
    getUserMedia,
    streams,
    createdUrls,
    revokedUrls,
    play,
    pause,
    recorder: () => FakeMediaRecorder.instances.at(-1) ?? null,
    refuseNext: (name) => {
      refusal = name
    },
    advance: (ms) => {
      clock += ms
    },
    holdNext: () => {
      let allow = () => {}
      let refuse = (_name: string) => {}
      heldPromise = new Promise<FakeStream>((resolve, reject) => {
        allow = () => {
          const stream = new FakeStream()
          streams.push(stream)
          resolve(stream)
        }
        refuse = (name) => reject(new DOMException('refused', name))
      })
      return { allow, refuse }
    },
  }
}

export function uninstallFakeRecorder() {
  if (saved === null) return
  const target = globalThis as unknown as Record<string, unknown>
  const media = HTMLMediaElement.prototype as unknown as Record<string, unknown>
  if (saved.mediaDevices !== undefined) {
    Object.defineProperty(navigator, 'mediaDevices', saved.mediaDevices)
  } else {
    delete (navigator as unknown as Record<string, unknown>).mediaDevices
  }
  if (saved.hadMediaRecorder) target.MediaRecorder = saved.mediaRecorder
  else delete target.MediaRecorder
  URL.createObjectURL = saved.createObjectURL as typeof URL.createObjectURL
  URL.revokeObjectURL = saved.revokeObjectURL as typeof URL.revokeObjectURL
  media.play = saved.play
  media.pause = saved.pause
  saved.clock?.mockRestore()
  saved = null
  FakeMediaRecorder.instances = []
}

/**
 * Starts a take, lets `ms` go by, stops it and lets the recorder end, so that the "Send" button
 * is there (the page's own button, a test then clicks it).
 */
export async function recordTake(
  user: ReturnType<typeof userEvent.setup>,
  kit: RecorderKit,
  options: { ms?: number; blob?: Blob } = {},
) {
  await user.click(screen.getByRole('button', { name: 'Start recording' }))
  const stop = await screen.findByRole('button', { name: 'Stop recording' })
  kit.advance(options.ms ?? 2000)
  await user.click(stop)
  act(() => kit.recorder()?.finish(options.blob))
  await screen.findByRole('button', { name: 'Send' })
}
