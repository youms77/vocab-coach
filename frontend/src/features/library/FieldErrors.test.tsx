import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import i18n from '../../i18n'
import { FieldErrors } from './FieldErrors'

const error = new ApiError(422, 'The request is invalid.', 'invalid_request', {
  errors: [
    { loc: ['body', 'rows', '0', 'term'], message: 'String should have at least 1 character', type: 'string_too_short' },
    { loc: ['body', 'kind'], message: 'A rule from a newer backend', type: 'brand_new_type' },
  ],
})

afterEach(() => i18n.changeLanguage('en'))

describe('FieldErrors (D-324)', () => {
  it('says each refused field from its stable type, in French', async () => {
    await i18n.changeLanguage('fr')
    render(<FieldErrors error={error} />)
    expect(screen.getByText('Ce texte est trop court.')).toBeInTheDocument()
    // Rows are counted from 1 for the reader.
    expect(screen.getByText('rows › 1 › term')).toBeInTheDocument()
  })

  it('says it in English too', () => {
    render(<FieldErrors error={error} />)
    expect(screen.getByText('This text is too short.')).toBeInTheDocument()
  })

  it('keeps the backend\'s English text, marked as English, for a type it does not know', async () => {
    await i18n.changeLanguage('fr')
    render(<FieldErrors error={error} />)
    const fallback = screen.getByText('A rule from a newer backend')
    expect(fallback).toHaveAttribute('lang', 'en')
  })

  it('shows nothing for an error without fields', () => {
    const { container } = render(<FieldErrors error={new ApiError(500, 'Boom')} />)
    expect(container).toBeEmptyDOMElement()
  })
})
