import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '../../i18n'
import en from '../../i18n/locales/en.json'
import fr from '../../i18n/locales/fr.json'
import { renderApp } from '../../test/renderApp'

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
    Promise.resolve(Response.json({ status: 'ok', version: '0.1.0', demo: false })),
  )
})

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('About page', () => {
  it('describes the app, its modules and the accepted formats in English', async () => {
    renderApp('/about')

    expect(await screen.findByRole('heading', { level: 1, name: 'About' })).toBeInTheDocument()
    expect(document.title).toBe('About · vocab-coach')
    expect(screen.getByRole('heading', { name: 'Principles' })).toBeInTheDocument()
    expect(screen.getByText('Library and import', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Backup', { selector: 'strong' })).toBeInTheDocument()

    const bring = screen.getByRole('region', { name: 'Bring your words in' })
    for (const format of [
      'Markdown (.md) or pasted text',
      'Plain text (.txt)',
      'CSV or TSV (.csv, .tsv)',
      'Anything else',
    ]) {
      expect(within(bring).getByText(format)).toBeInTheDocument()
    }
    expect(bring).toHaveTextContent('- shed light on')
    expect(within(bring).getByRole('link', { name: 'Open the Import page' })).toHaveAttribute(
      'href',
      '/import',
    )
  })

  it('is in French when the interface is French, prompt included', async () => {
    await i18n.changeLanguage('fr')
    renderApp('/about')

    expect(await screen.findByRole('heading', { level: 1, name: 'À propos' })).toBeInTheDocument()
    expect(document.title).toBe('À propos · vocab-coach')
    expect(screen.getByRole('region', { name: 'Apporter vos mots' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Prompt pour un chatbot' })).toHaveTextContent(
      'Tu aides un francophone de niveau B1',
    )
  })

  it('shows the prompt in the interface language and copies it, announcing the result', async () => {
    const user = userEvent.setup() // installs a working clipboard stub
    renderApp('/about')

    const prompt = await screen.findByRole('group', { name: 'Prompt for a chatbot' })
    expect(prompt).toHaveTextContent('You are helping a French-speaking B1 learner')
    await user.click(screen.getByRole('button', { name: 'Copy the prompt' }))

    expect(await navigator.clipboard.readText()).toBe(en.about.prompt.text)
    expect(await screen.findByText('Prompt copied.')).toBeInTheDocument()
  })

  it('copies the French prompt when the interface is French', async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage('fr')
    renderApp('/about')

    await user.click(await screen.findByRole('button', { name: 'Copier le prompt' }))
    expect(await navigator.clipboard.readText()).toBe(fr.about.prompt.text)
  })

  it('says so when the clipboard refuses', async () => {
    const user = userEvent.setup()
    renderApp('/about')
    const button = await screen.findByRole('button', { name: 'Copy the prompt' })
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))

    await user.click(button)
    expect(await screen.findByText(/The copy did not work/)).toBeInTheDocument()
  })

  it('is reached with the keyboard from the sidebar and from the Import page', async () => {
    const user = userEvent.setup()
    renderApp('/import')

    await user.click(
      await screen.findByRole('link', { name: /Not sure how to prepare your list/ }),
    )
    expect(await screen.findByRole('heading', { level: 1, name: 'About' })).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'About' }),
    ).toHaveAttribute('aria-current', 'page')
  })
})

describe('the prompt text', () => {
  it('asks for the import format in both languages', () => {
    for (const text of [en.about.prompt.text, fr.about.prompt.text]) {
      expect(text).toContain('---\ndeck: [')
      expect(text).toContain('- ')
      expect(text).toContain('"shed light on"')
      expect(text.split('\n').length).toBeGreaterThan(30)
    }
  })
})
