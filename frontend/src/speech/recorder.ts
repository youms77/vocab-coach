/*
 * Pure rules of the voice recorder (D-193). The browser objects (`navigator.mediaDevices`,
 * `MediaRecorder`) are read on every call, never cached, so a browser without them (or jsdom)
 * reports `unsupported` and a test can install a fake.
 */

/** What a recording is for; the bounds follow the backend's `DURATION_BOUNDS` (D-179). */
export type RecordingUse = 'shadowing' | 'speaking' | 'spoken_answer' | 'consolidation'

export interface Limits {
  /** Seconds. A shorter take is not sent. */
  min: number
  /** Seconds. The recorder stops by itself here. */
  max: number
  /** Seconds. A visible warning from here on, when set. */
  warnAt: number | null
}

export const LIMITS: Record<RecordingUse, Limits> = {
  shadowing: { min: 0.5, max: 30, warnAt: null },
  speaking: { min: 5, max: 180, warnAt: 120 },
  spoken_answer: { min: 1, max: 90, warnAt: null },
  consolidation: { min: 20, max: 240, warnAt: 200 },
}

/** The backend refuses a body over 10 MB (413 `audio_too_large`); the client checks first. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

/** Tried in this order; the backend accepts these types and ignores their parameters (D-169). */
export const AUDIO_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
] as const

/** The first type `isSupported` accepts, or null (the browser then picks its own default). */
export function pickAudioType(isSupported: (type: string) => boolean): string | null {
  return AUDIO_TYPES.find((type) => isSupported(type)) ?? null
}

export type FailureReason = 'unsupported' | 'denied' | 'no_device' | 'busy' | 'failed'

/** Why `getUserMedia` (or the recorder) failed, from the error's name. */
export function failureReason(error: unknown): FailureReason {
  const name =
    typeof error === 'object' && error !== null && 'name' in error ? String(error.name) : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'denied'
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'no_device'
  if (name === 'NotReadableError' || name === 'AbortError') return 'busy'
  return 'failed'
}

/** `unsupported` when this browser cannot record at all; read again at every call. */
export function unsupportedReason(): FailureReason | null {
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices
  const recorder = (globalThis as { MediaRecorder?: unknown }).MediaRecorder
  if (typeof recorder !== 'function') return 'unsupported'
  if (devices === undefined || typeof devices.getUserMedia !== 'function') return 'unsupported'
  return null
}

/** `performance.now()` in milliseconds (the recorder's clock; one place to fake it). */
export function now(): number {
  return performance.now()
}

export function isTooShort(seconds: number, use: RecordingUse): boolean {
  return seconds < LIMITS[use].min
}

/** The duration to send: never above the maximum (a timer fires a few milliseconds late). */
export function reportedDuration(seconds: number, use: RecordingUse): number {
  return Math.round(Math.min(Math.max(seconds, 0), LIMITS[use].max) * 100) / 100
}

/** `0:42`, `12:05`. */
export function formatClock(totalSeconds: number): string {
  const whole = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(whole / 60)
  const seconds = String(whole % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}
