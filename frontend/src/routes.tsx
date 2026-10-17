import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFoundPage } from './components/NotFoundPage'
import { EnrichmentPage } from './features/enrichment/EnrichmentPage'
import { HomePage } from './features/home/HomePage'
import { DecksPage } from './features/library/DecksPage'
import { DuplicatesPage } from './features/library/DuplicatesPage'
import { ImportPage } from './features/library/ImportPage'
import { ItemDetailPage } from './features/library/ItemDetailPage'
import { LibraryPage } from './features/library/LibraryPage'
import { TriagePage } from './features/library/TriagePage'
import { QueuePage } from './features/queue/QueuePage'
import { SessionPage } from './features/session/SessionPage'
import { SettingsPage } from './features/settings/SettingsPage'

// One entry per feature folder under src/features/ as milestones add them.
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
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
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
