import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import { mockApi } from '../../test/mockApi'
import { renderWithProviders } from '../../test/renderApp'
import {
  categoryTree,
  correctionError,
  feedback,
  loggedErrors,
  PARAGRAPH,
  spanOf,
  TWO_ERRORS,
} from '../../test/writingFixtures'
import { CorrectionView } from './CorrectionView'

const marks = () => Array.from(document.querySelectorAll('mark'))

describe('CorrectionView', () => {
  it('shows one numbered, underlined mark per error and the errors grouped by sentence', () => {
    mockApi({})
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    expect(marks()).toHaveLength(TWO_ERRORS.length)
    expect(marks().map((m) => m.firstChild?.textContent)).toEqual(['I lived', 'in campus'])
    // The numbers are text (not only a colour) and link to the entries.
    expect(within(marks()[0]).getByRole('link', { name: 'Error 1: go to its explanation' })).toHaveTextContent('1')
    expect(within(marks()[1]).getByRole('link', { name: 'Error 2: go to its explanation' })).toHaveTextContent('2')
    expect(screen.getByRole('heading', { name: 'Errors' })).toBeInTheDocument()
    // Both errors are in sentence 2: one group.
    expect(screen.getAllByText('Sentence 2')).toHaveLength(1)
    expect(screen.getByText('Error 1')).toBeInTheDocument()
    expect(screen.getByText('Error 2')).toBeInTheDocument()
    // The change, the alternatives, the category (label and code) and the English explanation.
    expect(screen.getByText('on campus')).toBeInTheDocument()
    expect(screen.getByText('at university')).toBeInTheDocument()
    expect(screen.getByText(/Fixed expression/)).toBeInTheDocument()
    expect(screen.getByText('grammar.preposition.fixed_expression')).toBeInTheDocument()
    expect(screen.getByText('We say "on campus" (a fixed expression).')).toBeInTheDocument()
    expect(screen.getByText('Clear and well organised.')).toBeInTheDocument()
  })

  it('groups errors under their own sentence', () => {
    mockApi({})
    const errors = [
      correctionError({ sentence_index: 1, wrong: 'moved to Yaoundé', correction: 'moved to Yaoundé city' }),
      correctionError(),
    ]
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH, { errors })} errors={loggedErrors(errors)} />,
    )
    expect(screen.getByText('Sentence 1')).toBeInTheDocument()
    expect(screen.getByText('Sentence 2')).toBeInTheDocument()
  })

  it('moves the focus from a mark to its entry and back', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    await user.click(screen.getByRole('link', { name: 'Error 2: go to its explanation' }))
    const entry = screen.getByText('Error 2').closest('li')
    expect(entry).toHaveFocus()
    await user.click(within(entry as HTMLElement).getByRole('link', { name: 'Back to the text' }))
    expect(marks()[1]).toHaveFocus()
  })

  it('hides the French explanation until it is asked for, per error', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    expect(screen.queryByText(/expression figée\)/)).toBeNull()
    const buttons = screen.getAllByRole('button', { name: 'Show in French' })
    expect(buttons).toHaveLength(2)
    await user.click(buttons[1])
    expect(screen.getByText('On dit « on campus » (expression figée).')).toBeInTheDocument()
    expect(screen.queryByText('« Since then » demande le present perfect.')).toBeNull()
    expect(screen.getByRole('button', { name: 'Hide the French' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows English first even when the interface is French', async () => {
    mockApi({})
    await i18n.changeLanguage('fr')
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    expect(screen.getByText('We say "on campus" (a fixed expression).')).toBeInTheDocument()
    expect(screen.queryByText('On dit « on campus » (expression figée).')).toBeNull()
    expect(screen.getAllByRole('button', { name: 'Afficher en français' })).toHaveLength(2)
    // The category label follows the interface language, the code stays.
    expect(screen.getByText(/Expression figée/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Erreurs' })).toBeInTheDocument()
  })

  it('has no French button when the French is null (an explanation edited since)', () => {
    mockApi({})
    const rows = loggedErrors().map((row) => ({ ...row, explanation_fr: null }))
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={rows} />)
    expect(screen.queryByRole('button', { name: 'Show in French' })).toBeNull()
  })

  it('uses the logged (possibly edited) explanation in preference to the stored one', () => {
    mockApi({})
    const rows = loggedErrors().map((row, i) => (i === 1 ? { ...row, explanation: 'My own note.' } : row))
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={rows} />)
    expect(screen.getByText('My own note.')).toBeInTheDocument()
    expect(screen.queryByText('We say "on campus" (a fixed expression).')).toBeNull()
  })

  it('leaves out the natural version when it is null, and offers Copy for the others', async () => {
    mockApi({})
    const withNull = feedback(PARAGRAPH, { output: { natural_text: null } })
    const { unmount } = renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={withNull} errors={loggedErrors()} />,
    )
    expect(screen.getByRole('heading', { name: 'Corrected version' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'More natural version' })).toBeNull()
    expect(screen.getAllByRole('button', { name: 'Copy' })).toHaveLength(1)
    unmount()

    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    expect(screen.getByRole('heading', { name: 'More natural version' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Copy' })).toHaveLength(2)
  })

  it('copies a version to the clipboard and says so', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    // userEvent.setup() installs a working clipboard stub.
    await user.click(screen.getAllByRole('button', { name: 'Copy' })[0])
    expect(await screen.findByText('Copied')).toBeInTheDocument()
    expect(await navigator.clipboard.readText()).toContain('I have lived on campus')
  })

  it('shows the plain text and "Not corrected yet" for a missing or unknown feedback', () => {
    mockApi({})
    const { unmount } = renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={null} />)
    expect(screen.getByText(PARAGRAPH)).toBeInTheDocument()
    expect(screen.getByText('Not corrected yet')).toBeInTheDocument()
    expect(marks()).toHaveLength(0)
    unmount()

    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={{ format: 'some-future-format', output: undefined }} />,
    )
    expect(screen.getByText(PARAGRAPH)).toBeInTheDocument()
    expect(screen.getByText('Not corrected yet')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Errors' })).toBeNull()
  })

  it('announces a proposed category with a link to the categories page', () => {
    mockApi({})
    renderWithProviders(
      <CorrectionView
        text={PARAGRAPH}
        feedback={feedback(PARAGRAPH)}
        errors={loggedErrors()}
        proposedCategories={[
          {
            id: 90,
            code: 'grammar.preposition.campus_words',
            parent_code: 'grammar.preposition',
            label_en: 'Campus prepositions',
            label_fr: 'Prépositions du campus',
            description_en: '',
            status: 'proposed',
          },
        ]}
      />,
    )
    expect(screen.getByText('The AI proposed a new category')).toBeInTheDocument()
    expect(screen.getByText(/Campus prepositions/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review the proposed categories' })).toHaveAttribute(
      'href',
      '/errors/categories',
    )
  })

  it('shows no notice without a proposed category', () => {
    mockApi({})
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} proposedCategories={[]} />,
    )
    expect(screen.queryByText('The AI proposed a new category')).toBeNull()
  })

  it('merges two overlapping errors into one mark that carries both numbers', () => {
    mockApi({})
    const errors = [
      correctionError({ wrong: 'I lived in campus', correction: 'I have lived on campus' }),
      correctionError({ wrong: 'in campus with', correction: 'on campus with' }),
    ]
    renderWithProviders(
      <CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH, { errors })} errors={loggedErrors(errors)} />,
    )
    expect(marks()).toHaveLength(1)
    const links = within(marks()[0]).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['1', '2'])
    expect(marks()[0].firstChild?.textContent).toBe('I lived in campus with')
    // Both entries still exist, and both lead back to the one mark.
    expect(screen.getAllByRole('link', { name: 'Back to the text' })).toHaveLength(2)
  })

  it('puts the mark at the right place when an emoji comes first', () => {
    mockApi({})
    const text = '\u{1F600} Since then, I lived in campus with friends.'
    const errors = [correctionError()]
    renderWithProviders(
      <CorrectionView
        text={text}
        feedback={feedback(text, { errors, spans: [spanOf(text, 'in campus', 0)] })}
        errors={loggedErrors(errors)}
      />,
    )
    expect(marks().map((m) => m.firstChild?.textContent)).toEqual(['in campus'])
  })

  it('says clearly that there are no errors (a text, then a single sentence)', () => {
    mockApi({})
    const clean = feedback(PARAGRAPH, { errors: [] })
    const { unmount } = renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={clean} errors={[]} />)
    expect(screen.getByText('No errors found.')).toBeInTheDocument()
    expect(marks()).toHaveLength(0)
    unmount()

    const one = feedback('I will look at the numbers.', { errors: [], output: { sentences: [{ index: 1, corrected: 'x', status: 'correct' }] } })
    renderWithProviders(<CorrectionView text="I will look at the numbers." feedback={one} errors={[]} />)
    expect(screen.getByText('Your sentence is correct.')).toBeInTheDocument()
  })

  it('presents naturalness remarks as correct but unnatural, never as errors', () => {
    mockApi({})
    const fb = feedback(PARAGRAPH, {
      errors: [],
      output: {
        naturalness_notes: [
          { sentence_index: 2, text: 'friends from my class', suggestion: 'classmates', note: 'Shorter.' },
        ],
      },
    })
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={fb} errors={[]} />)
    expect(screen.getByRole('heading', { name: 'Correct, but not very natural' })).toBeInTheDocument()
    expect(screen.getByText("“classmates”")).toBeInTheDocument()
    expect(screen.getByText('Shorter.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Errors' })).toBeNull()
    expect(marks()).toHaveLength(0)
  })

  it('shows the target terms: used or not, correctly or not, disagreement', () => {
    mockApi({})
    const fb = feedback(PARAGRAPH, {
      errors: [],
      extra: {
        targets: [
          { ref: 0, lexical_item_id: 31, used: true, used_correctly: false, ai_used: true, comment: 'Wrong preposition.', disagreement: false },
          { ref: 1, lexical_item_id: 32, used: false, used_correctly: false, ai_used: true, comment: null, disagreement: true },
        ],
      },
    })
    renderWithProviders(
      <CorrectionView
        text={PARAGRAPH}
        feedback={fb}
        errors={[]}
        targets={[
          { lexical_item_id: 31, term: 'account for', used: true, used_correctly: false },
          { lexical_item_id: 32, term: 'shed light on', used: false, used_correctly: false },
        ]}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Target terms' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'account for' })).toHaveAttribute('href', '/library/items/31')
    expect(screen.getByText(/used, but not correctly/)).toBeInTheDocument()
    expect(screen.getByText(/not used/)).toBeInTheDocument()
    expect(screen.getByText(/disagree about whether this term was used/)).toBeInTheDocument()
  })

  it('links an error to its target term', () => {
    mockApi({})
    const errors = [correctionError({ target_ref: 0 })]
    const rows = loggedErrors(errors).map((row) => ({ ...row, term: { id: 31, term: 'account for' } }))
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH, { errors })} errors={rows} />)
    expect(screen.getByText('Related term:', { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'account for' })).toHaveAttribute('href', '/library/items/31')
  })

  it('takes category labels from the tree when the errors are not logged rows, and falls back to the code', async () => {
    mockApi({ 'GET /error-categories': categoryTree() })
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} />)
    expect(await screen.findByText(/Fixed expression/)).toBeInTheDocument()
    expect(screen.getByText('grammar.preposition.fixed_expression')).toBeInTheDocument()
  })

  it('shows the code alone when the label cannot be found', async () => {
    mockApi({ 'GET /error-categories': [] })
    renderWithProviders(<CorrectionView text={PARAGRAPH} feedback={feedback(PARAGRAPH)} />)
    expect(await screen.findByText('grammar.preposition.fixed_expression')).toBeInTheDocument()
    expect(screen.queryByText(/Fixed expression/)).toBeNull()
  })

  it('compact: marks and list, a corrected version, but no natural version, copy or targets', () => {
    mockApi({})
    renderWithProviders(
      <CorrectionView compact level={3} text={PARAGRAPH} feedback={feedback(PARAGRAPH)} errors={loggedErrors()} />,
    )
    expect(marks()).toHaveLength(2)
    expect(screen.getByRole('heading', { level: 3, name: 'Errors' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Corrected version' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'More natural version' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Copy' })).toBeNull()
  })
})
