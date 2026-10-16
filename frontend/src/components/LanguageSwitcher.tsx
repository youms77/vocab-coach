import { useTranslation } from 'react-i18next'

import { SUPPORTED_LANGUAGES, type Language } from '../i18n'

const LABELS: Record<Language, string> = { en: 'English', fr: 'Français' }

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const current = (i18n.resolvedLanguage ?? 'en') as Language

  return (
    <label className="control">
      <span className="control__label">{t('settings.language')}</span>
      <select value={current} onChange={(event) => void i18n.changeLanguage(event.target.value)}>
        {SUPPORTED_LANGUAGES.map((lng) => (
          <option key={lng} value={lng} lang={lng}>
            {LABELS[lng]}
          </option>
        ))}
      </select>
    </label>
  )
}
