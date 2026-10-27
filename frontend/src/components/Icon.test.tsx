import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Icon } from './Icon'
import { ICON_NAMES } from './iconPaths'

describe('Icon', () => {
  it('is decorative and drawn in the current colour at the requested size', () => {
    const { container } = render(<Icon name="home" size={18} />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).toHaveAttribute('stroke', 'currentColor')
    expect(svg).toHaveAttribute('width', '18')
  })

  it('has a path for every name', () => {
    for (const name of ICON_NAMES) {
      const { container } = render(<Icon name={name} />)
      expect(container.querySelector('path')?.getAttribute('d')?.length).toBeGreaterThan(5)
    }
  })
})
