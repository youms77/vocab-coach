import { useTranslation } from 'react-i18next'

import { Notice } from './Notice'

/**
 * The page could not be shown, most often because the file of a page that loads on demand is gone
 * (the application was rebuilt while this tab stayed open). Never a blank screen: a message and a
 * way out.
 */
export function RouteError() {
  const { t } = useTranslation()
  return (
    <section className="card route-error">
      <Notice tone="danger" role="alert">
        <p>{t('route.error')}</p>
      </Notice>
      <button type="button" className="button" onClick={() => window.location.reload()}>
        {t('route.reload')}
      </button>
    </section>
  )
}
