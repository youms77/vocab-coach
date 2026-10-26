import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFoundPage } from './components/NotFoundPage'
import { ConsolidationAttemptPage } from './features/consolidation/ConsolidationAttemptPage'
import { ConsolidationPage } from './features/consolidation/ConsolidationPage'
import { ConsolidationTaskPage } from './features/consolidation/ConsolidationTaskPage'
import { TrackPage } from './features/curriculum/TrackPage'
import { TracksPage } from './features/curriculum/TracksPage'
import { UnitPage } from './features/curriculum/UnitPage'
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
import { ShadowingDetailPage } from './features/speaking/ShadowingDetailPage'
import { ShadowingHistoryPage } from './features/speaking/ShadowingHistoryPage'
import { ShadowingPage } from './features/speaking/ShadowingPage'
import { SpeakingDetailPage } from './features/speaking/SpeakingDetailPage'
import { SpeakingHistoryPage } from './features/speaking/SpeakingHistoryPage'
import { SpeakingPage } from './features/speaking/SpeakingPage'
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
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
