import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import { MAX_PASTED_CHARS } from '../../api/transcripts'
import { ErrorText } from '../settings/ErrorText'
import { TranscriptPreviewView } from './TranscriptPreviewView'
import type { TranscriptInput } from './useTranscriptInput'

/**
 * The text area, the "Preview" button and the preview with the choice of your turns. Over the
 * limit, a visible message and a disabled button, no request, and no `maxLength` (it would cut a
 * paste without saying so).
 */
export function TranscriptInputForm({
  input,
  readOnly = false,
  label,
}: {
  input: TranscriptInput
  readOnly?: boolean
  label?: string
}) {
  const { t } = useTranslation()
  const fieldId = useId()
  const countId = useId()
  return (
    <>
      <div className="field">
        <label htmlFor={fieldId}>{label ?? t('transcripts.paste.label')}</label>
        <textarea
          id={fieldId}
          lang="en"
          rows={12}
          value={input.text}
          onChange={(event) => input.setText(event.target.value)}
          readOnly={readOnly}
          aria-describedby={countId}
          aria-invalid={input.tooLong}
        />
        <p id={countId} className={`field-hint${input.tooLong ? ' field-hint--error' : ''}`}>
          {t('transcripts.paste.chars', { chars: input.chars, max: MAX_PASTED_CHARS })}
        </p>
        {input.tooLong && (
          <p className="form-message form-message--error" role="alert">
            {t('transcripts.paste.tooLong', { chars: input.chars, max: MAX_PASTED_CHARS })}
          </p>
        )}
      </div>
      <p>
        <button
          type="button"
          className="button"
          disabled={input.empty || input.tooLong || input.pending || readOnly}
          onClick={input.showPreview}
        >
          {input.pending ? t('transcripts.paste.previewing') : t('transcripts.paste.preview')}
        </button>
      </p>
      {input.error !== null && <ErrorText error={input.error} />}
      {input.stale && (
        <p className="form-message form-message--warn" role="status">
          {t('transcripts.paste.stale')}
        </p>
      )}
      {input.preview !== null && (
        <TranscriptPreviewView
          preview={input.preview}
          user={input.user}
          pending={input.pending || readOnly}
          onChoose={input.choose}
        />
      )}
    </>
  )
}
