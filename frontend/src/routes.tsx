import { type ComponentType, lazy } from 'react'
import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFoundPage } from './components/NotFoundPage'
import { PageBoundary } from './components/RouteFallback'
import { RouteError } from './components/RouteError'
/**
 * Every page is its own file, loaded when its route is first shown (a smaller first load). The
 * layout and the not-found page stay in the main file; `PageBoundary` waits for a page and
 * `RouteError` answers when a file cannot be loaded.
 */
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(async () => ({ default: (await load())[name] }))
}

const AboutPage = page(() => import('./features/about/AboutPage'), 'AboutPage')
const ConsolidationAttemptPage = page(
  () => import('./features/consolidation/ConsolidationAttemptPage'),
  'ConsolidationAttemptPage',
)
const ConsolidationPage = page(
  () => import('./features/consolidation/ConsolidationPage'),
  'ConsolidationPage',
)
const ConsolidationTaskPage = page(
  () => import('./features/consolidation/ConsolidationTaskPage'),
  'ConsolidationTaskPage',
)
const TrackPage = page(() => import('./features/curriculum/TrackPage'), 'TrackPage')
const TracksPage = page(() => import('./features/curriculum/TracksPage'), 'TracksPage')
const UnitPage = page(() => import('./features/curriculum/UnitPage'), 'UnitPage')
const EnrichmentPage = page(() => import('./features/enrichment/EnrichmentPage'), 'EnrichmentPage')
const DashboardPage = page(() => import('./features/dashboard/DashboardPage'), 'DashboardPage')
const DrillPage = page(() => import('./features/drills/DrillPage'), 'DrillPage')
const DrillsPage = page(() => import('./features/drills/DrillsPage'), 'DrillsPage')
const CategoriesPage = page(() => import('./features/errors/CategoriesPage'), 'CategoriesPage')
const ErrorDetailPage = page(() => import('./features/errors/ErrorDetailPage'), 'ErrorDetailPage')
const ErrorsPage = page(() => import('./features/errors/ErrorsPage'), 'ErrorsPage')
const ManualErrorPage = page(() => import('./features/errors/ManualErrorPage'), 'ManualErrorPage')
const HomePage = page(() => import('./features/home/HomePage'), 'HomePage')
const DecksPage = page(() => import('./features/library/DecksPage'), 'DecksPage')
const DuplicatesPage = page(() => import('./features/library/DuplicatesPage'), 'DuplicatesPage')
const ImportPage = page(() => import('./features/library/ImportPage'), 'ImportPage')
const ItemDetailPage = page(() => import('./features/library/ItemDetailPage'), 'ItemDetailPage')
const LibraryPage = page(() => import('./features/library/LibraryPage'), 'LibraryPage')
const TriagePage = page(() => import('./features/library/TriagePage'), 'TriagePage')
const QueuePage = page(() => import('./features/queue/QueuePage'), 'QueuePage')
const SessionPage = page(() => import('./features/session/SessionPage'), 'SessionPage')
const SettingsPage = page(() => import('./features/settings/SettingsPage'), 'SettingsPage')
const ShadowingDetailPage = page(
  () => import('./features/speaking/ShadowingDetailPage'),
  'ShadowingDetailPage',
)
const ShadowingHistoryPage = page(
  () => import('./features/speaking/ShadowingHistoryPage'),
  'ShadowingHistoryPage',
)
const ShadowingPage = page(() => import('./features/speaking/ShadowingPage'), 'ShadowingPage')
const SpeakingDetailPage = page(
  () => import('./features/speaking/SpeakingDetailPage'),
  'SpeakingDetailPage',
)
const SpeakingHistoryPage = page(
  () => import('./features/speaking/SpeakingHistoryPage'),
  'SpeakingHistoryPage',
)
const SpeakingPage = page(() => import('./features/speaking/SpeakingPage'), 'SpeakingPage')
const TranscriptDetailPage = page(
  () => import('./features/transcripts/TranscriptDetailPage'),
  'TranscriptDetailPage',
)
const TranscriptHistoryPage = page(
  () => import('./features/transcripts/TranscriptHistoryPage'),
  'TranscriptHistoryPage',
)
const TranscriptPage = page(() => import('./features/transcripts/TranscriptPage'), 'TranscriptPage')
const WritingDetailPage = page(
  () => import('./features/writing/WritingDetailPage'),
  'WritingDetailPage',
)
const WritingHistoryPage = page(
  () => import('./features/writing/WritingHistoryPage'),
  'WritingHistoryPage',
)
const WritingPage = page(() => import('./features/writing/WritingPage'), 'WritingPage')

// One entry per feature folder under src/features/ as milestones add them.
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        element: <PageBoundary />,
        errorElement: <RouteError />,
        children: [
          { index: true, element: <HomePage /> },
          { path: 'session', element: <SessionPage /> },
          { path: 'queue', element: <QueuePage /> },
          { path: 'library', element: <LibraryPage /> },
          { path: 'library/decks', element: <DecksPage /> },
          { path: 'library/items/:id', element: <ItemDetailPage /> },
          { path: 'import', element: <ImportPage /> },
          { path: 'enrichment', element: <EnrichmentPage /> },
          { path: 'triage', element: <TriagePage /> },
          { path: 'duplicates', element: <DuplicatesPage /> },
          { path: 'writing', element: <WritingPage /> },
          { path: 'writing/history', element: <WritingHistoryPage /> },
          { path: 'writing/:id', element: <WritingDetailPage /> },
          { path: 'speaking', element: <SpeakingPage /> },
          { path: 'speaking/history', element: <SpeakingHistoryPage /> },
          { path: 'speaking/:id', element: <SpeakingDetailPage /> },
          { path: 'speaking/shadowing', element: <ShadowingPage /> },
          { path: 'speaking/shadowing/history', element: <ShadowingHistoryPage /> },
          { path: 'speaking/shadowing/:id', element: <ShadowingDetailPage /> },
          { path: 'transcripts', element: <TranscriptPage /> },
          { path: 'transcripts/history', element: <TranscriptHistoryPage /> },
          { path: 'transcripts/:id', element: <TranscriptDetailPage /> },
          { path: 'consolidation', element: <ConsolidationPage /> },
          { path: 'consolidation/tasks/:id', element: <ConsolidationTaskPage /> },
          { path: 'consolidation/attempts/:id', element: <ConsolidationAttemptPage /> },
          { path: 'curriculum', element: <TracksPage /> },
          { path: 'curriculum/units/:id', element: <UnitPage /> },
          { path: 'curriculum/:code', element: <TrackPage /> },
          { path: 'drills', element: <DrillsPage /> },
          { path: 'drills/:id', element: <DrillPage /> },
          { path: 'errors', element: <ErrorsPage /> },
          { path: 'errors/new', element: <ManualErrorPage /> },
          { path: 'errors/categories', element: <CategoriesPage /> },
          { path: 'errors/:id', element: <ErrorDetailPage /> },
          { path: 'stats', element: <DashboardPage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: 'about', element: <AboutPage /> },
          // Development only (D-291): `import.meta.env.DEV` is replaced by `false` in a production build,
          // which removes this entry and, with it, the page and its stylesheet from the bundle.
          ...(import.meta.env.DEV
            ? [
                {
                  path: 'styleguide',
                  lazy: async () => ({
                    Component: (await import('./features/styleguide/StyleguidePage'))
                      .StyleguidePage,
                  }),
                },
              ]
            : []),
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]
