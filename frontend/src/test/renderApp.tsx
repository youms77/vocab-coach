import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import {
  createBrowserRouter,
  createMemoryRouter,
  MemoryRouter,
  RouterProvider,
} from 'react-router'

import { routes } from '../routes'

/** Renders the whole app at a given URL, with a fresh query cache and no retries. Returns the router too. */
export function renderApp(initialPath = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] })
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, router, queryClient }
}

/**
 * Like `renderApp`, but with the real browser history (`window.history`): for the tests that must
 * look at what a navigation writes to `history.state` and to the URL (the paste of a transcript
 * must never reach either, D-151). The memory router never writes there.
 */
export function renderAppInBrowser(initialPath = '/') {
  window.history.replaceState(null, '', initialPath)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createBrowserRouter(routes)
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, router, queryClient }
}

/** Renders one component with a fresh query cache and a router (for links), outside the layout. */
export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}
