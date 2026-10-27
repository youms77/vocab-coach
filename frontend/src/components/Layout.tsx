import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation } from 'react-router'

import { useHealth } from '../api/health'
import { readSidebarCollapsed, storeSidebarCollapsed } from '../sidebar'
import { useStopRecordingOnLeave } from '../speech/activeRecording'
import { useCancelSpeechOnLeave } from '../speech/useSpeech'
import { AiBanner } from './AiBanner'
import { type NavGroup, type NavItem, Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const SIDEBAR_ID = 'app-sidebar'

export function Layout() {
  const { t } = useTranslation()
  const health = useHealth()
  const { pathname } = useLocation()
  useCancelSpeechOnLeave()
  useStopRecordingOnLeave()

  const [collapsed, setCollapsed] = useState(readSidebarCollapsed)
  // The panel of small screens is open for the page it was opened on: following a link closes it.
  const [openedOn, setOpenedOn] = useState<string | null>(null)
  const menuOpen = openedOn === pathname
  const menuButton = useRef<HTMLButtonElement>(null)

  // Escape closes the panel and gives the focus back to the Menu button. On opening, the focus
  // moves to the first link, so the keyboard lands inside the panel and not after it.
  useEffect(() => {
    if (!menuOpen) return
    document.querySelector<HTMLElement>(`#${SIDEBAR_ID} .nav-item`)?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpenedOn(null)
      menuButton.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  function toggleCollapsed() {
    const next = !collapsed
    setCollapsed(next)
    storeSidebarCollapsed(next)
  }

  const item = (to: string, icon: NavItem['icon'], label: string, end = false): NavItem => ({
    to,
    icon,
    label,
    end,
  })
  const groups: NavGroup[] = [
    {
      items: [item('/', 'home', t('nav.home'), true), item('/session', 'today', t('nav.today'))],
    },
    {
      title: t('nav.groups.vocabulary'),
      items: [item('/library', 'library', t('nav.library'))],
    },
    {
      title: t('nav.groups.practice'),
      items: [
        item('/writing', 'writing', t('nav.writing')),
        item('/speaking', 'speaking', t('nav.speaking')),
        item('/curriculum', 'tracks', t('nav.curriculum')),
        item('/consolidation', 'consolidation', t('nav.consolidation')),
      ],
    },
    {
      title: t('nav.groups.progress'),
      items: [item('/errors', 'errors', t('nav.errors')), item('/stats', 'stats', t('nav.stats'))],
    },
  ]
  const bottom = [item('/settings', 'settings', t('nav.settings'))]

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t('nav.skipToContent')}
      </a>
      <Sidebar
        id={SIDEBAR_ID}
        appName={t('app.name')}
        navLabel={t('nav.label')}
        groups={groups}
        bottom={bottom}
        collapsed={collapsed}
        open={menuOpen}
      />
      {menuOpen && <div className="shell__backdrop" onClick={() => setOpenedOn(null)} />}
      <div className="shell__main">
        <TopBar
          sidebarId={SIDEBAR_ID}
          collapsed={collapsed}
          menuOpen={menuOpen}
          onToggleCollapsed={toggleCollapsed}
          onToggleMenu={() => setOpenedOn(menuOpen ? null : pathname)}
          menuButtonRef={menuButton}
          demo={health.data?.demo === true}
        />
        <AiBanner />
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
