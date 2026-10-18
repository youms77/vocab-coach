import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import i18n from '../../i18n'
import {
  CHOICE_SINCE,
  drillOf,
  drillServer,
  errorIdOf,
  GAP_AT,
  GAP_ON,
  MIXED_SPECS,
  PREPOSITION_CATEGORY,
  SOLUTION_TOKENS,
  TOKEN_CHOICE_SPEC,
  TOKEN_SPEC,
} from '../../test/drillFixtures'
import { apiErrorResponse, mockApi, type RecordedCall } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

const answerPosts = (calls: RecordedCall[]) =>
  calls.filter((c) => c.method === 'POST' && c.path.includes('/answer'))

const heading = (n: number, total = 3) => screen.findByRole('heading', { name: `Item ${n} of ${total}` })

async function next(user: ReturnType<typeof userEvent.setup>, name = 'Next') {
  await user.click(await screen.findByRole('button', { name }))
}

describe('Drill player: a whole drill', () => {
  it('goes through gap-fills and a choice, sends the exact bodies and ends with the score', async () => {
    const server = drillServer(MIXED_SPECS)
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')

    // The rule is there from the start, in English; the French only on request.
    expect(await screen.findByRole('heading', { level: 1, name: 'Fixed expression' })).toHaveFocus()
    expect(screen.getByText('Use "on" for a campus, "at" for a place of study.')).toBeInTheDocument()
    expect(screen.queryByText(/On utilise/)).toBeNull()
    await heading(1)

    // Item 1, a gap-fill answered wrongly.
    expect(screen.getByText('blank')).toHaveClass('visually-hidden')
    await user.type(screen.getByLabelText('Your answer'), 'in')
    await user.keyboard('{Enter}')
    const region = await screen.findByRole('region', { name: 'Result' })
    expect(region).toHaveFocus()
    expect(region).toHaveTextContent('Wrong')
    expect(region).toHaveTextContent('Your answer')
    expect(region).toHaveTextContent('Right answer')
    expect(region).toHaveTextContent('on')
    expect(region).toHaveTextContent('Also accepted')
    expect(region).toHaveTextContent('at')
    expect(region).toHaveTextContent('We say "on campus".')
    expect(region).toHaveTextContent('Added to your error log.')
    expect(screen.getByRole('link', { name: 'See the error' })).toHaveAttribute('href', `/errors/${errorIdOf(0)}`)
    expect(screen.getByText(/The correction is exact\. If you think your answer was correct/)).toBeInTheDocument()
    expect(screen.queryByText(/On dit « on campus »/)).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Show the explanation in French' }))
    expect(screen.getByText('On dit « on campus ».')).toBeInTheDocument()
    await next(user)

    // Item 2, a choice, answered with the key 2 ("since", the right one).
    await heading(2)
    const options = screen.getAllByRole('button', { name: /^\d/ })
    expect(options.map((o) => o.textContent)).toEqual(['1 for', '2 since', '3 during'])
    await user.keyboard('2')
    const second = await screen.findByRole('region', { name: 'Result' })
    expect(second).toHaveTextContent('Correct')
    expect(screen.queryByText('Added to your error log.')).toBeNull()
    expect(screen.getByRole('button', { name: /2 since\s*✓ right answer/ })).toBeInTheDocument()
    await user.keyboard('{Enter}')

    // Item 3, "I don't know" on a gap-fill: an empty answer, last item.
    await heading(3)
    await user.click(screen.getByRole('button', { name: "I don't know" }))
    expect(await screen.findByRole('region', { name: 'Result' })).toHaveTextContent('No answer')
    await next(user, 'See the score')

    // The end: score, recap, links.
    expect(await screen.findByRole('heading', { name: 'Drill finished' })).toBeInTheDocument()
    expect(screen.getByText('Score: 1 of 3 correct')).toBeInTheDocument()
    expect(screen.getByText('1 correct, 1 wrong, 1 without an answer.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'New drill on this category' })).toHaveAttribute(
      'href',
      '/drills?category=grammar.preposition.fixed_expression',
    )
    expect(screen.getByRole('link', { name: 'See these errors' })).toHaveAttribute(
      'href',
      '/errors?source=drill&category=grammar.preposition.fixed_expression',
    )
    expect(screen.queryByRole('link', { name: "Back to today's session" })).toBeNull()

    const posts = answerPosts(calls)
    expect(posts.map((p) => p.path)).toEqual([
      '/drills/7/items/0/answer',
      '/drills/7/items/1/answer',
      '/drills/7/items/2/answer',
    ])
    expect(posts[0].body).toEqual({ answer: 'in', response_time_ms: expect.any(Number) })
    expect(posts[1].body).toEqual({ choice_index: 1, response_time_ms: expect.any(Number) })
    expect(posts[2].body).toEqual({ answer: '', response_time_ms: expect.any(Number) })
  })

  it('sends choice_index null for "I don\'t know" on a choice', async () => {
    const server = drillServer([CHOICE_SINCE])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.click(await screen.findByRole('button', { name: "I don't know" }))
    expect(await screen.findByRole('region', { name: 'Result' })).toHaveTextContent('No answer')
    expect(answerPosts(calls)[0].body).toEqual({ choice_index: null, response_time_ms: expect.any(Number) })
  })

  it('measures the response time from the item being shown to the answer', async () => {
    const server = drillServer([GAP_ON])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')
    await screen.findByRole('region', { name: 'Result' })
    const ms = (answerPosts(calls)[0].body as { response_time_ms: number }).response_time_ms
    expect(Number.isInteger(ms)).toBe(true)
    expect(ms).toBeGreaterThanOrEqual(0)
    expect(ms).toBeLessThan(60_000)
  })

  it('offers "Back to today\'s session" when the drill comes from the session', async () => {
    const server = drillServer([GAP_ON], {
      answered: [{ index: 0, given: 'on', choice_index: null, outcome: 'exact' }],
    })
    mockApi({ ...base, ...server.routes })
    renderApp({ pathname: '/drills/7', state: { fromSession: 12 } })
    const link = await screen.findByRole('link', { name: "Back to today's session" })
    expect(link).toHaveAttribute('href', '/session')
    // The next drill stays linked to the session.
    expect(screen.getByRole('link', { name: 'New drill on this category' })).toBeInTheDocument()
  })
})

describe('Drill player: active recall (D-103, D-136)', () => {
  it('has no solution anywhere in the page, and asks for nothing more, before the answer', async () => {
    const server = drillServer([TOKEN_SPEC, TOKEN_CHOICE_SPEC])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')

    await heading(1, 2)
    // The rule is shown from the start; the solution of the first item is not.
    for (const token of SOLUTION_TOKENS) expect(document.body.innerHTML).not.toContain(token)
    // The French of the explanation, the accepted forms and the explanation do not exist yet.
    expect(calls.filter((c) => c.path.startsWith('/drills'))).toEqual([
      expect.objectContaining({ method: 'GET', path: '/drills/7' }),
    ])

    await user.type(screen.getByLabelText('Your answer'), 'something else')
    await user.keyboard('{Enter}')
    const result = await screen.findByRole('region', { name: 'Result' })
    expect(result).toHaveTextContent('ANSWER-TOKEN')
    expect(result).toHaveTextContent('ACCEPTED-TOKEN')
    expect(result).toHaveTextContent('EXPLANATION-EN-TOKEN')
    expect(document.body.innerHTML).not.toContain('EXPLANATION-FR-TOKEN') // French on request only
    await next(user)

    // The second item: the first one's solution is gone, and the right option is not marked.
    await heading(2, 2)
    expect(document.body.innerHTML).not.toContain('ANSWER-TOKEN')
    expect(document.body.innerHTML).not.toContain('CHOICE-EXPLANATION')
    expect(document.body.innerHTML).not.toContain('✓')
    expect(screen.getByRole('button', { name: /OPTION-B-RIGHT/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows no recap of the answered items while the drill is not finished', async () => {
    const server = drillServer(MIXED_SPECS, {
      answered: [{ index: 0, given: 'in', choice_index: null, outcome: 'wrong' }],
    })
    mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    await heading(2)
    // The solution of item 1 is not shown again while item 2 is in front of the user.
    expect(document.body.innerHTML).not.toContain('We say "on campus".')
    expect(screen.queryByText('Drill finished')).toBeNull()
  })
})

describe('Drill player: resuming and refusals', () => {
  it('resumes at the first item not answered', async () => {
    const server = drillServer(MIXED_SPECS, {
      answered: [
        { index: 0, given: 'on', choice_index: null, outcome: 'exact' },
        { index: 1, given: 'for', choice_index: 0, outcome: 'wrong' },
      ],
    })
    mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    await heading(3)
    expect(screen.getByText(/He is good/)).toBeInTheDocument()
  })

  it('shows the end of a finished drill straight away', async () => {
    const server = drillServer([GAP_ON, GAP_AT], {
      answered: [
        { index: 0, given: 'on', choice_index: null, outcome: 'exact' },
        { index: 1, given: 'in', choice_index: null, outcome: 'wrong' },
      ],
    })
    mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    expect(await screen.findByText('Score: 1 of 2 correct')).toBeInTheDocument()
    expect(screen.getByText('Most students live on campus.')).toBeInTheDocument()
    expect(screen.getByText('He is good at maths.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Your answer')).toBeNull()
  })

  it('reloads the drill and moves on when the item was answered elsewhere (409)', async () => {
    const server = drillServer(MIXED_SPECS)
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await heading(1)

    // Another tab answers item 1 first.
    server.answers.push({ index: 0, given: 'on', choice_index: null, outcome: 'exact' })
    await user.type(screen.getByLabelText('Your answer'), 'in')
    await user.keyboard('{Enter}')

    await heading(2)
    expect(screen.queryByRole('region', { name: 'Result' })).toBeNull()
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/drills/7')).toHaveLength(2)
    expect(answerPosts(calls)).toHaveLength(1)
  })

  it('says a mismatch in words and offers Retry, which reads the drill again', async () => {
    const server = drillServer(MIXED_SPECS)
    let refuse = true
    const calls = mockApi({
      ...base,
      ...server.routes,
      'POST /drills/7/items/0/answer': (call: RecordedCall) =>
        refuse
          ? apiErrorResponse(422, 'exercise_mismatch')
          : (server.routes['POST /drills/7/items/0/answer'] as (c: RecordedCall) => Response)(call),
    })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')

    expect(await screen.findByText('This exercise does not match the term.')).toBeInTheDocument()
    refuse = false
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await heading(1)
    expect(calls.filter((c) => c.method === 'GET' && c.path === '/drills/7')).toHaveLength(2)
    expect(screen.queryByText('This exercise does not match the term.')).toBeNull()
    expect(screen.getByLabelText('Your answer')).toHaveValue('')
  })

  it('keeps the typed answer when the request fails, so the user can try again', async () => {
    const server = drillServer([GAP_ON])
    let failing = true
    mockApi({
      ...base,
      ...server.routes,
      'POST /drills/7/items/0/answer': (call: RecordedCall) =>
        failing
          ? apiErrorResponse(404, 'drill_not_found')
          : (server.routes['POST /drills/7/items/0/answer'] as (c: RecordedCall) => Response)(call),
    })
    // A refusal that is not blocking would keep the form; a vanished drill needs Retry.
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')
    expect(await screen.findByText('This drill does not exist (any more).')).toBeInTheDocument()
    expect(screen.getByLabelText('Your answer')).toHaveValue('on')
    failing = false
  })

  it('says when the drill does not exist', async () => {
    mockApi({ ...base, 'GET /drills/7': () => apiErrorResponse(404, 'drill_not_found') })
    renderApp('/drills/7')
    expect(await screen.findByRole('alert')).toHaveTextContent('This drill does not exist (any more).')
    expect(screen.getByRole('link', { name: 'All drills' })).toHaveAttribute('href', '/drills')
  })
})

describe('Drill player: the keyboard', () => {
  it('reads the digit row of an AZERTY keyboard and the numeric keypad', async () => {
    const server = drillServer([CHOICE_SINCE, CHOICE_SINCE])
    const calls = mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    await heading(1, 2)

    // AZERTY without Shift: "é" is the key Digit2.
    fireEvent.keyDown(document.body, { key: 'é', code: 'Digit2' })
    await screen.findByRole('region', { name: 'Result' })
    expect(answerPosts(calls)[0].body).toMatchObject({ choice_index: 1 })

    fireEvent.keyDown(document.body, { key: 'Enter', code: 'Enter' })
    await heading(2, 2)
    fireEvent.keyDown(document.body, { key: '3', code: 'Numpad3' })
    await screen.findByRole('region', { name: 'Result' })
    expect(answerPosts(calls)[1].body).toMatchObject({ choice_index: 2 })
  })

  it('ignores digits with a modifier, while repeating, out of range and while typing', async () => {
    const server = drillServer([CHOICE_SINCE, GAP_ON])
    const calls = mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    await heading(1, 2)

    fireEvent.keyDown(document.body, { key: '2', code: 'Digit2', ctrlKey: true })
    fireEvent.keyDown(document.body, { key: '2', code: 'Digit2', altKey: true })
    fireEvent.keyDown(document.body, { key: '2', code: 'Digit2', metaKey: true })
    fireEvent.keyDown(document.body, { key: '2', code: 'Digit2', repeat: true })
    fireEvent.keyDown(document.body, { key: '4', code: 'Digit4' }) // only three options
    expect(answerPosts(calls)).toHaveLength(0)
    expect(screen.queryByRole('region', { name: 'Result' })).toBeNull()
  })

  it('does not read digits typed in the answer field as a choice', async () => {
    const server = drillServer([GAP_ON])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), '2')
    expect(answerPosts(calls)).toHaveLength(0)
    expect(screen.getByLabelText('Your answer')).toHaveValue('2')
  })

  it('does not send an empty gap-fill with Enter', async () => {
    const server = drillServer([GAP_ON])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.click(await screen.findByLabelText('Your answer'))
    await user.keyboard('{Enter}')
    expect(answerPosts(calls)).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Check' })).toBeDisabled()
  })

  it('sends one answer when Enter is pressed twice before the screen updates', async () => {
    const server = drillServer([GAP_ON])
    const calls = mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    const form = screen.getByLabelText('Your answer').closest('form') as HTMLFormElement

    act(() => {
      fireEvent.submit(form)
      fireEvent.submit(form)
    })
    await screen.findByRole('region', { name: 'Result' })
    expect(answerPosts(calls)).toHaveLength(1)
  })

  it('sends one answer when a choice key is pressed twice at once', async () => {
    const server = drillServer([CHOICE_SINCE])
    const calls = mockApi({ ...base, ...server.routes })
    renderApp('/drills/7')
    await heading(1, 1)
    act(() => {
      fireEvent.keyDown(document.body, { key: '2', code: 'Digit2' })
      fireEvent.keyDown(document.body, { key: '1', code: 'Digit1' })
    })
    await screen.findByRole('region', { name: 'Result' })
    expect(answerPosts(calls)).toHaveLength(1)
    expect(answerPosts(calls)[0].body).toMatchObject({ choice_index: 1 })
  })

  it('goes to the next item once when Enter is pressed twice', async () => {
    const server = drillServer(MIXED_SPECS)
    mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')
    await screen.findByRole('region', { name: 'Result' })

    act(() => {
      fireEvent.keyDown(document.body, { key: 'Enter', code: 'Enter' })
      fireEvent.keyDown(document.body, { key: 'Enter', code: 'Enter' })
    })
    await heading(2)
    expect(screen.queryByRole('heading', { name: 'Item 3 of 3' })).toBeNull()
  })

  it('leaves Enter to a focused button, so "Next" is not pressed twice', async () => {
    const server = drillServer(MIXED_SPECS)
    mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await user.type(await screen.findByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')
    const button = await screen.findByRole('button', { name: 'Next' })
    button.focus()
    await user.keyboard('{Enter}')
    await heading(2)
  })

  it('shows one keyboard hint per phase', async () => {
    const server = drillServer([GAP_ON, CHOICE_SINCE])
    mockApi({ ...base, ...server.routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await heading(1, 2)
    expect(document.querySelector('.key-hints')).toHaveTextContent('Enter check')
    await user.type(screen.getByLabelText('Your answer'), 'on')
    await user.keyboard('{Enter}')
    await screen.findByRole('region', { name: 'Result' })
    expect(document.querySelector('.key-hints')).toHaveTextContent('Enter next')
    await user.keyboard('{Enter}')
    await heading(2, 2)
    expect(document.querySelector('.key-hints')).toHaveTextContent('1–3 choose')
  })
})

describe('Drill player: the rule and the language', () => {
  it('shows the rule in French only on request', async () => {
    mockApi({ ...base, ...drillServer([GAP_ON]).routes })
    const user = userEvent.setup()
    renderApp('/drills/7')
    await heading(1, 1)
    expect(document.body.innerHTML).not.toContain('On utilise')
    const button = screen.getByRole('button', { name: 'Show the rule in French' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    await user.click(button)
    expect(screen.getByText(/On utilise « on » pour un campus/)).toBeInTheDocument()
    expect(button).toHaveAttribute('aria-expanded', 'true')
  })

  it('is translated, and uses the French label of the category', async () => {
    await i18n.changeLanguage('fr')
    mockApi({ ...base, ...drillServer([GAP_ON, GAP_AT]).routes })
    renderApp('/drills/7')
    expect(await screen.findByRole('heading', { level: 1, name: PREPOSITION_CATEGORY.label_fr })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Question 1 sur 2' })).toBeInTheDocument()
    expect(screen.getByText('blanc')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Je ne sais pas' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Afficher la règle en français' })).toBeInTheDocument()
  })

  it('has the drill fixture consistent with what the player reads', () => {
    expect(drillOf([GAP_ON]).items[0]).toMatchObject({ answered: false, result: null, options: null })
    expect(waitFor).toBeDefined()
  })
})
