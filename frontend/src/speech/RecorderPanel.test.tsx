import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { installFakeRecorder, OPUS, recordTake, type RecorderKit } from '../test/fakeRecorder'
import { installFakeSpeech } from '../test/fakeSpeech'
import { renderWithProviders } from '../test/renderApp'
import { useStopRecordingOnLeave } from './activeRecording'
import { Recorder } from './RecorderPanel'
import { SpeakButton } from './SpeakButton'
import type { Clip } from './useRecorder'

afterEach(() => {
  vi.useRealTimers()
})

function setup(props: Partial<React.ComponentProps<typeof Recorder>> = {}, supported?: string[]) {
  const kit = installFakeRecorder(supported)
  const onSend = vi.fn<(clip: Clip) => void>()
  const user = userEvent.setup()
  const view = render(<Recorder use="shadowing" onSend={onSend} {...props} />)
  return { kit, onSend, user, view }
}

const start = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: 'Start recording' }))

const allTracksStopped = (kit: RecorderKit) =>
  kit.streams.length > 0 && kit.streams.every((s) => s.tracks.every((track) => track.stopped))

describe('Recorder: a take', () => {
  it('asks for the microphone, records with the first accepted type and sends the clip', async () => {
    const { kit, onSend, user } = setup()
    await recordTake(user, kit)

    expect(kit.getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(kit.recorder()?.mimeType).toBe(OPUS)
    expect(kit.recorder()?.timeslice).toBe(1000)
    expect(screen.getByRole('button', { name: 'Listen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Record again' })).toBeInTheDocument()
    // The parent decides what sending means: nothing was sent yet.
    expect(onSend).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(onSend).toHaveBeenCalledTimes(1)
    const clip = onSend.mock.calls[0]![0]
    expect(clip.blob.type).toBe(OPUS)
    expect(clip.mimeType).toBe(OPUS)
    expect(clip.url).toBe(kit.createdUrls[0])
  })

  it('falls back to the next type the browser knows', async () => {
    const { kit, user } = setup({}, ['audio/webm'])
    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    expect(kit.recorder()?.mimeType).toBe('audio/webm')
  })

  it('measures the duration itself and says the state in words', async () => {
    const { kit, onSend, user } = setup()

    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    kit.advance(12_400)
    // The visible timer follows the clock (it is not a live region); the status says it once.
    expect(await screen.findByText('Recording… 0:12')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Recording started.')
    await user.click(screen.getByRole('button', { name: 'Stop recording' }))
    act(() => kit.recorder()?.finish())
    await user.click(await screen.findByRole('button', { name: 'Send' }))

    expect(onSend.mock.calls[0]![0].durationS).toBe(12.4)
    expect(screen.getByRole('status')).toHaveTextContent('Recording stopped: 0:12.')
  })

  it('stops by itself at the maximum and never reports more', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    const kit = installFakeRecorder()
    const onSend = vi.fn<(clip: Clip) => void>()
    render(<Recorder use="shadowing" onSend={onSend} />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start recording' }))
    })
    expect(kit.recorder()?.state).toBe('recording')
    kit.advance(29_900)
    await act(() => vi.advanceTimersByTimeAsync(29_900))
    expect(kit.recorder()?.state).toBe('recording')
    // The timer fires a little late: 30.3 s on the clock, the report is capped at 30.
    kit.advance(400)
    await act(() => vi.advanceTimersByTimeAsync(400))
    expect(kit.recorder()?.state).toBe('inactive')

    act(() => kit.recorder()?.finish())
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(onSend.mock.calls[0]![0].durationS).toBe(30)
  })

  it('does not send a take that is too short, and says so', async () => {
    const { kit, onSend, user } = setup()
    await recordTake(user, kit, { ms: 200 })

    expect(screen.getByText(/too short \(at least 0\.5 s\)/)).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send' })
    expect(send).toBeDisabled()
    await user.click(send)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('refuses a clip over 10 MB before it is sent', async () => {
    const { kit, onSend, user } = setup()
    const big = new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: OPUS })
    await recordTake(user, kit, { blob: big })
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('larger than 10 MB')
  })

  it('keeps nothing of the recording in the browser storages', async () => {
    const before = Object.keys(window.localStorage)
    const { kit, user } = setup()
    await recordTake(user, kit)
    expect(Object.keys(window.localStorage)).toEqual(before)
    expect(window.sessionStorage).toHaveLength(0)
  })
})

