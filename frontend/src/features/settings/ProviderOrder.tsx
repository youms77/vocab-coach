import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { AiStatus, ProviderName } from '../../api/ai'
import { useSettingsMutation } from '../../api/settings'
import { ErrorText } from './ErrorText'

interface Entry {
  name: ProviderName
  enabled: boolean
}

/** The saved order first, then the providers it leaves out (turned off). */
function entriesFrom(status: AiStatus): Entry[] {
  const enabled = status.order.map((name) => ({ name, enabled: true }))
  const rest = status.providers
    .filter((provider) => !status.order.includes(provider.name))
    .map((provider) => ({ name: provider.name, enabled: false }))
  return [...enabled, ...rest]
}

function orderOf(entries: Entry[]): ProviderName[] {
  return entries.filter((entry) => entry.enabled).map((entry) => entry.name)
}

export function ProviderOrder({ status, locked }: { status: AiStatus; locked: boolean }) {
  // The draft starts from the saved order; after a save, the two are equal again.
  const { t } = useTranslation()
  const mutation = useSettingsMutation()
  const [entries, setEntries] = useState(() => entriesFrom(status))
  const [saved, setSaved] = useState(false)

  const draft = orderOf(entries)
  const dirty = draft.join(',') !== status.order.join(',')
  const configured = new Map(status.providers.map((p) => [p.name, p.configured]))

  function update(next: Entry[]) {
    setEntries(next)
    setSaved(false)
    mutation.reset()
  }

  function move(index: number, delta: -1 | 1) {
    const next = [...entries]
    const [entry] = next.splice(index, 1)
    next.splice(index + delta, 0, entry)
    update(next)
  }

  function toggle(index: number) {
    update(entries.map((entry, i) => (i === index ? { ...entry, enabled: !entry.enabled } : entry)))
  }

  function save() {
    mutation.mutate({ ai_provider_order: draft }, { onSuccess: () => setSaved(true) })
  }

  return (
    <section className="card" aria-labelledby="order-title">
      <h2 id="order-title">{t('settings.order.title')}</h2>
      <p className="muted">{t('settings.order.intro')}</p>
      <ol className="order-list">
        {entries.map((entry, index) => {
          const name = t(`settings.provider.names.${entry.name}`)
          return (
            <li key={entry.name} className="order-list__item">
              <label className="order-list__toggle">
                <input
                  type="checkbox"
                  checked={entry.enabled}
                  onChange={() => toggle(index)}
                  disabled={locked}
                  aria-label={t('settings.order.use', { name })}
                />
                <span>{name}</span>
                {configured.get(entry.name) === false && (
                  <span className="muted"> ({t('settings.order.notConfigured')})</span>
                )}
              </label>
              <span className="order-list__moves">
                <button
                  type="button"
                  className="button button--icon"
                  onClick={() => move(index, -1)}
                  disabled={locked || index === 0}
                  aria-label={t('settings.order.up', { name })}
                >
                  <span aria-hidden="true">↑</span>
                </button>
                <button
                  type="button"
                  className="button button--icon"
                  onClick={() => move(index, 1)}
                  disabled={locked || index === entries.length - 1}
                  aria-label={t('settings.order.down', { name })}
                >
                  <span aria-hidden="true">↓</span>
                </button>
              </span>
            </li>
          )
        })}
      </ol>
      {draft.length === 0 && (
        <p className="form-message form-message--warn">{t('settings.order.allOff')}</p>
      )}
      <button
        type="button"
        className="button button--primary"
        onClick={save}
        disabled={locked || !dirty || mutation.isPending}
      >
        {t('settings.order.save')}
      </button>
      <div aria-live="polite">
        {saved && !dirty && <p className="form-message form-message--ok">{t('settings.saved')}</p>}
      </div>
      {mutation.isError && <ErrorText error={mutation.error} />}
    </section>
  )
}
