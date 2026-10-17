import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'

import { useHealth } from '../api/health'
import { AiBanner } from './AiBanner'
import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeSwitcher } from './ThemeSwitcher'

export function Layout() {
  const { t } = useTranslation()
  const health = useHealth()

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t('nav.skipToContent')}
      </a>
      <header className="topbar">
        <NavLink to="/" className="brand" end>
          <span className="brand__mark" aria-hidden="true">
            v
          </span>
          {t('app.name')}
        </NavLink>
        <nav aria-label={t('nav.label')} className="topbar__nav">
          <NavLink to="/" end>
            {t('nav.home')}
          </NavLink>
          <NavLink to="/library">{t('nav.library')}</NavLink>
          <NavLink to="/settings">{t('nav.settings')}</NavLink>
        </nav>
        {health.data?.demo === true && (
          <span className="demo-badge" title={t('demo.badgeHint')}>
            {t('demo.badge')}
          </span>
        )}
        <div className="topbar__controls">
          <LanguageSwitcher />
          <ThemeSwitcher />
        </div>
      </header>
      <AiBanner />
      <main id="main" className="content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
