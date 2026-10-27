import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type SpeechProviderState, useAiStatus, useCredentialMutation } from '../../api/ai'
import { usePronunciationUsage } from '../../api/pronunciation'
import { useSettings, useSettingsMutation } from '../../api/settings'
import { ConnectionTest } from './ConnectionTest'
import { ErrorText } from './ErrorText'

function CredentialForm({ azure, locked }: { azure: SpeechProviderState; locked: boolean }) {
  const { t } = useTranslation()
  const mutation = useCredentialMutation('azure')
  const [key, setKey] = useState('')
  const [region, setRegion] = useState(azure.region ?? '')
  const [problem, setProblem] = useState<'key' | 'region' | null>(null)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [done, setDone] = useState<'saved' | 'removed' | null>(null)
  const fromEnvironment = azure.credential_source === 'environment'
  const disabled = locked || fromEnvironment || mutation.isPending

  function submit(event: FormEvent) {
    event.preventDefault()
    setDone(null)
    if (key.trim() === '') return setProblem('key')
    if (region.trim() === '') return setProblem('region')
    setProblem(null)
    mutation.mutate(
      { value: key.trim(), region: region.trim() },
      {
        onSuccess: () => {
          // The key never stays on the page once the backend has it.
          setKey('')
          setDone('saved')
        },
      },
    )
  }

  function remove() {
    setConfirmingRemove(false)
    setDone(null)
    mutation.mutate(null, {
      onSuccess: () => {
        setRegion('')
        setDone('removed')
      },
    })
  }

  return (
    <form className="credential-form" onSubmit={submit} noValidate>
      <label htmlFor="azure-key">{t('settings.azure.keyLabel')}</label>
      <input
        id="azure-key"
        type="password"
        value={key}
        onChange={(event) => {
          setKey(event.target.value)
          setProblem(null)
        }}
        placeholder={
          azure.configured
            ? t('settings.provider.keyPlaceholderReplace')
            : t('settings.provider.keyPlaceholderNew')
        }
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        disabled={disabled}
        aria-invalid={problem === 'key' || undefined}
      />
      <label htmlFor="azure-region">{t('settings.azure.regionLabel')}</label>
      <div className="inline-fields">
        <input
          id="azure-region"
          type="text"
          value={region}
          onChange={(event) => {
            setRegion(event.target.value)
            setProblem(null)
          }}
          placeholder={t('settings.azure.regionPlaceholder')}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          disabled={disabled}
          aria-describedby="azure-region-hint"
          aria-invalid={problem === 'region' || undefined}
        />
        <button type="submit" className="button button--primary" disabled={disabled}>
          {mutation.isPending ? t('settings.provider.saving') : t('settings.provider.save')}
        </button>
        {azure.credential_source === 'env_file' && !confirmingRemove && (
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
      <p id="azure-region-hint" className="muted field-hint">
        {fromEnvironment
          ? t('settings.provider.environment', { variable: 'VOCAB_AZURE_SPEECH_KEY' })
          : t('settings.azure.regionHint')}
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
        {problem !== null && (
          <p className="form-message form-message--error">
            {problem === 'key' ? t('settings.azure.keyRequired') : t('settings.azure.regionRequired')}
          </p>
        )}
        {done !== null && !mutation.isPending && !mutation.isError && (
          <p className="form-message form-message--ok">
            {done === 'saved' ? t('settings.provider.savedKey') : t('settings.provider.removed')}
          </p>
        )}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </form>
  )
}

function EnableSetting({ azure, locked }: { azure: SpeechProviderState; locked: boolean }) {
  const { t } = useTranslation()
  const settings = useSettings()
  const mutation = useSettingsMutation()
  const [saved, setSaved] = useState(false)
  const info = settings.data?.pronunciation_assessment
  if (info === undefined) return null
  const on = info.value === 'azure'

  return (
    <div className="field">
      <label className="checkbox-row" htmlFor="azure-enable">
        <input
          id="azure-enable"
          type="checkbox"
          checked={on}
          disabled={locked || mutation.isPending || (!azure.configured && !on)}
          aria-describedby="azure-enable-hint"
          onChange={(event) => {
            setSaved(false)
            mutation.mutate(
              { pronunciation_assessment: event.target.checked ? 'azure' : 'off' },
              { onSuccess: () => setSaved(true) },
            )
          }}
        />{' '}
        {t('settings.azure.enableLabel')}
      </label>
      <p id="azure-enable-hint" className="muted field-hint">
        {t('settings.azure.enableHint')}{' '}
        {!azure.configured && !on && t('settings.azure.enableNeedsKey')}
      </p>
      <div aria-live="polite">
        {saved && !mutation.isPending && !mutation.isError && (
          <p className="form-message form-message--ok">{t('settings.azure.enableSaved')}</p>
        )}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </div>
  )
}

function Usage() {
  const { t, i18n } = useTranslation()
  const usage = usePronunciationUsage()
  if (usage.isPending) return null
  if (usage.isError) {
    return <p className="form-message form-message--error">{t('settings.azure.usageError')}</p>
  }
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 })
  return (
    <div>
      <h3>{t('settings.azure.usageTitle')}</h3>
      <p>
        {t('settings.azure.usage', {
          minutes: number.format(usage.data.audio_seconds / 60),
          count: usage.data.assessments,
          month: usage.data.month,
          limit: number.format(usage.data.limit_seconds / 60),
          checked: usage.data.limit_checked_on,
        })}
      </p>
      <p className="muted field-hint">{t('settings.azure.usageNote')}</p>
    </div>
  )
}

/** The optional Azure card (M6.c2): key + region, test, the setting, the monthly use (D-214, D-216). */
export function AzureCard() {
  const { t } = useTranslation()
  const status = useAiStatus()
  const azure = status.data?.speech_providers?.find((p) => p.name === 'azure')
  if (azure === undefined) return null
  const locked = status.data?.demo ?? false

  return (
    <section className="card" aria-labelledby="azure-title" id="azure">
      <h2 id="azure-title">{t('settings.azure.title')}</h2>
      <p className="muted">{t('settings.azure.intro')}</p>
      <p className="form-message form-message--warn">{t('settings.azure.privacy')}</p>
      {locked && <p className="form-message form-message--warn">{t('settings.azure.demoNote')}</p>}
      <p className={`status status--${azure.configured ? 'ok' : 'muted'}`}>
        {azure.configured
          ? t('settings.azure.regionCurrent', { region: azure.region ?? '?' })
          : t('settings.provider.state.notConfigured')}
      </p>
      <CredentialForm azure={azure} locked={locked} />
      <ConnectionTest provider="azure" configured={azure.configured} disabled={locked} />
      <EnableSetting azure={azure} locked={locked} />
      {azure.configured && <Usage />}
    </section>
  )
}
