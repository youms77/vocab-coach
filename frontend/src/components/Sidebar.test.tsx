import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SIDEBAR_STORAGE_KEY } from '../sidebar'
import { plan } from '../test/fixtures'
import { renderApp } from '../test/renderApp'

function mockApi() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.includes('/session/today')) {
      return Promise.resolve(Response.json({ plan: plan(), open_session: null }))
    }
    if (url.includes('/decks')) return Promise.resolve(Response.json([]))
    return Promise.resolve(Response.json({ status: 'ok', version: '0.1.0', demo: false }))
  })
}

beforeEach(() => {
  window.localStorage.removeItem(SIDEBAR_STORAGE_KEY)
  mockApi()
})

afterEach(() => {
  window.localStorage.removeItem(SIDEBAR_STORAGE_KEY)
})

describe('Navigation', () => {
  it('lists every page in the same order, grouped, with the current one marked', async () => {
    renderApp('/library')
    const nav = await screen.findByRole('navigation', { name: 'Main' })

    expect(within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/',
      '/session',
      '/library',
      '/writing',
      '/speaking',
      '/curriculum',
      '/consolidation',
      '/errors',
      '/stats',
      '/settings',
    ])
    expect(within(nav).getByRole('group', { name: 'Practice' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Library' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })
})

describe('Sidebar fold button', () => {
  it('is expanded by default and says what it will do', async () => {
    renderApp('/')
    const button = await screen.findByRole('button', { name: 'Collapse the menu' })

    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(button).toHaveAttribute('aria-controls', 'app-sidebar')
    expect(document.getElementById('app-sidebar')).not.toHaveClass('sidebar--collapsed')
  })

  it('folds, keeps every label reachable, and remembers the choice', async () => {
    const user = userEvent.setup()
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'Collapse the menu' }))

    const expand = screen.getByRole('button', { name: 'Expand the menu' })
    expect(expand).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById('app-sidebar')).toHaveClass('sidebar--collapsed')
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed')
    // The labels stay in the markup (hidden by CSS) and each item carries a title.
    expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('title', 'Library')

    await user.click(expand)
    expect(screen.getByRole('button', { name: 'Collapse the menu' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('expanded')
    expect(screen.getByRole('link', { name: 'Library' })).not.toHaveAttribute('title')
  })

  it('starts folded when the choice was stored', async () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'collapsed')
    renderApp('/')

    expect(await screen.findByRole('button', { name: 'Expand the menu' })).toBeInTheDocument()
    expect(document.getElementById('app-sidebar')).toHaveClass('sidebar--collapsed')
  })

  it('still works when the storage is unavailable', async () => {
    const user = userEvent.setup()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Collapse the menu' }))
    expect(screen.getByRole('button', { name: 'Expand the menu' })).toBeInTheDocument()
  })
})

describe('Menu panel (small screens)', () => {
  it('opens on the first link, closes on Escape and gives the focus back', async () => {
    const user = userEvent.setup()
    renderApp('/')
    const menu = await screen.findByRole('button', { name: 'Menu' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(menu).toHaveAttribute('aria-controls', 'app-sidebar')

    await user.click(menu)
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById('app-sidebar')).toHaveClass('sidebar--open')
    expect(screen.getByRole('link', { name: 'Home' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById('app-sidebar')).not.toHaveClass('sidebar--open')
    expect(menu).toHaveFocus()
  })

  it('closes when the route changes', async () => {
    const user = userEvent.setup()
    const { router } = renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'Menu' }))
    // A link of the panel navigates like this; the page it leads to does not matter here.
    await act(() => router.navigate('/nowhere'))

    expect(router.state.location.pathname).toBe('/nowhere')
    expect(screen.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById('app-sidebar')).not.toHaveClass('sidebar--open')
  })

  it('closes when the backdrop is clicked', async () => {
    const user = userEvent.setup()
    const { container } = renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'Menu' }))
    const backdrop = container.querySelector('.shell__backdrop')
    expect(backdrop).not.toBeNull()

    await user.click(backdrop as HTMLElement)
    expect(screen.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false')
  })
})
