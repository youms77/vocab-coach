import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { lazy } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import i18n from '../i18n'
import { PageBoundary, RouteFallback } from './RouteFallback'
import { RouteError } from './RouteError'

function renderRoutes(page: () => Promise<{ default: () => React.ReactElement }>) {
  const Page = lazy(page)
  const router = createMemoryRouter(
    [
      {
        element: <PageBoundary />,
        errorElement: <RouteError />,
        children: [{ path: '/', element: <Page /> }],
      },
    ],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('Route loading state', () => {
  it('is an announced status with translated text', async () => {
    const { unmount } = render(<RouteFallback />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    unmount()
    await i18n.changeLanguage('fr')
    render(<RouteFallback />)
    expect(screen.getByRole('status')).toHaveTextContent('Chargement…')
  })

  it('shows while the page loads, then gives way to the page', async () => {
    let finish: (value: { default: () => React.ReactElement }) => void = () => {}
    renderRoutes(() => new Promise((resolve) => (finish = resolve)))
    expect(await screen.findByRole('status')).toBeInTheDocument()
    finish({ default: () => <h1>The page</h1> })
    expect(await screen.findByRole('heading', { name: 'The page' })).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('A page file that cannot be loaded', () => {
  it('shows a message and a reload button, never a blank screen', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const reload = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, reload })
    renderRoutes(() => Promise.reject(new TypeError('Failed to fetch dynamically imported module')))

    expect(await screen.findByRole('alert')).toHaveTextContent('This page could not be loaded')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reload the page' }))
    expect(reload).toHaveBeenCalledOnce()
  })

  it('is translated into French', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    await i18n.changeLanguage('fr')
    renderRoutes(() => Promise.reject(new TypeError('Failed to fetch dynamically imported module')))

    expect(await screen.findByRole('button', { name: 'Recharger la page' })).toBeInTheDocument()
  })
})
