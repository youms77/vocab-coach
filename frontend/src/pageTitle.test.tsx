/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from './i18n'
import { pageTitleKey, useDocumentTitle } from './pageTitle'

function Probe() {
  useDocumentTitle(useLocation().pathname)
  return null
}

function titleAt(pathname: string): string {
  render(
    <MemoryRouter initialEntries={[pathname]}>
      <Probe />
    </MemoryRouter>,
  )
  return document.title
}

afterEach(() => i18n.changeLanguage('en'))

describe('the tab title', () => {
  it('names the page and the application, in the interface language', async () => {
    expect(titleAt('/errors')).toBe('Error log · vocab-coach')
    await i18n.changeLanguage('fr')
    expect(titleAt('/errors')).toBe('Journal d’erreurs · vocab-coach')
    expect(titleAt('/')).toBe('Accueil · vocab-coach')
    expect(titleAt('/settings')).toBe('Réglages · vocab-coach')
    expect(titleAt('/about')).toBe('À propos · vocab-coach')
  })

  it('gives a detail page the title of its section', () => {
    expect(pageTitleKey('/library/items/12')).toBe('library.title')
    expect(pageTitleKey('/speaking/shadowing/7')).toBe('shadowing.title')
    expect(pageTitleKey('/errors/categories')).toBe('errorLog.categories.title')
    expect(pageTitleKey('/nowhere')).toBe('notFound.title')
  })

  // Every route declared in routes.tsx has a title of its own, apart from the not-found page.
  it('covers every route of the application', () => {
    const source = readFileSync(join(import.meta.dirname, 'routes.tsx'), 'utf8')
    const paths = [...source.matchAll(/path: '([^'*]+)'/g)].map((m) => m[1]!).filter((p) => p !== '/')
    const forgotten = paths
      .filter((p) => !p.startsWith('styleguide'))
      .map((p) => `/${p.replace(/:\w+/g, '1')}`)
      .filter((pathname) => pageTitleKey(pathname) === 'notFound.title')
    expect(forgotten).toEqual([])
  })
})
