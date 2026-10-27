import { useEffect, useSyncExternalStore } from 'react'
import { useLocation } from 'react-router'

/*
 * One recording at a time (D-193). A recorder claims the microphone from the moment it asks for it
 * until its tracks are released. `stopActiveRecording()` lets the layout cut it on a route change,
 * and speech synthesis refuses to speak meanwhile (it would be recorded).
 */

let owner: symbol | null = null
let cancelOwner: (() => void) | null = null
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

/** True when no other recorder holds the microphone; the caller then owns it until `release`. */
export function claimRecording(token: symbol, cancel: () => void): boolean {
  if (owner !== null) return false
  owner = token
  cancelOwner = cancel
  emit()
  return true
}

export function releaseRecording(token: symbol) {
  if (owner !== token) return
  owner = null
  cancelOwner = null
  emit()
}

export function isRecording(): boolean {
  return owner !== null
}

/** Cancels the recording in progress, if any (the route changed). */
export function stopActiveRecording() {
  cancelOwner?.()
}

export function useIsRecording(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange)
      return () => listeners.delete(onChange)
    },
    isRecording,
    () => false,
  )
}

/** Cuts a recording when the route changes (mounted once, in the layout). */
export function useStopRecordingOnLeave() {
  const { pathname } = useLocation()
  useEffect(() => stopActiveRecording, [pathname])
}
