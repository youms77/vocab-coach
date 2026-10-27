import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { mockApi } from '../../test/mockApi'
import { renderWithProviders } from '../../test/renderApp'
import {
  loggedSpeakingErrors,
  SPEECH,
  speakingFeedback,
} from '../../test/speechFixtures'
import { CorrectionView } from './CorrectionView'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

const view = (structure?: object | null) => (
  <CorrectionView
    text={SPEECH}
    feedback={speakingFeedback(SPEECH, structure === undefined ? {} : { structure })}
    errors={loggedSpeakingErrors()}
  />
)

describe('CorrectionView: a spoken text (speaking-1)', () => {
  it('says what was heard, with the note, and groups the errors under "Part n"', () => {
    mockApi({})
    renderWithProviders(view())
    expect(
      screen.getByRole('heading', { name: 'What the speech recognition heard' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/a mistake the recogniser smoothed over is not reported, and a misheard word may be/),
    ).toBeInTheDocument()
    expect(screen.getByText('Part 1')).toBeInTheDocument()
    expect(screen.getByText('Part 2')).toBeInTheDocument()
    expect(screen.queryByText(/Sentence 1/)).not.toBeInTheDocument()
    // The marks are the numbered, underlined ones of the written view.
    expect(Array.from(document.querySelectorAll('mark')).map((m) => m.firstChild?.textContent)).toEqual([
      'in campus',
      'since two years',
    ])
  })

  it('shows the Structure section: comment, connectors, suggestions; French on demand', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderWithProviders(view())
    expect(screen.getByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(screen.getByText(/Easy to follow, but the parts are joined only by/)).toBeInTheDocument()
    expect(screen.getByText('Connectors you used')).toBeInTheDocument()
    expect(screen.getByText('so · first of all')).toBeInTheDocument()
    expect(screen.getByText('Try "In addition," to add a second idea.')).toBeInTheDocument()
    // The French is hidden until asked for.
    expect(screen.queryByText(/Facile à suivre/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Essayez « In addition/)).not.toBeInTheDocument()

    const [commentButton, suggestionButton] = screen
      .getAllByRole('button', { name: 'Show in French' })
      .slice(-2)
    await user.click(commentButton!)
    expect(screen.getByText(/Facile à suivre/)).toHaveAttribute('lang', 'fr')
    await user.click(suggestionButton!)
    expect(screen.getByText(/Essayez « In addition/)).toHaveAttribute('lang', 'fr')
  })

  it('says when no connector was found', () => {
    mockApi({})
    renderWithProviders(
      view({ comment_en: 'Short.', comment_fr: '', connectors_used: [], suggestions: [] }),
    )
    expect(screen.getByText('No connector was found in this speech.')).toBeInTheDocument()
    expect(screen.queryByText('Suggestions')).not.toBeInTheDocument()
  })

  it('has no Structure section in answer mode (structure is null)', () => {
    mockApi({})
    renderWithProviders(view(null))
    expect(screen.queryByRole('heading', { name: 'Structure' })).not.toBeInTheDocument()
    expect(screen.queryByText('Connectors you used')).not.toBeInTheDocument()
  })

  it('has no Structure section in the compact view of a review', () => {
    mockApi({})
    renderWithProviders(
      <CorrectionView compact text={SPEECH} feedback={speakingFeedback()} errors={loggedSpeakingErrors()} />,
    )
    expect(screen.queryByRole('heading', { name: 'Structure' })).not.toBeInTheDocument()
  })

  it('speaks French with the same keys', async () => {
    await i18n.changeLanguage('fr')
    mockApi({})
    renderWithProviders(view())
    expect(
      screen.getByRole('heading', { name: 'Ce que la reconnaissance vocale a entendu' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Passage 1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Structure' })).toBeInTheDocument()
    expect(screen.getByText('Connecteurs utilisés')).toBeInTheDocument()
  })
})
