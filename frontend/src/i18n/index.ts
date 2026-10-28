import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import fr from './locales/fr.json'

export const SUPPORTED_LANGUAGES = ['en', 'fr'] as const
export type Language = (typeof SUPPORTED_LANGUAGES)[number]
export const LANGUAGE_STORAGE_KEY = 'vocab-coach.language'

export const resources = {
  en: { translation: en },
  fr: { translation: fr },
} as const

// Immersion first: the interface is in English unless the user explicitly picks French.
// We therefore only read the stored choice, never the browser language.
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGUAGES,
    nonExplicitSupportedLngs: true,
    interpolation: { escapeValue: false }, // React already escapes output
    detection: {
      order: ['localStorage'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage'],
    },
  })

// `<html lang>` follows the interface language from the first paint, not only after a change:
// screen readers pick the voice from it (M10.c, D-320). index.html says "en" until this runs.
function applyDocumentLanguage(lng: string | undefined) {
  document.documentElement.lang = lng === 'fr' ? 'fr' : 'en'
}

applyDocumentLanguage(i18n.resolvedLanguage)
i18n.on('languageChanged', applyDocumentLanguage)

export default i18n
