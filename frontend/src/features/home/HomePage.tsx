import { useTranslation } from 'react-i18next'
import { useHealth } from '../../api/health'
import { TodayCard } from '../session/TodayCard'

function ApiStatus() {
  const { t } = useTranslation()
  const health = useHealth()

  if (health.isPending) {
    return <p className="status status--pending">{t('home.apiChecking')}</p>
  }
  if (health.isError) {
    return <p className="status status--down">{t('home.apiDown')}</p>
  }
  return (
    <p className="status status--ok">{t('home.apiOk', { version: health.data.version })}</p>
  )
}

export function HomePage() {
  const { t } = useTranslation()

  return (
    <div className="home">
      <section className="hero">
        <h1>{t('home.title')}</h1>
        <p className="hero__tagline">{t('app.tagline')}</p>
        <p className="muted">{t('home.intro')}</p>
      </section>

      <TodayCard />

      <section className="card" aria-labelledby="status-title" aria-live="polite">
        <h2 id="status-title">{t('home.statusTitle')}</h2>
        <ApiStatus />
      </section>
    </div>
  )
}