describe('Recorder: the five reasons it cannot record', () => {
  it.each([
    ['NotAllowedError', 'Access to the microphone was refused.'],
    ['NotFoundError', 'No microphone was found.'],
    ['NotReadableError', 'The microphone is used by another program or tab.'],
    ['SomethingElse', 'The recording failed. Try again.'],
  ])('%s', async (name, sentence) => {
    const { kit, user } = setup()
    kit.refuseNext(name)
    await start(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(sentence)
    // Nothing is recording, and the user can try again.
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeEnabled()
  })

  it('denied says how to allow the microphone for 127.0.0.1', async () => {
    const { kit, user } = setup()
    kit.refuseNext('NotAllowedError')
    await start(user)
    expect(await screen.findByText(/Allow the microphone for 127\.0\.0\.1/)).toBeInTheDocument()
  })

  it('unsupported: no MediaRecorder, the button is off and the reason is shown', () => {
    render(<Recorder use="shadowing" onSend={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('This browser cannot record sound')
  })
})

describe('Recorder: the microphone is released', () => {
  it('when the recording stops', async () => {
    const { kit, user } = setup()
    await recordTake(user, kit)
    expect(allTracksStopped(kit)).toBe(true)
  })

  it('when the page goes away while recording', async () => {
    const { kit, user, view } = setup()
    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    expect(allTracksStopped(kit)).toBe(false)
    view.unmount()
    expect(allTracksStopped(kit)).toBe(true)
  })

  it('when the page goes away before the browser has answered the permission request', async () => {
    const { kit, user, view } = setup()
    const pending = kit.holdNext()
    await start(user)
    view.unmount()
    await act(async () => pending.allow())
    expect(allTracksStopped(kit)).toBe(true)
  })

  it('when "Cancel" is pressed while the permission is pending', async () => {
    const { kit, user } = setup()
    const pending = kit.holdNext()
    await start(user)
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    await act(async () => pending.allow())
    expect(allTracksStopped(kit)).toBe(true)
    expect(screen.getByRole('button', { name: 'Start recording' })).toBeInTheDocument()
  })

  it('when the route changes', async () => {
    const kit = installFakeRecorder()
    const user = userEvent.setup()
    function Shell() {
      useStopRecordingOnLeave()
      return (
        <>
          <Link to="/elsewhere">Leave</Link>
          <Routes>
            <Route path="/" element={<Recorder use="shadowing" onSend={vi.fn()} />} />
            <Route path="/elsewhere" element={<p>Elsewhere</p>} />
          </Routes>
        </>
      )
    }
    render(
      <MemoryRouter>
        <Shell />
      </MemoryRouter>,
    )
    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    await user.click(screen.getByRole('link', { name: 'Leave' }))
    expect(await screen.findByText('Elsewhere')).toBeInTheDocument()
    expect(allTracksStopped(kit)).toBe(true)
  })

  it('when the recorder fails to start', async () => {
    const { kit, user } = setup()
    // A recorder that cannot start: the microphone, already open, must be given back.
    const original = kit.getUserMedia.getMockImplementation()
    expect(original).toBeDefined()
    const spy = vi.spyOn(window.MediaRecorder.prototype, 'start').mockImplementation(() => {
      throw new DOMException('no', 'NotSupportedError')
    })
    await start(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('The recording failed')
    expect(allTracksStopped(kit)).toBe(true)
    spy.mockRestore()
  })
})

describe('Recorder: one at a time, and without the synthetic voice', () => {
  it('cuts the speech synthesis before it records', async () => {
    const speech = installFakeSpeech()
    const { user } = setup()
    const before = speech.cancelCount
    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    expect(speech.cancelCount).toBeGreaterThan(before)
  })

  it('turns "Listen" off while it records', async () => {
    installFakeSpeech()
    const kit = installFakeRecorder()
    const user = userEvent.setup()
    renderWithProviders(
      <>
        <SpeakButton text="We account for it." />
        <Recorder use="shadowing" onSend={vi.fn()} />
      </>,
    )
    const listen = await screen.findByRole('button', { name: 'Listen to “We account for it.”' })
    await vi.waitFor(() => expect(listen).toBeEnabled())
    await start(user)
    await screen.findByRole('button', { name: 'Stop recording' })
    expect(listen).toBeDisabled()
    expect(screen.getByText('Listening is off while you record.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Stop recording' }))
    act(() => kit.recorder()?.finish())
    await vi.waitFor(() => expect(listen).toBeEnabled())
  })

  it('does not open a second microphone while another recorder holds it', async () => {
    const kit = installFakeRecorder()
    const user = userEvent.setup()
    render(
      <>
        <Recorder use="shadowing" onSend={vi.fn()} />
        <Recorder use="shadowing" onSend={vi.fn()} />
      </>,
    )
    const [first, second] = screen.getAllByRole('button', { name: 'Start recording' })
    await user.click(first!)
    await screen.findByRole('button', { name: 'Stop recording' })
    await user.click(second!)
    expect(kit.getUserMedia).toHaveBeenCalledTimes(1)
  })
})

describe('Recorder: the local clip', () => {
  it('is listened to through a blob: URL that is revoked when replaced and on unmount', async () => {
    const { kit, user, view } = setup()
    await recordTake(user, kit)
    const first = kit.createdUrls[0]!
    expect(document.querySelector('audio')).toHaveAttribute('src', first)

    await user.click(screen.getByRole('button', { name: 'Listen' }))
    expect(kit.play).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Record again' }))
    expect(kit.revokedUrls).toContain(first)

    await recordTake(user, kit)
    const second = kit.createdUrls[1]!
    expect(second).not.toBe(first)
    view.unmount()
    expect(kit.revokedUrls).toContain(second)
  })
})

