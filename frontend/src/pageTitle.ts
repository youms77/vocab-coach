import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * The title of the browser tab for each route (M10.c1, D-325): the page's name in the interface
 * language, then the name of the application. First match wins, so the specific routes come first.
 * A route with a detail (`/library/items/3`) carries the title of its section.
 */
const TITLES = [
  [/^\/$/, 'nav.home'],
  [/^\/session/, 'nav.today'],
  [/^\/queue/, 'queue.title'],
  [/^\/library\/decks/, 'library.decks.title'],
  [/^\/library/, 'library.title'],
  [/^\/import/, 'import.title'],
  [/^\/enrichment/, 'enrichment.title'],
  [/^\/triage/, 'triage.title'],
  [/^\/duplicates/, 'duplicates.title'],
  [/^\/writing/, 'writing.title'],
  [/^\/speaking\/shadowing/, 'shadowing.title'],
  [/^\/speaking/, 'speaking.title'],
  [/^\/transcripts/, 'transcripts.title'],
  [/^\/consolidation/, 'consolidation.title'],
  [/^\/curriculum/, 'curriculum.title'],
  [/^\/drills/, 'drills.title'],
  [/^\/errors\/categories/, 'errorLog.categories.title'],
  [/^\/errors/, 'errorLog.title'],
  [/^\/stats/, 'stats.title'],
  [/^\/settings/, 'settings.title'],
  [/^\/about/, 'about.title'],
] as const

export type PageTitleKey = (typeof TITLES)[number][1] | 'notFound.title'

export function pageTitleKey(pathname: string): PageTitleKey {
  for (const [pattern, key] of TITLES) if (pattern.test(pathname)) return key
  return 'notFound.title'
}

/** Keeps `document.title` in step with the route and the interface language. */
export function useDocumentTitle(pathname: string): void {
  const { t, i18n } = useTranslation()
  const page = t(pageTitleKey(pathname))
  const language = i18n.language
  useEffect(() => {
    const title = `${page} · ${t('app.name')}` // both parts come from i18n
    document.title = title
  }, [page, language, t])
}
