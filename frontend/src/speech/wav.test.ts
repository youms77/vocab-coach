import { afterEach, describe, expect, it, vi } from 'vitest'

import { canConvertToWav, convertToWav, encodeWav, WAV_SAMPLE_RATE } from './wav'

async function bytes(blob: Blob) {
  return new DataView(await blob.arrayBuffer())
}

describe('encodeWav', () => {
  it('writes a 16 kHz mono 16-bit PCM header the backend reads', async () => {
    const view = await bytes(encodeWav(new Float32Array(16_000)))
    const tag = (at: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => view.getUint8(at + i)))
    expect([tag(0), tag(8), tag(12), tag(36)]).toEqual(['RIFF', 'WAVE', 'fmt ', 'data'])
    expect(view.getUint16(20, true)).toBe(1)
    expect(view.getUint16(22, true)).toBe(1)
    expect(view.getUint32(24, true)).toBe(WAV_SAMPLE_RATE)
    expect(view.getUint16(34, true)).toBe(16)
    expect(view.getUint32(40, true)).toBe(32_000)
    expect(view.byteLength).toBe(44 + 32_000)
    expect(view.getUint32(4, true)).toBe(view.byteLength - 8)
  })

  it('clamps and scales the samples', async () => {
    const view = await bytes(encodeWav(new Float32Array([0, 1, -1, 2, -2, 0.5])))
    const sample = (i: number) => view.getInt16(44 + i * 2, true)
    expect([0, 1, 2, 3, 4].map(sample)).toEqual([0, 32767, -32768, 32767, -32768])
    expect(sample(5)).toBe(16384)
  })

  it('has the type audio/wav', () => {
    expect(encodeWav(new Float32Array(1)).type).toBe('audio/wav')
  })
})

describe('convertToWav', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns null without Web Audio (jsdom)', async () => {
    expect(canConvertToWav()).toBe(false)
    expect(await convertToWav(new Blob(['x']))).toBeNull()
  })

  it('decodes, resamples to 16 kHz and encodes', async () => {
    const rendered = { length: 8000, getChannelData: () => new Float32Array(8000).fill(0.25) }
    const offlineArgs: number[][] = []
    class Offline {
      destination = {}
      constructor(...args: number[]) {
        offlineArgs.push(args)
      }
      createBufferSource() {
        return { connect: vi.fn(), start: vi.fn(), buffer: null }
      }
      startRendering() {
        return Promise.resolve(rendered)
      }
    }
    class Context {
      decodeAudioData() {
        return Promise.resolve({ length: 24_000, duration: 0.5 })
      }
      close() {
        return Promise.resolve()
      }
    }
    vi.stubGlobal('AudioContext', Context)
    vi.stubGlobal('OfflineAudioContext', Offline)
    const wav = await convertToWav(new Blob(['webm']))
    expect(offlineArgs).toEqual([[1, 8000, 16_000]])
    expect(wav).not.toBeNull()
    expect((await bytes(wav as Blob)).getUint32(40, true)).toBe(16_000)
  })

  it('returns null when the data cannot be decoded', async () => {
    class Context {
      decodeAudioData() {
        return Promise.reject(new Error('bad'))
      }
      close() {
        return Promise.resolve()
      }
    }
    vi.stubGlobal('AudioContext', Context)
    vi.stubGlobal('OfflineAudioContext', class {})
    expect(await convertToWav(new Blob(['x']))).toBeNull()
  })
})
