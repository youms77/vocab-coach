import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type ProviderState, useCredentialMutation } from '../../api/ai'
import { ConnectionTest } from './ConnectionTest'
import { ErrorText } from './ErrorText'
import { Notice } from '../../components/Notice'

// The .env variable behind each provider (D-062). Names only, never values.
const VARIABLES: Record<ProviderState['name'], string> = {
  gemini: 'VOCAB_GEMINI_API_KEY',
  groq: 'VOCAB_GROQ_API_KEY',
  ollama: 'VOCAB_OLLAMA_BASE_URL',
}

function ProviderStateLine({ provider }: { provider: ProviderState }) {
  const { t, i18n } = useTranslation()

  let text: string
  let tone: 'ok' | 'warn' | 'down' | 'muted'
  if (!provider.configured) {
    text = t('settings.provider.state.notConfigured')
    tone = 'muted'
  } else if (provider.misconfigured) {
    text = t('settings.provider.state.misconfigured')
    tone = 'down'
  } else if (!provider.enabled) {
    text = t('settings.provider.state.disabled')
    tone = 'muted'
  } else if (provider.cooldown_until !== null) {
    const time = new Date(provider.cooldown_until).toLocaleTimeString(i18n.language, {
      hour: '2-digit',
      minute: '2-digit',
    })
    text = t('settings.provider.state.cooldown', { time })
    tone = 'warn'
  } else if (provider.available) {
    text = t('settings.provider.state.available')
    tone = 'ok'
  } else {
    text = t('settings.provider.state.unavailable')
    tone = 'warn'
  }
  return <p className={`status status--${tone}`}>{text}</p>
}

function CredentialForm({ provider, locked }: { provider: ProviderState; locked: boolean }) {
  const { t } = useTranslation()
  const mutation = useCredentialMutation(provider.name)
  const [value, setValue] = useState('')
  const [emptyError, setEmptyError] = useState(false)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [done, setDone] = useState<'saved' | 'removed' | null>(null)

  const isAddress = provider.credential_kind === 'base_url'
  const inputId = `credential-${provider.name}`
  const hintId = `${inputId}-hint`
  const fromEnvironment = provider.credential_source === 'environment'
  const disabled = locked || fromEnvironment || mutation.isPending

  function submit(event: FormEvent) {
    event.preventDefault()
    const trimmed = value.trim()
    if (trimmed === '') {
      setEmptyError(true)
      return
    }
    setEmptyError(false)
    setDone(null)
    mutation.mutate(trimmed, {
      onSuccess: () => {
        // The value never stays on the page once the backend has it.
        setValue('')
        setDone('saved')
      },
    })
  }

  function remove() {
    setConfirmingRemove(false)
    setDone(null)
    mutation.mutate(null, { onSuccess: () => setDone('removed') })
  }

  return (
    <form className="credential-form" onSubmit={submit} noValidate>
      <label htmlFor={inputId}>
        {isAddress ? t('settings.provider.addressLabel') : t('settings.provider.keyLabel')}
      </label>
      <div className="inline-fields">
        <input
          id={inputId}
          // A key is a password; an Ollama address is not secret (the owner's choice) but is
          // still never sent back by the API.
          type={isAddress ? 'url' : 'password'}
          value={value}
          onChange={(event) => {
            setValue(event.target.value)
            setEmptyError(false)
          }}
          placeholder={
            isAddress
              ? t('settings.provider.addressPlaceholder')
              : provider.configured
                ? t('settings.provider.keyPlaceholderReplace')
                : t('settings.provider.keyPlaceholderNew')
          }
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          disabled={disabled}
          aria-describedby={hintId}
          aria-invalid={emptyError || undefined}
        />
        <button type="submit" className="button button--primary" disabled={disabled}>
          {mutation.isPending ? t('settings.provider.saving') : t('settings.provider.save')}
        </button>
        {provider.credential_source === 'env_file' && !confirmingRemove && (
          <button
            type="button"
            className="button"
            onClick={() => setConfirmingRemove(true)}
            disabled={disabled}
          >
            {t('settings.provider.remove')}
          </button>
        )}
      </div>
      <p id={hintId} className="muted field-hint">
        {fromEnvironment
          ? t('settings.provider.environment', { variable: VARIABLES[provider.name] })
          : isAddress
            ? t('settings.provider.addressHint')
            : t('settings.provider.keyHint')}
      </p>
      {confirmingRemove && (
        <div className="confirm" role="group" aria-label={t('settings.provider.removeConfirm')}>
          <p>{t('settings.provider.removeConfirm')}</p>
          <button type="button" className="button button--danger" onClick={remove}>
            {t('settings.provider.removeYes')}
          </button>
          <button type="button" className="button" onClick={() => setConfirmingRemove(false)}>
            {t('settings.provider.cancel')}
          </button>
        </div>
      )}
      <div aria-live="polite">
        {emptyError && <Notice tone="danger">{t('settings.provider.emptyValue')}</Notice>}
        {done !== null && !mutation.isPending && !mutation.isError && (
          <Notice tone="success">
            {done === 'saved' ? t('settings.provider.savedKey') : t('settings.provider.removed')}
          </Notice>
        )}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </form>
  )
}

export function ProviderCard({ provider, locked }: { provider: ProviderState; locked: boolean }) {
  const { t } = useTranslation()
  const titleId = `provider-${provider.name}`

  return (
    <article className="provider-card" aria-labelledby={titleId}>
      <header className="provider-card__header">
        <h3 id={titleId}>{t(`settings.provider.names.${provider.name}`)}</h3>
        <ProviderStateLine provider={provider} />
      </header>
      {provider.last_error !== null && (
        <p className="muted">
          {t('settings.provider.lastError', {
            error: t(`settings.errorKinds.${provider.last_error}`),
          })}
        </p>
      )}
      <dl className="provider-card__models">
        <dt>{t('settings.provider.models')}</dt>
        {Object.entries(provider.models).map(([capability, model]) => (
          <dd key={capability}>
            {capability === 'text' || capability === 'transcription'
              ? t(`settings.provider.capabilities.${capability}`)
              : capability}
            {': '}
            <code>{model}</code>
          </dd>
        ))}
      </dl>
      <CredentialForm provider={provider} locked={locked} />
      <ConnectionTest provider={provider.name} configured={provider.configured} disabled={locked} />
    </article>
  )
}
