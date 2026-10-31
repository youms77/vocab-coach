import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import en from '../../i18n/locales/en.json'

const WRAPPERS = new Set(['body', 'content'])

type FieldErrorType = keyof typeof en.fieldErrors

function isFieldErrorType(type: unknown): type is FieldErrorType {
  return typeof type === 'string' && Object.hasOwn(en.fieldErrors, type)
}

/**
 * The fields a 422 refused (`invalid_request`, `invalid_exercise`: `errors: [{loc, message, type}]`).
 * The sentence comes from the stable `type` in the interface language (D-324); a type this version
 * does not know keeps the backend's English `message`. Never the value itself (the backend leaves
 * it out).
 */
export function FieldErrors({ error }: { error: unknown }) {
  const { t } = useTranslation()
  if (!(error instanceof ApiError) || !Array.isArray(error.detail.errors)) return null
  const errors = error.detail.errors as { loc?: unknown; message?: unknown; type?: unknown }[]
  if (errors.length === 0) return null
  return (
    <ul className="field-errors">
      {errors.map((e, index) => {
        const loc = Array.isArray(e.loc) ? e.loc.map(String).filter((p) => !WRAPPERS.has(p)) : []
        // Positions are 0-based in the backend: show them as the user counts rows.
        const where = loc.map((p) => (/^\d+$/.test(p) ? String(Number(p) + 1) : p)).join(' › ')
        const known = isFieldErrorType(e.type)
        return (
          <li key={index}>
            {where !== '' && <code>{where}</code>}{' '}
            {known ? (
              t(`fieldErrors.${e.type as FieldErrorType}`)
            ) : (
              <span lang="en">{String(e.message ?? '')}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
