import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { renderApp } from '../../test/renderApp'

function mockFetch(response: Response | Error) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(() =>
      // A body can be read once: every request (health, AI status) gets its own copy.
      response instanceof Error ? Promise.reject(response) : Promise.resolve(response.clone()),
    )
}

describe('HomePage', () => {
  it('renders in English by default and shows the backend version', async () => {
    mockFetch(Response.json({ status: 'ok', version: '0.1.0' }))
    renderApp('/')

    expect(screen.getByRole('heading', { level: 1, name: 'Welcome' })).toBeInTheDocument()
    expect(await screen.findByText('Local server is running (version 0.1.0).')).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('en')
  })

  it('points to the import and the library while there is nothing to review', () => {
    mockFetch(Response.json({ status: 'ok', version: '0.1.0' }))
    renderApp('/')

    expect(screen.getByRole('link', { name: 'Import a list' })).toHaveAttribute('href', '/import')
    expect(screen.getByRole('link', { name: 'Open the library' })).toHaveAttribute(
      'href',
      '/library',
    )
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })

  it('says so when the backend is unreachable', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    renderApp('/')

    expect(await screen.findByText(/Cannot reach the local server/)).toBeInTheDocument()
  })

  it('switches the interface to French and remembers the choice', async () => {
    mockFetch(Response.json({ status: 'ok', version: '0.1.0' }))
    const user = userEvent.setup()
    renderApp('/')

    await user.selectOptions(screen.getByLabelText('Language'), 'fr')

    expect(screen.getByRole('heading', { level: 1, name: 'Bienvenue' })).toBeInTheDocument()
    expect(window.localStorage.getItem('vocab-coach.language')).toBe('fr')
    expect(document.documentElement.lang).toBe('fr')
  })

  it('applies an explicit dark theme', async () => {
    mockFetch(Response.json({ status: 'ok', version: '0.1.0' }))
    const user = userEvent.setup()
    renderApp('/')

    await user.selectOptions(screen.getByLabelText('Theme'), 'dark')
    expect(document.documentElement.dataset.theme).toBe('dark')

    await user.selectOptions(screen.getByLabelText('Theme'), 'system')
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })

  it('shows a not-found page for unknown routes', () => {
    mockFetch(Response.json({ status: 'ok', version: '0.1.0' }))
    renderApp('/nope')

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})
