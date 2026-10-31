import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import '../../i18n'
import { RatingButtons } from './RatingButtons'

describe('RatingButtons', () => {
  it('gives each rating its name, its key and a stable tone class', () => {
    render(<RatingButtons proposed={null} selfGraded={false} pending={null} onRate={vi.fn()} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(4)
    expect(buttons.map((b) => b.className)).toEqual([
      expect.stringContaining('rating__button--again'),
      expect.stringContaining('rating__button--hard'),
      expect.stringContaining('rating__button--good'),
      expect.stringContaining('rating__button--easy'),
    ])
    expect(screen.getByRole('button', { name: /^1 Again/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^4 Easy/ })).toBeInTheDocument()
  })

  it('says "Suggested" in words on the proposed rating, not only by its look', () => {
    render(<RatingButtons proposed={3} selfGraded={false} pending={null} onRate={vi.fn()} />)

    const good = screen.getByRole('button', { name: /^3 Good/ })
    expect(good).toHaveTextContent('Suggested')
    expect(good.className).toContain('rating__button--suggested')
    expect(screen.getByRole('button', { name: /^1 Again/ })).not.toHaveTextContent('Suggested')
  })
})
