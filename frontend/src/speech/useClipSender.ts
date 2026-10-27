import { useCallback, useState } from 'react'

import { MAX_UPLOAD_BYTES } from './recorder'
import type { Clip } from './useRecorder'

/**
 * Sending a clip: one that is over the upload limit is refused here (and said, `tooLarge`), any
 * other goes to `onSend`. The panel's button and a keyboard shortcut of the parent share it.
 */
export function useClipSender(onSend: (clip: Clip) => void) {
  const [tooLarge, setTooLarge] = useState(false)
  const send = useCallback(
    (clip: Clip) => {
      if (clip.blob.size > MAX_UPLOAD_BYTES) {
        setTooLarge(true)
        return
      }
      setTooLarge(false)
      onSend(clip)
    },
    [onSend],
  )
  const clear = useCallback(() => setTooLarge(false), [])
  return { tooLarge, send, clear }
}
