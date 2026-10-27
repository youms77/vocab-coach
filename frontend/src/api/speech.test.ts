import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { apiErrorResponse, mockApi } from '../test/mockApi'
import { ApiError, apiUpload } from './client'
import { useShadowing, type SpeechOut } from './speech'

const SPEECH: SpeechOut = {
  production_id: 7,
  audio_url: '/api/productions/7/audio',
  audio_seconds: 3.2,
  transcription: { status: 'ok', text: 'we account for it', reason: null },
  comparison: null,
}

const clip = () => new Blob(['voice'], { type: 'audio/webm;codecs=opus' })

describe('apiUpload', () => {
  it('posts the Blob itself, with its own type, and the rest in the query string', async () => {
    const calls = mockApi({ 'POST /speech/shadowing': () => Response.json(SPEECH, { status: 201 }) })
    const blob = clip()
    const result = await apiUpload<SpeechOut>('/speech/shadowing', blob, {
      target_text: 'We account for it.',
      duration_s: 3.2,
      item_id: undefined,
      origin: 'shadowing',
    })

    expect(result.production_id).toBe(7)
    expect(calls).toHaveLength(1)
    const call = calls[0]!
    expect(call.method).toBe('POST')
    expect(call.body).toBe(blob)
    expect(call.headers['content-type']).toBe('audio/webm;codecs=opus')
    expect(call.path).toBe(
      '/speech/shadowing?target_text=We+account+for+it.&duration_s=3.2&origin=shadowing',
    )
  })

  it('sends no query string without parameters', async () => {
    const calls = mockApi({ 'POST /speech/review-answer': () => Response.json(SPEECH) })
    await apiUpload('/speech/review-answer', clip())
    expect(calls[0]!.path).toBe('/speech/review-answer')
  })

  it('answers with the same error as apiSend (code and detail kept)', async () => {
    mockApi({
      'POST /speech/shadowing': () =>
        apiErrorResponse(422, 'audio_too_short', 'too short', { min_s: 0.5, max_s: 30 }),
    })
    const error = await apiUpload('/speech/shadowing', clip(), {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(422)
    expect((error as ApiError).code).toBe('audio_too_short')
    expect((error as ApiError).detail).toMatchObject({ min_s: 0.5, max_s: 30 })
  })
})

describe('useShadowing', () => {
  it('sends the target, the measured duration and the origin', async () => {
    const calls = mockApi({ 'POST /speech/shadowing': () => Response.json(SPEECH, { status: 201 }) })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children)
    const { result } = renderHook(() => useShadowing(), { wrapper })

    result.current.mutate({
      blob: clip(),
      durationS: 4.5,
      target: 'We account for it.',
      itemId: 20,
      origin: 'discovery',
      studySessionId: 3,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const params = new URL(calls[0]!.path, 'http://x').searchParams
    expect(Object.fromEntries(params)).toEqual({
      target_text: 'We account for it.',
      duration_s: '4.5',
      item_id: '20',
      origin: 'discovery',
      study_session_id: '3',
    })
  })
})
