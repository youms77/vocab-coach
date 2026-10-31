import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { Ref } from 'react'

import { Icon } from './Icon'
import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeSwitcher } from './ThemeSwitcher'

/**
 * The bar across the top of the page column. From 960px the left button folds or unfolds the
 * sidebar; below it, the Menu button opens the navigation panel. Both are in the markup and CSS
 * shows one. Page titles and actions belong to the page, not to the bar.
 */
export function TopBar({
  sidebarId,
  collapsed,
  menuOpen,
  onToggleCollapsed,
  onToggleMenu,
  menuButtonRef,
  demo,
}: {
  sidebarId: string
  collapsed: boolean
  menuOpen: boolean
  onToggleCollapsed: () => void
  onToggleMenu: () => void
  menuButtonRef: Ref<HTMLButtonElement>
  demo: boolean
}) {
  const { t } = useTranslation()
  return (
    <header className="topbar">
      <button
        type="button"
        className="button button--ghost button--icon topbar__fold"
        aria-expanded={!collapsed}
        aria-controls={sidebarId}
        aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
        onClick={onToggleCollapsed}
      >
        <Icon name={collapsed ? 'sidebar-expand' : 'sidebar-collapse'} size={20} />
      </button>
      <button
        type="button"
        ref={menuButtonRef}
        className="button button--ghost topbar__menu"
        aria-expanded={menuOpen}
        aria-controls={sidebarId}
        onClick={onToggleMenu}
      >
        <Icon name="menu" size={18} />
        <span className="topbar__menu-label">{t('nav.menu')}</span>
      </button>
      <Link className="topbar__brand" to="/">
        <span className="sidebar__mark" aria-hidden="true">
          v
        </span>
        <span className="topbar__brand-name">{t('app.name')}</span>
      </Link>
      <div className="topbar__spacer" />
      {demo && (
        <span className="demo-badge" title={t('demo.badgeHint')}>
          {t('demo.badge')}
        </span>
      )}
      <div className="topbar__controls">
        <LanguageSwitcher />
        <ThemeSwitcher />
      </div>
    </header>
  )
}
