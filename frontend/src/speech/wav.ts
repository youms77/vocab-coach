/*
 * WAV 16 kHz mono 16-bit PCM, the format Azure's pronunciation assessment reads (D-211: it refuses
 * the webm that Chrome and Edge record). `encodeWav` is pure; `convertToWav` decodes and resamples
 * with the Web Audio API, which is read at every call (absent in jsdom, then `null`).
 */

export const WAV_SAMPLE_RATE = 16_000

/** Float samples (-1..1) to a complete WAV file: 44-byte header, then 16-bit little-endian PCM. */
export function encodeWav(samples: Float32Array, sampleRate = WAV_SAMPLE_RATE): Blob {
  const dataBytes = samples.length * 2
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i))
  }
  text(0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  text(36, 'data')
  view.setUint32(40, dataBytes, true)
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, Math.round(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff), true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

interface WebAudioGlobals {
  AudioContext?: new () => {
    decodeAudioData(data: ArrayBuffer): Promise<AudioBuffer>
    close(): Promise<void>
  }
  OfflineAudioContext?: new (channels: number, length: number, rate: number) => OfflineAudioContext
}

/** True when this browser can decode and resample (always in current browsers, never in jsdom). */
export function canConvertToWav(): boolean {
  const g = globalThis as WebAudioGlobals
  return typeof g.AudioContext === 'function' && typeof g.OfflineAudioContext === 'function'
}

/**
 * Decodes a recording (webm/opus, ogg, mp4) and returns it as WAV 16 kHz mono, or `null` when the
 * browser cannot (no Web Audio, undecodable data, empty result). The caller then keeps the original.
 */
export async function convertToWav(blob: Blob): Promise<Blob | null> {
  const g = globalThis as WebAudioGlobals
  if (!canConvertToWav() || g.AudioContext === undefined || g.OfflineAudioContext === undefined) {
    return null
  }
  const context = new g.AudioContext()
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer())
    if (decoded.length === 0) return null
    const length = Math.ceil(decoded.duration * WAV_SAMPLE_RATE)
    // One output channel: the engine mixes the channels down and resamples.
    const offline = new g.OfflineAudioContext(1, length, WAV_SAMPLE_RATE)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const rendered = await offline.startRendering()
    if (rendered.length === 0) return null
    return encodeWav(rendered.getChannelData(0))
  } catch {
    return null
  } finally {
    void context.close().catch(() => undefined)
  }
}
