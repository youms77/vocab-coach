import { useTranslation } from 'react-i18next'
import { Outlet } from 'react-router'
import { Suspense } from 'react'

/** Shown while the file of a page loads: an announced state that keeps the height of a page. */
export function RouteFallback() {
  const { t } = useTranslation()
  return (
    <div className="route-fallback" role="status">
      {t('route.loading')}
    </div>
  )
}

/** The pages are loaded on demand (`routes.tsx`): this is where the router waits for them. */
export function PageBoundary() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Outlet />
    </Suspense>
  )
}
