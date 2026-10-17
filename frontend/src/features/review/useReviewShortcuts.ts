import { useEffect, useRef } from 'react'

import type { Rating } from '../../api/reviews'
import { hasCommandModifier, isTyping } from '../../components/keyboard'

/**
 * The actions the current phase allows (D-122). A missing handler means its keys do nothing now:
 * the player passes `choose` and `reveal` while answering, `rate` and `acceptProposed` once the
 * answer is shown, and `replay` whenever there is something to hear.
 */
export interface ReviewShortcutHandlers {
  /** 1 to 4 while answering a choice exercise (0-based index). */
  choose?: (index: number) => void
  /** Space or Enter for an exercise without input. */
  reveal?: () => void
  /** 1 to 4 once the answer is shown. */
  rate?: (rating: Rating) => void
  /** Enter once the answer is shown, when a rating is proposed. */
  acceptProposed?: () => void
  /** R (normal) and Shift+R (slow). */
  replay?: (slow: boolean) => void
}

const DIGIT_CODES: Record<string, Rating> = {
  Digit1: 1,
  Digit2: 2,
  Digit3: 3,
  Digit4: 4,
  Numpad1: 1,
  Numpad2: 2,
  Numpad3: 3,
  Numpad4: 4,
}

/**
 * 1 to 4 from the key's character or from its physical position: on an AZERTY keyboard the
 * digit row gives "&", "é"... without Shift, and its `code` is still `Digit1`...
 */
export function digitOf(event: KeyboardEvent): Rating | null {
  if (['1', '2', '3', '4'].includes(event.key)) return Number(event.key) as Rating
  return DIGIT_CODES[event.code] ?? null
}

/** Enter and Space already activate a focused button or link: the page must not act twice. */
function activatesItself(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLButtonElement ||
    target instanceof HTMLAnchorElement ||
    (target instanceof HTMLElement && target.tagName === 'SUMMARY') ||
    (target instanceof HTMLInputElement && ['radio', 'checkbox', 'button', 'submit'].includes(target.type))
  )
}

/**
 * Review keys on the whole page. Ignored with Ctrl, Alt or Meta, while typing in a field (the
 * shared guard of the triage page, D-088) and for auto-repeated key presses.
 */
export function useReviewShortcuts(handlers: ReviewShortcutHandlers) {
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
        } else if (h.rate !== undefined) {
          event.preventDefault()
          h.rate(digit)
        }
        return
      }
      if (event.key === 'r' || event.key === 'R') {
        if (h.replay !== undefined) {
          event.preventDefault()
          h.replay(event.shiftKey)
        }
        return
      }
      if (event.key === 'Enter' || event.key === ' ') {
        if (event.shiftKey || activatesItself(event.target)) return
        if (event.key === 'Enter' && h.acceptProposed !== undefined) {
          event.preventDefault()
          h.acceptProposed()
        } else if (h.reveal !== undefined) {
          event.preventDefault()
          h.reveal()
        }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])
}
