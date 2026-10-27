import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Production } from '../../api/productions'
import type { AssessableReason, PronunciationScores } from '../../api/speech'
import { installFakeRecorder, recordTake } from '../../test/fakeRecorder'
import { installFakeSpeech } from '../../test/fakeSpeech'
import { mockApi } from '../../test/mockApi'
import { renderApp } from '../../test/renderApp'
import { shadowing, speechOut } from '../../test/speechFixtures'

const wav = vi.hoisted(() => ({ convert: vi.fn() }))
vi.mock('../../speech/wav', () => ({ convertToWav: wav.convert, canConvertToWav: () => true }))

const base = {
  'GET /health': { status: 'ok', version: '0.1.0', demo: false },
  'GET /ai/status': { ai_off: false, degraded: false, demo: false, order: [], providers: [] },
}

function scores(overrides: Partial<PronunciationScores> = {}): PronunciationScores {
  return {
    provider: 'azure',
    model: 'pa-rest-v1',
    assessed_at: '2026-10-24T10:00:00Z',
    status: 'ok',
    overall: { accuracy: 82, fluency: 90, completeness: 100, pronunciation: 78.4 },
    words: [
      { word: 'We', accuracy: 97, error_type: 'None', offset_ms: 0, duration_ms: 200, phonemes: [] },
      {
        word: 'account',
        accuracy: 41,
        error_type: 'Mispronunciation',
        offset_ms: 200,
        duration_ms: 500,
        phonemes: [
          { phoneme: 'ə', accuracy: 35 },
          { phoneme: 'k', accuracy: 92 },
          { phoneme: 'aʊ', accuracy: 60 },
        ],
      },
      { word: 'regional', accuracy: 0, error_type: 'Omission', offset_ms: 700, duration_ms: 0, phonemes: [] },
      { word: 'fixed', accuracy: 88, error_type: 'Weird', offset_ms: 700, duration_ms: 300, phonemes: [] },
    ],
    duration_s: 4.2,
    ...overrides,
  }
}

function assessable(overrides: Partial<Production> = {}) {
  return shadowing({ pronunciation: null, assessable: true, assessable_reason: null, ...overrides })
}

function refused(reason: AssessableReason) {
  return assessable({ assessable: false, assessable_reason: reason })
}

