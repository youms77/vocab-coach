import { useTranslation } from 'react-i18next'

import { useAiStatus } from '../../api/ai'
import { AzureCard } from './AzureCard'
import { ErrorText } from './ErrorText'
import { GeneralSettings } from './GeneralSettings'
import { ProviderCard } from './ProviderCard'
import { ProviderOrder } from './ProviderOrder'
import { UsagePanel } from './UsagePanel'
import { Notice } from '../../components/Notice'

function AiProviders() {
  const { t } = useTranslation()
  const status = useAiStatus()

  return (
    <>
      <section className="card" aria-labelledby="ai-title" id="ai">
        <h2 id="ai-title">{t('settings.ai.title')}</h2>
        <p className="muted">{t('settings.ai.intro')}</p>
        <p className="muted">{t('settings.ai.privacy')}</p>
        {status.isPending && <p className="muted">{t('settings.loading')}</p>}
        {status.isError && (
          <>
            <Notice tone="danger">{t('settings.ai.loadError')}</Notice>
            <ErrorText error={status.error} />
          </>
        )}
        {status.isSuccess && (
          <>
            {status.data.demo && (
              <Notice tone="warning">{t('settings.ai.demoNote')}</Notice>
            )}
            <div className="provider-list">
              {status.data.providers.map((provider) => (
                <ProviderCard key={provider.name} provider={provider} locked={status.data.demo} />
              ))}
            </div>
          </>
        )}
      </section>
      {status.isSuccess && <ProviderOrder status={status.data} locked={status.data.demo} />}
    </>
  )
}

export function SettingsPage() {
  const { t } = useTranslation()

  return (
    <div className="settings-page">
      <section className="hero">
        <h1>{t('settings.title')}</h1>
        <p className="muted">{t('settings.intro')}</p>
      </section>
      <AiProviders />
      <AzureCard />
      <UsagePanel />
      <GeneralSettings />
    </div>
  )
}
