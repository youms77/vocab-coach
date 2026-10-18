import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFoundPage } from './components/NotFoundPage'
import { EnrichmentPage } from './features/enrichment/EnrichmentPage'
import { DrillPage } from './features/drills/DrillPage'
import { DrillsPage } from './features/drills/DrillsPage'
import { CategoriesPage } from './features/errors/CategoriesPage'
import { ErrorDetailPage } from './features/errors/ErrorDetailPage'
import { ErrorsPage } from './features/errors/ErrorsPage'
import { ManualErrorPage } from './features/errors/ManualErrorPage'
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
import { TranscriptDetailPage } from './features/transcripts/TranscriptDetailPage'
import { TranscriptHistoryPage } from './features/transcripts/TranscriptHistoryPage'
import { TranscriptPage } from './features/transcripts/TranscriptPage'
import { WritingDetailPage } from './features/writing/WritingDetailPage'
import { WritingHistoryPage } from './features/writing/WritingHistoryPage'
import { WritingPage } from './features/writing/WritingPage'

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
      { path: 'writing', element: <WritingPage /> },
      { path: 'writing/history', element: <WritingHistoryPage /> },
      { path: 'writing/:id', element: <WritingDetailPage /> },
      { path: 'transcripts', element: <TranscriptPage /> },
      { path: 'transcripts/history', element: <TranscriptHistoryPage /> },
      { path: 'transcripts/:id', element: <TranscriptDetailPage /> },
      { path: 'drills', element: <DrillsPage /> },
      { path: 'drills/:id', element: <DrillPage /> },
      { path: 'errors', element: <ErrorsPage /> },
      { path: 'errors/new', element: <ManualErrorPage /> },
      { path: 'errors/categories', element: <CategoriesPage /> },
      { path: 'errors/:id', element: <ErrorDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
