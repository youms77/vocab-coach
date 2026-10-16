import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'

import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeSwitcher } from './ThemeSwitcher'

export function Layout() {
  const { t } = useTranslation()

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
        <nav aria-label="Main" className="topbar__nav">
          <NavLink to="/" end>
            {t('nav.home')}
          </NavLink>
        </nav>
        <div className="topbar__controls">
          <LanguageSwitcher />
          <ThemeSwitcher />
        </div>
      </header>
      <main id="main" className="content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
