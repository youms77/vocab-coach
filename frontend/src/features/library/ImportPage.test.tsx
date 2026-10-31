import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CommitBody, Preview, PreviewRow } from '../../api/import'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

function row(line: number, term: string, overrides: Partial<PreviewRow> = {}): PreviewRow {
  return {
    line,
    raw: `- ${term}`,
    term,
    sentence: null,
    item_type: 'collocation',
    normalized_form: term,
    include: true,
    ambiguous: false,
    problems: [],
    duplicates: [],
    in_target_deck: false,
    default_on_duplicate: null,
    ...overrides,
  }
}

const preview: Preview = {
  header: {
    deck: 'Presenting survey results',
    domain: 'statistics',
    source: 'Lecture notes, Survey Methods, week 4',
    context: null,
    deadline: '2099-06-30',
  },
  rows: [
    row(8, 'sampling frame', { sentence: 'The sampling frame excluded students.' }),
    row(13, 'shed light on', {
      sentence: 'These results shed light on how students commute.',
      problems: [
        {
          line: 13,
          severity: 'info',
          code: 'duplicate_exact',
          message: 'Already in your library.',
          suggestion: { item_id: 5 },
        },
      ],
      duplicates: [
        {
          id: 5,
          term: 'shed light on',
          normalized_form: 'shed light on',
          status: 'learning',
          match: 'exact',
          decks: [{ id: 2, name: 'Thesis writing' }],
        },
      ],
      default_on_duplicate: 'attach',
    }),
    row(14, 'nonresponse = non-réponse', {
      include: false,
      ambiguous: true,
      problems: [
        {
          line: 14,
          severity: 'ambiguous',
          code: 'looks_like_definition',
          message: 'Looks like a definition.',
          suggestion: { term: 'nonresponse', note: 'non-réponse' },
        },
      ],
    }),
    row(16, 'the confidence interval is wider for the smaller faculties', {
      include: false,
      ambiguous: true,
      problems: [
        {
          line: 16,
          severity: 'ambiguous',
          code: 'looks_like_sentence',
          message: 'Looks like a sentence.',
          suggestion: null,
        },
      ],
    }),
  ],
  problems: [
    {
      line: 7,
      severity: 'info',
      code: 'heading_ignored',
      message: 'Heading ignored.',
      suggestion: null,
    },
  ],
  rejected: false,
  lines_read: 4,
  importable: 2,
  ambiguous: 2,
  with_duplicates: 1,
}

const summary = {
  deck_id: 7,
  created_deck: true,
  lines_read: 4,
  imported: 2,
  attached: 1,
  skipped: 0,
  ambiguous: 1,
  item_ids: [10, 11, 5],
}

function routes(extra = {}) {
  return {
    'GET /decks': [],
    'POST /import/preview': preview,
    'POST /import/commit': summary,
    ...extra,
  }
}

async function previewText(text = '- sampling frame') {
  fireEvent.change(await screen.findByLabelText('Text'), { target: { value: text } })
  await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
  await screen.findByRole('heading', { name: '3. Check each line' })
}

function commitBody(calls: RecordedCall[]): CommitBody {
  return calls.find((c) => c.path === '/import/commit')!.body as CommitBody
}

