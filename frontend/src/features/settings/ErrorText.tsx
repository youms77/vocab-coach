import { useTranslation } from 'react-i18next'

import { describeError } from './errorMessage'

/** A failed request, announced to screen readers. */
export function ErrorText({ error }: { error: unknown }) {
  const { t } = useTranslation()
  const { text, detail, reasons } = describeError(t, error)
  return (
    <div className="form-message form-message--error" role="alert">
      <p>{text}</p>
      {reasons.length > 0 && (
        <ul>
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {detail !== null && (
        <p className="muted" lang="en">
          {detail}
        </p>
      )}
    </div>
  )
}
