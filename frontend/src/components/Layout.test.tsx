import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { renderApp } from '../test/renderApp'

function mockHealth(body: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(Response.json(body)))
}

describe('Demo data badge', () => {
  it('is shown when the backend serves demo data', async () => {
    mockHealth({ status: 'ok', version: '0.1.0', demo: true })
    renderApp('/')

    expect(await screen.findByText('Demo data')).toBeInTheDocument()
  })

  it('is translated into French', async () => {
    mockHealth({ status: 'ok', version: '0.1.0', demo: true })
    const user = userEvent.setup()
    renderApp('/')

    await screen.findByText('Demo data')
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getByText('Données de démo')).toBeInTheDocument()
  })

  it('is absent for the personal database', async () => {
    mockHealth({ status: 'ok', version: '0.1.0', demo: false })
    renderApp('/')

    expect(await screen.findByText('Local server is running (version 0.1.0).')).toBeInTheDocument()
    expect(screen.queryByText('Demo data')).not.toBeInTheDocument()
  })
})
