import type { RouteObject } from 'react-router'

import { Layout } from './components/Layout'
import { NotFoundPage } from './components/NotFoundPage'
import { HomePage } from './features/home/HomePage'
import { DecksPage } from './features/library/DecksPage'
import { ItemDetailPage } from './features/library/ItemDetailPage'
import { LibraryPage } from './features/library/LibraryPage'
import { SettingsPage } from './features/settings/SettingsPage'

// One entry per feature folder under src/features/ as milestones add them.
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'library/decks', element: <DecksPage /> },
      { path: 'library/items/:id', element: <ItemDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
