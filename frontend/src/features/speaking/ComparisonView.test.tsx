import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import i18n from '../../i18n'
import { comparison, step } from '../../test/speechFixtures'
import { ComparisonView } from './ComparisonView'

const WARNING =
  'Speech recognition is not a pronunciation judge: a word it missed may be clear to a person (accent, noise, homophones). Treat these as hints.'

const row = (label: string) => screen.getByText(label).closest('p') as HTMLElement

describe('ComparisonView', () => {
  it('says the result in words, without a percentage or a grade', () => {
    render(<ComparisonView comparison={comparison()} />)
    expect(screen.getByText('4 of 6 words recognised')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/%|\d\/\d/)
  })

  it('marks every operation with a text, never with the colour alone', () => {
    render(<ComparisonView comparison={comparison()} />)
    const target = within(row('Target'))
    // match: plain words
    expect(target.getByText('account')).toBeInTheDocument()
    // close: "≈" shown, and a hidden sentence for screen readers
    expect(target.getByText('effects').parentElement).toHaveTextContent('effects ≈')
    expect(target.getByText(/close match, counted as recognised/)).toHaveClass('visually-hidden')
    // substituted: what was heard instead
    expect(target.getByText('fixed').parentElement).toHaveTextContent('fixed (heard: fix)')
    // missing: not heard
    expect(target.getByText('for').parentElement).toHaveTextContent('for (not heard)')
    // extra, on the Heard row only
    const heard = within(row('Heard'))
    expect(heard.getByText('really').parentElement).toHaveTextContent('really (extra word)')
    expect(target.queryByText('really')).not.toBeInTheDocument()
    expect(heard.queryByText('for')).not.toBeInTheDocument()
  })

  it('lists the words not recognised', () => {
    render(<ComparisonView comparison={comparison()} />)
    const list = screen.getByRole('list')
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(list).toHaveTextContent('for — not heard')
    expect(list).toHaveTextContent('fixed — heard: fix')
  })

  it('always shows the warning, compact or not, even when everything was recognised', () => {
    const perfect = comparison({
      unrecognized: [],
      recognized_count: 2,
      target_word_count: 2,
      steps: [step('match', 'Hello', 'hello', [0, 1, 0, 1]), step('match', 'world', 'world', [1, 2, 1, 2])],
    })
    const { rerender } = render(<ComparisonView comparison={perfect} />)
    expect(screen.getByText(WARNING)).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    rerender(<ComparisonView comparison={comparison()} compact />)
    expect(screen.getByText(WARNING)).toBeInTheDocument()
  })

  it('offers "Log as an intelligibility error" for a substituted word only', async () => {
    const onLog = vi.fn()
    const user = userEvent.setup()
    render(<ComparisonView comparison={comparison()} onLog={onLog} />)
    const buttons = screen.getAllByRole('button', { name: /Log as an intelligibility error/ })
    // "for" was not heard: there is no wrong form to quote, so no button; "fixed" has one.
    expect(buttons).toHaveLength(1)
    await user.click(buttons[0]!)
    expect(onLog).toHaveBeenCalledWith({ target: 'fixed', heard: 'fix' })
  })

  it('has no log button in its compact form (discovery)', () => {
    render(<ComparisonView comparison={comparison()} compact onLog={vi.fn()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('is translated into French', async () => {
    await i18n.changeLanguage('fr')
    render(<ComparisonView comparison={comparison()} onLog={vi.fn()} />)
    expect(screen.getByText('4 mots reconnus sur 6')).toBeInTheDocument()
    expect(screen.getByText(/n’est pas un juge de prononciation/)).toBeInTheDocument()
    expect(screen.getByText('Cible')).toBeInTheDocument()
    expect(screen.getByText('Entendu')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Noter comme erreur d’intelligibilité/ })).toBeInTheDocument()
  })
})
