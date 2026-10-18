import { useTranslation } from 'react-i18next'

import { type ConnectionTestResult, type ProviderName, useConnectionTest } from '../../api/ai'
import { useElapsedSeconds } from '../../components/useElapsedSeconds'
import { ErrorText } from './ErrorText'

function seconds(ms: number, language: string) {
  return new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(ms / 1000)
}

function TestOutcome({ result }: { result: ConnectionTestResult }) {
  const { t, i18n } = useTranslation()
  const time = seconds(result.elapsed_ms, i18n.language)

  if (result.status === 'ok') {
    return (
      <div className="form-message form-message--ok">
        <p>{t('settings.test.ok', { model: result.model ?? '?', seconds: time })}</p>
        {result.input_tokens !== null && result.output_tokens !== null && (
          <p className="muted">
            {t('settings.test.tokens', { input: result.input_tokens, output: result.output_tokens })}
          </p>
        )}
      </div>
    )
  }
  return (
    <div className="form-message form-message--error">
      <p>
        {result.status === 'incomplete'
          ? t('settings.test.incomplete', { seconds: time })
          : t('settings.test.unavailable', {
              reason: t(`settings.test.reasons.${result.reason ?? 'all_failed'}`),
            })}
      </p>
      {result.http_status !== null && (
        <p className="muted">{t('settings.test.httpStatus', { status: result.http_status })}</p>
      )}
      {result.message !== null && (
        <details>
          <summary>{t('settings.test.details')}</summary>
          <p lang="en" className="provider-message">
            {result.message}
          </p>
        </details>
      )}
    </div>
  )
}

/** "Test connection": one real call to the provider, which can take up to ~90 s (D-064). */
export function ConnectionTest({
  provider,
  configured,
  disabled,
}: {
  provider: ProviderName
  configured: boolean
  disabled: boolean
}) {
  const { t } = useTranslation()
  const test = useConnectionTest(provider)
  const elapsed = useElapsedSeconds(test.isPending, test.submittedAt)
  const hintId = `test-hint-${provider}`

  return (
    <div className="connection-test">
      <button
        type="button"
        className="button"
        onClick={() => test.mutate()}
        // A second click would spend the free quota twice: the backend refuses it too (409).
        disabled={disabled || !configured || test.isPending}
        aria-describedby={hintId}
      >
        {test.isPending ? t('settings.test.running', { seconds: elapsed }) : t('settings.test.button')}
      </button>
      <p id={hintId} className="muted field-hint">
        {configured ? t('settings.test.runningHint') : t('settings.test.needsCredential')}
      </p>
      <div aria-live="polite">
        {test.isPending && <span className="spinner" aria-hidden="true" />}
        {test.isSuccess && <TestOutcome result={test.data} />}
        {test.isError && <ErrorText error={test.error} />}
      </div>
    </div>
  )
}
