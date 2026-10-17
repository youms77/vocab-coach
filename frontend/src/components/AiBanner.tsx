import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router'

import { useAiStatus } from '../api/ai'

/** Says, on every page, that the app runs without AI (SPEC §7 degraded mode). */
export function AiBanner() {
  const { t } = useTranslation()
  const status = useAiStatus()
  const { pathname } = useLocation()

  // No banner while loading or when the backend is down (the home page already says so).
  if (status.data?.degraded !== true) return null

  return (
    <div className="ai-banner" role="status">
      <p>{status.data.ai_off ? t('aiBanner.aiOff') : t('aiBanner.degraded')}</p>
      {pathname !== '/settings' && <Link to="/settings">{t('aiBanner.link')}</Link>}
    </div>
  )
}