describe('Shadowing: pronunciation assessment', () => {
  it('shows the scores of an assessed take: overall, words with their type, weakest sounds', async () => {
    installFakeSpeech()
    mockApi({
      ...base,
      'GET /productions/7': shadowing({
        pronunciation: scores(),
        assessable: false,
        assessable_reason: 'already_assessed',
      }),
    })
    renderApp('/speaking/shadowing/7')

    const section = await screen.findByRole('region', { name: 'Pronunciation' })
    expect(within(section).getByText(/An automatic estimate, not a teacher's judgment/)).toBeInTheDocument()
    expect(within(section).getByText('Accuracy').nextSibling).toHaveTextContent('82 / 100')
    expect(within(section).getByText('Pronunciation', { selector: 'dt' }).nextSibling).toHaveTextContent('78 / 100')
    expect(within(section).getByText('41 / 100, mispronounced')).toBeInTheDocument()
    expect(within(section).getByText('0 / 100, omitted')).toBeInTheDocument()
    expect(within(section).getByText('88 / 100, to check')).toBeInTheDocument()
    // Sounds below 80, worst first.
    const sounds = within(section).getAllByText(/ in “/)
    expect(sounds.map((li) => li.textContent)).toEqual([
      'ə in “account”: 35 / 100',
      'aʊ in “account”: 60 / 100',
    ])
    // Nothing is offered once assessed.
    expect(within(section).queryByRole('button')).not.toBeInTheDocument()
  })

  it('says that no speech was heard, without a score table', async () => {
    installFakeSpeech()
    mockApi({
      ...base,
      'GET /productions/7': shadowing({
        pronunciation: scores({
          status: 'silence',
          overall: { accuracy: null, fluency: null, completeness: null, pronunciation: null },
          words: [],
        }),
        assessable: false,
        assessable_reason: 'already_assessed',
      }),
    })
    renderApp('/speaking/shadowing/7')
    const section = await screen.findByRole('region', { name: 'Pronunciation' })
    expect(within(section).getByText(/heard no speech/)).toBeInTheDocument()
    expect(within(section).queryByText('Overall scores')).not.toBeInTheDocument()
  })

  it('asks before anything is sent, then stores nothing on screen but the refreshed scores', async () => {
    installFakeSpeech()
    let current = assessable()
    const calls = mockApi({
      ...base,
      'GET /productions/7': () => Response.json(current),
      'POST /productions/7/pronunciation': () => {
        current = shadowing({ pronunciation: scores(), assessable: false, assessable_reason: 'already_assessed' })
        return Response.json({ production_id: 7, status: 'ok', reason: null, scores: scores() })
      },
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')

    const section = await screen.findByRole('region', { name: 'Pronunciation' })
    expect(within(section).getByText(/sends the recording to Microsoft Azure/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    await user.click(within(section).getByRole('button', { name: 'Assess my pronunciation' }))
    expect(await within(section).findByText('Overall scores')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
  })

  it('keeps the button for another try when the assessment is unavailable', async () => {
    installFakeSpeech()
    mockApi({
      ...base,
      'GET /productions/7': assessable(),
      'POST /productions/7/pronunciation': {
        production_id: 7,
        status: 'unavailable',
        reason: 'quota',
        scores: null,
      },
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing/7')
    const section = await screen.findByRole('region', { name: 'Pronunciation' })
    await user.click(within(section).getByRole('button', { name: 'Assess my pronunciation' }))
    expect(await within(section).findByText(/could not be done/)).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Try again' })).toBeEnabled()
  })

  it.each([
    ['disabled', /Turned off in the settings/],
    ['not_configured', /Azure is not configured/],
    ['unsupported_format', /not in a format Azure reads/],
    ['too_long', /longer than 30 seconds/],
    ['no_target', /no sentence to compare/],
  ] as const)('greys the button out with the reason %s', async (reason, text) => {
    installFakeSpeech()
    mockApi({ ...base, 'GET /productions/7': refused(reason) })
    renderApp('/speaking/shadowing/7')
    const section = await screen.findByRole('region', { name: 'Pronunciation' })
    expect(within(section).getByRole('button', { name: 'Assess my pronunciation' })).toBeDisabled()
    expect(within(section).getByText(text)).toBeInTheDocument()
    const link = within(section).queryByRole('link', { name: 'Open the settings' })
    expect(link !== null).toBe(reason === 'disabled' || reason === 'not_configured')
  })

  it('shows nothing for a backend without the fields', async () => {
    installFakeSpeech()
    mockApi({ ...base, 'GET /productions/7': shadowing() })
    renderApp('/speaking/shadowing/7')
    await screen.findByRole('heading', { name: 'Transcription and comparison' })
    expect(screen.queryByRole('region', { name: 'Pronunciation' })).not.toBeInTheDocument()
  })
})

describe('Shadowing: recording for the assessment', () => {
  const azureStatus = {
    ...base['GET /ai/status'],
    speech_providers: [
      {
        name: 'azure',
        capabilities: ['pronunciation_assessment'],
        configured: true,
        enabled: true,
        available: true,
        cooldown_until: null,
        misconfigured: false,
        last_error: null,
        models: {},
        credential_source: 'env_file',
        credential_kind: 'api_key',
        region: 'westeurope',
      },
    ],
  }
  const setting = (value: string) => ({
    value,
    default: 'off',
    is_default: value === 'off',
    type: 'str',
    minimum: null,
    maximum: null,
    choices: ['off', 'azure'],
    item_choices: null,
  })

  async function sendOne(assessment: string, status: object, converted: Blob | null = new Blob(['RIFF'], { type: 'audio/wav' })) {
    wav.convert.mockReset()
    wav.convert.mockResolvedValue(converted)
    const kit = installFakeRecorder()
    installFakeSpeech()
    const calls = mockApi({
      ...base,
      'GET /ai/status': status,
      'GET /settings': { pronunciation_assessment: setting(assessment) },
      'POST /speech/shadowing': () => Response.json(speechOut(), { status: 201 }),
      'GET /productions/7': shadowing(),
    })
    const user = userEvent.setup()
    renderApp('/speaking/shadowing')
    await user.type(await screen.findByLabelText('Sentence to repeat'), 'We account for regional fixed effects.')
    // The readiness comes from two requests: wait for them before recording.
    await waitFor(() => expect(calls.some((c) => c.path === '/settings')).toBe(true))
    await waitFor(() => expect(calls.some((c) => c.path === '/ai/status')).toBe(true))
    await new Promise((resolve) => setTimeout(resolve, 50))
    await recordTake(user, kit)
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByRole('heading', { name: 'Transcription and comparison' })
    return calls.find((c) => c.method === 'POST' && c.path.startsWith('/speech/shadowing'))
  }

  it('converts the take to WAV when the assessment is on and Azure is configured', async () => {
    const sent = await sendOne('azure', azureStatus)
    expect(wav.convert).toHaveBeenCalledTimes(1)
    expect(sent).toBeDefined()
    expect(((sent as { body: unknown }).body as Blob).type).toBe('audio/wav')
  })

  it('sends the take as recorded when the assessment is off', async () => {
    const sent = await sendOne('off', azureStatus)
    expect(wav.convert).not.toHaveBeenCalled()
    expect(sent).toBeDefined()
    expect(((sent as { body: unknown }).body as Blob).type).not.toBe('audio/wav')
  })

  it('sends the original when the conversion is impossible', async () => {
    const sent = await sendOne('azure', azureStatus, null)
    expect(wav.convert).toHaveBeenCalledTimes(1)
    expect(sent).toBeDefined()
    expect(((sent as { body: unknown }).body as Blob).type).not.toBe('audio/wav')
  })
})
