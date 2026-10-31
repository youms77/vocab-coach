import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { renderApp } from '../../test/renderApp'

describe('Style guide (development only)', () => {
  it('shows the tokens, the components and both sidebar states', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      Response.json({ status: 'ok', version: '0.1.0', demo: false }),
    )
    renderApp('/styleguide')

    expect(await screen.findByRole('heading', { level: 1, name: 'Style guide' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Colour tokens' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Folded' })).toBeInTheDocument()
    expect(screen.getAllByText(/ notice: /)).toHaveLength(4)
  })
})
