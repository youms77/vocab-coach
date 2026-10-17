import type { TFunction } from 'i18next'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import {
  type SettingInfo,
  type SettingsMap,
  type SettingValue,
  useSettings,
  useSettingsMutation,
} from '../../api/settings'
import { ErrorText } from './ErrorText'
import { VoiceSetting } from './VoiceSetting'

// The settings shown here, by group. `ai_provider_order` has its own card; `ui_language` is left
// out on purpose: the language is chosen in the top bar and stored in the browser (D-066).
const GROUPS = [
  { id: 'study', keys: ['daily_time_budget_minutes', 'new_items_per_day', 'target_retention'] },
  { id: 'schedule', keys: ['timezone', 'day_start_hour'] },
  { id: 'consolidation', keys: ['consolidation_share', 'consolidation_min_stability_days'] },
  { id: 'audio', keys: ['tts_rate'] },
] as const

type Group = (typeof GROUPS)[number]
type FieldKey = Group['keys'][number]

// Spin-button steps for the float settings; integers step by 1.
const STEPS: Partial<Record<FieldKey, number>> = {
  target_retention: 0.01,
  consolidation_share: 0.05,
  tts_rate: 0.1,
}

function display(value: SettingValue, language: string) {
  return typeof value === 'number' ? new Intl.NumberFormat(language).format(value) : String(value)
}

/** The value to send, or the translated reason it cannot be sent. */
function parse(
  t: TFunction,
  info: SettingInfo,
  raw: string,
): { value: SettingValue } | { error: string } {
  const text = raw.trim()
  if (text === '') return { error: t('settings.general.required') }
  if (info.type === 'str') return { value: text }
  if (info.type === 'int' && !/^-?\d+$/.test(text)) {
    return { error: t('settings.general.notAnInteger') }
  }
  const number = Number(text)
  if (!Number.isFinite(number)) return { error: t('settings.general.notANumber') }
  if (
    (info.minimum !== null && number < info.minimum) ||
    (info.maximum !== null && number > info.maximum)
  ) {
    return { error: t('settings.general.outOfRange') }
  }
  return { value: number }
}

function rangeHint(t: TFunction, info: SettingInfo, language: string) {
  if (info.minimum !== null && info.maximum !== null) {
    return t('settings.general.range', {
      min: display(info.minimum, language),
      max: display(info.maximum, language),
    })
  }
  if (info.minimum !== null) {
    return t('settings.general.atLeast', { min: display(info.minimum, language) })
  }
  return null
}

function GroupForm({ group, settings }: { group: Group; settings: SettingsMap }) {
  const { t, i18n } = useTranslation()
  const mutation = useSettingsMutation()
  const keys = group.keys.filter((key) => key in settings)
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(keys.map((key) => [key, String(settings[key].value)])),
  )
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  const changed = keys.filter((key) => draft[key] !== String(settings[key].value))
  const serverKey =
    mutation.error instanceof ApiError && mutation.error.code === 'invalid_setting'
      ? String(mutation.error.detail.key ?? '')
      : null

  function submit(event: FormEvent) {
    event.preventDefault()
    const errors: Record<string, string> = {}
    const changes: Record<string, SettingValue> = {}
    for (const key of changed) {
      const parsed = parse(t, settings[key], draft[key])
      if ('error' in parsed) errors[key] = parsed.error
      else changes[key] = parsed.value
    }
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0 || Object.keys(changes).length === 0) return
    mutation.mutate(changes, {
      onSuccess: (next) => {
        // Show what the backend stored (e.g. "0.9" for "0.90").
        setDraft(Object.fromEntries(keys.map((key) => [key, String(next[key].value)])))
        setSaved(true)
      },
    })
  }

  return (
    <form className="settings-group" onSubmit={submit} noValidate>
      <fieldset>
        <legend>{t(`settings.general.groups.${group.id}`)}</legend>
        {keys.map((key) => {
          const info = settings[key]
          const id = `setting-${key}`
          const error =
            fieldErrors[key] ?? (serverKey === key ? t('errors.invalid_setting') : undefined)
          const range = rangeHint(t, info, i18n.language)
          return (
            <div className="field" key={key}>
              <label htmlFor={id}>{t(`settings.general.fields.${key}.label`)}</label>
              <input
                id={id}
                type={info.type === 'str' ? 'text' : 'number'}
                inputMode={info.type === 'int' ? 'numeric' : info.type === 'float' ? 'decimal' : undefined}
                step={info.type === 'float' ? (STEPS[key] ?? 'any') : info.type === 'int' ? 1 : undefined}
                min={info.minimum ?? undefined}
                max={info.maximum ?? undefined}
                value={draft[key]}
                onChange={(event) => {
                  setDraft({ ...draft, [key]: event.target.value })
                  setSaved(false)
                }}
                spellCheck={false}
                aria-invalid={error !== undefined || undefined}
                aria-describedby={`${id}-hint${error !== undefined ? ` ${id}-error` : ''}`}
              />
              <p id={`${id}-hint`} className="muted field-hint">
                {t(`settings.general.fields.${key}.hint`)} {range}{' '}
                {t('settings.general.default', { value: display(info.default, i18n.language) })}
              </p>
              {error !== undefined && (
                <p id={`${id}-error`} className="form-message form-message--error">
                  {error}
                </p>
              )}
            </div>
          )
        })}
      </fieldset>
      <button
        type="submit"
        className="button button--primary"
        disabled={changed.length === 0 || mutation.isPending}
      >
        {t('settings.general.save')}
      </button>
      <div aria-live="polite">
        {saved && changed.length === 0 && (
          <p className="form-message form-message--ok">{t('settings.saved')}</p>
        )}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </form>
  )
}

export function GeneralSettings() {
  const { t } = useTranslation()
  const settings = useSettings()

  return (
    <section className="card" aria-labelledby="general-title">
      <h2 id="general-title">{t('settings.general.title')}</h2>
      {settings.isPending && <p className="muted">{t('settings.loading')}</p>}
      {settings.isError && (
        <>
          <p className="form-message form-message--error">{t('settings.general.loadError')}</p>
          <ErrorText error={settings.error} />
        </>
      )}
      {settings.isSuccess && (
        <div className="settings-groups">
          {GROUPS.map((group) => (
            <GroupForm key={group.id} group={group} settings={settings.data} />
          ))}
          {'tts_voice' in settings.data && <VoiceSetting settings={settings.data} />}
        </div>
      )}
    </section>
  )
}
