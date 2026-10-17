import { ApiError } from '../../api/client'

const WRAPPERS = new Set(['body', 'content'])

/**
 * The fields a 422 refused (`invalid_request`, `invalid_exercise`: `errors: [{loc, message}]`), with
 * the backend's English message. Never the value itself (the backend leaves it out).
 */
export function FieldErrors({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || !Array.isArray(error.detail.errors)) return null
  const errors = error.detail.errors as { loc?: unknown; message?: unknown }[]
  if (errors.length === 0) return null
  return (
    <ul className="field-errors" lang="en">
      {errors.map((e, index) => {
        const loc = Array.isArray(e.loc) ? e.loc.map(String).filter((p) => !WRAPPERS.has(p)) : []
        // Positions are 0-based in the backend: show them as the user counts rows.
        const where = loc.map((p) => (/^\d+$/.test(p) ? String(Number(p) + 1) : p)).join(' › ')
        return (
          <li key={index}>
            {where !== '' && <code>{where}</code>} {String(e.message ?? '')}
          </li>
        )
      })}
    </ul>
  )
}
