import { vi } from 'vitest'

export interface RecordedCall {
  method: string
  path: string
  headers: Record<string, string>
  body: unknown
}

type Handler = (call: RecordedCall) => Response | Promise<Response>

/**
 * Replaces fetch with a small router: `routes['GET /ai/status'] = () => Response.json(...)`.
 * Paths are matched without the `/api` prefix and without the query string. An unknown route
 * answers 404, so a forgotten mock fails visibly.
 */
export function mockApi(routes: Record<string, Handler | object>) {
  const calls: RecordedCall[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://127.0.0.1:5173')
    const path = url.pathname.replace(/^\/api/, '')
    const method = init?.method ?? 'GET'
    const headers = Object.fromEntries(new Headers(init?.headers).entries())
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined
    const call = { method, path: path + url.search, headers, body }
    calls.push(call)
    const route = routes[`${method} ${path}`]
    if (route === undefined) return Response.json({ detail: 'Not Found' }, { status: 404 })
    const answer = Promise.resolve(
      typeof route === 'function' ? (route as Handler)(call) : Response.json(route),
    )
    const signal = init?.signal
    if (signal === undefined || signal === null) return answer
    // Like fetch: an aborted request rejects with an AbortError, even if the route never answers.
    const aborted = new Promise<never>((_, reject) => {
      const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'))
      if (signal.aborted) abort()
      else signal.addEventListener('abort', abort, { once: true })
    })
    return Promise.race([answer, aborted])
  })
  return calls
}

/** An error answer in the backend's format (D-063). */
export function apiErrorResponse(status: number, code: string, message = code, extra = {}) {
  return Response.json({ detail: { code, message, ...extra } }, { status })
}
