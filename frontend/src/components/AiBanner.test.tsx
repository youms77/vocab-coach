import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { mockApi } from '../test/mockApi'
import { renderApp } from '../test/renderApp'

const health = { status: 'ok', version: '0.1.0' }

function aiStatus(degraded: boolean, aiOff = false) {
  return { ai_off: aiOff, degraded, demo: false, order: aiOff ? [] : ['gemini'], providers: [] }
}

describe('Degraded-mode banner', () => {
  it('says the app runs without AI and links to the settings', async () => {
    mockApi({ 'GET /health': health, 'GET /ai/status': aiStatus(true) })
    const user = userEvent.setup()
    renderApp('/')

    expect(await screen.findByText(/^No AI provider is available right now/)).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Open the AI settings' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()
    // Already on the settings page: no link to itself.
    expect(screen.queryByRole('link', { name: 'Open the AI settings' })).not.toBeInTheDocument()
  })

  it('uses its own wording when the owner turned AI off', async () => {
    mockApi({ 'GET /health': health, 'GET /ai/status': aiStatus(true, true) })
    renderApp('/')

    expect(await screen.findByText(/^AI is turned off/)).toBeInTheDocument()
  })

  it('is absent when a provider is available', async () => {
    mockApi({ 'GET /health': health, 'GET /ai/status': aiStatus(false) })
    renderApp('/')

    expect(await screen.findByText('Local server is running (version 0.1.0).')).toBeInTheDocument()
    expect(screen.queryByText(/No AI provider/)).not.toBeInTheDocument()
  })

  it('is translated into French', async () => {
    mockApi({ 'GET /health': health, 'GET /ai/status': aiStatus(true) })
    const user = userEvent.setup()
    renderApp('/')

    await screen.findByText(/^No AI provider/)
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getByText(/^Aucun fournisseur d'IA n'est disponible/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Ouvrir les réglages de l'IA" })).toBeInTheDocument()
  })
})
