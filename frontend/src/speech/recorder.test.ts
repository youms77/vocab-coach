import { afterEach, describe, expect, it } from 'vitest'

import { installFakeRecorder, uninstallFakeRecorder } from '../test/fakeRecorder'
import {
  AUDIO_TYPES,
  failureReason,
  formatClock,
  isTooShort,
  LIMITS,
  MAX_UPLOAD_BYTES,
  pickAudioType,
  reportedDuration,
  unsupportedReason,
} from './recorder'

describe('pickAudioType', () => {
  it('takes the first accepted type, in the documented order', () => {
    expect(pickAudioType(() => true)).toBe('audio/webm;codecs=opus')
    expect(pickAudioType((type) => type !== 'audio/webm;codecs=opus')).toBe('audio/webm')
    expect(pickAudioType((type) => type.startsWith('audio/ogg'))).toBe('audio/ogg;codecs=opus')
    expect(pickAudioType((type) => type === 'audio/mp4')).toBe('audio/mp4')
    expect(AUDIO_TYPES).toEqual([
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ])
  })

  it('gives null when nothing is accepted (the browser then picks)', () => {
    expect(pickAudioType(() => false)).toBeNull()
  })
})

describe('bounds', () => {
  it('follow the backend per use', () => {
    expect(LIMITS.shadowing).toEqual({ min: 0.5, max: 30, warnAt: null })
    expect(LIMITS.speaking).toEqual({ min: 5, max: 180, warnAt: 120 })
    expect(LIMITS.spoken_answer).toEqual({ min: 1, max: 90, warnAt: null })
    expect(MAX_UPLOAD_BYTES).toBe(10 * 1024 * 1024)
  })

  it('tell a take that is too short', () => {
    expect(isTooShort(0.4, 'shadowing')).toBe(true)
    expect(isTooShort(0.5, 'shadowing')).toBe(false)
    expect(isTooShort(4.9, 'speaking')).toBe(true)
    expect(isTooShort(0.9, 'spoken_answer')).toBe(true)
  })

  it('never report more than the maximum (a timer fires late)', () => {
    expect(reportedDuration(30.04, 'shadowing')).toBe(30)
    expect(reportedDuration(12.3456, 'shadowing')).toBe(12.35)
    expect(reportedDuration(-1, 'shadowing')).toBe(0)
  })
})

describe('failureReason', () => {
  it('reads the error name', () => {
    expect(failureReason(new DOMException('x', 'NotAllowedError'))).toBe('denied')
    expect(failureReason(new DOMException('x', 'NotFoundError'))).toBe('no_device')
    expect(failureReason(new DOMException('x', 'NotReadableError'))).toBe('busy')
    expect(failureReason(new DOMException('x', 'AbortError'))).toBe('busy')
    expect(failureReason(new Error('boom'))).toBe('failed')
    expect(failureReason(null)).toBe('failed')
  })
})

describe('formatClock', () => {
  it('shows minutes and seconds', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(42.9)).toBe('0:42')
    expect(formatClock(125)).toBe('2:05')
  })
})

describe('unsupportedReason', () => {
  afterEach(() => uninstallFakeRecorder())

  it('is read at every call: unsupported without MediaRecorder, then fine with the fake', () => {
    expect(unsupportedReason()).toBe('unsupported')
    installFakeRecorder()
    expect(unsupportedReason()).toBeNull()
    uninstallFakeRecorder()
    expect(unsupportedReason()).toBe('unsupported')
  })

  it('is unsupported without getUserMedia', () => {
    installFakeRecorder()
    Object.defineProperty(navigator, 'mediaDevices', { value: {}, configurable: true })
    expect(unsupportedReason()).toBe('unsupported')
  })
})
