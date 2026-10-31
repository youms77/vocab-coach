import { beforeEach, describe, expect, it, vi } from 'vitest'

// The module reads the stored choice when it is first imported, as at page load.
async function loadApp(stored: string | null) {
  vi.resetModules()
  localStorage.clear()
  if (stored !== null) localStorage.setItem('vocab-coach.language', stored)
  document.documentElement.lang = 'en'
  return (await import('./index')).default
}

describe('<html lang> at load', () => {
  beforeEach(() => localStorage.clear())

  it('is French straight away when French was chosen', async () => {
    await loadApp('fr')
    expect(document.documentElement.lang).toBe('fr')
  })

  it('is English by default, whatever the browser says', async () => {
    await loadApp(null)
    expect(document.documentElement.lang).toBe('en')
  })

  it('follows a change without a reload', async () => {
    const i18n = await loadApp(null)
    await i18n.changeLanguage('fr')
    expect(document.documentElement.lang).toBe('fr')
    await i18n.changeLanguage('en')
    expect(document.documentElement.lang).toBe('en')
  })
})
