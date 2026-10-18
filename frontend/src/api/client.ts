/** Minimal JSON client for the local backend. All requests go through the /api prefix. */

/**
 * An error answer from the backend. `code` is the stable `detail.code` (D-063), mapped to an i18n
 * key by the page; `message` is the backend's English text. Both are null when the request never
 * reached the backend or the answer was not in the backend's error format.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly detail: Record<string, unknown>

  constructor(status: number, message: string, code: string | null = null, detail = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function errorFrom(response: Response, what: string): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Not JSON (e.g. a proxy error page): fall back to the status alone.
  }
  const detail =
    body !== null && typeof body === 'object' && 'detail' in body ? body.detail : undefined
  if (detail !== null && typeof detail === 'object' && 'code' in detail) {
    const fields = detail as Record<string, unknown>
    const message = typeof fields.message === 'string' ? fields.message : what
    return new ApiError(response.status, message, String(fields.code), fields)
  }
  return new ApiError(response.status, `${what} failed with ${response.status}`)
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    throw await errorFrom(response, `GET /api${path}`)
  }
  return (await response.json()) as T
}

/**
 * A write request. The body, when given, is sent as JSON (the backend refuses anything else).
 * `signal` stops waiting for the answer; the server may still finish the request.
 */
export async function apiSend<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    throw await errorFrom(response, `${method} /api${path}`)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
