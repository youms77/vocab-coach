import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AiStatus, SpeechProviderState } from '../../api/ai'
import type { SettingsMap } from '../../api/settings'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { apiErrorResponse, mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'

const KEY = 'invented-azure-key-0123456789'

function azure(overrides: Partial<SpeechProviderState> = {}): SpeechProviderState {
  return {
    name: 'azure',
    capabilities: ['pronunciation_assessment'],
    configured: false,
    enabled: true,
    available: false,
    cooldown_until: null,
    misconfigured: false,
    last_error: null,
    models: { pronunciation_assessment: 'pa-rest-v1' },
    credential_source: 'none',
    credential_kind: 'api_key',
    region: null,
    ...overrides,
  }
}

function status(speech: SpeechProviderState, demo = false): AiStatus {
  return {
    ai_off: false,
    degraded: true,
    demo,
    order: ['gemini', 'groq', 'ollama'],
    providers: [],
    speech_providers: [speech],
  }
}

function setting(value: string | string[], extra = {}) {
  return {
    value,
    default: value,
    is_default: true,
    type: 'str',
    minimum: null,
    maximum: null,
    choices: null,
    item_choices: null,
    ...extra,
  } as SettingsMap[string]
}

const settings = (assessment = 'off'): SettingsMap => ({
  pronunciation_assessment: setting(assessment, { choices: ['off', 'azure'] }),
  tts_voice: setting(''),
})

const usage = {
  month: '2026-10',
  audio_seconds: 150,
  assessments: 5,
  limit_seconds: 18000,
  limit_checked_on: '2026-10-24',
  note: 'estimate',
}

function routes(speech: SpeechProviderState, assessment = 'off', demo = false) {
  return {
    'GET /health': { status: 'ok', version: '0.1.0', demo },
    'GET /ai/status': () => Response.json(status(speech, demo)),
    'GET /ai/usage': { days: [] },
    'GET /settings': settings(assessment),
    'GET /speech/pronunciation/usage': usage,
  }
}

describe('Settings page: Azure card', () => {
  it('warns about Microsoft and F0, and asks for a key and a region', async () => {
    installFakeSpeech()
    mockApi(routes(azure()))
    renderApp('/settings')

    const card = await screen.findByRole('region', {
      name: 'Pronunciation assessment (optional, Azure)',
    })
    expect(within(card).getByText(/sent to Microsoft/)).toBeInTheDocument()
    expect(within(card).getByText(/F0 resource only, never S0/)).toBeInTheDocument()
    expect(within(card).getByLabelText('Azure Speech key')).toHaveAttribute('type', 'password')
    expect(within(card).getByRole('button', { name: 'Test connection' })).toBeDisabled()
    // Nothing can be turned on before a key is saved.
    expect(within(card).getByRole('checkbox')).toBeDisabled()
    expect(within(card).queryByText('Use this month')).not.toBeInTheDocument()
  })

  it('needs both fields, then saves the key and the region together and clears the key', async () => {
    installFakeSpeech()
    let current = azure()
    const calls = mockApi({
      ...routes(azure()),
      'GET /ai/status': () => Response.json(status(current)),
      'PUT /ai/providers/azure/credential': () => {
        current = azure({ configured: true, credential_source: 'env_file', region: 'westeurope' })
        return Response.json(current)
      },
    })
    const user = userEvent.setup()
    renderApp('/settings')
    const card = await screen.findByRole('region', {
      name: 'Pronunciation assessment (optional, Azure)',
    })

    await user.click(within(card).getByRole('button', { name: 'Save' }))
    expect(within(card).getByText('Paste your key.')).toBeInTheDocument()
    await user.type(within(card).getByLabelText('Azure Speech key'), KEY)
    await user.click(within(card).getByRole('button', { name: 'Save' }))
    expect(within(card).getByText('Enter the region of your Azure resource.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'PUT')).toBe(false)

    await user.type(within(card).getByLabelText('Region'), 'westeurope')
    await user.click(within(card).getByRole('button', { name: 'Save' }))

    expect(await within(card).findByText('Saved. It is used from now on.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ value: KEY, region: 'westeurope' })
    expect(within(card).getByLabelText('Azure Speech key')).toHaveValue('')
    expect(await within(card).findByText('Current region: westeurope.')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(KEY)
  })

  it('shows a refused region in words', async () => {
    installFakeSpeech()
    mockApi({
      ...routes(azure()),
      'PUT /ai/providers/azure/credential': () => apiErrorResponse(422, 'invalid_region'),
    })
    const user = userEvent.setup()
    renderApp('/settings')
    const card = await screen.findByRole('region', {
      name: 'Pronunciation assessment (optional, Azure)',
    })
    await user.type(within(card).getByLabelText('Azure Speech key'), KEY)
    await user.type(within(card).getByLabelText('Region'), 'west europe!')
    await user.click(within(card).getByRole('button', { name: 'Save' }))
    expect(await within(card).findByText(/This region is not valid/)).toBeInTheDocument()
  })

  it('turns the setting on, and shows the use of the month', async () => {
    installFakeSpeech()
    const calls = mockApi({
      ...routes(azure({ configured: true, credential_source: 'env_file', region: 'westeurope' })),
      'PATCH /settings': () => Response.json(settings('azure')),
    })
    const user = userEvent.setup()
    renderApp('/settings')
    const card = await screen.findByRole('region', {
      name: 'Pronunciation assessment (optional, Azure)',
    })

    expect(await within(card).findByText(/2.5 min of audio sent in 5 assessments/)).toBeInTheDocument()
    expect(within(card).getByText(/about 300 min a month/)).toBeInTheDocument()
    await user.click(within(card).getByRole('checkbox'))
    expect(await within(card).findByText('Setting saved.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      pronunciation_assessment: 'azure',
    })
  })

  it('is locked on the demo database', async () => {
    installFakeSpeech()
    mockApi(routes(azure({ configured: true, region: 'westeurope' }), 'off', true))
    renderApp('/settings')
    const card = await screen.findByRole('region', {
      name: 'Pronunciation assessment (optional, Azure)',
    })
    expect(within(card).getByLabelText('Azure Speech key')).toBeDisabled()
    expect(within(card).getByRole('checkbox')).toBeDisabled()
    expect(within(card).getByRole('button', { name: 'Test connection' })).toBeDisabled()
  })

  it('is absent when the backend lists no speech provider', async () => {
    installFakeSpeech()
    mockApi({
      ...routes(azure()),
      'GET /ai/status': () => Response.json({ ...status(azure()), speech_providers: undefined }),
    })
    renderApp('/settings')
    await screen.findByRole('heading', { name: 'AI providers' })
    expect(screen.queryByText('Pronunciation assessment (optional, Azure)')).not.toBeInTheDocument()
  })
})
