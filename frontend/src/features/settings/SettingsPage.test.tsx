import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AiStatus, AiUsage, ConnectionTestResult, ProviderState } from '../../api/ai'
import type { SettingsMap } from '../../api/settings'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const KEY = 'AIzaSy-invented-key-1234567890'

function provider(name: ProviderState['name'], overrides: Partial<ProviderState> = {}): ProviderState {
  return {
    name,
    capabilities: name === 'groq' ? ['text', 'transcription'] : ['text'],
    configured: false,
    enabled: true,
    available: false,
    cooldown_until: null,
    misconfigured: false,
    last_error: null,
    models:
      name === 'gemini'
        ? { text: 'gemini-3.5-flash-lite' }
        : name === 'groq'
          ? { text: 'openai/gpt-oss-20b', transcription: 'whisper-large-v3' }
          : { text: 'gemma3:4b' },
    credential_source: 'none',
    credential_kind: name === 'ollama' ? 'base_url' : 'api_key',
    ...overrides,
  }
}

function status(overrides: Partial<AiStatus> = {}, providers?: ProviderState[]): AiStatus {
  return {
    ai_off: false,
    degraded: true,
    demo: false,
    order: ['gemini', 'groq', 'ollama'],
    providers: providers ?? [provider('gemini'), provider('groq'), provider('ollama')],
    ...overrides,
  }
}

const emptyDay = (day: string) => ({
  day,
  requests: 0,
  successes: 0,
  input_tokens: 0,
  output_tokens: 0,
  rows: [],
})

const usage: AiUsage = {
  days: [
    {
      day: '2026-10-16',
      requests: 3,
      successes: 2,
      input_tokens: 120,
      output_tokens: 45,
      rows: [
        {
          provider: 'gemini',
          model: 'gemini-3.5-flash-lite',
          requests: 3,
          successes: 2,
          errors: { auth: 1 },
          input_tokens: 120,
          output_tokens: 45,
          avg_duration_ms: 1500,
        },
      ],
    },
    ...['15', '14', '13', '12', '11', '10'].map((d) => emptyDay(`2026-10-${d}`)),
  ],
}

function setting(value: number | string, extra: Partial<SettingsMap[string]> = {}) {
  return {
    value,
    default: value,
    is_default: true,
    type: typeof value === 'string' ? 'str' : Number.isInteger(value) ? 'int' : 'float',
    minimum: null,
    maximum: null,
    choices: null,
    item_choices: null,
    ...extra,
  } as SettingsMap[string]
}

const settings: SettingsMap = {
  daily_time_budget_minutes: setting(45, { minimum: 10, maximum: 240 }),
  new_items_per_day: setting(12, { minimum: 0, maximum: 100 }),
  target_retention: setting(0.9, { type: 'float', minimum: 0.7, maximum: 0.97 }),
  timezone: setting('Africa/Douala'),
  day_start_hour: setting(4, { minimum: 0, maximum: 23 }),
  consolidation_share: setting(0.8, { type: 'float', minimum: 0, maximum: 1 }),
  consolidation_min_stability_days: setting(7, { minimum: 1 }),
  ui_language: setting('en', { choices: ['en', 'fr'] }),
  tts_rate: setting(1, { type: 'float', minimum: 0.5, maximum: 2 }),
  ai_provider_order: {
    ...setting('x'),
    value: ['gemini', 'groq', 'ollama'],
    default: ['gemini', 'groq', 'ollama'],
    type: 'list',
    item_choices: ['gemini', 'groq', 'ollama'],
  },
}

function baseRoutes(aiStatus: AiStatus = status()) {
  return {
    'GET /health': { status: 'ok', version: '0.1.0', demo: aiStatus.demo },
    'GET /ai/status': () => Response.json(aiStatus),
    'GET /ai/usage': usage,
    'GET /settings': settings,
  }
}

function card(name: string) {
  return screen.getByRole('article', { name })
}

const testOk: ConnectionTestResult = {
  provider: 'gemini',
  status: 'ok',
  reason: null,
  model: 'gemini-3.5-flash-lite',
  elapsed_ms: 1234,
  input_tokens: 40,
  output_tokens: 8,
  error_code: null,
  http_status: null,
  message: null,
  detail_kind: 'none',
}