describe('import page', () => {
  it('previews the text: header, counts, translated problems, ambiguous rows left out', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    await previewText('- sampling frame')
    expect(calls.find((c) => c.path === '/import/preview')!.body).toEqual({
      text: '- sampling frame',
    })
    expect(screen.getByText('Lecture notes, Survey Methods, week 4')).toBeInTheDocument()
    expect(screen.getByText(/4 lines read · 2 ready · 2 ambiguous/)).toBeInTheDocument()
    expect(screen.getByText(/Heading: not a term, ignored/)).toBeInTheDocument()
    expect(screen.getByText(/Line 7/)).toBeInTheDocument()
    expect(screen.getByLabelText('Import line 8')).toBeChecked()
    // Ambiguous rows: unchecked, with "Import anyway" instead of the normal box.
    expect(screen.queryByLabelText('Import line 14')).not.toBeInTheDocument()
    expect(screen.getAllByLabelText('Import anyway')).toHaveLength(2)
    for (const box of screen.getAllByLabelText('Import anyway')) expect(box).not.toBeChecked()
    expect(screen.getByText('2 rows will be imported.')).toBeInTheDocument()
    // The new deck is named after the header.
    expect(screen.getByLabelText('Name of the new deck')).toHaveValue('Presenting survey results')
  })

  it('sends an ambiguous row only once confirmed, and the duplicate choice as chosen', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    await previewText()
    const sentenceRow = screen.getByLabelText('Term of line 16').closest('tr')!
    await userEvent.click(within(sentenceRow).getByLabelText('Import anyway'))
    expect(screen.getByLabelText('Existing term for line 13')).toHaveValue('attach:5')
    await userEvent.selectOptions(screen.getByLabelText('Existing term for line 13'), 'skip')
    await userEvent.click(screen.getByRole('radio', { name: 'Go straight to the learning queue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByText('2 new terms')).toBeInTheDocument()
    const body = commitBody(calls)
    expect(body.header).toEqual(preview.header)
    expect(body.target).toEqual({ new_deck_name: 'Presenting survey results' })
    expect(body.intake).toBe('queued')
    expect(body.rows).toHaveLength(4)
    expect(body.rows[0]).toEqual({
      line: 8,
      term: 'sampling frame',
      sentence: 'The sampling frame excluded students.',
      item_type: 'collocation',
      include: true,
      confirmed: false,
    })
    expect(body.rows[1]).toMatchObject({ line: 13, include: true, on_duplicate: 'skip' })
    expect(body.rows[1]).not.toHaveProperty('attach_to')
    expect(body.rows[2]).toMatchObject({ line: 14, include: false, confirmed: false })
    expect(body.rows[3]).toMatchObject({ line: 16, include: true, confirmed: true })
  })

  it('keeps the default duplicate choice: attach to the exact match', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    await previewText()
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    await screen.findByText('Import done')
    expect(commitBody(calls).rows[1]).toMatchObject({ on_duplicate: 'attach', attach_to: 5 })
    // Triage is the default intake: the summary links to it.
    expect(commitBody(calls).intake).toBe('triage')
    expect(screen.getByRole('link', { name: 'Sort the new terms' })).toHaveAttribute(
      'href',
      '/triage?deck=7',
    )
  })

  it('a corrected term (the suggestion) is included without confirmation', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    await previewText()
    await userEvent.click(screen.getByRole('button', { name: 'Use “nonresponse”' }))
    expect(screen.getByLabelText('Import line 14')).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    await screen.findByText('Import done')
    expect(commitBody(calls).rows[2]).toMatchObject({
      term: 'nonresponse',
      include: true,
      confirmed: false,
    })
  })

  it('imports into an existing deck', async () => {
    const calls = mockApi(
      routes({
        'GET /decks': [
          {
            id: 2,
            name: 'Thesis writing',
            description: null,
            domain: null,
            kind: 'topic',
            status: 'queued',
            deadline: null,
            priority: 0,
            queue_position: 1,
            source: null,
            created_at: '2026-10-16T10:00:00Z',
            updated_at: '2026-10-16T10:00:00Z',
            item_count: 1,
            items_by_status: {},
          },
        ],
      }),
    )
    renderApp('/import')
    await previewText()
    await userEvent.click(screen.getByRole('radio', { name: 'An existing deck' }))
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
    await userEvent.selectOptions(await screen.findByLabelText('Existing deck'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    await screen.findByText('Import done')
    expect(commitBody(calls).target).toEqual({ deck_id: 2 })
  })

  it('reads a file in the browser and sends its text', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    const file = new File(['- margin of error\n'], 'list.md', { type: 'text/markdown' })
    await userEvent.upload(await screen.findByLabelText('File (.csv, .tsv, .txt or .md)'), file)
    await waitFor(() => expect(screen.getByLabelText('Text')).toHaveValue('- margin of error\n'))
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByRole('heading', { name: '3. Check each line' })
    expect(calls.find((c) => c.path === '/import/preview')!.body).toEqual({
      text: '- margin of error\n',
    })
  })

  it('sends a picked .csv file as a table', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    const csv = 'terme;phrase\nbias;The bias is small.\n'
    const file = new File([csv], 'words.csv', { type: 'text/csv' })
    await userEvent.upload(await screen.findByLabelText('File (.csv, .tsv, .txt or .md)'), file)
    await waitFor(() => expect(screen.getByLabelText('Text')).toHaveValue(csv))
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByRole('heading', { name: '3. Check each line' })
    expect(calls.find((c) => c.path === '/import/preview')!.body).toEqual({
      text: csv,
      format: 'csv',
    })
  })

  it('sends a .tsv as tsv, a .txt as plain Markdown, and edited text as Markdown', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    const input = await screen.findByLabelText('File (.csv, .tsv, .txt or .md)')
    await userEvent.upload(input, new File(['bias\tA bias.'], 'w.tsv', { type: '' }))
    await waitFor(() => expect(screen.getByLabelText('Text')).toHaveValue('bias\tA bias.'))
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await screen.findByRole('heading', { name: '3. Check each line' })
    expect(calls.filter((c) => c.path === '/import/preview')[0]!.body).toEqual({
      text: 'bias\tA bias.',
      format: 'tsv',
    })

    await userEvent.upload(input, new File(['bias'], 'w.txt', { type: 'text/plain' }))
    await waitFor(() => expect(screen.getByLabelText('Text')).toHaveValue('bias'))
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    await waitFor(() => expect(calls.filter((c) => c.path === '/import/preview')).toHaveLength(2))
    expect(calls.filter((c) => c.path === '/import/preview')[1]!.body).toEqual({ text: 'bias' })
  })

  it('asks for CSV UTF-8 when the file is not UTF-8', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    const file = new File(['caf\uFFFD;A caf\uFFFD.'], 'words.csv', { type: 'text/csv' })
    await userEvent.upload(await screen.findByLabelText('File (.csv, .tsv, .txt or .md)'), file)
    expect(await screen.findByText(/CSV UTF-8/)).toBeInTheDocument()
    expect(screen.getByLabelText('Text')).toHaveValue('')
    expect(calls.some((c) => c.path === '/import/preview')).toBe(false)
  })

  it('lists the accepted formats under the file input', async () => {
    mockApi(routes())
    renderApp('/import')
    const input = await screen.findByLabelText('File (.csv, .tsv, .txt or .md)')
    expect(input).toHaveAccessibleDescription(/column 1/)
    expect(input).toHaveAttribute('accept', '.csv,.tsv,.txt,.md,.markdown')
  })

  it('refuses a file over the limit before sending anything', async () => {
    const calls = mockApi(routes())
    renderApp('/import')
    const file = new File(['x'.repeat(300_001)], 'big.md', { type: 'text/markdown' })
    await userEvent.upload(await screen.findByLabelText('File (.csv, .tsv, .txt or .md)'), file)
    expect(await screen.findByText(/longer than 300,000 characters/)).toBeInTheDocument()
    expect(screen.getByLabelText('Text')).toHaveValue('')
    expect(calls.some((c) => c.path === '/import/preview')).toBe(false)
  })

  it('shows a refused preview and keeps the text', async () => {
    mockApi(
      routes({ 'POST /import/preview': () => apiErrorResponse(422, 'invalid_request', 'bad') }),
    )
    renderApp('/import')
    fireEvent.change(await screen.findByLabelText('Text'), { target: { value: '- term' } })
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByText('The request was not in the expected shape.')).toBeInTheDocument()
    expect(screen.getByLabelText('Text')).toHaveValue('- term')
  })

  it('explains a rejected row and names its line', async () => {
    mockApi(
      routes({
        'POST /import/commit': () =>
          apiErrorResponse(422, 'row_rejected', 'rejected', { row: 2, line: 14 }),
      }),
    )
    renderApp('/import')
    await previewText()
    await userEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByText(/must be corrected or confirmed/)).toBeInTheDocument()
    expect(screen.getByText('Line 14')).toBeInTheDocument()
  })

  it('shows a rejected file without the review', async () => {
    mockApi(
      routes({
        'POST /import/preview': {
          ...preview,
          rows: [],
          rejected: true,
          problems: [
            { line: null, severity: 'error', code: 'too_large', message: 'big', suggestion: null },
          ],
        },
      }),
    )
    renderApp('/import')
    fireEvent.change(await screen.findByLabelText('Text'), { target: { value: '- term' } })
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByText(/This text cannot be imported/)).toBeInTheDocument()
    expect(screen.getByText(/The file is too large/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Import' })).not.toBeInTheDocument()
  })

  it('is available in French', async () => {
    mockApi(routes())
    renderApp('/import')
    await screen.findByRole('heading', { name: 'Import a list' })
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'fr')
    expect(screen.getByRole('heading', { name: 'Importer une liste' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Texte'), { target: { value: '- term' } })
    await userEvent.click(screen.getByRole('button', { name: 'Aperçu' }))
    expect(await screen.findAllByLabelText('Importer quand même')).toHaveLength(2)
    expect(screen.getByText(/Ressemble à une phrase/)).toBeInTheDocument()
  })
})
