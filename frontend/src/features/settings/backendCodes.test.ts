/// <reference types="node" />
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'
import { describeError } from './errorMessage'

// M10.c1 (D-323): every error code the backend can answer (D-063) has a sentence in both
// languages, so the interface never shows the backend's English text instead of a translation.

const BACKEND = join(import.meta.dirname, '..', '..', '..', '..', 'backend', 'app')

function pythonFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== '__pycache__') pythonFiles(path, out)
    } else if (entry.name.endsWith('.py')) {
      out.push(path)
    }
  }
  return out
}

/** Codes that are never an HTTP error code, with the reason. */
const NOT_HTTP_CODES: ReadonlyMap<string, string> = new Map([
  ['task_open', 'a reason of `not_ready` (translated as consolidation.reasons.*), and a CLI message'],
])

function backendCodes(): string[] {
  const codes = new Set<string>()
  const patterns = [
    /status,\s*code\s*=\s*\d+,\s*"([a-z_0-9]+)"/g, // class Foo(LibraryError): status, code = 409, "x"
    /api_error\(\s*[\w.]+,\s*"([a-z_0-9]+)"/g, // raise api_error(422, "x", ...)
    /"code":\s*"([a-z_0-9]+)"/g, // a hand-built detail
  ]
  for (const file of pythonFiles(BACKEND)) {
    const source = readFileSync(file, 'utf8')
    for (const pattern of patterns) {
      for (const match of source.matchAll(pattern)) codes.add(match[1]!)
    }
  }
  return [...codes].filter((code) => !NOT_HTTP_CODES.has(code)).sort()
}

const t = ((key: string) => key) as never

describe('backend error codes', () => {
  const codes = backendCodes()

  it('are found in the backend sources', () => {
    expect(codes.length).toBeGreaterThan(50)
  })

  it('all have a translated sentence in both languages', () => {
    const missing: string[] = []
    const has = (tree: Record<string, unknown>, code: string) =>
      typeof (tree.errors as Record<string, unknown>)[code] === 'string'
    for (const code of codes) {
      // Some codes are said by their own page (consolidation.reasons.*, transcripts.*): they still
      // go through describeError, which returns the generic sentence when nothing is known.
      const described = describeError(t, new ApiError(400, 'English text', code)).text
      if (described === 'errors.unknown_code') missing.push(code)
      else if (!has(en, code) || !has(fr, code)) missing.push(`${code} (no errors.${code})`)
    }
    expect(missing).toEqual([])
  })

  it('an unknown code gives the generic sentence, with the English text underneath', () => {
    const described = describeError(t, new ApiError(418, 'I am a teapot', 'teapot'))
    expect(described.text).toBe('errors.unknown_code')
    expect(described.detail).toBe('I am a teapot')
  })

  it('a failed request without a code keeps the HTTP status sentence', () => {
    expect(describeError(t, new ApiError(500, 'Boom')).text).toBe('errors.unexpected')
  })
})
