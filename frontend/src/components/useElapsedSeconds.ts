import { useEffect, useState } from 'react'

/** Whole seconds since `start` (ms), ticking every second while `running`. */
export function useElapsedSeconds(running: boolean, start: number) {
  const [now, setNow] = useState(start)
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running])
  return Math.max(0, Math.floor((now - start) / 1000))
}
