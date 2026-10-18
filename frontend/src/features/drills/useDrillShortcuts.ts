import { useEffect, useRef } from 'react'

import { hasCommandModifier, isTyping } from '../../components/keyboard'
import { activatesItself, digitOf } from '../review/useReviewShortcuts'

/**
 * The actions the current phase allows (D-122 applied to drills). A missing handler means its key
 * does nothing now: `choose` while answering a choice item, `next` once the result is shown.
 */
export interface DrillShortcutHandlers {
  /** 1 to 4 while answering a choice item (0-based index). */
  choose?: (index: number) => void
  /** Enter once the result is shown. */
  next?: () => void
}

/**
 * Drill keys on the whole page. Ignored with Ctrl, Alt or Meta, while typing in a field (the
 * shared guard of the triage page, D-088), for auto-repeated key presses, and for Enter on a
 * button or link, which the browser activates by itself.
 */
export function useDrillShortcuts(handlers: DrillShortcutHandlers) {
  const current = useRef(handlers)
  useEffect(() => {
    current.current = handlers
  })

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || hasCommandModifier(event) || isTyping(event.target)) return
      const h = current.current
      const digit = digitOf(event)
      if (digit !== null) {
        if (h.choose !== undefined) {
          event.preventDefault()
          h.choose(digit - 1)
        }
        return
      }
      if (event.key === 'Enter' && h.next !== undefined) {
        if (event.shiftKey || activatesItself(event.target)) return
        event.preventDefault()
        h.next()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])
}
