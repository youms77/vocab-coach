import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { applyTheme, readStoredTheme, THEMES, type Theme } from '../theme'

export function ThemeSwitcher() {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<Theme>(readStoredTheme)

  const labels: Record<Theme, string> = {
    system: t('settings.themeSystem'),
    light: t('settings.themeLight'),
    dark: t('settings.themeDark'),
  }

  function onChange(next: Theme) {
    setTheme(next)
    applyTheme(next)
  }

  return (
    <label className="control">
      <span className="control__label">{t('settings.theme')}</span>
      <select value={theme} onChange={(event) => onChange(event.target.value as Theme)}>
        {THEMES.map((value) => (
          <option key={value} value={value}>
            {labels[value]}
          </option>
        ))}
      </select>
    </label>
  )
}