describe('Settings page: providers', () => {
  it('shows each provider with its state and models, never a key', async () => {
    mockApi(
      baseRoutes(
        status({ degraded: false }, [
          provider('gemini', { configured: true, available: true, credential_source: 'env_file' }),
          provider('groq', {
            configured: true,
            cooldown_until: '2026-10-16T10:30:00Z',
            last_error: 'quota_exhausted',
            credential_source: 'env_file',
          }),
          provider('ollama', { configured: false, enabled: false }),
        ]),
      ),
    )
    renderApp('/settings')

    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()
    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    expect(within(gemini).getByText('Ready')).toBeInTheDocument()
    expect(within(gemini).getByText('gemini-3.5-flash-lite')).toBeInTheDocument()
    expect(within(gemini).getByLabelText('API key')).toHaveValue('')
    expect(within(gemini).getByLabelText('API key')).toHaveAttribute('type', 'password')

    const groq = card('Groq')
    expect(within(groq).getByText(/^Paused until/)).toBeInTheDocument()
    expect(within(groq).getByText('Last error: daily quota used up')).toBeInTheDocument()
    expect(within(groq).getByText('whisper-large-v3')).toBeInTheDocument()

    const ollama = card('Ollama (on this computer)')
    expect(within(ollama).getByText('Not configured')).toBeInTheDocument()
    expect(within(ollama).getByLabelText('Ollama address')).toHaveAttribute('type', 'url')
    expect(within(ollama).getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(within(ollama).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
  })

  it('saves a key as JSON, clears the field and refreshes the status', async () => {
    let current = status()
    const calls = mockApi({
      ...baseRoutes(),
      'GET /ai/status': () => Response.json(current),
      'PUT /ai/providers/gemini/credential': () => {
        const saved = provider('gemini', { configured: true, credential_source: 'env_file' })
        current = status({}, [saved, provider('groq'), provider('ollama')])
        return Response.json(saved)
      },
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.type(within(gemini).getByLabelText('API key'), KEY)
    await user.click(within(gemini).getByRole('button', { name: 'Save' }))

    expect(await within(gemini).findByText('Saved. It is used from now on.')).toBeInTheDocument()
    expect(within(gemini).getByLabelText('API key')).toHaveValue('')
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.body).toEqual({ value: KEY })
    expect(put?.headers['content-type']).toBe('application/json')
    expect(document.body.innerHTML).not.toContain(KEY)
    // The refreshed status now offers to remove the saved key.
    expect(await within(gemini).findByRole('button', { name: 'Remove' })).toBeInTheDocument()
    expect(calls.filter((c) => c.path === '/ai/status').length).toBeGreaterThan(1)
  })

  it('refuses an empty value without calling the backend', async () => {
    const calls = mockApi(baseRoutes())
    const user = userEvent.setup()
    renderApp('/settings')

    const groq = await screen.findByRole('article', { name: 'Groq' })
    await user.type(within(groq).getByLabelText('API key'), '   ')
    await user.click(within(groq).getByRole('button', { name: 'Save' }))

    expect(within(groq).getByText('Enter a value first.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)
  })

  it('translates a refused key and keeps the English reason as detail', async () => {
    mockApi({
      ...baseRoutes(),
      'PUT /ai/providers/groq/credential': () =>
        apiErrorResponse(422, 'invalid_credential', 'The key contains a space.'),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const groq = await screen.findByRole('article', { name: 'Groq' })
    await user.type(within(groq).getByLabelText('API key'), 'gsk_invented')
    await user.click(within(groq).getByRole('button', { name: 'Save' }))

    const alert = await within(groq).findByRole('alert')
    expect(alert).toHaveTextContent('This value cannot be saved.')
    expect(alert).toHaveTextContent('The key contains a space.')
    // On failure the value stays, so the user can correct it.
    expect(within(groq).getByLabelText('API key')).toHaveValue('gsk_invented')
  })

  it('explains a locked .env file', async () => {
    mockApi({
      ...baseRoutes(),
      'PUT /ai/providers/gemini/credential': () => apiErrorResponse(409, 'env_file_locked'),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.type(within(gemini).getByLabelText('API key'), KEY)
    await user.click(within(gemini).getByRole('button', { name: 'Save' }))

    expect(await within(gemini).findByRole('alert')).toHaveTextContent(
      'Another program has the .env file open. Close it and try again.',
    )
  })

  it('says when the backend cannot be reached', async () => {
    mockApi({
      ...baseRoutes(),
      'PUT /ai/providers/gemini/credential': () => Promise.reject(new TypeError('Failed to fetch')),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.type(within(gemini).getByLabelText('API key'), KEY)
    await user.click(within(gemini).getByRole('button', { name: 'Save' }))

    expect(await within(gemini).findByRole('alert')).toHaveTextContent(
      'Cannot reach the local server',
    )
  })

  it('asks for confirmation before removing a saved key', async () => {
    const calls = mockApi({
      ...baseRoutes(
        status({}, [
          provider('gemini', { configured: true, credential_source: 'env_file' }),
          provider('groq'),
          provider('ollama'),
        ]),
      ),
      'DELETE /ai/providers/gemini/credential': provider('gemini'),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.click(within(gemini).getByRole('button', { name: 'Remove' }))
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(within(gemini).getByRole('button', { name: 'Cancel' }))
    await user.click(within(gemini).getByRole('button', { name: 'Remove' }))
    await user.click(within(gemini).getByRole('button', { name: 'Yes, remove' }))

    expect(
      await within(gemini).findByText('Removed. The provider is no longer used.'),
    ).toBeInTheDocument()
    const deletes = calls.filter((c) => c.method === 'DELETE')
    expect(deletes).toHaveLength(1)
    expect(deletes[0].body).toBeUndefined()
  })

  it('disables a key set by an environment variable and says where to change it', async () => {
    mockApi(
      baseRoutes(
        status({}, [
          provider('gemini'),
          provider('groq', { configured: true, credential_source: 'environment' }),
          provider('ollama'),
        ]),
      ),
    )
    renderApp('/settings')

    const groq = await screen.findByRole('article', { name: 'Groq' })
    expect(within(groq).getByLabelText('API key')).toBeDisabled()
    expect(within(groq).getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(within(groq).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
    expect(within(groq).getByText(/VOCAB_GROQ_API_KEY/)).toBeInTheDocument()
    // The test still works: the key exists, it is only not editable here.
    expect(within(groq).getByRole('button', { name: 'Test connection' })).toBeEnabled()
  })

  it('locks keys, test and order on the demo database', async () => {
    mockApi(
      baseRoutes(
        status({ demo: true }, [
          provider('gemini', { configured: true, credential_source: 'env_file' }),
          provider('groq'),
          provider('ollama'),
        ]),
      ),
    )
    renderApp('/settings')

    expect(await screen.findByText(/^Demo database: keys/)).toBeInTheDocument()
    const gemini = card('Google Gemini')
    expect(within(gemini).getByLabelText('API key')).toBeDisabled()
    expect(within(gemini).getByRole('button', { name: 'Test connection' })).toBeDisabled()
    expect(within(gemini).getByRole('button', { name: 'Remove' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Use Groq' })).toBeDisabled()
    // Other settings stay editable on the demo database (D-064).
    expect(await screen.findByLabelText('Daily time budget (minutes)')).toBeEnabled()
  })
})

describe('Settings page: connection test', () => {
  const configured = status({}, [
    provider('gemini', { configured: true, credential_source: 'env_file' }),
    provider('groq'),
    provider('ollama'),
  ])

  it('shows a waiting state, then the result, and cannot be started twice', async () => {
    let finish: (response: Response) => void = () => {}
    const calls = mockApi({
      ...baseRoutes(configured),
      'POST /ai/test': () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        }),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.click(within(gemini).getByRole('button', { name: 'Test connection' }))

    const running = await within(gemini).findByRole('button', { name: /^Testing…/ })
    expect(running).toBeDisabled()
    await user.click(running)
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ provider: 'gemini' })

    finish(Response.json(testOk))
    expect(
      await within(gemini).findByText(/It works: gemini-3\.5-flash-lite answered in 1\.2 s\./),
    ).toBeInTheDocument()
    expect(within(gemini).getByText('Tokens: 40 in, 8 out.')).toBeInTheDocument()
    expect(within(gemini).getByRole('button', { name: 'Test connection' })).toBeEnabled()
  })

  it('explains a failed test with the HTTP status and the provider message', async () => {
    mockApi({
      ...baseRoutes(configured),
      'POST /ai/test': {
        ...testOk,
        status: 'unavailable',
        reason: 'auth',
        model: null,
        input_tokens: null,
        output_tokens: null,
        error_code: 'auth',
        http_status: 400,
        message: 'API key not valid. Please pass a valid API key.',
        detail_kind: 'provider',
      },
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.click(within(gemini).getByRole('button', { name: 'Test connection' }))

    expect(
      await within(gemini).findByText('The test failed: the key was refused.'),
    ).toBeInTheDocument()
    expect(within(gemini).getByText('HTTP status 400')).toBeInTheDocument()
    expect(within(gemini).getByText('Provider message (English)')).toBeInTheDocument()
    expect(within(gemini).getByText(/API key not valid/)).toBeInTheDocument()
  })

  it('says when a test of the same provider is already running', async () => {
    mockApi({
      ...baseRoutes(configured),
      'POST /ai/test': () => apiErrorResponse(409, 'test_in_progress'),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const gemini = await screen.findByRole('article', { name: 'Google Gemini' })
    await user.click(within(gemini).getByRole('button', { name: 'Test connection' }))

    expect(await within(gemini).findByRole('alert')).toHaveTextContent(
      'A test of this provider is already running.',
    )
  })
})

describe('Settings page: provider order', () => {
  it('reorders and turns providers off, then saves the order in one request', async () => {
    const calls = mockApi({
      ...baseRoutes(),
      'PATCH /settings': (call) => {
        const order = (call.body as { ai_provider_order: string[] }).ai_provider_order
        return Response.json({ ...settings, ai_provider_order: { ...settings.ai_provider_order, value: order } })
      },
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const save = await screen.findByRole('button', { name: 'Save the order' })
    expect(save).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move Google Gemini up' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Move Groq up' }))
    await user.click(screen.getByRole('checkbox', { name: 'Use Ollama (on this computer)' }))
    await user.click(save)

    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      ai_provider_order: ['groq', 'gemini'],
    })
  })

  it('warns that turning every provider off means no AI', async () => {
    mockApi(baseRoutes())
    const user = userEvent.setup()
    renderApp('/settings')

    for (const name of ['Google Gemini', 'Groq', 'Ollama (on this computer)']) {
      await user.click(await screen.findByRole('checkbox', { name: `Use ${name}` }))
    }
    expect(
      screen.getByText('Every provider is turned off: the app will run without AI.'),
    ).toBeInTheDocument()
  })
})

describe('Settings page: usage', () => {
  it("shows today's calls per provider and model, and the last 7 days", async () => {
    mockApi(baseRoutes())
    renderApp('/settings')

    const section = await screen.findByRole('region', { name: 'AI usage' })
    const table = await within(section).findAllByRole('table')
    expect(table).toHaveLength(2)
    const row = within(table[0]).getByRole('row', { name: /gemini-3\.5-flash-lite/ })
    expect(row).toHaveTextContent('120 / 45')
    expect(row).toHaveTextContent('1.5 s')
    expect(within(table[1]).getAllByRole('row')).toHaveLength(8) // header + 7 days
  })

  it('says when there was no call today', async () => {
    mockApi({ ...baseRoutes(), 'GET /ai/usage': { days: [emptyDay('2026-10-16')] } })
    renderApp('/settings')

    expect(await screen.findByText('No AI call today.')).toBeInTheDocument()
  })
})

describe('Settings page: study settings', () => {
  it('checks bounds before saving and sends only what changed', async () => {
    const calls = mockApi({
      ...baseRoutes(),
      'PATCH /settings': (call) => {
        const changes = call.body as Record<string, number>
        return Response.json({
          ...settings,
          daily_time_budget_minutes: {
            ...settings.daily_time_budget_minutes,
            value: changes.daily_time_budget_minutes,
          },
        })
      },
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const budget = await screen.findByLabelText('Daily time budget (minutes)')
    const study = screen.getByRole('group', { name: 'Daily study' })
    const save = within(study.closest('form') as HTMLElement).getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()

    await user.clear(budget)
    await user.type(budget, '300')
    await user.click(save)
    expect(within(study).getByText('Out of range.')).toBeInTheDocument()
    expect(budget).toHaveAttribute('aria-invalid', 'true')
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false)

    await user.clear(budget)
    await user.type(budget, '60')
    await user.click(save)
    expect(await within(study.closest('form') as HTMLElement).findByText('Saved.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ daily_time_budget_minutes: 60 })
  })

  it('shows a value refused by the backend next to its field', async () => {
    mockApi({
      ...baseRoutes(),
      'PATCH /settings': () =>
        apiErrorResponse(422, 'invalid_setting', "timezone: unknown time zone 'Mars/Olympus'", {
          key: 'timezone',
        }),
    })
    const user = userEvent.setup()
    renderApp('/settings')

    const timezone = await screen.findByLabelText('Time zone')
    await user.clear(timezone)
    await user.type(timezone, 'Mars/Olympus')
    const form = screen.getByRole('group', { name: 'Study day' }).closest('form') as HTMLElement
    await user.click(within(form).getByRole('button', { name: 'Save' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('unknown time zone')
    expect(timezone).toHaveAttribute('aria-invalid', 'true')
  })

  it('does not offer the interface language, which lives in the top bar', async () => {
    mockApi(baseRoutes())
    renderApp('/settings')

    await screen.findByLabelText('Daily time budget (minutes)')
    expect(screen.getAllByLabelText('Language')).toHaveLength(1)
  })
})

describe('Settings page: French', () => {
  it('is translated', async () => {
    mockApi(baseRoutes())
    const user = userEvent.setup()
    renderApp('/settings')

    await screen.findByRole('article', { name: 'Google Gemini' })
    await user.selectOptions(screen.getByLabelText('Language'), 'fr')

    expect(screen.getByRole('heading', { level: 1, name: 'Réglages' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Fournisseurs d'IA" })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Tester la connexion' })).toHaveLength(3)
  })
})
