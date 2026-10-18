import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CategoryNode } from '../../api/errors'
import i18n from '../../i18n'
import { treeWithProposal } from '../../test/errorFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { categoryTree } from '../../test/writingFixtures'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const resolves = (calls: RecordedCall[]) =>
  calls.filter((c) => c.method === 'POST' && c.path.endsWith('/resolve'))

describe('Categories page', () => {
  it('shows the tree with counts, statuses, origins and the rejected ones folded', async () => {
    const tree = treeWithProposal()
    tree[0].children[0].count = 9
    tree[0].children[0].count_recent = 2
    mockApi({ ...base, 'GET /error-categories': tree })
    renderApp('/errors/categories')

    expect(await screen.findByRole('heading', { level: 1, name: 'Error categories' })).toHaveFocus()
    const taxonomy = (await screen.findByRole('heading', { name: 'Taxonomy' })).closest('section') as HTMLElement
    const row = within(taxonomy).getByText('Prepositions').closest('p') as HTMLElement
    expect(row).toHaveTextContent('grammar.preposition')
    expect(row).toHaveTextContent('active')
    expect(row).toHaveTextContent('built-in')
    expect(row).toHaveTextContent('9 errors · 2 in the last 14 days')
    expect(within(row).getByRole('link', { name: 'See the errors' })).toHaveAttribute(
      'href',
      '/errors?category=grammar.preposition',
    )
    // A proposed category appears in the tree with its status; a rejected one only in the fold.
    expect(within(taxonomy).getByText('Particles of phrasal verbs')).toBeInTheDocument()
    const fold = within(taxonomy).getByText('Rejected categories (1)').closest('details') as HTMLElement
    expect(fold).not.toHaveAttribute('open')
    expect(within(fold).getByText('Old idea')).toBeInTheDocument()
    expect(within(taxonomy).queryAllByText('Old idea')).toHaveLength(1)
  })

  it('says when no proposal is waiting', async () => {
    mockApi({ ...base, 'GET /error-categories': categoryTree() })
    renderApp('/errors/categories')
    expect(await screen.findByText('No proposal is waiting.')).toBeInTheDocument()
  })

  it('accepts a proposal, sending a rename only when it differs', async () => {
    let tree = treeWithProposal()
    const calls = mockApi({
      ...base,
      'GET /error-categories': () => Response.json(tree),
      'POST /error-categories/901/resolve': (call) => {
        const body = call.body as { label_en?: string }
        const node = {
          ...(tree[0].children[0].children[2] as CategoryNode),
          status: 'active',
          label_en: body.label_en ?? 'Particles of phrasal verbs',
        } as CategoryNode
        tree = categoryTree()
        return Response.json({ category: node, reassigned_error_ids: [] })
      },
    })
    const user = userEvent.setup()
    renderApp('/errors/categories')

    await screen.findByText('Under Prepositions · 4 errors · 4 in the last 14 days')
    await user.click(screen.getByText('Rename before accepting (optional)'))
    const proposal = screen.getByText('Rename before accepting (optional)').closest('li') as HTMLElement
    const english = within(proposal).getByLabelText('English label')
    await user.clear(english)
    await user.type(english, 'Phrasal verb particles')
    await user.click(screen.getByRole('button', { name: 'Accept “Particles of phrasal verbs”' }))

    expect(await screen.findByText('“Phrasal verb particles” is now an active category.')).toBeInTheDocument()
    expect(resolves(calls).map((c) => c.body)).toEqual([
      { decision: 'accept', label_en: 'Phrasal verb particles' },
    ])
    // The tree was reloaded: the proposal has gone.
    await waitFor(() => expect(screen.getByText('No proposal is waiting.')).toBeInTheDocument())
  })

  it('accepts without a rename when the labels are untouched', async () => {
    const calls = mockApi({
      ...base,
      'GET /error-categories': treeWithProposal(),
      'POST /error-categories/901/resolve': () =>
        Response.json({ category: treeWithProposal()[0].children[0].children[2], reassigned_error_ids: [] }),
    })
    const user = userEvent.setup()
    renderApp('/errors/categories')
    await user.click(await screen.findByRole('button', { name: 'Accept “Particles of phrasal verbs”' }))
    await waitFor(() => expect(resolves(calls)).toHaveLength(1))
    expect(resolves(calls)[0].body).toEqual({ decision: 'accept' })
  })

  it('explains a rejection before doing it, then says how many errors moved', async () => {
    let tree = treeWithProposal()
    const calls = mockApi({
      ...base,
      'GET /error-categories': () => Response.json(tree),
      'POST /error-categories/901/resolve': () => {
        const node = { ...tree[0].children[0].children[2], status: 'rejected' } as CategoryNode
        tree = categoryTree()
        return Response.json({ category: node, reassigned_error_ids: [3, 4, 8, 9] })
      },
    })
    const user = userEvent.setup()
    renderApp('/errors/categories')

    await user.click(await screen.findByRole('button', { name: 'Reject “Particles of phrasal verbs”' }))
    expect(
      screen.getByText('Rejecting “Particles of phrasal verbs” moves its errors to the parent category.'),
    ).toBeInTheDocument()
    expect(resolves(calls)).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reject “Particles of phrasal verbs”' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reject it' }))

    expect(
      await screen.findByText(
        '“Particles of phrasal verbs” rejected. 4 errors moved to the parent category.',
      ),
    ).toBeInTheDocument()
    expect(resolves(calls)).toHaveLength(1)
    expect(resolves(calls)[0].body).toEqual({ decision: 'reject' })
    expect(screen.getByRole('status')).toHaveTextContent('4 errors moved')
  })

  it('reloads the tree when the proposal was already decided elsewhere', async () => {
    let loads = 0
    mockApi({
      ...base,
      'GET /error-categories': () => {
        loads += 1
        return Response.json(loads === 1 ? treeWithProposal() : categoryTree())
      },
      'POST /error-categories/901/resolve': () => apiErrorResponse(409, 'category_not_proposed'),
    })
    const user = userEvent.setup()
    renderApp('/errors/categories')
    await user.click(await screen.findByRole('button', { name: 'Accept “Particles of phrasal verbs”' }))

    expect(
      await screen.findByText('This category is no longer waiting for a decision.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(loads).toBe(2))
    expect(await screen.findByText('No proposal is waiting.')).toBeInTheDocument()
  })

  it('creates a subcategory with the exact body, and reports a duplicate code', async () => {
    let answer: Response | null = null
    const calls = mockApi({
      ...base,
      'GET /error-categories': categoryTree(),
      'POST /error-categories': () =>
        answer ??
        Response.json(
          {
            id: 77,
            code: 'grammar.preposition.time',
            parent_code: 'grammar.preposition',
            label_en: 'Time prepositions',
            label_fr: 'Prépositions de temps',
            description_en: '',
            description_fr: '',
            status: 'active',
            origin: 'user',
            count: 0,
            count_recent: 0,
            children: [],
          },
          { status: 201 },
        ),
    })
    const user = userEvent.setup()
    renderApp('/errors/categories')

    await user.selectOptions(await screen.findByLabelText('Parent category'), 'grammar.preposition')
    await user.type(screen.getByLabelText('Code name'), 'Time')
    expect(screen.getByRole('button', { name: 'Create the category' })).toBeDisabled()
    expect(screen.getByText(/The code name must follow the rule/)).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Code name'))
    await user.type(screen.getByLabelText('Code name'), 'time')
    await user.type(screen.getByLabelText('English label'), 'Time prepositions')
    await user.type(screen.getByLabelText('French label'), 'Prépositions de temps')
    await user.type(screen.getByLabelText('English description (optional)'), 'In, on, at for time.')
    await user.click(screen.getByRole('button', { name: 'Create the category' }))

    expect(await screen.findByText('Created “Time prepositions” (grammar.preposition.time).')).toBeInTheDocument()
    const created = calls.filter((c) => c.method === 'POST' && c.path === '/error-categories')
    expect(created.map((c) => c.body)).toEqual([
      {
        parent_code: 'grammar.preposition',
        slug: 'time',
        label_en: 'Time prepositions',
        label_fr: 'Prépositions de temps',
        description_en: 'In, on, at for time.',
        description_fr: '',
      },
    ])
    expect(screen.getByLabelText('Code name')).toHaveValue('')

    answer = apiErrorResponse(409, 'category_exists')
    await user.type(screen.getByLabelText('Code name'), 'time')
    await user.type(screen.getByLabelText('English label'), 'Time')
    await user.type(screen.getByLabelText('French label'), 'Temps')
    await user.click(screen.getByRole('button', { name: 'Create the category' }))
    expect(await screen.findByText('A category with this code already exists.')).toBeInTheDocument()
  })

  it('is in French when the language is French', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, 'GET /error-categories': treeWithProposal() })
    renderApp('/errors/categories')
    expect(await screen.findByRole('heading', { level: 1, name: "Catégories d'erreurs" })).toBeInTheDocument()
    expect((await screen.findAllByText('Particules des verbes à particule')).length).toBeGreaterThan(0)
    expect(screen.getByText('Catégories rejetées (1)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Accepter « Particules des verbes à particule »' })).toBeInTheDocument()
  })
})
